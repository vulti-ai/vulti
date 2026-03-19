"""
Append-only audit event log for Vulti.

Records significant agent actions: inter-agent messages, cron executions,
rule triggers, tool calls, and connection usage. Events are stored as JSONL
at ``~/.vulti/audit/events.jsonl``.

Each event carries a ``trace_id`` that propagates through multi-agent flows,
enabling end-to-end request tracing.

Usage::

    from orchestrator.audit import emit

    emit("interagent_send", agent_id="scout", details={
        "target": "researcher", "message_preview": "..."
    })
"""

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_VULTI_HOME = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))
_AUDIT_DIR = _VULTI_HOME / "audit"
_EVENTS_FILE = _AUDIT_DIR / "events.jsonl"

_write_lock = threading.Lock()

# Thread-local trace context
_trace_local = threading.local()


# ── Trace ID management ──────────────────────────────────────────────

def new_trace_id() -> str:
    """Generate a new trace ID (short UUID prefix for readability)."""
    return uuid.uuid4().hex[:12]


def current_trace_id() -> Optional[str]:
    """Return the active trace ID for this thread, if any."""
    return getattr(_trace_local, "trace_id", None)


def set_trace_id(trace_id: str) -> None:
    """Set the trace ID for the current thread."""
    _trace_local.trace_id = trace_id
    os.environ["VULTI_TRACE_ID"] = trace_id


def clear_trace_id() -> None:
    """Clear the trace ID for the current thread."""
    _trace_local.trace_id = None
    os.environ.pop("VULTI_TRACE_ID", None)


# ── Event emission ───────────────────────────────────────────────────

def emit(
    event_type: str,
    agent_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None,
) -> None:
    """Append an audit event to the log.

    Args:
        event_type: Category of event (e.g. ``interagent_send``,
            ``cron_execute``, ``rule_trigger``, ``tool_call``).
        agent_id: The agent that performed or triggered the action.
            Falls back to AgentContext if not provided.
        details: Arbitrary event-specific payload.
        trace_id: Explicit trace ID override.  Falls back to
            thread-local trace context, then to env var.
    """
    if agent_id is None:
        try:
            from orchestrator.agent_context import AgentContext
            agent_id = AgentContext.current_agent_id()
        except Exception:
            agent_id = os.getenv("VULTI_AGENT_ID", "unknown")

    resolved_trace = (
        trace_id
        or current_trace_id()
        or os.getenv("VULTI_TRACE_ID")
    )

    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        "agent_id": agent_id,
        "trace_id": resolved_trace,
    }
    if details:
        event["details"] = details

    _append(event)


def _append(event: dict) -> None:
    """Thread-safe append to the JSONL file."""
    try:
        _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, default=str) + "\n"
        with _write_lock:
            with open(_EVENTS_FILE, "a") as f:
                f.write(line)
    except Exception as exc:
        # Audit must never break the main flow
        logger.debug("Audit write failed: %s", exc)


# ── Query helpers ────────────────────────────────────────────────────

def tail(n: int = 50, agent_id: Optional[str] = None,
         trace_id: Optional[str] = None,
         event_type: Optional[str] = None) -> list:
    """Return the last *n* events, optionally filtered.

    Returns list of dicts, newest last.
    """
    if not _EVENTS_FILE.exists():
        return []

    events = []
    try:
        with open(_EVENTS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if agent_id and ev.get("agent_id") != agent_id:
                    continue
                if trace_id and ev.get("trace_id") != trace_id:
                    continue
                if event_type and ev.get("event") != event_type:
                    continue
                events.append(ev)
    except Exception:
        return []

    return events[-n:]
