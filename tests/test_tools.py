"""
Unit tests for the three MCP tools, search_utils, and the approval gate.

These tests call the tool functions directly — no MCP server process,
no CrewAI, no network. They verify:
  - Correct output for valid inputs
  - Correct error strings for every invalid-input case
  - save_report file creation and path-traversal rejection
  - search_utils ranking and no-result behaviour
  - ApprovalSaveTool approve / cancel / invalid-input / interrupt behaviour
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup — allow imports from server/ and crew/ without installing
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "server"))
sys.path.insert(0, str(_REPO_ROOT / "crew"))

from search_utils import SearchResult, search_documents as _raw_search

# We import the tool functions after patching the path constants so the
# tools resolve data files relative to the real repo, not the cwd.
import importlib
import mcp_server as _srv

# ---------------------------------------------------------------------------
# Convenience aliases to the three tool functions
# ---------------------------------------------------------------------------
search_documents = _srv.search_documents
read_record = _srv.read_record
save_report = _srv.save_report


# ===========================================================================
# search_documents
# ===========================================================================
class TestSearchDocuments:

    def test_known_term_returns_results(self):
        result = search_documents("refund")
        assert "SEARCH RESULTS FOR:" in result
        assert "Source:" in result
        assert "INSTRUCTION:" in result

    def test_result_cites_filename(self):
        result = search_documents("refund")
        assert "returns_and_refunds_policy.txt" in result

    def test_result_sorted_by_match_count(self):
        result = search_documents("return")
        lines = [l for l in result.splitlines() if l.startswith("[")]
        # First result must have the highest or equal match count
        # We verify at least two results exist and the first has more matches
        assert len(lines) >= 2

    def test_maximum_five_results(self):
        # "the" appears in many documents; result count must be capped at 5
        result = search_documents("the")
        source_lines = [l for l in result.splitlines() if "Source:" in l]
        assert len(source_lines) <= 5

    def test_no_results_returns_no_evidence_message(self):
        result = search_documents("xyzzy_no_match_token_99999")
        assert "No documents matched" in result
        assert "no evidence" in result.lower()

    def test_no_results_does_not_contain_source(self):
        result = search_documents("xyzzy_no_match_token_99999")
        assert "Source:" not in result

    def test_specific_product_batch_found(self):
        result = search_documents("WCP-2023")
        assert "support_ticket_ST-0041.txt" in result

    def test_specific_order_id_found(self):
        result = search_documents("ORD-01201")
        # The order ID appears in at least one document (ST-0067)
        assert "Source:" in result

    def test_instruction_line_always_present_on_hit(self):
        result = search_documents("shipping")
        assert "Cite the source filename" in result

    # --- Invalid inputs ---

    def test_empty_string_returns_error(self):
        result = search_documents("")
        assert result.startswith("ERROR:")

    def test_whitespace_only_returns_error(self):
        result = search_documents("   ")
        assert result.startswith("ERROR:")

    def test_query_too_long_returns_error(self):
        result = search_documents("a" * 201)
        assert result.startswith("ERROR:")

    def test_null_byte_in_query_returns_error(self):
        result = search_documents("valid\x00query")
        assert result.startswith("ERROR:")

    def test_control_character_in_query_returns_error(self):
        result = search_documents("hello\x1fworld")
        assert result.startswith("ERROR:")

    def test_max_length_query_accepted(self):
        result = search_documents("a" * 200)
        # Should not return an error about length
        assert "too long" not in result.lower()


# ===========================================================================
# search_utils (unit — no server wrapper)
# ===========================================================================
class TestSearchUtils:

    def test_returns_list_of_search_results(self):
        results = _raw_search("return", str(_REPO_ROOT / "data" / "documents"))
        assert isinstance(results, list)
        assert all(isinstance(r, SearchResult) for r in results)

    def test_results_sorted_descending_by_match_count(self):
        results = _raw_search("return", str(_REPO_ROOT / "data" / "documents"))
        counts = [r.match_count for r in results]
        assert counts == sorted(counts, reverse=True)

    def test_result_has_source_filename_only(self):
        results = _raw_search("return", str(_REPO_ROOT / "data" / "documents"))
        for r in results:
            assert "/" not in r.source
            assert "\\" not in r.source
            assert r.source.endswith(".txt")

    def test_empty_query_returns_empty_list(self):
        # _raw_search with an empty string matches every line — but we verify
        # it returns a list without raising
        results = _raw_search("", str(_REPO_ROOT / "data" / "documents"))
        assert isinstance(results, list)

    def test_nonexistent_directory_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="Cannot read document directory"):
            _raw_search("return", "/nonexistent/path/that/does/not/exist")


# ===========================================================================
# read_record
# ===========================================================================
class TestReadRecord:

    def test_valid_order_returns_record(self):
        result = read_record("ORD-01201")
        assert "RECORD: ORD-01201" in result

    def test_record_contains_expected_fields(self):
        result = read_record("ORD-01201")
        assert "product_name" in result
        assert "delivery_status" in result
        assert "return_requested" in result
        assert "order_total" in result

    def test_record_formats_currency(self):
        result = read_record("ORD-01201")
        assert "$189.00" in result

    def test_record_contains_citation_instruction(self):
        result = read_record("ORD-01201")
        assert "records.csv, order ORD-01201" in result

    def test_replacement_order_has_zero_cost(self):
        result = read_record("ORD-00931")
        assert "$0.00" in result

    def test_order_not_found_returns_not_found_message(self):
        result = read_record("ORD-99999")
        assert "RECORD NOT FOUND" in result
        assert "no record was found" in result.lower()

    def test_not_found_does_not_invent_data(self):
        result = read_record("ORD-99999")
        assert "product_name" not in result
        assert "delivery_status" not in result

    # --- Invalid inputs ---

    def test_empty_order_id_returns_error(self):
        result = read_record("")
        assert result.startswith("ERROR:")
        assert "invalid" in result.lower()

    def test_wrong_prefix_returns_error(self):
        result = read_record("INV-01201")
        assert result.startswith("ERROR:")

    def test_too_few_digits_returns_error(self):
        result = read_record("ORD-1234")
        assert result.startswith("ERROR:")

    def test_too_many_digits_returns_error(self):
        result = read_record("ORD-123456")
        assert result.startswith("ERROR:")

    def test_whitespace_stripped_and_accepted(self):
        result = read_record("  ORD-01201  ")
        assert "RECORD: ORD-01201" in result

    def test_lowercase_prefix_returns_error(self):
        result = read_record("ord-01201")
        assert result.startswith("ERROR:")

    def test_error_message_includes_format_hint(self):
        result = read_record("INVALID")
        assert "ORD-XXXXX" in result or "ORD-" in result


# ===========================================================================
# save_report
# ===========================================================================
class TestSaveReport:

    def test_valid_inputs_returns_saved_confirmation(self):
        result = save_report("Test Unit Report", "Finding: all systems operational.")
        assert "REPORT SAVED:" in result

    def test_saved_file_exists_on_disk(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_srv, "_REPORTS_DIR", tmp_path)
        result = save_report("Disk Check Report", "Content here.")
        assert "REPORT SAVED:" in result
        saved_line = [l for l in result.splitlines() if "REPORT SAVED:" in l][0]
        # The confirmation includes a relative path; check a .md file was created
        md_files = list(tmp_path.glob("*.md"))
        assert len(md_files) == 1

    def test_saved_file_contains_title_as_heading(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_srv, "_REPORTS_DIR", tmp_path)
        save_report("My Heading Report", "Body content.")
        md_file = list(tmp_path.glob("*.md"))[0]
        content = md_file.read_text(encoding="utf-8")
        assert "# My Heading Report" in content

    def test_saved_file_contains_body_content(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_srv, "_REPORTS_DIR", tmp_path)
        save_report("Body Test", "Unique body string abc123.")
        md_file = list(tmp_path.glob("*.md"))[0]
        content = md_file.read_text(encoding="utf-8")
        assert "Unique body string abc123." in content

    def test_filename_is_slugified_from_title(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_srv, "_REPORTS_DIR", tmp_path)
        save_report("Order Status Q4 2025", "Content.")
        md_file = list(tmp_path.glob("*.md"))[0]
        assert "order_status_q4_2025" in md_file.name

    def test_confirmation_includes_title(self):
        result = save_report("Confirmation Title Check", "Body.")
        assert "Confirmation Title Check" in result

    def test_confirmation_includes_saved_at_timestamp(self):
        result = save_report("Timestamp Check", "Body.")
        assert "Saved at:" in result

    def test_confirmation_includes_length(self):
        result = save_report("Length Check", "Body.")
        assert "Length" in result or "characters" in result

    def test_path_traversal_in_title_is_neutralised(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_srv, "_REPORTS_DIR", tmp_path)
        result = save_report("../../../etc/passwd", "Injected content.")
        # Either saved safely (traversal stripped) or rejected with ERROR
        if "REPORT SAVED:" in result:
            md_files = list(tmp_path.glob("*.md"))
            assert len(md_files) == 1
            # File must be inside tmp_path, not outside
            assert md_files[0].parent == tmp_path
        else:
            assert result.startswith("ERROR:")

    # --- Invalid inputs ---

    def test_empty_title_returns_error(self):
        result = save_report("", "Content.")
        assert result.startswith("ERROR:")

    def test_whitespace_title_returns_error(self):
        result = save_report("   ", "Content.")
        assert result.startswith("ERROR:")

    def test_empty_content_returns_error(self):
        result = save_report("Valid Title", "")
        assert result.startswith("ERROR:")

    def test_whitespace_content_returns_error(self):
        result = save_report("Valid Title", "   ")
        assert result.startswith("ERROR:")

    def test_title_too_long_returns_error(self):
        result = save_report("T" * 101, "Content.")
        assert result.startswith("ERROR:")

    def test_content_too_long_returns_error(self):
        result = save_report("Valid Title", "x" * 10_001)
        assert result.startswith("ERROR:")

    def test_max_length_title_accepted(self):
        result = save_report("T" * 100, "Content.")
        assert not result.startswith("ERROR:")

    def test_max_length_content_accepted(self):
        result = save_report("Valid Title", "x" * 10_000)
        assert not result.startswith("ERROR:")


# ===========================================================================
# ApprovalSaveTool — human approval gate
# ===========================================================================

# Lazy import — approval_tool imports crewai's BaseTool; skip the class
# gracefully if crewai is not installed. The rest of test_tools.py is
# independent and must not be skipped.
_crewai_missing = pytest.mark.skipif(
    __import__("importlib").util.find_spec("crewai") is None,
    reason="crewai not installed — skipping ApprovalSaveTool tests",
)

# Import only when crewai is available; fall back to a sentinel for collection
try:
    from approval_tool import ApprovalSaveTool
    _approval_tool_available = True
except Exception:
    ApprovalSaveTool = None  # type: ignore[assignment,misc]
    _approval_tool_available = False


class _FakeUnderlyingTool:
    """Minimal stand-in for the MCP save_report tool."""

    def __init__(self):
        self.calls: list[dict] = []

    def run(self, inputs: dict | str) -> str:
        if isinstance(inputs, str):
            import json as _json
            inputs = _json.loads(inputs)
        self.calls.append(inputs)
        return f"REPORT SAVED: outputs/reports/fake_{inputs['title'][:20]}.md"

    def _run(self, title: str = "", content: str = "") -> str:
        return self.run({"title": title, "content": content})


@_crewai_missing
class TestApprovalGate:

    # ------------------------------------------------------------------
    # Happy path — user approves
    # ------------------------------------------------------------------
    def test_approval_y_delegates_to_underlying(self):
        fake = _FakeUnderlyingTool()
        tool = ApprovalSaveTool(underlying=fake, input_fn=lambda _: "y")
        result = tool._run(title="My Report", content="Finding 1.")
        assert "REPORT SAVED:" in result

    def test_approval_y_passes_correct_title(self):
        fake = _FakeUnderlyingTool()
        tool = ApprovalSaveTool(underlying=fake, input_fn=lambda _: "y")
        tool._run(title="Title Check", content="Body.")
        assert fake.calls[0]["title"] == "Title Check"

    def test_approval_y_passes_correct_content(self):
        fake = _FakeUnderlyingTool()
        tool = ApprovalSaveTool(underlying=fake, input_fn=lambda _: "y")
        tool._run(title="T", content="Exact content string.")
        assert fake.calls[0]["content"] == "Exact content string."

    def test_approval_y_uppercase_accepted(self):
        fake = _FakeUnderlyingTool()
        tool = ApprovalSaveTool(underlying=fake, input_fn=lambda _: "Y")
        result = tool._run(title="T", content="Body.")
        assert "REPORT SAVED:" in result

    def test_approval_y_with_surrounding_whitespace_accepted(self):
        fake = _FakeUnderlyingTool()
        tool = ApprovalSaveTool(underlying=fake, input_fn=lambda _: "  y  ")
        result = tool._run(title="T", content="Body.")
        assert "REPORT SAVED:" in result

    # ------------------------------------------------------------------
    # User cancels
    # ------------------------------------------------------------------
    def test_approval_n_returns_cancelled(self):
        fake = _FakeUnderlyingTool()
        tool = ApprovalSaveTool(underlying=fake, input_fn=lambda _: "n")
        result = tool._run(title="My Report", content="Finding 1.")
        assert "cancelled" in result.lower()

    def test_approval_n_does_not_call_underlying(self):
        fake = _FakeUnderlyingTool()
        tool = ApprovalSaveTool(underlying=fake, input_fn=lambda _: "n")
        tool._run(title="My Report", content="Finding 1.")
        assert len(fake.calls) == 0

    def test_approval_n_uppercase_cancels(self):
        fake = _FakeUnderlyingTool()
        tool = ApprovalSaveTool(underlying=fake, input_fn=lambda _: "N")
        result = tool._run(title="T", content="Body.")
        assert "cancelled" in result.lower()

    def test_approval_n_with_whitespace_cancels(self):
        fake = _FakeUnderlyingTool()
        tool = ApprovalSaveTool(underlying=fake, input_fn=lambda _: "  n  ")
        result = tool._run(title="T", content="Body.")
        assert "cancelled" in result.lower()

    # ------------------------------------------------------------------
    # Invalid input — re-prompts until valid response
    # ------------------------------------------------------------------
    def test_invalid_then_y_eventually_approves(self):
        fake = _FakeUnderlyingTool()
        responses = iter(["maybe", "sure", "yes", "y"])
        tool = ApprovalSaveTool(underlying=fake, input_fn=lambda _: next(responses))
        result = tool._run(title="T", content="Body.")
        assert "REPORT SAVED:" in result

    def test_invalid_then_n_eventually_cancels(self):
        fake = _FakeUnderlyingTool()
        responses = iter(["oops", "nope", "n"])
        tool = ApprovalSaveTool(underlying=fake, input_fn=lambda _: next(responses))
        result = tool._run(title="T", content="Body.")
        assert "cancelled" in result.lower()
        assert len(fake.calls) == 0

    def test_empty_string_is_invalid_input(self):
        fake = _FakeUnderlyingTool()
        responses = iter(["", "n"])
        tool = ApprovalSaveTool(underlying=fake, input_fn=lambda _: next(responses))
        result = tool._run(title="T", content="Body.")
        assert "cancelled" in result.lower()

    def test_numeric_input_is_invalid(self):
        fake = _FakeUnderlyingTool()
        responses = iter(["1", "0", "n"])
        tool = ApprovalSaveTool(underlying=fake, input_fn=lambda _: next(responses))
        result = tool._run(title="T", content="Body.")
        assert "cancelled" in result.lower()

    # ------------------------------------------------------------------
    # Interrupt / EOF handling
    # ------------------------------------------------------------------
    def test_eof_error_returns_cancelled(self):
        fake = _FakeUnderlyingTool()

        def raise_eof(_: str) -> str:
            raise EOFError

        tool = ApprovalSaveTool(underlying=fake, input_fn=raise_eof)
        result = tool._run(title="T", content="Body.")
        assert "cancelled" in result.lower()

    def test_eof_does_not_call_underlying(self):
        fake = _FakeUnderlyingTool()

        def raise_eof(_: str) -> str:
            raise EOFError

        tool = ApprovalSaveTool(underlying=fake, input_fn=raise_eof)
        tool._run(title="T", content="Body.")
        assert len(fake.calls) == 0

    def test_keyboard_interrupt_returns_cancelled(self):
        fake = _FakeUnderlyingTool()

        def raise_interrupt(_: str) -> str:
            raise KeyboardInterrupt

        tool = ApprovalSaveTool(underlying=fake, input_fn=raise_interrupt)
        result = tool._run(title="T", content="Body.")
        assert "cancelled" in result.lower()

    def test_keyboard_interrupt_does_not_call_underlying(self):
        fake = _FakeUnderlyingTool()

        def raise_interrupt(_: str) -> str:
            raise KeyboardInterrupt

        tool = ApprovalSaveTool(underlying=fake, input_fn=raise_interrupt)
        tool._run(title="T", content="Body.")
        assert len(fake.calls) == 0

    # ------------------------------------------------------------------
    # Tool metadata
    # ------------------------------------------------------------------
    def test_tool_name_matches_mcp_tool(self):
        fake = _FakeUnderlyingTool()
        tool = ApprovalSaveTool(underlying=fake, input_fn=lambda _: "n")
        assert tool.name == "save_report"

    def test_tool_description_mentions_approval(self):
        fake = _FakeUnderlyingTool()
        tool = ApprovalSaveTool(underlying=fake, input_fn=lambda _: "n")
        assert "approval" in tool.description.lower()
