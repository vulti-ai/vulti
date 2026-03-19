"""Tests for orchestrator/audit.py — event log and trace IDs."""

import json
import os
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.audit import (
    _EVENTS_FILE,
    clear_trace_id,
    current_trace_id,
    emit,
    new_trace_id,
    set_trace_id,
    tail,
)


@pytest.fixture
def tmp_audit_dir(tmp_path, monkeypatch):
    """Redirect audit log to a temp directory."""
    audit_dir = tmp_path / "audit"
    events_file = audit_dir / "events.jsonl"
    monkeypatch.setattr("orchestrator.audit._AUDIT_DIR", audit_dir)
    monkeypatch.setattr("orchestrator.audit._EVENTS_FILE", events_file)
    return events_file


class TestTraceId:
    def test_new_trace_id_is_12_hex_chars(self):
        tid = new_trace_id()
        assert len(tid) == 12
        assert all(c in "0123456789abcdef" for c in tid)

    def test_set_and_get_trace_id(self):
        set_trace_id("abc123")
        assert current_trace_id() == "abc123"
        assert os.environ.get("VULTI_TRACE_ID") == "abc123"
        clear_trace_id()
        assert current_trace_id() is None
        assert "VULTI_TRACE_ID" not in os.environ

    def test_trace_id_is_thread_local(self):
        set_trace_id("main-thread")
        results = {}

        def worker():
            results["before"] = current_trace_id()
            set_trace_id("worker-thread")
            results["after"] = current_trace_id()

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        # Main thread trace should be unaffected
        assert current_trace_id() == "main-thread"
        # Worker should have had no trace initially (env var leaks but thread-local doesn't)
        assert results["after"] == "worker-thread"
        clear_trace_id()


class TestEmit:
    def test_emit_creates_file_and_appends(self, tmp_audit_dir):
        emit("test_event", agent_id="scout", details={"key": "val"}, trace_id="t1")
        emit("test_event2", agent_id="scout", trace_id="t1")

        lines = tmp_audit_dir.read_text().strip().split("\n")
        assert len(lines) == 2

        ev1 = json.loads(lines[0])
        assert ev1["event"] == "test_event"
        assert ev1["agent_id"] == "scout"
        assert ev1["trace_id"] == "t1"
        assert ev1["details"] == {"key": "val"}
        assert "ts" in ev1

        ev2 = json.loads(lines[1])
        assert ev2["event"] == "test_event2"
        assert "details" not in ev2  # No details provided

    def test_emit_uses_thread_local_trace(self, tmp_audit_dir):
        set_trace_id("implicit-trace")
        emit("test", agent_id="a")
        clear_trace_id()

        ev = json.loads(tmp_audit_dir.read_text().strip())
        assert ev["trace_id"] == "implicit-trace"

    def test_emit_falls_back_to_env_agent_id(self, tmp_audit_dir, monkeypatch):
        monkeypatch.setenv("VULTI_AGENT_ID", "env-agent")
        # Patch AgentContext at the source module so the lazy import picks it up
        with patch("orchestrator.agent_context.AgentContext") as mock_ctx:
            mock_ctx.current_agent_id.side_effect = Exception("no context")
            emit("test", trace_id="t1")

        ev = json.loads(tmp_audit_dir.read_text().strip())
        assert ev["agent_id"] == "env-agent"


class TestTail:
    def test_tail_returns_last_n(self, tmp_audit_dir):
        for i in range(10):
            emit(f"event_{i}", agent_id="a", trace_id="t")

        events = tail(n=3)
        assert len(events) == 3
        assert events[0]["event"] == "event_7"
        assert events[2]["event"] == "event_9"

    def test_tail_filters_by_agent(self, tmp_audit_dir):
        emit("e1", agent_id="scout", trace_id="t")
        emit("e2", agent_id="researcher", trace_id="t")
        emit("e3", agent_id="scout", trace_id="t")

        events = tail(agent_id="scout")
        assert len(events) == 2
        assert all(e["agent_id"] == "scout" for e in events)

    def test_tail_filters_by_trace(self, tmp_audit_dir):
        emit("e1", agent_id="a", trace_id="trace-1")
        emit("e2", agent_id="a", trace_id="trace-2")
        emit("e3", agent_id="a", trace_id="trace-1")

        events = tail(trace_id="trace-1")
        assert len(events) == 2

    def test_tail_filters_by_event_type(self, tmp_audit_dir):
        emit("interagent_send", agent_id="a", trace_id="t")
        emit("cron_execute", agent_id="a", trace_id="t")
        emit("interagent_send", agent_id="a", trace_id="t")

        events = tail(event_type="cron_execute")
        assert len(events) == 1

    def test_tail_empty_log(self, tmp_audit_dir):
        assert tail() == []
