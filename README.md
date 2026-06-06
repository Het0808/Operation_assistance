# Operations Assistant: A Multi-Agent Crew on an MCP Server

> Futurense AI Clinic — Week 14 Mini-Project

A small MCP server exposes tools over a local operations knowledge base. A CrewAI crew of three agents connects to it over stdio, answers business questions by searching documents and reading order records, and writes a sourced markdown report. Every claim in every answer cites the document or CSV record it came from.

---

## What It Does

An operations team keeps knowledge in two places: a folder of policy and procedure documents, and a CSV of order records. Staff normally answer questions by hand — opening files, cross-checking the spreadsheet, writing a summary. This assistant automates that workflow with a crew of agents that share a set of tools, so the answer always says where each fact came from.

---

## Project Structure

```
operations-assistant/
├── README.md
├── .env.example                  # environment variable template
│
├── data/
│   ├── README.md                 # describes each document and CSV column
│   ├── documents/                # 11 synthetic .txt files (policies, procedures, tickets)
│   └── records.csv               # 20-row order history CSV
│
├── server/
│   ├── mcp_server.py             # FastMCP server — three tools + one resource
│   └── search_utils.py           # keyword search helper (importable independently)
│
├── crew/
│   ├── crew.py                   # entry point: run_crew(question) → answer string
│   └── tracer.py                 # structured JSON-line tracer for all agent steps
│
├── outputs/
│   └── reports/                  # save_report writes .md files here
│
├── traces/                       # run_<timestamp>.log written per crew run
│
├── tests/
│   ├── test_tools.py             # 51 unit tests — tools called directly, no subprocess
│   └── test_crew_e2e.py          # end-to-end tests (requires crewai + local model)
│
├── examples/
│   ├── q1_electronics_return_window.md
│   ├── q2_defective_charging_pad_batch.md
│   └── q3_mispick_order_resolution.md
│
├── decision_log.md
├── reflection.md
└── AI_usage_log.md
```

---

## Quick Start

### 1. Clone and enter the repo

```bash
git clone <repo-url>
cd operations-assistant
```

### 2. Install dependencies

```bash
pip install mcp pydantic crewai "crewai-tools[mcp]"
```

Python 3.11 or 3.12 recommended. The project runs on 3.14 for the MCP server and unit tests, but `crewai` may require an earlier version.

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and set MODEL_NAME and OLLAMA_BASE_URL
```

### 4. Run the MCP server standalone (optional — for MCP Inspector)

```bash
python server/mcp_server.py
```

Test it in [MCP Inspector](https://github.com/modelcontextprotocol/inspector).

### 5. Run the unit tests

```bash
python -m pytest tests/test_tools.py -v
# 51 passed
```

### 6. Ask a question (requires crewai + Ollama)

```bash
python crew/crew.py "What is the return window for electronics?"
```

The crew prints a sourced answer to stdout and saves a markdown report to `outputs/reports/`.
A structured trace log is written to `traces/`.

### 7. Run end-to-end tests

```bash
python -m pytest tests/test_crew_e2e.py -v
```

---

## MCP Server

Built with [FastMCP](https://github.com/modelcontextprotocol/python-sdk). Runs over stdio. Three tools:

| Tool | Description |
|------|-------------|
| `search_documents(query)` | Keyword search across all `.txt` files in `data/documents/`. Returns up to 5 ranked excerpts with source filenames. |
| `read_record(order_id)` | Retrieves one row from `records.csv` by `order_id` (format: `ORD-XXXXX`). Returns all fields as labelled key-value pairs. |
| `save_report(title, content)` | Writes a markdown report to `outputs/reports/` with a timestamped filename. Returns the saved path. |

One resource:
- `ops://documents/list` — lists all available document filenames.

All tool inputs are validated with Pydantic v2. Errors are returned as clean strings — no tracebacks, no internal paths.

---

## Crew

Three agents run sequentially:

| Agent | Role | Tools | max_iter |
|-------|------|-------|----------|
| Researcher | Searches documents, collects raw evidence with source filenames | `search_documents` | 5 |
| Analyst | Retrieves order records, cross-references against document evidence | `read_record`, `search_documents` | 8 |
| Writer | Synthesises a sourced markdown report and saves it | `save_report` | 3 |

The Writer has no access to `search_documents` or `read_record` — it can only write what the Analyst hands it. This structurally enforces the grounding contract.

A grounding rule is injected into every agent's backstory and every task description:

> *Every factual claim must cite its source. If a tool returns no results, state that explicitly. Never invent, infer, or recall facts from training data.*

---

## Data

**Documents** (`data/documents/`) — 11 synthetic `.txt` files:

| File | Type |
|------|------|
| `returns_and_refunds_policy.txt` | Policy |
| `shipping_and_delivery_policy.txt` | Policy |
| `low_stock_reorder_policy.txt` | Policy |
| `product_damage_claims_procedure.txt` | Procedure |
| `warehouse_dispatch_procedure.txt` | Procedure |
| `product_notes_electronics.txt` | Product Notes |
| `product_notes_office_supplies.txt` | Product Notes |
| `support_ticket_ST-0041.txt` | Support Ticket |
| `support_ticket_ST-0055.txt` | Support Ticket |
| `support_ticket_ST-0067.txt` | Support Ticket |
| `supplier_contact_directory.txt` | Reference |

**Records** (`data/records.csv`) — 20 rows of order history (October–November 2025). Columns: `order_id`, `customer_account`, `account_tier`, `sku`, `product_name`, `quantity`, `unit_price`, `order_total`, `order_date`, `dispatch_date`, `carrier`, `tracking_number`, `delivery_status`, `return_requested`, `notes`.

---

## Tracing

Every run writes a structured log to `traces/run_<timestamp>.log`. Each line is a JSON object:

```json
{"event": "TOOL_CALL", "agent": "Researcher", "tool": "search_documents", "inputs": {"query": "refund"}, "ts": "2026-06-06T08:27:11Z"}
{"event": "TOOL_RESULT", "agent": "Researcher", "tool": "search_documents", "duration_ms": 12, "error": false, "output_preview": "SEARCH RESULTS FOR...", "ts": "..."}
{"event": "AGENT_FINISH", "agent": "Writer", "output_preview": "Report saved...", "ts": "..."}
```

Events: `RUN_START`, `TOOL_CALL`, `TOOL_RESULT`, `AGENT_ACTION`, `AGENT_FINISH`, `RUN_END`.

---

## Security Notes

- All file paths inside the MCP server are hardcoded constants — no caller-supplied path reaches the filesystem.
- Tool inputs are validated before any file I/O. Control characters, path traversal attempts, and oversized inputs are rejected with clear error messages.
- `save_report` slugifies the title before using it as a filename, and runs a `relative_to` check to confirm the final path stays inside `outputs/reports/`.
- The MCP connection is always closed in a `finally` block.
- No secrets are committed. Copy `.env.example` to `.env` and fill in your values.

---

## Example Questions

See `examples/` for three worked examples with full tool call traces and grounding check tables:

1. **q1** — What is the return window for electronics, and does a restocking fee apply?
2. **q2** — Which orders were affected by the defective WCP-2023 charging pad batch?
3. **q3** — What happened with the mispick on order ORD-01047, and what are the staff consequences?

---

## Requirements

| Package | Purpose |
|---------|---------|
| `mcp` | FastMCP server SDK |
| `pydantic>=2.0` | Input validation on all tools |
| `crewai` | Agent framework |
| `crewai-tools[mcp]` | `MCPServerAdapter` for stdio connection |
| `pytest` | Unit and e2e tests |
| Ollama (local) | LLM — no paid API required |
