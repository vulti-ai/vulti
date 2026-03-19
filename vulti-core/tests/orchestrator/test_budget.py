"""Tests for orchestrator/budget.py — per-agent cost/token budgets."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.budget import (
    _today_key,
    check_budget,
    get_budget_status,
    record_usage,
)


@pytest.fixture
def tmp_vulti(tmp_path, monkeypatch):
    """Redirect VULTI_HOME to a temp directory with an agent."""
    monkeypatch.setattr("orchestrator.budget._VULTI_HOME", tmp_path)
    agent_dir = tmp_path / "agents" / "scout"
    agent_dir.mkdir(parents=True)
    return tmp_path


class TestCheckBudget:
    def test_no_budget_returns_none(self, tmp_vulti):
        with patch("orchestrator.budget._load_budget_config", return_value={}):
            assert check_budget("scout") is None

    def test_under_cost_budget_returns_none(self, tmp_vulti):
        with patch("orchestrator.budget._load_budget_config",
                    return_value={"max_cost_per_day": 10.0}):
            assert check_budget("scout") is None

    def test_over_cost_budget_returns_error(self, tmp_vulti):
        # Write usage that exceeds budget
        usage = {"date": _today_key(), "input_tokens": 0, "output_tokens": 0, "cost_usd": 11.0}
        usage_path = tmp_vulti / "agents" / "scout" / "budget_usage.json"
        usage_path.write_text(json.dumps(usage))

        with patch("orchestrator.budget._load_budget_config",
                    return_value={"max_cost_per_day": 10.0}):
            result = check_budget("scout")
            assert result is not None
            assert "exceeded" in result
            assert "$10.00" in result

    def test_over_token_budget_returns_error(self, tmp_vulti):
        usage = {"date": _today_key(), "input_tokens": 300000, "output_tokens": 200001, "cost_usd": 0}
        usage_path = tmp_vulti / "agents" / "scout" / "budget_usage.json"
        usage_path.write_text(json.dumps(usage))

        with patch("orchestrator.budget._load_budget_config",
                    return_value={"max_tokens_per_day": 500000}):
            result = check_budget("scout")
            assert result is not None
            assert "exceeded" in result
            assert "500,000" in result

    def test_stale_date_resets_counters(self, tmp_vulti):
        usage = {"date": "1999-01-01", "input_tokens": 999999, "output_tokens": 999999, "cost_usd": 999}
        usage_path = tmp_vulti / "agents" / "scout" / "budget_usage.json"
        usage_path.write_text(json.dumps(usage))

        with patch("orchestrator.budget._load_budget_config",
                    return_value={"max_cost_per_day": 10.0}):
            # Should not be exceeded because date is stale = reset
            assert check_budget("scout") is None


class TestRecordUsage:
    def test_records_tokens(self, tmp_vulti):
        with patch("orchestrator.budget._load_budget_config", return_value={}):
            record_usage("scout", 1000, 500)
            record_usage("scout", 2000, 1000)

        usage_path = tmp_vulti / "agents" / "scout" / "budget_usage.json"
        data = json.loads(usage_path.read_text())
        assert data["input_tokens"] == 3000
        assert data["output_tokens"] == 1500
        assert data["date"] == _today_key()


class TestGetBudgetStatus:
    def test_status_with_no_budget(self, tmp_vulti):
        with patch("orchestrator.budget._load_budget_config", return_value={}):
            status = get_budget_status("scout")
            assert status["agent_id"] == "scout"
            assert status["tokens_used"] == 0
            assert "note" in status

    def test_status_with_budget(self, tmp_vulti):
        usage = {"date": _today_key(), "input_tokens": 5000, "output_tokens": 3000, "cost_usd": 2.5}
        usage_path = tmp_vulti / "agents" / "scout" / "budget_usage.json"
        usage_path.write_text(json.dumps(usage))

        with patch("orchestrator.budget._load_budget_config",
                    return_value={"max_cost_per_day": 10.0, "max_tokens_per_day": 100000}):
            status = get_budget_status("scout")
            assert status["tokens_used"] == 8000
            assert status["cost_usd"] == 2.5
            assert status["cost_remaining"] == 7.5
            assert status["tokens_remaining"] == 92000
