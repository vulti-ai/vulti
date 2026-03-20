"""
Per-agent token and cost budget enforcement.

Reads budget limits from agent config.yaml under the ``budget`` key::

    budget:
      max_cost_per_day: 5.00      # USD
      max_tokens_per_day: 500000
      max_cost_per_month: 50.00   # USD
      max_tokens_per_month: 5000000
      auto_pause: true            # auto-pause agent when budget exceeded

Tracks daily usage in ``~/.vulti/agents/{agent_id}/budget_usage.json``.
Tracks monthly usage in ``~/.vulti/agents/{agent_id}/budget_monthly.json``.

Before each agent invocation, call ``check_budget(agent_id)`` — it returns
an error string if the budget is exceeded, or ``None`` if OK.

After each invocation, call ``record_usage(agent_id, input_tokens, output_tokens, model)``
to update the running totals.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_VULTI_HOME = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))


# ---------------------------------------------------------------------------
# Daily usage helpers
# ---------------------------------------------------------------------------

def _usage_path(agent_id: str) -> Path:
    return _VULTI_HOME / "agents" / agent_id / "budget_usage.json"


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_usage(agent_id: str) -> Dict[str, Any]:
    path = _usage_path(agent_id)
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_usage(agent_id: str, data: Dict[str, Any]) -> None:
    path = _usage_path(agent_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _get_today_usage(agent_id: str) -> Dict[str, Any]:
    data = _load_usage(agent_id)
    today = _today_key()
    if data.get("date") != today:
        # New day — reset counters
        return {"date": today, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    return data


# ---------------------------------------------------------------------------
# Monthly usage helpers
# ---------------------------------------------------------------------------

def _monthly_usage_path(agent_id: str) -> Path:
    return _VULTI_HOME / "agents" / agent_id / "budget_monthly.json"


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _load_monthly_usage(agent_id: str) -> Dict[str, Any]:
    path = _monthly_usage_path(agent_id)
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_monthly_usage(agent_id: str, data: Dict[str, Any]) -> None:
    path = _monthly_usage_path(agent_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _get_month_usage(agent_id: str) -> Dict[str, Any]:
    data = _load_monthly_usage(agent_id)
    month = _month_key()
    if data.get("month") != month:
        return {"month": month, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    return data


# ---------------------------------------------------------------------------
# Auto-pause helpers
# ---------------------------------------------------------------------------

def _auto_pause_agent(agent_id: str, reason: str) -> None:
    """Set agent status to 'paused' in the registry and emit audit event."""
    try:
        from vulti_cli.agent_registry import AgentRegistry
        reg = AgentRegistry()
        agent = reg.get_agent(agent_id)
        if agent and agent.status != "paused":
            reg.update_agent(agent_id, {"status": "paused"})
            logger.warning("Agent '%s' auto-paused: %s", agent_id, reason)
    except Exception as e:
        logger.warning("Failed to auto-pause agent '%s': %s", agent_id, e)

    # Emit audit event
    try:
        from orchestrator.audit import emit
        emit("agent_paused", agent_id=agent_id, details={"reason": reason, "auto": True})
    except Exception:
        pass


def unpause_agent(agent_id: str) -> bool:
    """Clear the paused state for an agent. Returns True if successful."""
    try:
        from vulti_cli.agent_registry import AgentRegistry
        reg = AgentRegistry()
        agent = reg.get_agent(agent_id)
        if agent and agent.status == "paused":
            reg.update_agent(agent_id, {"status": "active"})
            try:
                from orchestrator.audit import emit
                emit("agent_unpaused", agent_id=agent_id)
            except Exception:
                pass
            return True
    except Exception as e:
        logger.warning("Failed to unpause agent '%s': %s", agent_id, e)
    return False


# ---------------------------------------------------------------------------
# Budget config
# ---------------------------------------------------------------------------

def _load_budget_config(agent_id: str) -> Dict[str, Any]:
    """Load budget settings from agent config."""
    try:
        from vulti_cli.config import load_config
        config = load_config(agent_id=agent_id)
        return config.get("budget", {})
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Check budget (daily + monthly)
# ---------------------------------------------------------------------------

def check_budget(agent_id: str) -> Optional[str]:
    """Check if the agent has exceeded its daily or monthly budget.

    Returns an error message if budget exceeded, None if OK.
    If auto_pause is enabled, pauses the agent on first exceed.
    """
    budget = _load_budget_config(agent_id)
    if not budget:
        return None  # No budget configured

    auto_pause = budget.get("auto_pause", False)

    # --- Daily checks ---
    usage = _get_today_usage(agent_id)

    max_cost = budget.get("max_cost_per_day")
    if max_cost is not None and usage.get("cost_usd", 0) >= float(max_cost):
        msg = (
            f"Agent '{agent_id}' has exceeded its daily cost budget "
            f"(${usage['cost_usd']:.2f} / ${max_cost:.2f}). "
            f"Budget resets at midnight UTC."
        )
        if auto_pause:
            _auto_pause_agent(agent_id, msg)
        return msg

    max_tokens = budget.get("max_tokens_per_day")
    if max_tokens is not None:
        total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        if total_tokens >= int(max_tokens):
            msg = (
                f"Agent '{agent_id}' has exceeded its daily token budget "
                f"({total_tokens:,} / {int(max_tokens):,} tokens). "
                f"Budget resets at midnight UTC."
            )
            if auto_pause:
                _auto_pause_agent(agent_id, msg)
            return msg

    # --- Monthly checks ---
    monthly = _get_month_usage(agent_id)

    max_cost_month = budget.get("max_cost_per_month")
    if max_cost_month is not None and monthly.get("cost_usd", 0) >= float(max_cost_month):
        msg = (
            f"Agent '{agent_id}' has exceeded its monthly cost budget "
            f"(${monthly['cost_usd']:.2f} / ${max_cost_month:.2f}). "
            f"Budget resets at the start of next month."
        )
        if auto_pause:
            _auto_pause_agent(agent_id, msg)
        return msg

    max_tokens_month = budget.get("max_tokens_per_month")
    if max_tokens_month is not None:
        total_monthly = monthly.get("input_tokens", 0) + monthly.get("output_tokens", 0)
        if total_monthly >= int(max_tokens_month):
            msg = (
                f"Agent '{agent_id}' has exceeded its monthly token budget "
                f"({total_monthly:,} / {int(max_tokens_month):,} tokens). "
                f"Budget resets at the start of next month."
            )
            if auto_pause:
                _auto_pause_agent(agent_id, msg)
            return msg

    return None


def record_usage(
    agent_id: str,
    input_tokens: int,
    output_tokens: int,
    model: str = "",
) -> None:
    """Record token usage and estimated cost for an agent invocation."""
    cost = 0.0
    if model:
        try:
            from agent.usage_pricing import estimate_cost_usd
            cost = estimate_cost_usd(model, input_tokens, output_tokens)
        except Exception:
            pass

    # Update daily usage
    usage = _get_today_usage(agent_id)
    usage["input_tokens"] = usage.get("input_tokens", 0) + input_tokens
    usage["output_tokens"] = usage.get("output_tokens", 0) + output_tokens
    usage["cost_usd"] = usage.get("cost_usd", 0.0) + cost
    _save_usage(agent_id, usage)

    # Update monthly usage
    monthly = _get_month_usage(agent_id)
    monthly["input_tokens"] = monthly.get("input_tokens", 0) + input_tokens
    monthly["output_tokens"] = monthly.get("output_tokens", 0) + output_tokens
    monthly["cost_usd"] = monthly.get("cost_usd", 0.0) + cost
    _save_monthly_usage(agent_id, monthly)

    # Emit audit event for cost tracking
    try:
        from orchestrator.audit import emit
        emit("budget_usage", agent_id=agent_id, details={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
            "model": model,
        })
    except Exception:
        pass


def get_budget_status(agent_id: str) -> Dict[str, Any]:
    """Return current budget status for an agent.

    Returns dict with budget limits, current usage, and remaining allowance.
    """
    budget = _load_budget_config(agent_id)
    usage = _get_today_usage(agent_id)
    monthly = _get_month_usage(agent_id)
    total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    cost = usage.get("cost_usd", 0.0)
    total_monthly_tokens = monthly.get("input_tokens", 0) + monthly.get("output_tokens", 0)
    monthly_cost = monthly.get("cost_usd", 0.0)

    status = {
        "agent_id": agent_id,
        "date": usage.get("date", _today_key()),
        "month": monthly.get("month", _month_key()),
        "tokens_used_today": total_tokens,
        "cost_usd_today": round(cost, 4),
        "tokens_used_month": total_monthly_tokens,
        "cost_usd_month": round(monthly_cost, 4),
        "auto_pause": budget.get("auto_pause", False),
    }

    # Daily limits
    max_cost = budget.get("max_cost_per_day")
    if max_cost is not None:
        status["max_cost_per_day"] = float(max_cost)
        status["cost_remaining_today"] = round(max(0, float(max_cost) - cost), 4)

    max_tokens = budget.get("max_tokens_per_day")
    if max_tokens is not None:
        status["max_tokens_per_day"] = int(max_tokens)
        status["tokens_remaining_today"] = max(0, int(max_tokens) - total_tokens)

    # Monthly limits
    max_cost_month = budget.get("max_cost_per_month")
    if max_cost_month is not None:
        status["max_cost_per_month"] = float(max_cost_month)
        status["cost_remaining_month"] = round(max(0, float(max_cost_month) - monthly_cost), 4)

    max_tokens_month = budget.get("max_tokens_per_month")
    if max_tokens_month is not None:
        status["max_tokens_per_month"] = int(max_tokens_month)
        status["tokens_remaining_month"] = max(0, int(max_tokens_month) - total_monthly_tokens)

    if not budget:
        status["note"] = "No budget configured. Add 'budget' section to agent config.yaml."

    return status
