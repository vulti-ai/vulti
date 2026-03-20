"""
Approval gates — require human approval for high-stakes agent actions.

Pending approvals are stored in ``~/.vulti/approvals/pending.json``.
Agents request approval via the ``request_approval`` tool, then poll
until the human approves/denies via the Tauri UI or times out.

Supported action types:
  - crypto_send: large crypto transactions
  - agent_delete: deleting an agent
  - budget_override: exceeding budget limits
  - config_change: significant config changes

Config (in agent config.yaml)::

    approvals:
      crypto_send_threshold_usd: 100.00
      require_for:
        - agent_delete
        - budget_override
        - crypto_send
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_VULTI_HOME = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))
_APPROVALS_DIR = _VULTI_HOME / "approvals"
_PENDING_FILE = _APPROVALS_DIR / "pending.json"


def _ensure_dir() -> None:
    _APPROVALS_DIR.mkdir(parents=True, exist_ok=True)


def _load_pending() -> List[Dict[str, Any]]:
    if not _PENDING_FILE.exists():
        return []
    try:
        with open(_PENDING_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_pending(approvals: List[Dict[str, Any]]) -> None:
    _ensure_dir()
    with open(_PENDING_FILE, "w") as f:
        json.dump(approvals, f, indent=2)


def request_approval(
    agent_id: str,
    action_type: str,
    description: str,
    details: Optional[Dict[str, Any]] = None,
    ttl_hours: int = 24,
) -> Dict[str, Any]:
    """Create a pending approval request.

    Returns the approval dict with id, status, etc.
    """
    now = datetime.now(timezone.utc)
    approval = {
        "id": uuid.uuid4().hex[:12],
        "agent_id": agent_id,
        "action_type": action_type,
        "description": description,
        "details": details or {},
        "status": "pending",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=ttl_hours)).isoformat(),
        "resolved_at": None,
        "resolved_by": None,
    }

    approvals = _load_pending()
    approvals.append(approval)
    _save_pending(approvals)

    logger.info("Approval requested: [%s] %s — %s", approval["id"], action_type, description)

    # Emit audit event
    try:
        from orchestrator.audit import emit
        emit("approval_requested", agent_id=agent_id, details={
            "approval_id": approval["id"],
            "action_type": action_type,
            "description": description,
        })
    except Exception:
        pass

    # Notify via Matrix if possible
    _notify_owner(approval)

    return approval


def check_approval(approval_id: str) -> str:
    """Return the status of an approval: pending, approved, denied, or expired."""
    approvals = _load_pending()
    for a in approvals:
        if a["id"] == approval_id:
            # Check expiry
            if a["status"] == "pending":
                expires = datetime.fromisoformat(a["expires_at"])
                if datetime.now(timezone.utc) > expires:
                    a["status"] = "expired"
                    _save_pending(approvals)
                    return "expired"
            return a["status"]
    return "not_found"


def wait_for_approval(approval_id: str, timeout_seconds: int = 300) -> bool:
    """Poll the approval file until resolved or timeout.

    Returns True if approved, False otherwise.
    """
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        status = check_approval(approval_id)
        if status == "approved":
            return True
        if status in ("denied", "expired", "not_found"):
            return False
        time.sleep(2)
    return False


def approve(approval_id: str, resolved_by: str = "owner") -> Optional[Dict[str, Any]]:
    """Approve a pending request."""
    return _resolve(approval_id, "approved", resolved_by)


def deny(approval_id: str, resolved_by: str = "owner") -> Optional[Dict[str, Any]]:
    """Deny a pending request."""
    return _resolve(approval_id, "denied", resolved_by)


def _resolve(approval_id: str, status: str, resolved_by: str) -> Optional[Dict[str, Any]]:
    approvals = _load_pending()
    for a in approvals:
        if a["id"] == approval_id and a["status"] == "pending":
            a["status"] = status
            a["resolved_at"] = datetime.now(timezone.utc).isoformat()
            a["resolved_by"] = resolved_by
            _save_pending(approvals)

            logger.info("Approval %s: %s (by %s)", approval_id, status, resolved_by)

            try:
                from orchestrator.audit import emit
                emit(f"approval_{status}", agent_id=a["agent_id"], details={
                    "approval_id": approval_id,
                    "action_type": a["action_type"],
                    "resolved_by": resolved_by,
                })
            except Exception:
                pass

            return a
    return None


def list_pending(agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return pending approvals, optionally filtered by agent."""
    now = datetime.now(timezone.utc)
    approvals = _load_pending()
    result = []
    for a in approvals:
        if a["status"] != "pending":
            continue
        # Auto-expire
        expires = datetime.fromisoformat(a["expires_at"])
        if now > expires:
            a["status"] = "expired"
            continue
        if agent_id and a["agent_id"] != agent_id:
            continue
        result.append(a)
    return result


def is_approval_required(agent_id: str, action_type: str) -> bool:
    """Check if this action type requires approval for this agent."""
    try:
        from vulti_cli.config import load_config
        config = load_config(agent_id=agent_id)
        approvals_cfg = config.get("approvals", {})
        require_for = approvals_cfg.get("require_for", [])
        return action_type in require_for
    except Exception:
        return False


def get_approval_threshold(agent_id: str, key: str) -> Optional[float]:
    """Get a numeric threshold from approval config (e.g. crypto_send_threshold_usd)."""
    try:
        from vulti_cli.config import load_config
        config = load_config(agent_id=agent_id)
        return config.get("approvals", {}).get(key)
    except Exception:
        return None


def _notify_owner(approval: Dict[str, Any]) -> None:
    """Best-effort Matrix notification to the owner about a pending approval."""
    try:
        from tools.send_message_tool import _send_to_platform
        from gateway.config import load_gateway_config, Platform
        import asyncio

        config = load_gateway_config()
        pconfig = config.platforms.get(Platform.MATRIX)
        if not pconfig or not pconfig.enabled:
            return

        # Find owner's home channel
        home = config.get_home_channel(Platform.MATRIX)
        if not home:
            return

        msg = (
            f"**Approval required** from agent `{approval['agent_id']}`\n\n"
            f"**Action:** {approval['action_type']}\n"
            f"**Description:** {approval['description']}\n"
            f"**ID:** `{approval['id']}`\n\n"
            f"Approve or deny in VultiHub."
        )

        try:
            asyncio.run(_send_to_platform(Platform.MATRIX, pconfig, home.chat_id, msg))
        except RuntimeError:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(asyncio.run, _send_to_platform(Platform.MATRIX, pconfig, home.chat_id, msg)).result(timeout=10)
    except Exception as e:
        logger.debug("Failed to notify owner about approval: %s", e)
