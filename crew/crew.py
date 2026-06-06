"""
Operations Assistant crew.
Four agents — Researcher, Analyst, Writer, Verifier — share one MCP server
via MCPServerAdapter over stdio and answer a business question with
a verified, sourced markdown report.

Workflow
--------
Researcher  → collects raw document evidence
Analyst     → cross-references evidence against CSV records
Writer      → drafts a sourced markdown report (does NOT save it)
Verifier    → checks every claim in the draft against retrieved evidence;
              calls save_report only if all claims are supported,
              otherwise returns "Verification Failed" with unsupported statements listed
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from crewai import Agent, Crew, Process, Task
from crewai_tools import MCPServerAdapter
from mcp import StdioServerParameters

from tracer import RunTracer

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
_SERVER_SCRIPT = _REPO_ROOT / "server" / "mcp_server.py"

# ---------------------------------------------------------------------------
# Grounding rule — injected into every agent backstory and every task
# ---------------------------------------------------------------------------
_GROUNDING_RULE = (
    "GROUNDING RULE: Every factual claim you produce must cite its source — "
    "either the exact document filename returned by search_documents, or "
    "'records.csv, order ORD-XXXXX' returned by read_record. "
    "If a tool returns no results, state explicitly that no evidence was found. "
    "Never invent, infer, or recall facts from training data."
)

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def run_crew(question: str) -> str:
    """
    Run the four-agent crew against the given question.
    Returns the Verifier's final answer string (either a saved-report confirmation
    or a Verification Failed message with unsupported statements listed).
    The MCP server subprocess is always stopped in the finally block.
    """
    if not question or not question.strip():
        raise ValueError("question must not be empty.")

    tracer = RunTracer(question)
    tracer.start()

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(_SERVER_SCRIPT)],
        env={**os.environ},
    )

    adapter = MCPServerAdapter(server_params)

    try:
        adapter.start()
        tools = adapter.tools
        tracer.log_agent_action("system", thought=f"MCP server started | tools: {[t.name for t in tools]}")

        # Partition tools by name so each agent receives only what it needs
        def _tool(name: str):
            match = [t for t in tools if t.name == name]
            if not match:
                raise RuntimeError(
                    f"Expected tool '{name}' not found on MCP server. "
                    f"Available: {[t.name for t in tools]}"
                )
            return match[0]

        search_tool   = _tool("search_documents")
        record_tool   = _tool("read_record")
        report_tool   = _tool("save_report")

        # -------------------------------------------------------------------
        # Agents
        # -------------------------------------------------------------------
        researcher = Agent(
            role="Operations Knowledge Researcher",
            goal=(
                "Search the operations document corpus to find every passage "
                "relevant to the user's question. Collect raw evidence — exact "
                "excerpts and source filenames — without interpreting or summarising. "
                "Pass a complete, attributed evidence package to the Analyst."
            ),
            backstory=(
                "You are a meticulous research librarian embedded in an operations team. "
                "Your only job is to find what the documents actually say — not what seems "
                "likely, not what you recall from training. You have learned the hard way "
                "that an unsourced claim causes more damage than admitting you found nothing. "
                "If a search returns no results, you say so plainly and do not fill the gap. "
                "Every excerpt you hand off must include the exact filename it came from. "
                f"{_GROUNDING_RULE}"
            ),
            tools=[search_tool],
            max_iter=5,
            verbose=True,
        )

        analyst = Agent(
            role="Operations Data Analyst",
            goal=(
                "Cross-reference the documentary evidence from the Researcher against "
                "the order records in the CSV. Retrieve every relevant record, verify "
                "the facts, and produce a cited fact set that explicitly links every "
                "finding to its source."
            ),
            backstory=(
                "You are a detail-oriented data analyst who spent years reconciling "
                "discrepancies between what policies say and what actually happened in "
                "the records. You trust nothing until you have checked it against a "
                "primary source. You receive a package of document excerpts from the "
                "Researcher and your job is to find the corresponding data in the order "
                "records, flag any contradictions between the two, and deliver a clean, "
                "cited fact set to the Writer. You never state a number or status from "
                "memory — you always call read_record and quote what comes back. "
                f"{_GROUNDING_RULE}"
            ),
            tools=[record_tool, search_tool],
            max_iter=8,
            verbose=True,
        )

        writer = Agent(
            role="Operations Report Writer",
            goal=(
                "Synthesise the Analyst's verified fact set into a clear, concise "
                "markdown report draft that directly answers the user's question. "
                "Every factual claim must cite its source. "
                "Output the complete draft as plain text — do NOT call save_report. "
                "The Verifier will review and save the report."
            ),
            backstory=(
                "You are a clear, precise technical writer who produces operational "
                "briefings for senior managers who have no patience for vague answers. "
                "You know that a report without sources is an opinion, not a finding. "
                "You receive a verified fact set from the Analyst and your only job is "
                "to turn it into a readable markdown draft — no new research, no invented details. "
                "If the fact set contains a gap flagged by the Analyst, you include it "
                "honestly rather than papering over it. "
                "Do NOT call save_report — output the draft text only. "
                "A Verifier will check every claim before the report is saved. "
                f"{_GROUNDING_RULE}"
            ),
            tools=[],
            max_iter=3,
            verbose=True,
        )

        verifier = Agent(
            role="Operations Report Verifier",
            goal=(
                "Review the Writer's draft report claim by claim. "
                "For every factual statement, confirm it is supported by a source citation "
                "that appears in the Analyst's evidence. Use search_documents to spot-check "
                "any claim that lacks a clear citation or looks suspicious. "
                "If ALL claims are supported, output 'Verification Passed', then call "
                "save_report with the verified report. "
                "If ANY claim is unsupported or hallucinated, output 'Verification Failed' "
                "followed by a numbered list of every unsupported statement — do NOT save."
            ),
            backstory=(
                "You are a rigorous quality-control analyst whose entire job is to catch "
                "fabricated or unsourced claims before they reach a manager. You have seen "
                "AI systems confidently state things that never appeared in any source document, "
                "and you know that a single uncited claim destroys trust in the whole report. "
                "You read the draft line by line. For each factual statement you ask: "
                "'Is there a citation? Does the cited source actually say this?' "
                "You use search_documents to verify any claim you are uncertain about. "
                "You do not care about writing quality — only about whether every claim "
                "is traceable to the retrieved evidence. "
                "You never save a report that contains even one unsupported statement. "
                f"{_GROUNDING_RULE}"
            ),
            tools=[search_tool, report_tool],
            max_iter=6,
            verbose=True,
        )

        # -------------------------------------------------------------------
        # Tasks
        # -------------------------------------------------------------------
        research_task = Task(
            description=(
                f"User question: {question}\n\n"
                "1. Optionally review the list of available documents to identify "
                "   which ones are most likely to contain relevant information.\n"
                "2. Identify every distinct concept in the question and run "
                "   search_documents for each one.\n"
                "3. Collect all returned excerpts exactly as returned — do not paraphrase.\n"
                "4. If any search returns no results, record that explicitly.\n"
                "5. Do NOT draw conclusions. Do NOT answer the question.\n\n"
                f"{_GROUNDING_RULE}"
            ),
            expected_output=(
                "A structured evidence package formatted as a numbered list. "
                "Each item: [source filename] → [exact excerpt]. "
                "If a search returned nothing, include: [query] → NO RESULTS FOUND. "
                "No conclusions, no interpretation, no invented content."
            ),
            agent=researcher,
        )

        analysis_task = Task(
            description=(
                f"User question: {question}\n\n"
                "You will receive the Researcher's evidence package as context.\n\n"
                "1. Extract every order ID (format ORD-XXXXX) referenced in the "
                "   evidence package or implied by the question.\n"
                "2. Call read_record for each order ID found.\n"
                "3. Cross-reference each retrieved record against the relevant "
                "   document excerpts — identify agreements, contradictions, and gaps.\n"
                "4. If a new question arises that requires a document lookup, "
                "   call search_documents.\n"
                "5. Do NOT call save_report. Do NOT write the final report.\n\n"
                f"{_GROUNDING_RULE}"
            ),
            expected_output=(
                "A verified fact set formatted as a numbered list. "
                "Each item: [claim] | source: [document filename OR 'records.csv, order ORD-XXXXX']. "
                "A separate 'GAPS / CONFLICTS' section listing anything that could not be verified "
                "or where the document and record disagree. "
                "No invented content. Every claim has a source."
            ),
            agent=analyst,
            context=[research_task],
        )

        write_task = Task(
            description=(
                f"User question: {question}\n\n"
                "You will receive the Analyst's verified fact set as context.\n\n"
                "Write a markdown report DRAFT with this exact structure:\n"
                "  ## Answer\n"
                "  One paragraph directly answering the question.\n\n"
                "  ## Supporting Evidence\n"
                "  Bulleted list of findings. Each bullet ends with its source in "
                "  parentheses, e.g. (source: returns_and_refunds_policy.txt) or "
                "  (source: records.csv, order ORD-01201).\n\n"
                "  ## Gaps and Unverified Items\n"
                "  Honest list of anything the Analyst flagged as unverified or "
                "  conflicting. If there are none, write 'None.'\n\n"
                "IMPORTANT RULES:\n"
                "- Use only facts from the Analyst's fact set. No new research.\n"
                "- Every factual claim must end with a (source: ...) citation.\n"
                "- Do NOT call save_report — output the draft text only.\n"
                "- The Verifier will check your draft and save it if it passes.\n\n"
                f"{_GROUNDING_RULE}"
            ),
            expected_output=(
                "A complete markdown report draft as plain text, following the "
                "## Answer / ## Supporting Evidence / ## Gaps and Unverified Items "
                "structure. Every factual claim includes a (source: ...) citation. "
                "No save_report call. No file path. Draft text only."
            ),
            agent=writer,
            context=[analysis_task],
        )

        verify_task = Task(
            description=(
                f"User question: {question}\n\n"
                "You will receive the Writer's draft report as context.\n\n"
                "Your job is to verify EVERY factual claim in the draft:\n"
                "1. Read the draft line by line.\n"
                "2. For each factual statement, check it has a (source: ...) citation.\n"
                "3. If a claim has no citation, mark it as UNSUPPORTED.\n"
                "4. If a claim has a citation but you are uncertain it is accurate, "
                "   call search_documents to spot-check it against the source document.\n"
                "5. If search_documents returns no match for a cited claim, mark it UNSUPPORTED.\n\n"
                "DECISION:\n"
                "- If ALL claims are supported:\n"
                "  Output the line 'Verification Passed' on its own line.\n"
                "  Then call save_report with title and the full verified report content.\n"
                "  Then output the save_report confirmation and a one-paragraph summary.\n\n"
                "- If ANY claim is unsupported or hallucinated:\n"
                "  Output 'Verification Failed' on its own line.\n"
                "  Then output a numbered list of every unsupported statement.\n"
                "  Do NOT call save_report.\n\n"
                f"{_GROUNDING_RULE}"
            ),
            expected_output=(
                "Either:\n"
                "  'Verification Passed' followed by the save_report confirmation "
                "  (REPORT SAVED: ...) and a one-paragraph plain-English summary, OR\n"
                "  'Verification Failed' followed by a numbered list of every "
                "  unsupported statement found in the draft."
            ),
            agent=verifier,
            context=[analysis_task, write_task],
        )

        # -------------------------------------------------------------------
        # Crew
        # -------------------------------------------------------------------
        crew = Crew(
            agents=[researcher, analyst, writer, verifier],
            tasks=[research_task, analysis_task, write_task, verify_task],
            process=Process.sequential,
            verbose=True,
            step_callback=tracer.step_callback,
        )

        result = crew.kickoff(inputs={"question": question})
        tracer.stop()
        return str(result)

    except Exception as exc:
        tracer.stop(error=str(exc))
        raise

    finally:
        try:
            adapter.stop()
        except Exception:
            pass
        print(f"\nTrace written to: {tracer.trace_path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python crew.py \"<your question>\"", file=sys.stderr)
        sys.exit(1)

    question_arg = " ".join(sys.argv[1:])
    answer = run_crew(question_arg)
    print("\n" + "=" * 60)
    print("FINAL ANSWER")
    print("=" * 60)
    print(answer)
