"""
Human approval gate for save_report.

ApprovalSaveTool wraps the MCP save_report tool and requires explicit
human approval (y/n) before any file is written.

The input function is injectable so tests can drive the gate without
touching builtins or stdin.
"""

from __future__ import annotations

import builtins
import json
from typing import Any, Callable, Type

from pydantic import BaseModel, Field, PrivateAttr

try:
    from crewai.tools import BaseTool
    _CREWAI_AVAILABLE = True
except ImportError:  # allow import in unit-test environment without crewai
    BaseTool = object  # type: ignore[assignment,misc]
    _CREWAI_AVAILABLE = False


# ---------------------------------------------------------------------------
# Input schema — mirrors the MCP save_report schema exactly
# ---------------------------------------------------------------------------
class _SaveInput(BaseModel):
    title: str = Field(..., description="Title for the report.")
    content: str = Field(..., description="Full markdown body of the report.")


# ---------------------------------------------------------------------------
# ApprovalSaveTool
# ---------------------------------------------------------------------------
class ApprovalSaveTool(BaseTool):  # type: ignore[misc]
    """
    Wraps the MCP save_report tool with a human approval gate.

    Before writing anything to disk the tool displays the report title and
    a five-line preview, then prompts the operator:

        Approve report? (y/n):

    Behaviour:
      y           → delegates to the underlying MCP save_report and returns its result
      n           → returns "Report save cancelled." without writing
      anything else → prints a hint and re-prompts (loops until valid input)
      EOF / Ctrl-C  → treated as 'n'; returns "Report save cancelled."
    """

    name: str = "save_report"
    description: str = (
        "Save a verified report to disk. "
        "Requires human approval before writing. "
        "Inputs: title (str), content (str markdown)."
    )
    args_schema: Type[BaseModel] = _SaveInput

    # Private — not part of the Pydantic model schema
    _underlying: Any = PrivateAttr()
    _input_fn: Callable[[str], str] = PrivateAttr()

    def __init__(
        self,
        underlying: Any,
        input_fn: Callable[[str], str] = builtins.input,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._underlying = underlying
        self._input_fn = input_fn

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------
    def _run(self, title: str, content: str) -> str:
        _print_approval_banner(title, content)

        while True:
            try:
                raw = self._input_fn("Approve report? (y/n): ")
            except (EOFError, KeyboardInterrupt):
                print("\nApproval interrupted. Report save cancelled.")
                return "Report save cancelled."

            response = raw.strip().lower()

            if response == "y":
                return _call_underlying(self._underlying, title, content)

            if response == "n":
                print("Report save cancelled by operator.")
                return "Report save cancelled."

            # Invalid input — re-prompt without looping forever
            print(
                f"Invalid response {raw!r}. "
                "Please enter 'y' to approve or 'n' to cancel."
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_PREVIEW_LINES = 5
_BANNER_WIDTH = 62


def _print_approval_banner(title: str, content: str) -> None:
    lines = content.splitlines()
    preview = "\n".join(lines[:_PREVIEW_LINES])
    if len(lines) > _PREVIEW_LINES:
        preview += f"\n... ({len(lines) - _PREVIEW_LINES} more lines)"

    print(f"\n{'=' * _BANNER_WIDTH}")
    print("  HUMAN APPROVAL REQUIRED")
    print(f"{'=' * _BANNER_WIDTH}")
    print(f"  Title   : {title}")
    print(f"  Lines   : {len(lines)}")
    print(f"{'─' * _BANNER_WIDTH}")
    print(preview)
    print(f"{'=' * _BANNER_WIDTH}")


def _call_underlying(tool: Any, title: str, content: str) -> str:
    """
    Call the underlying MCP save_report tool.
    CrewAI MCP tool adapters expose a .run() method that accepts either
    a JSON string or a plain dict; we try the dict form first.
    """
    try:
        # Most crewai-tools BaseTool subclasses accept a dict directly
        return tool.run({"title": title, "content": content})
    except Exception:
        pass
    try:
        # Fallback: JSON string (some adapter versions expect this)
        return tool.run(json.dumps({"title": title, "content": content}))
    except Exception:
        pass
    # Last resort: call _run directly
    return tool._run(title=title, content=content)
