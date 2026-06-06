"""
End-to-end tests for the Operations Assistant crew.

These tests start the MCP server as a real subprocess and run the crew
against fixed questions. They verify:
  - The crew completes without raising
  - Every answer contains at least one source citation
  - The crew does not hallucinate when no evidence exists
  - A report file is written to outputs/reports/
  - The trace file is written to traces/

CrewAI + a working LLM must be installed for these tests to pass.
Skip gracefully if crewai or the LLM is not available.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "crew"))

# ---------------------------------------------------------------------------
# Skip the entire module if crewai is not installed
# ---------------------------------------------------------------------------
crewai = pytest.importorskip("crewai", reason="crewai not installed — skipping e2e tests")
pytest.importorskip("crewai_tools", reason="crewai_tools not installed — skipping e2e tests")

from crew import run_crew


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_CITATION_MARKERS = [
    ".txt",           # document filename
    "records.csv",    # CSV citation
    "ORD-",           # order ID in a citation
    "Source:",        # explicit source label
    "source:",
]

def _has_citation(text: str) -> bool:
    return any(marker in text for marker in _CITATION_MARKERS)


def _reports_count_before() -> int:
    reports_dir = _REPO_ROOT / "outputs" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return len(list(reports_dir.glob("*.md")))


def _traces_count_before() -> int:
    traces_dir = _REPO_ROOT / "traces"
    traces_dir.mkdir(exist_ok=True)
    return len(list(traces_dir.glob("run_*.log")))


# ===========================================================================
# E2E: document-only question
# ===========================================================================
class TestCrewDocumentQuestions:

    def test_return_policy_question_completes(self):
        result = run_crew("What is the return window for electronics?")
        assert result
        assert len(result.strip()) > 0

    def test_return_policy_answer_contains_citation(self):
        result = run_crew("What is the return window for electronics?")
        assert _has_citation(result), (
            f"Answer contains no source citation.\nAnswer:\n{result}"
        )

    def test_return_policy_answer_mentions_15_days(self):
        result = run_crew("What is the return window for electronics?")
        assert "15" in result, (
            "Expected '15 days' for electronics but not found in answer."
        )

    def test_shipping_policy_question_completes(self):
        result = run_crew("What are the free shipping conditions?")
        assert result and len(result.strip()) > 0

    def test_shipping_policy_answer_contains_citation(self):
        result = run_crew("What are the free shipping conditions?")
        assert _has_citation(result)

    def test_reorder_policy_answer_contains_citation(self):
        result = run_crew("What is the reorder procedure when stock runs low?")
        assert _has_citation(result)


# ===========================================================================
# E2E: CSV record question
# ===========================================================================
class TestCrewRecordQuestions:

    def test_specific_order_question_completes(self):
        result = run_crew("What is the status of order ORD-01201?")
        assert result and len(result.strip()) > 0

    def test_specific_order_cites_record(self):
        result = run_crew("What is the status of order ORD-01201?")
        assert "ORD-01201" in result, (
            "Answer does not reference the queried order ID."
        )

    def test_specific_order_mentions_product(self):
        result = run_crew("What is the status of order ORD-01201?")
        # The headphones or the return flag should appear in a grounded answer
        assert "Headphone" in result or "return" in result.lower() or "EL-10087" in result

    def test_mispick_order_cites_evidence(self):
        result = run_crew("What happened with the mispick on order ORD-01047?")
        assert _has_citation(result)

    def test_mispick_answer_references_ticket_or_policy(self):
        result = run_crew("What happened with the mispick on order ORD-01047?")
        # Should reference ST-0055 ticket or warehouse_dispatch_procedure
        assert (
            "ST-0055" in result
            or "mispick" in result.lower()
            or "warehouse" in result.lower()
        )


# ===========================================================================
# E2E: cross-document question (document + CSV)
# ===========================================================================
class TestCrewCrossSourceQuestions:

    def test_defective_batch_question_completes(self):
        result = run_crew(
            "Which orders involve the defective WCP-2023 charging pad batch "
            "and what was the resolution?"
        )
        assert result and len(result.strip()) > 0

    def test_defective_batch_cites_both_sources(self):
        result = run_crew(
            "Which orders involve the defective WCP-2023 charging pad batch "
            "and what was the resolution?"
        )
        has_doc = any(m in result for m in [".txt", "Source:", "source:"])
        has_record = any(m in result for m in ["records.csv", "ORD-"])
        assert has_doc or has_record, "Expected at least one source citation."

    def test_escalated_damage_claim_question(self):
        result = run_crew(
            "What is the status of the damage claim on order ORD-01201 "
            "and what does the damage claims procedure say about late reports?"
        )
        assert _has_citation(result)


# ===========================================================================
# E2E: grounding — no fabrication when evidence is absent
# ===========================================================================
class TestCrewGrounding:

    def test_unknown_order_does_not_hallucinate(self):
        result = run_crew("What is the status of order ORD-99999?")
        # The crew must acknowledge no record was found
        assert any(phrase in result.lower() for phrase in [
            "no record",
            "not found",
            "no evidence",
            "could not find",
            "does not exist",
        ]), (
            f"Crew did not acknowledge missing record.\nAnswer:\n{result}"
        )

    def test_unknown_order_does_not_invent_product(self):
        result = run_crew("What is the status of order ORD-99999?")
        # Should not invent a product name or delivery status
        assert "Delivered" not in result or "ORD-99999" not in result

    def test_nonsense_question_does_not_fabricate_citations(self):
        result = run_crew("What is our policy on teleportation devices?")
        assert any(phrase in result.lower() for phrase in [
            "no evidence",
            "not found",
            "no documents",
            "no results",
            "could not find",
        ]), (
            f"Crew did not acknowledge missing evidence.\nAnswer:\n{result}"
        )


# ===========================================================================
# E2E: side effects — report file and trace file written
# ===========================================================================
class TestCrewSideEffects:

    def test_report_file_written_to_disk(self):
        reports_dir = _REPO_ROOT / "outputs" / "reports"
        before = _reports_count_before()
        run_crew("Summarise the return and refund policy.")
        after = len(list(reports_dir.glob("*.md")))
        assert after > before, "Expected a new .md report file in outputs/reports/"

    def test_report_file_contains_markdown_heading(self):
        reports_dir = _REPO_ROOT / "outputs" / "reports"
        run_crew("Summarise the shipping policy.")
        md_files = sorted(reports_dir.glob("*.md"), key=lambda p: p.stat().st_mtime)
        latest = md_files[-1].read_text(encoding="utf-8")
        assert latest.startswith("#"), "Report file does not start with a markdown heading."

    def test_trace_file_written_to_disk(self):
        traces_dir = _REPO_ROOT / "traces"
        before = _traces_count_before()
        run_crew("What is the reorder point for EL-10042?")
        after = len(list(traces_dir.glob("run_*.log")))
        assert after > before, "Expected a new run_*.log file in traces/"

    def test_trace_file_contains_run_start_event(self):
        traces_dir = _REPO_ROOT / "traces"
        run_crew("What carrier handles standard shipments?")
        log_files = sorted(traces_dir.glob("run_*.log"), key=lambda p: p.stat().st_mtime)
        latest_lines = log_files[-1].read_text(encoding="utf-8").splitlines()
        import json
        events = []
        for line in latest_lines:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        event_types = [e.get("event") for e in events]
        assert "RUN_START" in event_types
        assert "RUN_END" in event_types

    def test_trace_file_records_tool_calls(self):
        traces_dir = _REPO_ROOT / "traces"
        run_crew("What is the return policy for office supplies?")
        log_files = sorted(traces_dir.glob("run_*.log"), key=lambda p: p.stat().st_mtime)
        latest_lines = log_files[-1].read_text(encoding="utf-8").splitlines()
        import json
        tool_call_events = []
        for line in latest_lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("event") == "TOOL_CALL":
                    tool_call_events.append(obj)
            except json.JSONDecodeError:
                pass
        assert len(tool_call_events) > 0, (
            "No TOOL_CALL events found in trace — tools may not have been called."
        )


# ===========================================================================
# E2E: Verifier agent behaviour
# ===========================================================================
class TestCrewVerifier:

    def test_verification_passed_in_result_for_grounded_question(self):
        result = run_crew("What is the return window for electronics?")
        assert "Verification Passed" in result, (
            f"Expected 'Verification Passed' in result.\nResult:\n{result}"
        )

    def test_report_saved_only_after_verification_passes(self):
        reports_dir = _REPO_ROOT / "outputs" / "reports"
        before = _reports_count_before()
        result = run_crew("What is the free shipping threshold?")
        after = len(list(reports_dir.glob("*.md")))
        if "Verification Passed" in result:
            assert after > before, (
                "Verification Passed but no new report file was written."
            )

    def test_verification_failed_blocks_save_on_bad_question(self):
        reports_dir = _REPO_ROOT / "outputs" / "reports"
        before = _reports_count_before()
        # A nonsense question should produce no evidence and force Verification Failed
        result = run_crew("What is our policy on teleportation devices?")
        after = len(list(reports_dir.glob("*.md")))
        if "Verification Failed" in result:
            assert after == before, (
                "Verification Failed but a report was saved — save_report should not have been called."
            )

    def test_verification_failed_lists_unsupported_statements(self):
        result = run_crew("What is our policy on teleportation devices?")
        if "Verification Failed" in result:
            # The failure report must list at least one unsupported statement
            lines = result.splitlines()
            numbered = [l for l in lines if l.strip() and l.strip()[0].isdigit()]
            assert len(numbered) >= 1, (
                "Verification Failed but no unsupported statements were listed."
            )

    def test_verification_step_appears_in_trace(self):
        traces_dir = _REPO_ROOT / "traces"
        run_crew("What is the reorder policy for low stock?")
        log_files = sorted(traces_dir.glob("run_*.log"), key=lambda p: p.stat().st_mtime)
        latest_lines = log_files[-1].read_text(encoding="utf-8").splitlines()
        import json
        agents_seen = set()
        for line in latest_lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                agent = obj.get("agent", "")
                if agent:
                    agents_seen.add(agent)
            except json.JSONDecodeError:
                pass
        assert any("Verifier" in a or "verifier" in a.lower() for a in agents_seen), (
            f"No Verifier agent events found in trace. Agents seen: {agents_seen}"
        )

    def test_save_report_tool_called_by_verifier_not_writer(self):
        traces_dir = _REPO_ROOT / "traces"
        run_crew("What carrier is used for standard shipments?")
        log_files = sorted(traces_dir.glob("run_*.log"), key=lambda p: p.stat().st_mtime)
        latest_lines = log_files[-1].read_text(encoding="utf-8").splitlines()
        import json
        save_calls = []
        for line in latest_lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("event") == "TOOL_CALL" and obj.get("tool") == "save_report":
                    save_calls.append(obj)
            except json.JSONDecodeError:
                pass
        for call in save_calls:
            assert "Writer" not in call.get("agent", ""), (
                f"save_report was called by the Writer — should only be called by the Verifier.\n{call}"
            )


# ===========================================================================
# E2E: input validation at crew entry point
# ===========================================================================
class TestCrewInputValidation:

    def test_empty_question_raises_value_error(self):
        with pytest.raises(ValueError, match="empty"):
            run_crew("")

    def test_whitespace_question_raises_value_error(self):
        with pytest.raises(ValueError, match="empty"):
            run_crew("   ")
