"""
Wallet Tool — read-only access to the agent's stored payment methods.

Card details are NOT injected into the system prompt. The agent knows it has
a card (name + last 4 digits) from the prompt, and calls this tool to fetch
the full details only when needed for a transaction.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _load_wallet() -> Dict[str, Any]:
    """Load wallet.json for the current agent."""
    vulti_home = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))
    agent_id = os.getenv("VULTI_AGENT_ID")
    if not agent_id:
        return {}
    wallet_path = vulti_home / "agents" / agent_id / "wallet.json"
    if not wallet_path.exists():
        return {}
    try:
        return json.loads(wallet_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def wallet_tool(action: str) -> str:
    """Handle wallet tool calls. Currently only supports 'get_credit_card'."""
    data = _load_wallet()

    if action == "get_credit_card":
        cc = data.get("credit_card")
        if not cc or not cc.get("number"):
            return json.dumps({"success": False, "error": "No credit card stored."})
        return json.dumps({
            "success": True,
            "name": cc.get("name", ""),
            "number": cc["number"],
            "expiry": cc.get("expiry", ""),
            "cvv": cc.get("code", ""),
        })

    return json.dumps({"success": False, "error": f"Unknown action '{action}'. Use: get_credit_card"})


def check_wallet_requirements() -> bool:
    """Available when the agent has a wallet.json with a credit card."""
    data = _load_wallet()
    cc = data.get("credit_card")
    return bool(cc and cc.get("number"))


WALLET_SCHEMA = {
    "name": "wallet",
    "description": (
        "Retrieve your stored payment card details. Use this when you need "
        "the full card number, expiry, or CVV for a purchase or payment. "
        "Your system prompt tells you WHICH card you have — call this tool "
        "to get the sensitive fields."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get_credit_card"],
                "description": "What to retrieve.",
            },
        },
        "required": ["action"],
    },
}


# --- Registry ---
from tools.registry import registry

registry.register(
    name="wallet",
    toolset="wallet",
    schema=WALLET_SCHEMA,
    handler=lambda args, **kw: wallet_tool(action=args.get("action", "")),
    check_fn=check_wallet_requirements,
    emoji="💳",
)
