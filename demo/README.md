# Demo

## 5-Minute Clip

**Link:** [Google Drive Demo Video](https://drive.google.com/file/d/1Sf3VAq2r4bdtoekuD3NQ_QWwliD5oznc/view?usp=sharing)

The clip must cover:

| Time | What to cover |
|------|--------------|
| ~1 min | **The pitch.** What you built and why it matters. |
| ~1 min | **Show it run.** Ask one question, show the crew calling MCP tools, show the answer with sources. |
| ~1.5 min | **One decision and one failure.** A real choice you made and why; one thing that broke and how you fixed it. |
| ~1 min | **What you learned.** Explain MCP and CrewAI in your own words, the one security risk you took seriously, the two or three sources you used most. |
| ~30 sec | **What is next.** What you would change before this touched real company data. |

## Suggested Demo Script

```bash
# Terminal 1 — show the MCP server starting
python server/mcp_server.py

# Terminal 2 — show a crew run answering a real question
python crew/crew.py "What is the return window for electronics, and does a restocking fee apply?"

# Terminal 3 — show the saved report
cat outputs/reports/<latest>.md

# Terminal 4 — show the trace
cat traces/run_<latest>.log | python3 -m json.tool | head -60

# Terminal 5 — show the tests passing
python -m pytest tests/test_tools.py tests/test_tracer.py -v
```

## Suggested Questions to Demo

1. `"What is the return window for electronics, and does a restocking fee apply?"`  
   → Exercises `search_documents`, cites `returns_and_refunds_policy.txt`

2. `"What happened with order ORD-01201?"`  
   → Exercises `read_record`, cites `records.csv` + `support_ticket_ST-0067.txt`

3. `"Which orders were affected by the defective WCP-2023 charging pad batch?"`  
   → Cross-source: documents + CSV + support ticket chain
