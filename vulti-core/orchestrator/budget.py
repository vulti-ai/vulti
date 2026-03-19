"""
Per-agent token and cost budget enforcement.

Reads budget limits from agent config.yaml under the ``budget`` key::

    budget:
      max_cost_per_day: 5.00    # USD
      max_tokens_per_day: 500000

Tracks daily usage in ``~/.vulti/agents/{agent_id}/budget_usage.json``.
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


def _load_budget_config(agent_id: str) -> Dict[str, Any]:
    """Load budget settings from agent config."""
    try:
        from vulti_cli.config import load_config
        config = load_config(agent_id=agent_id)
        return config.get("budget", {})
    except Exception:
        return {}


def check_budget(agent_id: str) -> Optional[str]:
    """Check if the agent has exceeded its daily budget.

    Returns an error message if budget exceeded, None if OK.
    """
    budget = _load_budget_config(agent_id)
    if not budget:
        return None  # No budget configured

    usage = _get_today_usage(agent_id)

    max_cost = budget.get("max_cost_per_day")
    if max_cost is not None and usage.get("cost_usd", 0) >= float(max_cost):
        return (
            f"Agent '{agent_id}' has exceeded its daily cost budget "
            f"(${usage['cost_usd']:.2f} / ${max_cost:.2f}). "
            f"Budget resets at midnight UTC."
        )

    max_tokens = budget.get("max_tokens_per_day")
    if max_tokens is not None:
        total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        if total_tokens >= int(max_tokens):
            return (
                f"Agent '{agent_id}' has exceeded its daily token budget "
                f"({total_tokens:,} / {int(max_tokens):,} tokens). "
                f"Budget resets at midnight UTC."
            )

    return None


def record_usage(
    agent_id: str,
    input_tokens: int,
    output_tokens: int,
    model: str = "",
) -> None:
    """Record token usage and estimated cost for an agent invocation."""
    usage = _get_today_usage(agent_id)

    usage["input_tokens"] = usage.get("input_tokens", 0) + input_tokens
    usage["output_tokens"] = usage.get("output_tokens", 0) + output_tokens

    if model:
        try:
            from agent.usage_pricing import estimate_cost_usd
            cost = estimate_cost_usd(model, input_tokens, output_tokens)
            usage["cost_usd"] = usage.get("cost_usd", 0.0) + cost
        except Exception:
            pass

    _save_usage(agent_id, usage)


def get_budget_status(agent_id: str) -> Dict[str, Any]:
    """Return current budget status for an agent.

    Returns dict with budget limits, current usage, and remaining allowance.
    """
    budget = _load_budget_config(agent_id)
    usage = _get_today_usage(agent_id)
    total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    cost = usage.get("cost_usd", 0.0)

    status = {
        "agent_id": agent_id,
        "date": usage.get("date", _today_key()),
        "tokens_used": total_tokens,
        "cost_usd": round(cost, 4),
    }

    max_cost = budget.get("max_cost_per_day")
    if max_cost is not None:
        status["max_cost_per_day"] = float(max_cost)
        status["cost_remaining"] = round(max(0, float(max_cost) - cost), 4)

    max_tokens = budget.get("max_tokens_per_day")
    if max_tokens is not None:
        status["max_tokens_per_day"] = int(max_tokens)
        status["tokens_remaining"] = max(0, int(max_tokens) - total_tokens)

    if not budget:
        status["note"] = "No budget configured. Add 'budget' section to agent config.yaml."

    return status
