"""
Prompt injection detection and sanitization for the document corpus.

Documents are read from disk and passed through LLMs via tool outputs.
Any text that looks like a directive to the model — rather than factual
business content — is flagged, logged, and redacted from excerpts before
they reach an agent.

Risk levels
-----------
HIGH    Unambiguous LLM manipulation: instruction overrides, role hijacks,
        anti-grounding commands, destructive directives.
MEDIUM  Suspicious phrasing that could be legitimate in some business
        contexts (e.g. "act as" in a training document).
SAFE    No patterns matched.

The guard never raises — it always returns a result. Errors in pattern
matching are caught and logged; the document is returned as SAFE rather
than crashing the search.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pattern registry
# Each entry: (compiled regex, human-readable description, risk level)
# ---------------------------------------------------------------------------

class _Pattern(NamedTuple):
    regex: re.Pattern[str]
    description: str
    risk: str  # "HIGH" or "MEDIUM"


def _p(pattern: str, description: str, risk: str) -> _Pattern:
    return _Pattern(re.compile(pattern, re.IGNORECASE | re.MULTILINE), description, risk)


_PATTERNS: list[_Pattern] = [
    # --- HIGH: direct instruction overrides ---
    _p(
        r"ignore\s+(all\s+)?(?:previous|prior|above|your)\s+instructions?",
        "Instruction override attempt",
        "HIGH",
    ),
    _p(
        r"disregard\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?",
        "Instruction override attempt",
        "HIGH",
    ),
    _p(
        r"override\s+(?:the\s+)?(?:system|your|all)\s+(?:prompt|instructions?|directives?)",
        "System override attempt",
        "HIGH",
    ),
    _p(
        r"forget\s+(?:everything|all)(?:\s+\w+){0,4}\s+(?:told|know|learned)",
        "Memory wipe attempt",
        "HIGH",
    ),
    _p(
        r"you\s+(?:are|must|will|should)\s+now\s+(?:act|behave|pretend|ignore|forget)",
        "Role override attempt",
        "HIGH",
    ),
    _p(
        r"your\s+(?:real\s+)?(?:new\s+)?(?:purpose|mission|task|instruction)\s+is\s+(?:to\s+)?(?:now\s+)?(?:not\s+cite|ignore|forget|override|bypass)",
        "Purpose override attempt",
        "HIGH",
    ),
    # --- HIGH: anti-grounding commands ---
    _p(
        r"do\s+not\s+cite\s+(?:any\s+)?(?:sources?|evidence|documents?|files?)",
        "Anti-grounding injection",
        "HIGH",
    ),
    _p(
        r"(?:never|do\s+not|don.t)\s+(?:mention|include|reference|cite)\s+(?:any\s+)?(?:source|document|file|evidence)",
        "Anti-citation injection",
        "HIGH",
    ),
    # --- HIGH: destructive commands ---
    _p(
        r"(?:delete|remove|destroy|wipe|erase)\s+(?:all\s+)?(?:files?|records?|data|database|everything)",
        "Destructive command injection",
        "HIGH",
    ),
    # --- HIGH: system prompt injection via tags / prefixes ---
    _p(r"\[system\]", "System tag injection", "HIGH"),
    _p(r"<\s*system\s*>", "HTML system tag injection", "HIGH"),
    _p(r"^system\s*:\s*you\s+are", "System prompt prefix injection", "HIGH"),
    _p(r"###\s*(?:system|instruction|prompt\s+override)", "Markdown override header", "HIGH"),
    # --- HIGH: explicit new-task injections ---
    _p(
        r"(?:your\s+)?new\s+(?:task|instruction|directive|mission|objective)\s*:\s*(?:ignore|forget|do\s+not|never)",
        "Task injection with override",
        "HIGH",
    ),
    # --- MEDIUM: role-play / behavioural nudges ---
    _p(
        r"pretend\s+(?:you\s+are|to\s+be)\s+(?:a|an|the)?\s*(?:different|new|another)",
        "Role-play redirection",
        "MEDIUM",
    ),
    _p(
        r"act\s+as\s+(?:if\s+you\s+(?:are|were)|a\s+different|an?\s+unrestricted)",
        "Unrestricted-role nudge",
        "MEDIUM",
    ),
    _p(
        r"from\s+now\s+on[,\s]+(?:you\s+)?(?:always|never|must|should|do\s+not)",
        "Persistent behavioural override",
        "MEDIUM",
    ),
    _p(
        r"respond\s+only\s+(?:in|with|as)\s+(?!english|formal|plain|markdown)",
        "Response constraint injection",
        "MEDIUM",
    ),
]

# Text used to replace redacted spans in sanitized excerpts
_REDACTION_MARKER = "[REDACTED: potential injection pattern]"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class InjectionFinding:
    description: str   # human-readable pattern name
    matched_text: str  # the actual matched substring (truncated to 120 chars)
    position: int      # character offset in the original text
    risk: str          # "HIGH" or "MEDIUM"


@dataclass
class InjectionCheckResult:
    document: str
    risk_level: str                            # "SAFE", "MEDIUM", or "HIGH"
    findings: list[InjectionFinding] = field(default_factory=list)
    sanitized_text: str = ""                   # text with injection spans replaced

    @property
    def is_safe(self) -> bool:
        return self.risk_level == "SAFE"

    @property
    def metadata(self) -> dict:
        if self.is_safe:
            return {
                "document": self.document,
                "risk": "SAFE",
                "reason": "No injection patterns detected",
            }
        reasons = "; ".join(
            f.description for f in self.findings[:3]
        )
        return {
            "document": self.document,
            "risk": self.risk_level,
            "reason": f"Prompt injection pattern detected: {reasons}",
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_document(filename: str, text: str) -> InjectionCheckResult:
    """
    Scan *text* for prompt injection patterns.
    Returns an InjectionCheckResult with risk level, findings, and
    sanitized text (injection spans replaced with _REDACTION_MARKER).

    Never raises — errors produce a SAFE result with a logged warning.
    """
    try:
        return _check(filename, text)
    except Exception as exc:
        logger.warning(
            "injection_guard: error scanning %s (treating as SAFE): %s",
            filename,
            exc,
        )
        return InjectionCheckResult(
            document=filename,
            risk_level="SAFE",
            sanitized_text=text,
        )


def sanitize_excerpt(text: str) -> str:
    """
    Replace all injection-pattern spans in *text* with _REDACTION_MARKER.
    Safe to call on any string; never raises.
    """
    try:
        return _redact(text)
    except Exception:
        return text


# ---------------------------------------------------------------------------
# Internal implementation
# ---------------------------------------------------------------------------

def _check(filename: str, text: str) -> InjectionCheckResult:
    findings: list[InjectionFinding] = []

    for pat in _PATTERNS:
        for m in pat.regex.finditer(text):
            findings.append(
                InjectionFinding(
                    description=pat.description,
                    matched_text=m.group()[:120],
                    position=m.start(),
                    risk=pat.risk,
                )
            )

    if not findings:
        return InjectionCheckResult(
            document=filename,
            risk_level="SAFE",
            sanitized_text=text,
        )

    risk_level = "HIGH" if any(f.risk == "HIGH" for f in findings) else "MEDIUM"

    logger.warning(
        "INJECTION GUARD | document=%s | risk=%s | findings=%d | patterns=%s",
        filename,
        risk_level,
        len(findings),
        [f.description for f in findings],
    )

    return InjectionCheckResult(
        document=filename,
        risk_level=risk_level,
        findings=findings,
        sanitized_text=_redact(text),
    )


def _redact(text: str) -> str:
    """Replace every injection-pattern match with the redaction marker."""
    result = text
    # Process patterns in reverse position order so offsets stay valid
    # after substitution — but since we process the full string with re.sub,
    # order of pattern application does not matter.
    for pat in _PATTERNS:
        result = pat.regex.sub(_REDACTION_MARKER, result)
    return result
