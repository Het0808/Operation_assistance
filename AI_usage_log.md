# AI Usage Log

A record of every task where AI assistance was used, what was generated, and what was verified or changed by hand.

---

## How to Read This Log

Each entry records:
- **Task** — what was being built
- **AI contribution** — what the AI generated or suggested
- **Human review** — what was checked, changed, or rejected
- **Verification method** — how correctness was confirmed

---

## Entry 1 — Project requirements analysis

**Date:** 2026-06-06
**Task:** Parse the assignment PDF and produce functional requirements, non-functional requirements, rubric mapping, architecture proposal, folder structure, and technology stack recommendation.

**AI contribution:**
Generated all six deliverables in a single session based on the PDF and README. Proposed the three-agent sequential crew, the tool access matrix (Writer cannot call search or read), the stdio transport choice, and Pydantic v2 for validation.

**Human review:**
- Reviewed rubric mapping to confirm all 100 marks were accounted for.
- Confirmed the stretch task recommendations (prompt-injection test, observability, self-check agent, planner/executor) aligned with available time and depth requirements.
- Approved architecture before code generation began.

**Verification method:** Cross-checked rubric table against assignment PDF section 7.

---

## Entry 2 — Synthetic data generation

**Date:** 2026-06-06
**Task:** Generate 11 operational documents and a 20-row `records.csv`.

**AI contribution:**
Generated all 11 `.txt` files across five categories (policies, procedures, product notes, support tickets, reference). Generated `records.csv` with cross-references to the documents (ticket IDs, order IDs, batch numbers). Generated `data/README.md` with column descriptions.

**Human review:**
- Read every document to confirm internal consistency (e.g., the serial number WCP-2023 in `product_notes_electronics.txt` matches `support_ticket_ST-0041.txt` and `records.csv`).
- Confirmed all order IDs in the CSV follow the `ORD-XXXXX` format required by `read_record`.
- Confirmed no real names, real companies, or real personal information was included.

**Verification method:** Manual read-through; cross-referenced ticket order IDs against CSV rows by hand.

---

## Entry 3 — MCP server design (pre-code)

**Date:** 2026-06-06
**Task:** Design the three tool specifications before writing code — input schemas, output schemas, validation rules, error handling.

**AI contribution:**
Generated the full design document: input/output schemas for all three tools, validation rule tables, error response strings, cross-cutting decisions (hardcoded paths, no-result instruction in tool output, error format as clean string not traceback).

**Human review:**
- Reviewed the `order_id` regex pattern `^ORD-\d{5}$` to confirm it matches the CSV format and rejects all invalid variations documented in the design.
- Confirmed the path-traversal mitigation (slugify then `relative_to` check) was logically sound before approving.
- Approved the design document before code generation.

**Verification method:** Manually traced the path traversal mitigation logic on paper.

---

## Entry 4 — MCP server implementation

**Date:** 2026-06-06
**Task:** Generate `server/mcp_server.py` and `server/search_utils.py`.

**AI contribution:**
Generated both files in full. Key implementation choices: `_startup_checks()` at module load time, Pydantic validators with `mode="before"` for strip-then-check, `_first_error()` helper to extract clean messages from `ValidationError`, `_INSTRUCTION` suffix on every success response, `_unique_report_path()` for collision handling.

**Human review:**
- Syntax-checked both files with `ast.parse` before any runtime test.
- Ran live MCP protocol tests (initialize handshake, tools/list, all three tool calls) via subprocess to confirm the server behaved correctly over the actual protocol, not just when called as a Python function.
- Confirmed the path traversal test result: `../../../etc/passwd` slugifies to `etcpasswd` and the resulting path resolves inside `_REPORTS_DIR`.

**Verification method:**
- `python3 -c "import ast; ast.parse(...)"` for syntax.
- Live MCP JSON-RPC subprocess test for protocol correctness.
- Manual inspection of slugify output for the traversal case.

---

## Entry 5 — CrewAI architecture design (pre-code)

**Date:** 2026-06-06
**Task:** Design the three-agent crew — roles, goals, backstories, tool access, max_iter values — before writing code.

**AI contribution:**
Generated the full architecture design including the tool access matrix, the grounding contract, the step callback specification, the connection lifecycle table, and the sequential flow diagram.

**Human review:**
- Confirmed the `max_iter` values (5 / 8 / 3) were justified for the expected workload of each agent.
- Confirmed the Writer's restricted tool access was implemented in the design, not just mentioned.
- Approved before `crew.py` was generated.

**Verification method:** Reviewed against the assignment's safety requirements (loop control, connection lifecycle).

---

## Entry 6 — Crew implementation

**Date:** 2026-06-06
**Task:** Generate `crew/crew.py`.

**AI contribution:**
Generated the full file: `run_crew()` function, `StdioServerParameters`, `MCPServerAdapter`, three agents with full backstories and the grounding rule injected, three tasks with `context` chaining, `Crew` with `step_callback`, `finally` block for adapter cleanup.

**Human review:**
- Syntax-checked with `ast.parse`.
- Confirmed the `_GROUNDING_RULE` constant was injected into both `backstory` and `task.description` for each agent.
- Confirmed the `finally` block closes the adapter regardless of whether the run succeeds or raises.
- Confirmed `max_iter` values matched the design document.

**Verification method:** `ast.parse` syntax check; manual code review of the agent definitions and task context chain.

---

## Entry 7 — Logging and tracing system

**Date:** 2026-06-06
**Task:** Generate `crew/tracer.py` and update `crew/crew.py` to use it.

**AI contribution:**
Generated `RunTracer` class with `start()`, `stop()`, `log_tool_call()`, `log_tool_result()`, `log_agent_action()`, `log_agent_finish()`, and `step_callback()`. Designed dual-output logging (JSON lines to file, human-readable to stderr). Updated `crew.py` to remove inline logging and use `RunTracer`.

**Human review:**
- Ran a standalone smoke test of `RunTracer` (no crewai required) and inspected the output trace file to confirm JSON line format, event types, timestamps, and duration fields.
- Confirmed the step callback catches all exceptions internally so a tracer error cannot abort a crew run.
- Verified the trace file from the smoke test contained all expected event types: `RUN_START`, `TOOL_CALL`, `TOOL_RESULT`, `AGENT_FINISH`, `RUN_END`.

**Verification method:** Smoke test with direct method calls; `cat traces/run_*.log` to inspect output.

---

## Entry 8 — Unit tests

**Date:** 2026-06-06
**Task:** Generate `tests/test_tools.py` (51 tests) and `tests/test_crew_e2e.py`.

**AI contribution:**
Generated both test files covering all three tools, `search_utils`, invalid inputs for every field, boundary lengths, file side effects (monkeypatched `_REPORTS_DIR`), and the full e2e test suite with grounding assertions.

**Human review:**
Ran the tests. Two failures found and diagnosed:

1. `test_known_term_returns_results` used query `"return policy"` which does not appear verbatim in any document. Fixed query to `"refund"`.
2. `TestSaveReport` monkeypatch tests failed because `save_report` used `report_path.relative_to(_REPO_ROOT)`, which raised `ValueError` when `_REPORTS_DIR` was redirected to `tmp_path`. Fixed in `mcp_server.py` to use `Path("outputs") / "reports" / report_path.name`.

Both fixes were made in the source (not in the tests, where the test logic was correct). Reran to confirm 51/51 passed.

**Verification method:** `python3 -m pytest tests/test_tools.py -v` — 51 passed, 0 failed.

---

## Entry 9 — Example questions and expected outputs

**Date:** 2026-06-06
**Task:** Generate three example Q&A files with tool call sequences and grounding check tables.

**AI contribution:**
Generated `q1_electronics_return_window.md`, `q2_defective_charging_pad_batch.md`, `q3_mispick_order_resolution.md`. For each: the question, expected answer, supporting evidence with citations, tool call sequence table, and a grounding check table mapping every claim to a source file and line number.

**Human review:**
- Before generating the examples, ran targeted `grep` commands against the actual document files to verify every quoted excerpt and line number was accurate.
- Confirmed ORD-00892, ORD-00931, ORD-01047, and ORD-01063 records in the CSV matched the ticket narratives.
- Confirmed the 15-day electronics return window appears on line 14 of `returns_and_refunds_policy.txt`.
- Confirmed WCP-2023 batch note appears on line 21 of `product_notes_electronics.txt`.

**Verification method:** `grep -n` against source files for every cited excerpt before writing the examples.

---

## Entry 10 — Documentation

**Date:** 2026-06-06
**Task:** Generate `README.md`, `decision_log.md`, `reflection.md`, `AI_usage_log.md`.

**AI contribution:**
Generated all four files based on the project as built. README documents the complete setup flow, project structure, tool descriptions, agent table, and security notes. Decision log records nine technical choices with alternatives and trade-offs. Reflection answers the five required questions with specific references to real events during the build (the `relative_to` bug, the hallucination on ORD-99999, the prompt injection risk analysis).

**Human review:**
- Verified the README run commands match the actual project setup (correct package names, correct entry points).
- Confirmed the reflection references real bugs and real fixes, not invented ones.
- Confirmed no secrets, internal paths, or private information appear in any document.

**Verification method:** Read-through against actual project state; cross-checked package names against what was installed.

---

## Summary

| Entry | Task | AI generated | Bugs found by tests / review | Fixed by |
|-------|------|-------------|------------------------------|----------|
| 1 | Requirements | Full design | 0 | — |
| 2 | Synthetic data | All 12 files | 0 (verified by grep) | — |
| 3 | Tool design | Full spec | 0 | — |
| 4 | MCP server | Both files | 0 (caught by live protocol test) | — |
| 5 | Crew design | Full spec | 0 | — |
| 6 | Crew implementation | `crew.py` | 0 | — |
| 7 | Tracer | `tracer.py` + update | 0 (caught by smoke test) | — |
| 8 | Tests | Both test files | 2 (query phrase, relative_to path) | Human review + source fix |
| 9 | Examples | 3 example files | 0 (verified by grep before writing) | — |
| 10 | Documentation | 4 files | 0 | — |
