# Decision Log

A record of every significant technical choice made during the build, the alternatives considered, and the reason for the final decision.

---

## 1. Transport: stdio over SSE or HTTP

**Chosen:** stdio (`StdioServerParameters`)

**Alternatives considered:**
- SSE (Server-Sent Events) transport
- Streamable HTTP transport

**Reason:**
stdio requires no port management, no network configuration, and no firewall rules. `MCPServerAdapter` manages the subprocess lifecycle automatically. For a single-machine, single-crew deployment this is strictly simpler — there is no benefit to SSE or HTTP when the client and server run on the same machine in the same session. SSE/HTTP would be the right choice if the server needed to serve multiple concurrent clients or run as a persistent background service, neither of which this project requires.

**Trade-off accepted:** stdio is not observable from an external tool while the crew is running. MCP Inspector requires running the server as a standalone process, which is a one-line command and is documented in the README.

---

## 2. Search strategy: keyword scan over vector embeddings

**Chosen:** Case-insensitive substring match with `re.findall` and match-count ranking.

**Alternatives considered:**
- `rapidfuzz` for fuzzy matching
- Sentence-transformer embeddings + cosine similarity (semantic search)
- `whoosh` or `tantivy` full-text index

**Reason:**
The corpus is 11 short documents totalling under 20 KB. Every document fits in memory; a linear scan completes in under 5 ms. Semantic search adds a model-loading dependency (hundreds of MB) and warm-up latency for a corpus where keyword matching already achieves high precision — the domain terms (SKUs, policy names, order IDs) are exact strings, not paraphrases. Fuzzy matching was considered for handling LLM-generated query variations but the grounding rule already instructs agents to use exact terms from tool results, which eliminates the need.

**Trade-off accepted:** A query that uses a synonym ("exchange" instead of "return") will miss documents. Mitigated by instructing the Researcher agent to run multiple searches with different phrasings.

---

## 3. Three agents instead of two

**Chosen:** Researcher → Analyst → Writer (three agents)

**Alternatives considered:**
- Two agents: Researcher/Analyst combined → Writer
- Single agent with all three tools

**Reason:**
Separating Researcher from Analyst enforces a clean data handoff: the Researcher collects raw excerpts without interpreting them, and the Analyst cross-references them against the CSV records. This separation makes the grounding chain auditable — you can read the trace and see exactly what evidence was retrieved before any analysis happened. A single agent with all tools tends to interleave search, analysis, and writing in ways that are hard to trace and easy to hallucinate into.

The three-agent split also enables targeted tool access: the Writer has no access to `search_documents` or `read_record`, so it is structurally impossible for it to introduce unverified claims. This is stronger than a prompt instruction.

**Trade-off accepted:** Three agents mean three LLM calls minimum, which increases latency. Acceptable for a question-answering assistant where accuracy matters more than speed.

---

## 4. Grounding rule in both backstory and task description

**Chosen:** `_GROUNDING_RULE` constant injected into every agent's `backstory` and every `task.description`.

**Alternatives considered:**
- System prompt only
- Task description only
- Post-processing filter on the Writer's output

**Reason:**
CrewAI can compress or truncate context in long runs. Placing the grounding rule in both the backstory (persistent agent identity) and the task description (active instruction for this specific task) makes it more likely to survive context compression. A post-processing filter was rejected because it would catch hallucinations after the fact rather than preventing them, and it adds complexity without addressing the root cause.

**Trade-off accepted:** Repetition adds tokens to every agent prompt. At the scale of this project (local model, small corpus) this has no meaningful cost.

---

## 5. Pydantic v2 validation on all tool inputs

**Chosen:** Pydantic `BaseModel` with `field_validator` on all three tools.

**Alternatives considered:**
- Manual `if/elif` input checks
- `typing.TypedDict` with manual validation
- No validation (rely on FastMCP schema)

**Reason:**
FastMCP generates a JSON schema from the function signature but does not enforce constraints like `min_length`, `max_length`, or pattern matching at the application layer. Pydantic v2 validators run before any file I/O and return structured error messages. The strip-then-check pattern (strip whitespace, then enforce non-empty) is cleaner than trying to catch this in the tool body. Manual `if/elif` chains were rejected because they are harder to test and easier to get wrong.

**Trade-off accepted:** Pydantic is a dependency. It is already pulled in by CrewAI so this adds no new package.

---

## 6. Hardcoded file paths in the server (no caller-supplied paths)

**Chosen:** All four path constants (`_DOCUMENTS_DIR`, `_RECORDS_CSV`, `_REPORTS_DIR`, `_SERVER_DIR`) are set at module load time from `__file__`. No caller can influence them.

**Alternatives considered:**
- Accept a `data_dir` argument on `search_documents`
- Read paths from environment variables at runtime

**Reason:**
Tool inputs arrive from an LLM, not a trusted user. Allowing any caller-supplied path — even validated — creates a path traversal surface. The assignment explicitly states "treat every tool input as untrusted." Hardcoding the paths eliminates the attack surface at the architecture level. Environment variables were considered for the data directory but rejected for the same reason: a compromised environment variable could redirect reads to sensitive files.

**Trade-off accepted:** The server is not configurable without editing the source. Acceptable for a single-deployment assistant; would need to change for a multi-tenant service.

---

## 7. RunTracer as a separate module

**Chosen:** `crew/tracer.py` with a `RunTracer` class; `_step_callback` removed from `crew.py`.

**Alternatives considered:**
- Inline `logging.basicConfig` and a free function callback (the original approach)
- No structured tracing; rely on CrewAI's verbose console output

**Reason:**
The assignment requires saved traces with proof of tool calls. CrewAI's verbose output goes to stderr and is not structured — parsing it to verify tool calls is fragile. A dedicated `RunTracer` emits one JSON object per event, making the trace machine-readable. This also allows the e2e tests to parse the trace file and assert that `TOOL_CALL` events were recorded, which is a stronger grounding check than string-matching the final answer.

Separating the tracer into its own module means it can be tested in isolation (the smoke test in the previous session) and reused without importing the full crew machinery.

**Trade-off accepted:** Two log outputs (stderr for humans, file for machines) require two handlers on the logger. This is a minor complexity increase.

---

## 8. `max_iter` values per agent

**Chosen:** Researcher=5, Analyst=8, Writer=3

**Alternatives considered:**
- A single `max_iter=10` across all agents
- No limit (CrewAI default)

**Reason:**
Each agent has a distinct workload. The Researcher may need up to five search angles. The Analyst may need to look up multiple order IDs plus follow-up document searches — eight covers six record lookups and two clarification searches with margin. The Writer's job is one pass: draft and save. Three is generous. A uniform limit would either under-constrain the Analyst or over-constrain the Writer. No limit is explicitly rejected by the assignment's safety requirements.

---

## 9. Corpus domain: inventory and operations

**Chosen:** A synthetic mid-sized operations team: order records, returns policies, product notes, support tickets, supplier contacts.

**Alternatives considered:**
- HR documents and employee records
- Technical documentation (API specs, runbooks)
- Customer-facing FAQ content

**Reason:**
Inventory and operations is the domain specified in the assignment scenario. It produces realistic cross-source queries: a support ticket references an order (CSV) which references a product (product notes) which references a policy. This chain exercises all three tools in a single question and produces grounding chains that are easy to audit by hand. HR and technical documentation would also work but would not produce the order-record cross-reference that makes `read_record` a meaningful tool.

---

## Rejected Approaches

| Approach | Why rejected |
|----------|-------------|
| Jupyter notebook submission | Explicitly disallowed by the assignment |
| Paid API (OpenAI, Anthropic) | Assignment requires free/local model |
| `langchain` instead of `crewai` | Assignment specifies CrewAI |
| SQLite instead of CSV | Over-engineering for 20 rows; CSV is readable by hand as required |
| Async FastMCP | Unnecessary complexity for stdio; sync functions are simpler to test |
| Caching CSV reads | Adds state to a stateless tool; fresh reads are safer and the file is 2 KB |
