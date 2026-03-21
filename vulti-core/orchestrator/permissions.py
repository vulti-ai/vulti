"""
Per-agent permission management.

Each agent owns its permissions at ``~/.vulti/agents/{agent_id}/permissions.json``.
This file stores the agent's allowed connections list and any pending permission
requests. Connections themselves remain global in ``connections.yaml`` — this
module only governs what each agent is *allowed* to use.

File format::

    {
        "allowed_connections": ["github", "gmail"],
        "pending_requests": [
            {
                "id": "abc123def456",
                "connection_name": "slack",
                "reason": "Need to post updates",
                "status": "pending",
                "created_at": "2026-03-22T...",
                "resolved_at": null
            }
        ]
    }
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _agent_permissions_path(agent_id: str) -> Path:
    """Return the path to an agent's permissions.json."""
    vulti_home = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))
    return vulti_home / "agents" / agent_id / "permissions.json"


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def _load_permissions(agent_id: str) -> Dict[str, Any]:
    """Load an agent's permissions file. Returns default structure if missing."""
    path = _agent_permissions_path(agent_id)
    if not path.exists():
        return {"allowed_connections": [], "pending_requests": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # Ensure both keys exist
        data.setdefault("allowed_connections", [])
        data.setdefault("pending_requests", [])
        return data
    except Exception:
        return {"allowed_connections": [], "pending_requests": []}


def _save_permissions(agent_id: str, data: Dict[str, Any]) -> None:
    """Write an agent's permissions file with secure permissions."""
    path = _agent_permissions_path(agent_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Allowed connections
# ---------------------------------------------------------------------------

def get_allowed_connections(agent_id: str) -> List[str]:
    """Return the list of connection names this agent is allowed to use."""
    return _load_permissions(agent_id).get("allowed_connections", [])


def set_allowed_connections(agent_id: str, connections: List[str]) -> None:
    """Replace the agent's full allowed connections list."""
    data = _load_permissions(agent_id)
    data["allowed_connections"] = sorted(set(connections))
    _save_permissions(agent_id, data)


def add_allowed_connection(agent_id: str, connection_name: str) -> None:
    """Add a single connection to the agent's allow list (idempotent)."""
    data = _load_permissions(agent_id)
    allowed = data["allowed_connections"]
    if connection_name not in allowed:
        allowed.append(connection_name)
        allowed.sort()
        _save_permissions(agent_id, data)


def remove_allowed_connection(agent_id: str, connection_name: str) -> None:
    """Remove a single connection from the agent's allow list (idempotent)."""
    data = _load_permissions(agent_id)
    allowed = data["allowed_connections"]
    if connection_name in allowed:
        allowed.remove(connection_name)
        _save_permissions(agent_id, data)


# ---------------------------------------------------------------------------
# Permission requests
# ---------------------------------------------------------------------------

def request_permission(
    agent_id: str,
    connection_name: str,
    reason: str = "",
) -> Dict[str, Any]:
    """Create a pending permission request for a connection.

    Returns the request dict. If a pending request already exists for this
    agent+connection pair, returns the existing one instead of duplicating.
    """
    data = _load_permissions(agent_id)
    pending = data["pending_requests"]

    # Check for existing pending request
    for req in pending:
        if (req.get("connection_name") == connection_name
                and req.get("status") == "pending"):
            return req

    request = {
        "id": uuid.uuid4().hex[:12],
        "connection_name": connection_name,
        "reason": reason,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resolved_at": None,
    }
    pending.append(request)
    _save_permissions(agent_id, data)

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
    """Return pending permission requests.

    If ``agent_id`` is given, returns only that agent's pending requests.
    If ``agent_id`` is None, aggregates pending requests across all agents.
    """
    if agent_id:
        data = _load_permissions(agent_id)
        return [r for r in data["pending_requests"] if r.get("status") == "pending"]

    # Aggregate across all agents
    from vulti_cli.agent_registry import AgentRegistry
    try:
        registry = AgentRegistry()
        agents = registry.list_agents()
    except Exception:
        return []

    result = []
    for agent in agents:
        data = _load_permissions(agent.id)
        for req in data["pending_requests"]:
            if req.get("status") == "pending":
                req_copy = dict(req)
                req_copy["agent_id"] = agent.id
                result.append(req_copy)
    return result


def approve(request_id: str, agent_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Approve a permission request, adding the connection to the agent's allow list.

    If ``agent_id`` is provided, searches only that agent's file.
    Otherwise searches all agents (slower).
    """
    agent_ids = [agent_id] if agent_id else _all_agent_ids()

    for aid in agent_ids:
        data = _load_permissions(aid)
        for req in data["pending_requests"]:
            if req.get("id") == request_id and req.get("status") == "pending":
                req["status"] = "approved"
                req["resolved_at"] = datetime.now(timezone.utc).isoformat()

                # Add to allowed connections
                allowed = data["allowed_connections"]
                if req["connection_name"] not in allowed:
                    allowed.append(req["connection_name"])
                    allowed.sort()

                _save_permissions(aid, data)

                try:
                    from orchestrator.audit import emit as audit_emit
                    audit_emit("permission_approved", agent_id=aid, details={
                        "connection": req["connection_name"],
                        "request_id": request_id,
                    })
                except Exception:
                    pass

                result = dict(req)
                result["agent_id"] = aid
                return result

    return None


def deny(request_id: str, agent_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Deny a permission request.

    If ``agent_id`` is provided, searches only that agent's file.
    Otherwise searches all agents (slower).
    """
    agent_ids = [agent_id] if agent_id else _all_agent_ids()

    for aid in agent_ids:
        data = _load_permissions(aid)
        for req in data["pending_requests"]:
            if req.get("id") == request_id and req.get("status") == "pending":
                req["status"] = "denied"
                req["resolved_at"] = datetime.now(timezone.utc).isoformat()
                _save_permissions(aid, data)

                try:
                    from orchestrator.audit import emit as audit_emit
                    audit_emit("permission_denied", agent_id=aid, details={
                        "connection": req["connection_name"],
                        "request_id": request_id,
                    })
                except Exception:
                    pass

                result = dict(req)
                result["agent_id"] = aid
                return result

    return None


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def migrate_from_registry(vulti_home: Path = None) -> int:
    """Migrate allowed_connections from registry.json into per-agent permissions.json.

    Also migrates any pending requests from the old global pending.json.
    Returns the number of agents migrated.
    """
    if vulti_home is None:
        vulti_home = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))

    registry_path = vulti_home / "agents" / "registry.json"
    if not registry_path.exists():
        return 0

    try:
        with open(registry_path, encoding="utf-8") as f:
            registry_data = json.load(f)
    except Exception:
        return 0

    agents = registry_data.get("agents", {})
    migrated = 0

    # Load old global pending requests
    old_pending_path = vulti_home / "permissions" / "pending.json"
    old_pending: List[Dict[str, Any]] = []
    if old_pending_path.exists():
        try:
            with open(old_pending_path, encoding="utf-8") as f:
                old_pending = json.load(f)
        except Exception:
            old_pending = []

    for agent_id, agent_data in agents.items():
        old_allowed = agent_data.get("allowed_connections", [])
        if not old_allowed and not old_pending:
            continue

        perm_path = vulti_home / "agents" / agent_id / "permissions.json"

        # Don't overwrite if already migrated
        if perm_path.exists():
            continue

        # Collect pending requests for this agent from old global file
        agent_pending = [
            {k: v for k, v in req.items() if k != "agent_id"}
            for req in old_pending
            if req.get("agent_id") == agent_id
        ]

        perm_data = {
            "allowed_connections": sorted(old_allowed),
            "pending_requests": agent_pending,
        }

        perm_path.parent.mkdir(parents=True, exist_ok=True)
        with open(perm_path, "w", encoding="utf-8") as f:
            json.dump(perm_data, f, indent=2, ensure_ascii=False)
        try:
            os.chmod(perm_path, 0o600)
        except OSError:
            pass

        # Remove allowed_connections from the registry entry
        agent_data.pop("allowed_connections", None)
        migrated += 1

    if migrated:
        # Save cleaned registry
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry_data, f, indent=2, ensure_ascii=False)

        # Remove old global pending file
        if old_pending_path.exists():
            try:
                old_pending_path.unlink()
                # Remove empty permissions dir
                old_dir = old_pending_path.parent
                if old_dir.exists() and not any(old_dir.iterdir()):
                    old_dir.rmdir()
            except OSError:
                pass

        logger.info("Migrated permissions for %d agent(s) to per-agent files", migrated)

    return migrated


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _all_agent_ids() -> List[str]:
    """Return all registered agent IDs."""
    try:
        from vulti_cli.agent_registry import AgentRegistry
        return [a.id for a in AgentRegistry().list_agents()]
    except Exception:
        return []


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
        reg_data = registry._load()
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
