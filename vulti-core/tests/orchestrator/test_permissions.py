"""Tests for orchestrator/permissions.py — permission escalation flow."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.permissions import (
    approve,
    deny,
    list_pending,
    request_permission,
)


@pytest.fixture
def tmp_permissions(tmp_path, monkeypatch):
    """Redirect permissions storage to a temp directory."""
    perm_dir = tmp_path / "permissions"
    monkeypatch.setattr("orchestrator.permissions._PERMISSIONS_DIR", perm_dir)
    monkeypatch.setattr("orchestrator.permissions._PENDING_FILE", perm_dir / "pending.json")
    return perm_dir


class TestRequestPermission:
    def test_creates_pending_request(self, tmp_permissions):
        with patch("orchestrator.permissions._notify_owner"):
            req = request_permission("scout", "github", reason="Need to check PRs")

        assert req["agent_id"] == "scout"
        assert req["connection_name"] == "github"
        assert req["status"] == "pending"
        assert req["reason"] == "Need to check PRs"
        assert len(req["id"]) == 12

    def test_deduplicates_pending_requests(self, tmp_permissions):
        with patch("orchestrator.permissions._notify_owner"):
            req1 = request_permission("scout", "github")
            req2 = request_permission("scout", "github")

        assert req1["id"] == req2["id"]
        assert len(list_pending()) == 1

    def test_different_connections_create_separate_requests(self, tmp_permissions):
        with patch("orchestrator.permissions._notify_owner"):
            request_permission("scout", "github")
            request_permission("scout", "gmail")

        assert len(list_pending()) == 2


class TestListPending:
    def test_filters_by_agent(self, tmp_permissions):
        with patch("orchestrator.permissions._notify_owner"):
            request_permission("scout", "github")
            request_permission("researcher", "gmail")

        assert len(list_pending(agent_id="scout")) == 1
        assert len(list_pending(agent_id="researcher")) == 1
        assert len(list_pending()) == 2

    def test_empty_when_no_requests(self, tmp_permissions):
        assert list_pending() == []


class TestApprove:
    def test_approve_updates_status(self, tmp_permissions):
        with patch("orchestrator.permissions._notify_owner"):
            req = request_permission("scout", "github")

        with patch("orchestrator.permissions._add_to_allow_list") as mock_add:
            result = approve(req["id"])

        assert result["status"] == "approved"
        assert result["resolved_at"] is not None
        mock_add.assert_called_once_with("scout", "github")
        assert len(list_pending()) == 0  # No longer pending

    def test_approve_nonexistent_returns_none(self, tmp_permissions):
        assert approve("nonexistent") is None


class TestDeny:
    def test_deny_updates_status(self, tmp_permissions):
        with patch("orchestrator.permissions._notify_owner"):
            req = request_permission("scout", "github")

        result = deny(req["id"])
        assert result["status"] == "denied"
        assert len(list_pending()) == 0

    def test_deny_nonexistent_returns_none(self, tmp_permissions):
        assert deny("nonexistent") is None


class TestApproveActuallyUpdatesAllowList:
    def test_add_to_allow_list_calls_registry(self, tmp_permissions):
        mock_meta = MagicMock()
        mock_meta.allowed_connections = ["existing"]

        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = mock_meta

        with patch("vulti_cli.agent_registry.AgentRegistry", return_value=mock_registry):
            from orchestrator.permissions import _add_to_allow_list
            _add_to_allow_list("scout", "github")

        mock_registry.update_agent.assert_called_once_with(
            "scout", {"allowed_connections": ["existing", "github"]}
        )
