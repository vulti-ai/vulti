"""
Wallet Tool — manage the agent's stored payment methods.

Supports saving and retrieving credit card details.
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


def _wallet_path() -> Path:
    """Return the creditcard.json path for the current agent."""
    vulti_home = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))
    agent_id = os.getenv("VULTI_AGENT_ID")
    if not agent_id:
        return vulti_home / "creditcard.json"
    return vulti_home / "agents" / agent_id / "creditcard.json"


def _load_wallet() -> Dict[str, Any]:
    """Load creditcard.json for the current agent."""
    wp = _wallet_path()
    if not wp.exists():
        return {}
    try:
        return json.loads(wp.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_wallet(data: Dict[str, Any]) -> None:
    """Save creditcard.json for the current agent."""
    wp = _wallet_path()
    wp.parent.mkdir(parents=True, exist_ok=True)
    wp.write_text(json.dumps(data, indent=2), encoding="utf-8")


def wallet_tool(args: dict) -> str:
    """Handle wallet tool calls."""
    action = args.get("action", "")
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
            "cvv_note": "CVV is not stored for security. Ask the owner for it at transaction time.",
        })

    if action == "save_credit_card":
        name = args.get("name", "")
        number = args.get("number", "")
        expiry = args.get("expiry", "")
        # CVV is intentionally NOT stored — security best practice

        if not number:
            return json.dumps({"success": False, "error": "Card number is required."})

        data["credit_card"] = {
            "name": name,
            "number": number,
            "expiry": expiry,
            # CVV never persisted to disk — ask owner at transaction time
        }
        _save_wallet(data)

        last4 = number[-4:] if len(number) >= 4 else number
        return json.dumps({
            "success": True,
            "message": f"Credit card saved (ending {last4}). CVV is not stored — you'll need to ask the owner for it when making a purchase.",
        })

    if action == "remove_credit_card":
        if "credit_card" in data:
            del data["credit_card"]
            _save_wallet(data)
        return json.dumps({"success": True, "message": "Credit card removed."})

    return json.dumps({
        "success": False,
        "error": f"Unknown action '{action}'. Use: get_credit_card, save_credit_card, remove_credit_card",
    })


def check_wallet_requirements() -> bool:
    """Always available when an agent is running."""
    return bool(os.getenv("VULTI_AGENT_ID") or os.getenv("VULTI_INTERACTIVE"))


WALLET_SCHEMA = {
    "name": "wallet",
    "description": (
        "Manage your stored payment card. Actions:\n"
        "- save_credit_card: Save a credit card (requires name, number, expiry). CVV is NOT stored for security.\n"
        "- get_credit_card: Retrieve stored card details for a purchase. Returns card number and expiry but NOT the CVV.\n"
        "- remove_credit_card: Delete the stored card.\n"
        "When making a purchase, you MUST ask the owner for their CVV — it is never stored."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get_credit_card", "save_credit_card", "remove_credit_card"],
                "description": "What to do.",
            },
            "name": {
                "type": "string",
                "description": "Name on the card (for save_credit_card).",
            },
            "number": {
                "type": "string",
                "description": "Card number (for save_credit_card).",
            },
            "expiry": {
                "type": "string",
                "description": "Expiry date MM/YY (for save_credit_card).",
            },
            "code": {
                "type": "string",
                "description": "CVV/security code (for save_credit_card).",
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
    handler=lambda args, **kw: wallet_tool(args),
    check_fn=check_wallet_requirements,
    emoji="💳",
)
