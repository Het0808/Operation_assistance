"""
Structured tracer for the Operations Assistant crew.

Writes one JSON line per event to traces/run_<timestamp>.log.
Every event has a timestamp, event type, and type-specific fields.

Event types
-----------
RUN_START       crew run begins
TOOL_CALL       agent calls an MCP tool (input recorded)
TOOL_RESULT     MCP tool returns (output + duration recorded)
AGENT_ACTION    agent produces a thought, plan, or intermediate step
AGENT_FINISH    agent produces its final answer for a task
RUN_END         crew run ends (success or error)
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
_TRACES_DIR = _REPO_ROOT / "traces"
_TRACES_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# RunTracer
# ---------------------------------------------------------------------------
class RunTracer:
    """
    One instance per crew run.
    Call start() before kickoff, stop() in the finally block.
    Use step_callback as the CrewAI step_callback hook.
    """

    def __init__(self, question: str) -> None:
        self._run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._trace_path = _TRACES_DIR / f"run_{self._run_id}.log"
        self._question = question
        self._run_start: datetime | None = None

        # Each open tool call stores its start time here keyed by a
        # (agent, tool_name) pair so duration can be computed on result.
        self._pending_tool_starts: dict[tuple[str, str], datetime] = {}

        # File handler writes JSON lines; stderr handler writes human-readable.
        self._file_handler = logging.FileHandler(self._trace_path, encoding="utf-8")
        self._file_handler.setFormatter(_JsonLineFormatter())

        self._console_handler = logging.StreamHandler(sys.stderr)
        self._console_handler.setFormatter(
            logging.Formatter("%(asctime)s [TRACE] %(message)s", datefmt="%H:%M:%S")
        )

        self._logger = logging.getLogger(f"tracer.{self._run_id}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False
        self._logger.addHandler(self._file_handler)
        self._logger.addHandler(self._console_handler)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------
    @property
    def trace_path(self) -> Path:
        return self._trace_path

    @property
    def run_id(self) -> str:
        return self._run_id

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        self._run_start = datetime.now(timezone.utc)
        self._emit("RUN_START", {
            "run_id": self._run_id,
            "question": self._question,
        })

    def stop(self, *, error: str | None = None) -> None:
        elapsed = None
        if self._run_start:
            elapsed = round(
                (datetime.now(timezone.utc) - self._run_start).total_seconds(), 3
            )
        self._emit("RUN_END", {
            "run_id": self._run_id,
            "elapsed_seconds": elapsed,
            "status": "error" if error else "success",
            "error": error,
        })
        self._file_handler.close()
        self._logger.removeHandler(self._file_handler)
        self._logger.removeHandler(self._console_handler)

    # ------------------------------------------------------------------
    # Tool events — called explicitly from tool wrappers if needed,
    # but also inferred from step_callback when crewai exposes them.
    # ------------------------------------------------------------------
    def log_tool_call(self, agent: str, tool: str, inputs: dict[str, Any]) -> None:
        key = (agent, tool)
        self._pending_tool_starts[key] = datetime.now(timezone.utc)
        self._emit("TOOL_CALL", {
            "agent": agent,
            "tool": tool,
            "inputs": _truncate_dict(inputs, max_value_len=400),
        })

    def log_tool_result(
        self,
        agent: str,
        tool: str,
        output: str,
        *,
        error: bool = False,
    ) -> None:
        key = (agent, tool)
        start = self._pending_tool_starts.pop(key, None)
        duration_ms = None
        if start:
            duration_ms = round(
                (datetime.now(timezone.utc) - start).total_seconds() * 1000
            )
        self._emit("TOOL_RESULT", {
            "agent": agent,
            "tool": tool,
            "duration_ms": duration_ms,
            "error": error,
            "output_preview": output[:500],
        })

    # ------------------------------------------------------------------
    # Agent events
    # ------------------------------------------------------------------
    def log_agent_action(
        self,
        agent: str,
        thought: str | None = None,
        action: str | None = None,
        action_input: Any = None,
    ) -> None:
        self._emit("AGENT_ACTION", {
            "agent": agent,
            "thought": thought[:300] if thought else None,
            "action": action,
            "action_input": str(action_input)[:300] if action_input is not None else None,
        })

    def log_agent_finish(self, agent: str, output: str) -> None:
        self._emit("AGENT_FINISH", {
            "agent": agent,
            "output_preview": output[:500],
        })

    # ------------------------------------------------------------------
    # CrewAI step_callback hook
    # ------------------------------------------------------------------
    def step_callback(self, step_output: Any) -> None:
        """
        Pass this as step_callback=tracer.step_callback in the Crew constructor.
        CrewAI calls it after every agent step with an AgentAction or AgentFinish object.
        We extract what we can; missing attributes are handled gracefully.
        """
        try:
            agent = str(getattr(step_output, "agent", "unknown"))

            # AgentFinish has a 'return_values' dict
            return_values = getattr(step_output, "return_values", None)
            if return_values is not None:
                output = return_values.get("output", str(return_values))
                self.log_agent_finish(agent, output)
                return

            # AgentAction has tool + tool_input + log
            tool = getattr(step_output, "tool", None)
            tool_input = getattr(step_output, "tool_input", None)
            thought = getattr(step_output, "log", None)
            result = getattr(step_output, "result", None)

            if tool:
                inputs = {"input": tool_input} if not isinstance(tool_input, dict) else tool_input
                self.log_tool_call(agent, tool, inputs)
                if result is not None:
                    is_error = str(result).startswith("ERROR:")
                    self.log_tool_result(agent, tool, str(result), error=is_error)
            else:
                self.log_agent_action(
                    agent,
                    thought=str(thought) if thought else None,
                    action=tool,
                    action_input=tool_input,
                )

        except Exception as exc:
            # Callback errors must never abort the crew run
            self._emit("TRACE_ERROR", {
                "detail": str(exc),
                "traceback": traceback.format_exc(limit=3),
            })

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        payload["event"] = event_type
        payload["ts"] = datetime.now(timezone.utc).isoformat()
        # Human-readable console message
        self._logger.info("%s | %s", event_type, _short_summary(event_type, payload))
        # Structured JSON line written by the file handler
        self._logger.debug("__JSON__", extra={"_json_payload": payload})


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------
class _JsonLineFormatter(logging.Formatter):
    """Writes structured JSON lines for DEBUG records tagged with _json_payload."""

    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "_json_payload", None)
        if payload is None:
            return ""
        return json.dumps(payload, ensure_ascii=False, default=str)

    def emit_blank_lines(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _truncate_dict(d: dict[str, Any], max_value_len: int) -> dict[str, Any]:
    return {
        k: (v[:max_value_len] + "…" if isinstance(v, str) and len(v) > max_value_len else v)
        for k, v in d.items()
    }


def _short_summary(event_type: str, payload: dict[str, Any]) -> str:
    if event_type == "TOOL_CALL":
        return f"agent={payload.get('agent')} tool={payload.get('tool')} inputs={payload.get('inputs')}"
    if event_type == "TOOL_RESULT":
        ms = payload.get("duration_ms")
        err = payload.get("error")
        return (
            f"agent={payload.get('agent')} tool={payload.get('tool')} "
            f"duration={ms}ms error={err} preview={payload.get('output_preview','')[:80]!r}"
        )
    if event_type == "AGENT_ACTION":
        return f"agent={payload.get('agent')} action={payload.get('action')} thought={str(payload.get('thought',''))[:80]!r}"
    if event_type == "AGENT_FINISH":
        return f"agent={payload.get('agent')} output={payload.get('output_preview','')[:80]!r}"
    if event_type == "RUN_START":
        return f"run_id={payload.get('run_id')} question={payload.get('question','')[:80]!r}"
    if event_type == "RUN_END":
        return (
            f"run_id={payload.get('run_id')} status={payload.get('status')} "
            f"elapsed={payload.get('elapsed_seconds')}s"
        )
    return str(payload)[:120]
