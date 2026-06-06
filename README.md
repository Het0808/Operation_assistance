# Operations Assistant: A Multi-Agent Crew on an MCP Server

> **Futurense AI Clinic | Week 14 Mini-Project**

Build a small MCP server that exposes tools over local data, then build a CrewAI crew that connects to it and finishes one real task end to end — with traces, tests, and answers that cite their evidence.

| | |
|---|---|
| **BUILD** | One MCP server with a few tools + a CrewAI crew that uses them to answer a question and write a sourced report |
| **SKILLS** | MCP servers (tools, resources, transports), CrewAI (agents, tasks, crews), and the practical know-hows that make agents safe and reliable |
| **OUTPUT** | A public repo that runs from a fresh clone, an inspectable MCP server, a working crew, saved run traces, and a demo recording |
| **RULE** | Core carries 80, stretch 20. A notebook is not a submission. Keep it laptop-runnable with a free or local model |

---

## 1 · The Scenario

A mid-sized operations team keeps its knowledge in two places: a folder of short documents (policies, product notes, past support tickets) and one small spreadsheet of orders or inventory. Today, staff answer routine questions by hand — opening files, searching, cross-checking the spreadsheet, and writing a short summary.

You will build a small assistant that does this the way a real team would. A crew of agents shares one set of tools, and those tools live behind an MCP server that you build. Given a question, the crew searches the documents, reads the relevant records, and writes a short report that says where each fact came from.

---

## 2 · What You Are Building

| Part | What it does |
|---|---|
| **MCP server** | Exposes 2–3 tools over local data: `search_documents(query)`, `read_record(id)`, and (for Core) `save_report(title, content)`. Optionally a resource that lists the documents. |
| **Tools** | Plain Python functions with validated inputs and clear error messages, built with the official `mcp` SDK (FastMCP). |
| **CrewAI crew** | Two or three agents with clear roles (e.g. Researcher and Writer) that connect to the server through `MCPServerAdapter` and use its tools. |
| **One task** | Answer a business question by retrieving evidence and producing a short, sourced report. |
| **Evidence** | Saved traces of each agent step and tool call, example questions with their outputs, and tests. |

> **The point of the week is the wiring:** one server, one crew, tools shared between them, and an answer you can trust because every claim points to a document or a record.

---

## 3 · Inputs and Scope Rules

- **Data.** A tiny corpus: ~8–15 short text documents (public, synthetic, or written by you) plus one small CSV of 10–50 rows. Keep it small enough to read by hand.
- **Model.** Use a local model through Ollama, or any model you already have access to. Do not require a paid API. Do not hardcode keys — use an `.env.example` file.
- **Safety.** Commit only small samples. No secrets, no private data, and no personal information in documents, screenshots, or the demo.

---

## 4 · The Work

### MVP (Runnable Minimum — ~70% of Core)

| Requirement | Tag |
|---|---|
| **Repo and setup.** README, clear folder structure, env file, and run commands. Must run from a fresh clone. | `MVP` |
| **Sample data.** Commit the small document folder and the CSV, with a short note on what they contain. | `MVP` |
| **MCP server with two tools.** `search_documents` and `read_record`, built with the official `mcp` SDK. Server runs and opens in MCP Inspector. | `MVP` |
| **A crew that uses the server.** Two CrewAI agents connect through `MCPServerAdapter` over stdio and complete the task, producing an answer. | `MVP` |
| **Grounding.** Every answer names the document or record each fact came from. If a tool returns nothing, the agent says so instead of inventing an answer. | `MVP` |
| **A basic check.** Three example questions with saved outputs, and proof from the run log that tools were actually called, not guessed. | `MVP` |

### Core Hardening (toward 80 marks)

| Requirement | Tag |
|---|---|
| **A third tool and roles.** Add `save_report` (writes a markdown report to an output folder) and a third agent, or a resource that lists documents. Give each agent a clear role, goal, and task. | `CORE` |
| **Input validation and errors.** Validate tool inputs with strict schemas and return clear messages on bad input. | `CORE` |
| **Loop control and tracing.** Set `max_iter` so an agent cannot loop forever. Turn on verbose mode and save a trace of each agent step and tool call to a file. | `CORE` |
| **Tests.** Unit tests that call the MCP tools directly, and one end-to-end test that runs the crew on a fixed question. | `CORE` |
| **Decision log.** A short log of what you tried, what you chose, and what you rejected. | `CORE` |

### Stretch (any 4, scored on depth — up to 5 marks each, capped at 20)

| Task | Description |
|---|---|
| **Two MCP servers** | Add a second server (e.g. a public filesystem or fetch server) and give different tools to different agents. |
| **Human approval gate** | Require human approval before `save_report` writes anything, or before any action that changes data. |
| **A self-check step** | Add an agent or step that checks the report's claims against the retrieved evidence and flags anything unsupported. |
| **Planner and executor** | Use CrewAI's hierarchical process: a manager agent plans, worker agents execute. |
| **Observability** | Save a structured trace of every tool call with timings and token counts, and produce a small run report. |
| **Remote transport** | Run the server as a separate process over SSE or streamable HTTP instead of stdio. |
| **Prompt-injection test** | Hide a malicious instruction inside one document and show your guardrails refuse it. |

> Stretch is scored on depth, not count: two strong tasks beat four shallow ones.

---

## 5 · Practical Know-Hows to Apply

- **Treat every tool input as untrusted.** Inputs reach your tools through an LLM, not directly from a person. Validate them with strict schemas, and never pass raw input into shell commands or file paths without checking.
- **A stdio MCP server runs code on your machine.** Only connect to servers you trust. If you use a public server, read what it does first.
- **Watch for the rug pull.** A server can change its tool definitions after you approve them. Pin and review the tools you depend on.
- **Stop runaway agents.** Set `max_iter` and a step limit. An agent without a ceiling can loop and burn time or tokens.
- **Close the connection.** With `MCPServerAdapter`, use the context manager (`with ... as tools:`) or call `stop()` in a `finally` block.
- **Stay free and reproducible.** Use a local model, keep keys in environment variables, and ship a small sample so the project runs from a clone.

---

## 6 · How to Run It

> Everything runs locally and free.

```bash
# Requirements
python 3.11 or 3.12 (managed with uv)

# Install MCP server SDK
pip install mcp        # includes FastMCP

# Install CrewAI and MCP adapter
pip install crewai 'crewai-tools[mcp]'

# Model: local via Ollama, or any model you have — no paid API required
```

**Test the server** with the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).

**Connect the crew** over stdio using `StdioServerParameters`.

---

## 7 · Scoring

| Area | Marks | What earns the marks |
|---|---|---|
| MVP tasks | 55 | Repo, sample data, working MCP server with two tools, crew that uses them, grounded answers, runs from a clone |
| Core hardening | 15 | Third tool and roles, input validation, loop control and tracing, tests, and a demo |
| AI-assisted engineering | 10 | Decision log, AI red-team review of your own server, and verified fixes |
| Stretch | 20 | Advanced features that work, marked on depth (any four, five marks each) |
| **Total** | **100** | |

> Core work caps at 80. Stretch is the only way past 80. Marks reward a system that runs and answers you can trust, not a clever demo that cannot be explained.

---

## 8 · Minimum Acceptance Criteria

- [ ] The repo runs from a fresh clone using the documented commands
- [ ] The MCP server runs and can be opened in the MCP Inspector
- [ ] The crew connects to the server and completes the task on sample data
- [ ] Every answer cites the document or record behind each fact, and refuses when no evidence is found
- [ ] Your 5-minute clip is submitted and covers the points in section 10
- [ ] No secrets, keys, or private data are committed

---

## 9 · Submit and Reflect

**Submit:** GitHub repo · README with setup commands · server and crew code · sample data · three example questions with saved outputs · run traces · tests · 5-minute clip · decision log · AI usage log · short reflection

### reflection.md — answer these questions:

1. Why these tools and these agent roles, over the alternatives you considered?
2. What broke first when you connected the crew to the server, and what did you change?
3. Show one answer the crew got wrong or ungrounded. How did your guardrail catch it, or why did it slip through?
4. Where is the biggest security risk in your server, and how did you reduce it?
5. What would you change before letting this touch real company data?

> **How this is checked:** Your 5-minute clip and a short live walkthrough within 48 hours of the deadline confirm the work is yours. Any function in your server or crew may be picked at random for you to explain. AI-assisted code is fine and expected. Code you cannot explain does not count.

---

## 10 · Your 5-Minute Clip

Record ~5 minutes, keep your face or voice on, share your screen for the demo. One continuous take is fine — no editing needed.

| Time | What to cover |
|---|---|
| ~1 min | **The pitch.** What you built and why it matters, the way you would open in an interview. |
| ~1 min | **Show it run.** Ask one question, show the crew calling your MCP tools, show the answer with its sources. |
| ~1.5 min | **One decision and one failure.** A real choice you made and why, and one thing that broke and how you fixed it. |
| ~1 min | **What you learned.** Explain MCP and CrewAI in your own words, the one security risk you took seriously, and the two or three sources you used most. |
| ~30 sec | **What is next.** What you would change before this touched real company data. |

> If you can do this clearly in five minutes, you can do it in an interview. That is the real goal.

---

## 11 · References

### Documentation

| Resource | Link |
|---|---|
| What MCP is | https://modelcontextprotocol.io/docs/getting-started/intro |
| MCP Python SDK (FastMCP) | https://github.com/modelcontextprotocol/python-sdk |
| Build an MCP server, step by step | https://gofastmcp.com/tutorials/create-mcp-server |
| MCP Inspector | https://github.com/modelcontextprotocol/inspector |
| CrewAI docs | https://docs.crewai.com |
| CrewAI + MCP | https://docs.crewai.com/en/mcp/overview |
| CrewAI tools (MCP adapter) | https://github.com/crewAIInc/crewAI-tools |
| Anthropic MCP launch post | https://www.anthropic.com/news/model-context-protocol |

### Videos to Follow and Replicate

| Video | Link |
|---|---|
| Build an MCP server with FastMCP | https://www.youtube.com/watch?v=_mUuhOwv9PY |
| Build a CrewAI multi-agent crew | https://www.youtube.com/watch?v=K2UAE1OlC8s |
| A worked CrewAI + MCP server example | https://www.youtube.com/watch?v=f05kjsjqdsE |

> For the integration step, the official walkthrough on the CrewAI MCP page is the most reliable reference — it is maintained with the library.

---

## Suggested Folder Structure

```
operations-assistant/
├── README.md
├── .env.example
├── data/
│   ├── documents/          # 8–15 short .txt files
│   └── records.csv         # 10–50 row spreadsheet
├── server/
│   └── mcp_server.py       # FastMCP server with tools
├── crew/
│   └── crew.py             # CrewAI agents and tasks
├── outputs/
│   └── reports/            # saved_report outputs
├── traces/                 # agent step + tool call logs
├── tests/
│   ├── test_tools.py       # unit tests for MCP tools
│   └── test_crew_e2e.py    # end-to-end crew test
├── examples/               # 3 example Q&A outputs
├── decision_log.md
├── reflection.md
└── demo/                   # 5-minute clip or link
```
