"""
Operations Assistant crew.
Three agents — Researcher, Analyst, Writer — share one MCP server
via MCPServerAdapter over stdio and answer a business question with
a sourced markdown report.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from crewai import Agent, Crew, Process, Task
from crewai_tools import MCPServerAdapter
from mcp import StdioServerParameters

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
_SERVER_SCRIPT = _REPO_ROOT / "server" / "mcp_server.py"
_TRACES_DIR = _REPO_ROOT / "traces"
_TRACES_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Logging — trace file per run
# ---------------------------------------------------------------------------
_RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
_TRACE_FILE = _TRACES_DIR / f"run_{_RUN_ID}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(_TRACE_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger("crew")

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
# Step callback — writes one structured line per agent step to the trace file
# ---------------------------------------------------------------------------
def _step_callback(step_output) -> None:
    try:
        agent_name = getattr(step_output, "agent", "unknown")
        tool = getattr(step_output, "tool", None)
        tool_input = getattr(step_output, "tool_input", None)
        result = getattr(step_output, "result", None)

        action = tool if tool else "final_answer"
        input_preview = str(tool_input)[:300] if tool_input else ""
        output_preview = str(result)[:200] if result else ""

        logger.info(
            "STEP | agent=%s | action=%s | input=%r | output_preview=%r",
            agent_name,
            action,
            input_preview,
            output_preview,
        )
    except Exception as exc:
        logger.warning("Step callback error (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def run_crew(question: str) -> str:
    """
    Run the three-agent crew against the given question.
    Returns the Writer's final answer string.
    The MCP server subprocess is always stopped in the finally block.
    """
    if not question or not question.strip():
        raise ValueError("question must not be empty.")

    logger.info("Run started | question=%r", question)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(_SERVER_SCRIPT)],
        env={**os.environ},
    )

    adapter = MCPServerAdapter(server_params)

    try:
        adapter.start()
        tools = adapter.tools
        logger.info("MCP server started | tools available: %s", [t.name for t in tools])

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
                "markdown report that directly answers the user's question. Every "
                "factual claim must cite its source. Save the finished report using "
                "save_report and return the saved file path alongside a brief summary."
            ),
            backstory=(
                "You are a clear, precise technical writer who produces operational "
                "briefings for senior managers who have no patience for vague answers. "
                "You know that a report without sources is an opinion, not a finding. "
                "You receive a verified fact set from the Analyst and your only job is "
                "to turn it into a readable report — no new research, no invented details. "
                "If the fact set contains a gap flagged by the Analyst, you include it "
                "honestly in the report rather than papering over it. The report is not "
                "finished until save_report has been called and returned a confirmation. "
                f"{_GROUNDING_RULE}"
            ),
            tools=[report_tool],
            max_iter=3,
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
                "Write a markdown report with this structure:\n"
                "  ## Answer\n"
                "  One paragraph directly answering the question.\n\n"
                "  ## Supporting Evidence\n"
                "  Bulleted list of findings. Each bullet ends with its source in "
                "  parentheses, e.g. (source: returns_and_refunds_policy.txt) or "
                "  (source: records.csv, order ORD-01201).\n\n"
                "  ## Gaps and Unverified Items\n"
                "  Honest list of anything the Analyst flagged as unverified or "
                "  conflicting. If there are none, write 'None.'\n\n"
                "Rules:\n"
                "- Use only facts from the Analyst's fact set. No new research.\n"
                "- Do not include any claim without a source citation.\n"
                "- Call save_report exactly once when the report is complete.\n\n"
                f"{_GROUNDING_RULE}"
            ),
            expected_output=(
                "The path to the saved report file as returned by save_report, "
                "followed by a one-paragraph plain-English summary of the findings "
                "that could be read aloud to a manager. "
                "Every claim in the summary must be traceable to the saved report."
            ),
            agent=writer,
            context=[analysis_task],
        )

        # -------------------------------------------------------------------
        # Crew
        # -------------------------------------------------------------------
        crew = Crew(
            agents=[researcher, analyst, writer],
            tasks=[research_task, analysis_task, write_task],
            process=Process.sequential,
            verbose=True,
            step_callback=_step_callback,
        )

        result = crew.kickoff(inputs={"question": question})
        logger.info("Run completed | result_preview=%r", str(result)[:300])
        return str(result)

    except Exception as exc:
        logger.error("Crew run failed: %s", exc, exc_info=True)
        raise

    finally:
        try:
            adapter.stop()
            logger.info("MCP server stopped cleanly.")
        except Exception as exc:
            logger.warning("Error stopping MCP server (non-fatal): %s", exc)
        logger.info("Trace written to: %s", _TRACE_FILE)


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
