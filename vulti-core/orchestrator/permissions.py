"""
Permission escalation for agents.

When an agent tries to use a connection it isn't allowed to access,
this module creates a pending permission request that surfaces to the
owner via Matrix DM or hub notification.

Pending requests are stored at ``~/.vulti/permissions/pending.json``.
The owner can approve or deny them, which updates the agent's
``allowed_connections`` in the registry.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_VULTI_HOME = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))
_PERMISSIONS_DIR = _VULTI_HOME / "permissions"
_PENDING_FILE = _PERMISSIONS_DIR / "pending.json"


def _load_pending() -> List[Dict[str, Any]]:
    if not _PENDING_FILE.exists():
        return []
    try:
        with open(_PENDING_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _save_pending(requests: List[Dict[str, Any]]) -> None:
    _PERMISSIONS_DIR.mkdir(parents=True, exist_ok=True)
    with open(_PENDING_FILE, "w") as f:
        json.dump(requests, f, indent=2)


def request_permission(
    agent_id: str,
    connection_name: str,
    reason: str = "",
) -> Dict[str, Any]:
    """Create a pending permission request.

    Returns the request dict. If a pending request already exists for this
    agent+connection pair, returns the existing one instead of duplicating.
    """
    pending = _load_pending()

    # Check for existing pending request
    for req in pending:
        if (req.get("agent_id") == agent_id
                and req.get("connection_name") == connection_name
                and req.get("status") == "pending"):
            return req

    request = {
        "id": uuid.uuid4().hex[:12],
        "agent_id": agent_id,
        "connection_name": connection_name,
        "reason": reason,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    pending.append(request)
    _save_pending(pending)

    # Audit
    try:
        from orchestrator.audit import emit as audit_emit
        audit_emit("permission_request", agent_id=agent_id, details={
            "connection": connection_name,
            "reason": reason,
        })
    except Exception:
        pass

    # Notify owner via Matrix if possible
    _notify_owner(agent_id, connection_name, reason)

    return request


def list_pending(agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return pending permission requests, optionally filtered by agent."""
    pending = _load_pending()
    result = [r for r in pending if r.get("status") == "pending"]
    if agent_id:
        result = [r for r in result if r.get("agent_id") == agent_id]
    return result


def approve(request_id: str) -> Optional[Dict[str, Any]]:
    """Approve a permission request, adding the connection to the agent's allow list."""
    pending = _load_pending()

    for req in pending:
        if req.get("id") == request_id and req.get("status") == "pending":
            req["status"] = "approved"
            req["resolved_at"] = datetime.now(timezone.utc).isoformat()
            _save_pending(pending)

            # Add to agent's allowed connections
            _add_to_allow_list(req["agent_id"], req["connection_name"])

            try:
                from orchestrator.audit import emit as audit_emit
                audit_emit("permission_approved", agent_id=req["agent_id"], details={
                    "connection": req["connection_name"],
                    "request_id": request_id,
                })
            except Exception:
                pass

            return req

    return None


def deny(request_id: str) -> Optional[Dict[str, Any]]:
    """Deny a permission request."""
    pending = _load_pending()

    for req in pending:
        if req.get("id") == request_id and req.get("status") == "pending":
            req["status"] = "denied"
            req["resolved_at"] = datetime.now(timezone.utc).isoformat()
            _save_pending(pending)

            try:
                from orchestrator.audit import emit as audit_emit
                audit_emit("permission_denied", agent_id=req["agent_id"], details={
                    "connection": req["connection_name"],
                    "request_id": request_id,
                })
            except Exception:
                pass

            return req

    return None


def _add_to_allow_list(agent_id: str, connection_name: str) -> None:
    """Add a connection to an agent's allowed_connections in the registry."""
    try:
        from vulti_cli.agent_registry import AgentRegistry
        registry = AgentRegistry()
        meta = registry.get_agent(agent_id)
        if meta and connection_name not in meta.allowed_connections:
            meta.allowed_connections.append(connection_name)
            registry.update_agent(agent_id, {"allowed_connections": meta.allowed_connections})
    except Exception as e:
        logger.error("Failed to update allow list for %s: %s", agent_id, e)


def _notify_owner(agent_id: str, connection_name: str, reason: str) -> None:
    """Notify the owner about a permission request via Matrix DM."""
    try:
        from gateway.matrix_agents import (
            get_agent_matrix_credentials,
            send_room_message,
        )
        from vulti_cli.agent_registry import AgentRegistry

        registry = AgentRegistry()
        meta = registry.get_agent(agent_id)
        agent_name = meta.name if meta else agent_id

        # Find owner DM room for this agent
        reg_data = registry._load_registry()
        owner_dm_room = None
        for rel in reg_data.get("relationships", []):
            if (rel.get("from_agent_id") == "owner"
                    and rel.get("to_agent_id") == agent_id
                    and rel.get("matrix_room_id")):
                owner_dm_room = rel["matrix_room_id"]
                break

        if not owner_dm_room:
            return

        creds = get_agent_matrix_credentials(agent_id)
        if not creds:
            return

        homeserver_url = creds.get("homeserver_url", "http://127.0.0.1:6167")
        msg = (
            f"Permission request: I need access to the **{connection_name}** connection."
        )
        if reason:
            msg += f"\n\nReason: {reason}"
        msg += "\n\nUse `/permissions approve` or `/permissions deny` to respond."

        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(asyncio.run,
                    send_room_message(homeserver_url, agent_id, owner_dm_room, msg)
                ).result(timeout=10)
        else:
            asyncio.run(send_room_message(homeserver_url, agent_id, owner_dm_room, msg))

    except Exception as e:
        logger.debug("Owner notification for permission request failed: %s", e)
