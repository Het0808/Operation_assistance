"""
Keyword search helpers for the document corpus.
Kept separate so unit tests can call them directly without starting the MCP server.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MAX_RESULTS = 5
EXCERPT_RADIUS = 200  # characters on each side of the first match


@dataclass
class SearchResult:
    source: str
    excerpt: str
    match_count: int


def _safe_excerpt(text: str, query: str, radius: int = EXCERPT_RADIUS) -> str:
    """Return a substring centred on the first case-insensitive match of query."""
    idx = text.lower().find(query.lower())
    if idx == -1:
        return text[:radius * 2].strip()
    start = max(0, idx - radius)
    end = min(len(text), idx + len(query) + radius)
    excerpt = text[start:end].strip()
    if start > 0:
        excerpt = "..." + excerpt
    if end < len(text):
        excerpt = excerpt + "..."
    return excerpt


def search_documents(query: str, documents_dir: str) -> list[SearchResult]:
    """
    Case-insensitive keyword search across all .txt files in documents_dir.
    Returns up to MAX_RESULTS results sorted by descending match count.
    Unreadable files are skipped with a warning.
    """
    results: list[SearchResult] = []
    query_lower = query.lower()

    try:
        entries = os.listdir(documents_dir)
    except OSError as exc:
        raise RuntimeError(f"Cannot read document directory: {exc}") from exc

    for filename in sorted(entries):
        if not filename.endswith(".txt"):
            continue
        filepath = os.path.join(documents_dir, filename)
        try:
            with open(filepath, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            logger.warning("Skipping unreadable file: %s", filename)
            continue

        count = len(re.findall(re.escape(query_lower), text.lower()))
        if count > 0:
            results.append(SearchResult(
                source=filename,
                excerpt=_safe_excerpt(text, query),
                match_count=count,
            ))

    results.sort(key=lambda r: r.match_count, reverse=True)
    return results[:MAX_RESULTS]
