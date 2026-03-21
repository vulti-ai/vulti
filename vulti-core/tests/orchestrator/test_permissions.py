"""Tests for orchestrator/permissions.py — per-agent permission management."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.permissions import (
    add_allowed_connection,
    approve,
    deny,
    get_allowed_connections,
    list_pending,
    remove_allowed_connection,
    request_permission,
    set_allowed_connections,
)


@pytest.fixture
def tmp_vulti_home(tmp_path, monkeypatch):
    """Redirect VULTI_HOME so per-agent files go to a temp directory."""
    monkeypatch.setenv("VULTI_HOME", str(tmp_path))
    # Create agent directories
    for agent_id in ("scout", "researcher", "default"):
        (tmp_path / "agents" / agent_id).mkdir(parents=True, exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Allowed connections
# ---------------------------------------------------------------------------

class TestAllowedConnections:
    def test_empty_by_default(self, tmp_vulti_home):
        assert get_allowed_connections("scout") == []

    def test_set_and_get(self, tmp_vulti_home):
        set_allowed_connections("scout", ["github", "gmail"])
        assert get_allowed_connections("scout") == ["github", "gmail"]

    def test_add_connection(self, tmp_vulti_home):
        add_allowed_connection("scout", "github")
        add_allowed_connection("scout", "gmail")
        assert get_allowed_connections("scout") == ["github", "gmail"]

    def test_add_is_idempotent(self, tmp_vulti_home):
        add_allowed_connection("scout", "github")
        add_allowed_connection("scout", "github")
        assert get_allowed_connections("scout") == ["github"]

    def test_remove_connection(self, tmp_vulti_home):
        set_allowed_connections("scout", ["github", "gmail"])
        remove_allowed_connection("scout", "github")
        assert get_allowed_connections("scout") == ["gmail"]

    def test_remove_nonexistent_is_noop(self, tmp_vulti_home):
        set_allowed_connections("scout", ["github"])
        remove_allowed_connection("scout", "slack")
        assert get_allowed_connections("scout") == ["github"]

    def test_agents_are_isolated(self, tmp_vulti_home):
        set_allowed_connections("scout", ["github"])
        set_allowed_connections("researcher", ["gmail"])
        assert get_allowed_connections("scout") == ["github"]
        assert get_allowed_connections("researcher") == ["gmail"]


# ---------------------------------------------------------------------------
# Permission requests
# ---------------------------------------------------------------------------

class TestRequestPermission:
    def test_creates_pending_request(self, tmp_vulti_home):
        with patch("orchestrator.permissions._notify_owner"):
            req = request_permission("scout", "github", reason="Need to check PRs")

        assert req["connection_name"] == "github"
        assert req["status"] == "pending"
        assert req["reason"] == "Need to check PRs"
        assert len(req["id"]) == 12

    def test_deduplicates_pending_requests(self, tmp_vulti_home):
        with patch("orchestrator.permissions._notify_owner"):
            req1 = request_permission("scout", "github")
            req2 = request_permission("scout", "github")

        assert req1["id"] == req2["id"]
        assert len(list_pending(agent_id="scout")) == 1

    def test_different_connections_create_separate_requests(self, tmp_vulti_home):
        with patch("orchestrator.permissions._notify_owner"):
            request_permission("scout", "github")
            request_permission("scout", "gmail")

        assert len(list_pending(agent_id="scout")) == 2


class TestListPending:
    def test_filters_by_agent(self, tmp_vulti_home):
        with patch("orchestrator.permissions._notify_owner"):
            request_permission("scout", "github")
            request_permission("researcher", "gmail")

        assert len(list_pending(agent_id="scout")) == 1
        assert len(list_pending(agent_id="researcher")) == 1

    def test_empty_when_no_requests(self, tmp_vulti_home):
        assert list_pending(agent_id="scout") == []


class TestApprove:
    def test_approve_updates_status_and_adds_connection(self, tmp_vulti_home):
        with patch("orchestrator.permissions._notify_owner"):
            req = request_permission("scout", "github")

        result = approve(req["id"], agent_id="scout")

        assert result["status"] == "approved"
        assert result["resolved_at"] is not None
        # Connection should now be in allowed list
        assert "github" in get_allowed_connections("scout")
        # No longer pending
        assert len(list_pending(agent_id="scout")) == 0

    def test_approve_nonexistent_returns_none(self, tmp_vulti_home):
        assert approve("nonexistent", agent_id="scout") is None


class TestDeny:
    def test_deny_updates_status(self, tmp_vulti_home):
        with patch("orchestrator.permissions._notify_owner"):
            req = request_permission("scout", "github")

        result = deny(req["id"], agent_id="scout")
        assert result["status"] == "denied"
        assert len(list_pending(agent_id="scout")) == 0
        # Should NOT add to allowed list
        assert "github" not in get_allowed_connections("scout")

    def test_deny_nonexistent_returns_none(self, tmp_vulti_home):
        assert deny("nonexistent", agent_id="scout") is None


# ---------------------------------------------------------------------------
# File isolation
# ---------------------------------------------------------------------------

class TestFileIsolation:
    def test_permissions_stored_in_agent_directory(self, tmp_vulti_home):
        set_allowed_connections("scout", ["github"])
        perm_file = tmp_vulti_home / "agents" / "scout" / "permissions.json"
        assert perm_file.exists()
        data = json.loads(perm_file.read_text())
        assert data["allowed_connections"] == ["github"]

    def test_no_global_permissions_file(self, tmp_vulti_home):
        set_allowed_connections("scout", ["github"])
        with patch("orchestrator.permissions._notify_owner"):
            request_permission("scout", "slack")
        # Old global path should NOT exist
        assert not (tmp_vulti_home / "permissions" / "pending.json").exists()
