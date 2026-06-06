"""
Operations Assistant MCP Server.
Exposes three tools over local data:
  - search_documents(query)
  - read_record(order_id)
  - save_report(title, content)
And one resource:
  - list_documents
"""

from __future__ import annotations

import csv
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, field_validator

from search_utils import search_documents as _search_documents

# ---------------------------------------------------------------------------
# Paths — all hardcoded; callers cannot influence file locations
# ---------------------------------------------------------------------------
_SERVER_DIR = Path(__file__).parent
_REPO_ROOT = _SERVER_DIR.parent
_DOCUMENTS_DIR = _REPO_ROOT / "data" / "documents"
_RECORDS_CSV = _REPO_ROOT / "data" / "records.csv"
_REPORTS_DIR = _REPO_ROOT / "outputs" / "reports"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mcp_server")

# ---------------------------------------------------------------------------
# Startup checks
# ---------------------------------------------------------------------------
def _startup_checks() -> None:
    if not _DOCUMENTS_DIR.is_dir():
        logger.error("Document directory not found: %s", _DOCUMENTS_DIR)
        sys.exit(1)
    if not _RECORDS_CSV.is_file():
        logger.error("Records CSV not found: %s", _RECORDS_CSV)
        sys.exit(1)
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Startup checks passed. Server ready.")

_startup_checks()

# ---------------------------------------------------------------------------
# FastMCP app
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="operations-assistant",
    instructions=(
        "You are connected to an operations data store. "
        "Always cite the source document filename or record ID for every fact you use. "
        "If a tool returns no results, state that no evidence was found — do not invent an answer."
    ),
)

# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------

class SearchInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)

    @field_validator("query", mode="before")
    @classmethod
    def strip_and_check(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query must not be empty after stripping whitespace.")
        if any(ord(c) < 32 for c in v):
            raise ValueError("query contains invalid control characters.")
        return v


class ReadRecordInput(BaseModel):
    order_id: str = Field(..., pattern=r"^ORD-\d{5}$")

    @field_validator("order_id", mode="before")
    @classmethod
    def strip_id(cls, v: str) -> str:
        return v.strip()


class SaveReportInput(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=10_000)

    @field_validator("title", "content", mode="before")
    @classmethod
    def strip_fields(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Field must not be empty after stripping whitespace.")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert a title to a safe filename slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text.strip("_")[:60]


def _unique_report_path(slug: str) -> Path:
    """Return a path that does not already exist, appending _1, _2, … if needed."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = _REPORTS_DIR / f"{timestamp}_{slug}.md"
    if not base.exists():
        return base
    counter = 1
    while True:
        candidate = _REPORTS_DIR / f"{timestamp}_{slug}_{counter}.md"
        if not candidate.exists():
            return candidate
        counter += 1


# ---------------------------------------------------------------------------
# Tool: search_documents
# ---------------------------------------------------------------------------

@mcp.tool()
def search_documents(query: str) -> str:
    """
    Search the operations document corpus for a keyword or phrase.
    Returns up to 5 ranked excerpts with source filenames.
    Cite the source filename for every fact you use from this result.
    """
    try:
        validated = SearchInput(query=query)
    except Exception as exc:
        return f"ERROR: {_first_error(exc)}"

    try:
        results = _search_documents(validated.query, str(_DOCUMENTS_DIR))
    except RuntimeError as exc:
        logger.error("Document search failed: %s", exc)
        return "ERROR: document store is unavailable. Contact the system administrator."

    if not results:
        return (
            f'SEARCH RESULTS FOR: "{validated.query}"\n'
            "No documents matched this query. "
            "Do not invent an answer. State that no evidence was found."
        )

    lines = [f'SEARCH RESULTS FOR: "{validated.query}"', f"Found in {len(results)} document(s).", ""]
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] Source: {r.source} ({r.match_count} match(es))")
        lines.append(f"    Excerpt: \"{r.excerpt}\"")
        lines.append("")

    lines.append(
        "INSTRUCTION: Cite the source filename in your answer for every fact you use."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: read_record
# ---------------------------------------------------------------------------

@mcp.tool()
def read_record(order_id: str) -> str:
    """
    Retrieve a single order record from records.csv by its order_id (format: ORD-XXXXX).
    Cite 'records.csv, order <order_id>' as the source for any fact from this record.
    """
    try:
        validated = ReadRecordInput(order_id=order_id)
    except Exception as exc:
        return (
            f"ERROR: order_id format is invalid. {_first_error(exc)} "
            "Expected format: ORD-XXXXX (e.g. ORD-01201)."
        )

    try:
        with open(_RECORDS_CSV, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            rows = [row for row in reader if row.get("order_id") == validated.order_id]
    except OSError as exc:
        logger.error("Cannot read records CSV: %s", exc)
        return "ERROR: records store is unavailable. Contact the system administrator."

    if not rows:
        return (
            f"RECORD NOT FOUND: {validated.order_id}\n"
            "No order with this ID exists in records. "
            "Do not invent details. State that no record was found."
        )

    if len(rows) > 1:
        logger.warning("Duplicate order_id %s found; returning first row.", validated.order_id)

    row = rows[0]
    lines = [f"RECORD: {validated.order_id}"]
    for key, value in row.items():
        if key == "order_id":
            continue
        display_value = value if value else "(empty)"
        if key in ("unit_price", "order_total"):
            try:
                display_value = f"${float(value):.2f}"
            except (ValueError, TypeError):
                pass
        lines.append(f"  {key:<20}: {display_value}")

    lines.append("")
    lines.append(
        f'INSTRUCTION: Cite "records.csv, order {validated.order_id}" '
        "as the source for any fact from this record."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: save_report
# ---------------------------------------------------------------------------

@mcp.tool()
def save_report(title: str, content: str) -> str:
    """
    Write a markdown report to outputs/reports/.
    Returns the saved filename so it can be cited in your response.
    Only call this when the report is complete and ready to save.
    """
    try:
        validated = SaveReportInput(title=title, content=content)
    except Exception as exc:
        return f"ERROR: {_first_error(exc)}"

    slug = _slugify(validated.title)
    if not slug:
        return "ERROR: title contains invalid characters that cannot be used in a filename."

    report_path = _unique_report_path(slug)

    # Paranoia check: confirm final path is strictly inside _REPORTS_DIR
    try:
        report_path.relative_to(_REPORTS_DIR)
    except ValueError:
        logger.error("Path traversal attempt blocked: %s", report_path)
        return "ERROR: title contains invalid characters that cannot be used in a filename."

    markdown = f"# {validated.title}\n\n{validated.content}\n"
    saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        report_path.write_text(markdown, encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to write report: %s", exc)
        return "ERROR: Report could not be saved due to a file system error. Contact the system administrator."

    display_path = Path("outputs") / "reports" / report_path.name
    return (
        f"REPORT SAVED: {display_path}\n"
        f"Title   : {validated.title}\n"
        f"Length  : {len(markdown)} characters\n"
        f"Saved at: {saved_at}"
    )


# ---------------------------------------------------------------------------
# Resource: list_documents
# ---------------------------------------------------------------------------

@mcp.resource("ops://documents/list")
def list_documents() -> str:
    """List all document filenames available in the operations knowledge base."""
    try:
        files = sorted(
            f for f in os.listdir(_DOCUMENTS_DIR) if f.endswith(".txt")
        )
    except OSError as exc:
        logger.error("Cannot list documents: %s", exc)
        return "ERROR: document store is unavailable."

    if not files:
        return "No documents found in the knowledge base."

    lines = ["AVAILABLE DOCUMENTS:", ""]
    for f in files:
        lines.append(f"  - {f}")
    lines.append("")
    lines.append(f"Total: {len(files)} document(s).")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_error(exc: Exception) -> str:
    """Extract a clean first-error message from a Pydantic ValidationError or plain Exception."""
    try:
        # Pydantic v2 ValidationError
        errors = exc.errors()  # type: ignore[attr-defined]
        return errors[0]["msg"] if errors else str(exc)
    except AttributeError:
        return str(exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
