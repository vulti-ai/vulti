"""
Permission request tool — allows agents to request access to connections.

Registered into hermes-agent's tool registry so agents can call
``request_connection(connection_name='github', reason='Need to check PRs')``
when they discover they don't have access to a connection they need.
"""

import json
import os

from orchestrator.permissions import (
    add_allowed_connection,
    get_allowed_connections,
    list_pending,
    remove_allowed_connection,
    request_permission,
    set_allowed_connections,
)


def request_connection(args, **kw):
    """Handle request_connection tool calls."""
    connection_name = args.get("connection_name", "")
    reason = args.get("reason", "")

    if not connection_name:
        return json.dumps({"success": False, "error": "connection_name is required"})

    agent_id = os.getenv("VULTI_AGENT_ID", "default")

    # Check if connection even exists
    try:
        from vulti_cli.config import get_vulti_home
        from vulti_cli.connection_registry import ConnectionRegistry
        registry = ConnectionRegistry(get_vulti_home())
        conn = registry.get(connection_name)
        if not conn:
            return json.dumps({
                "success": False,
                "error": f"Connection '{connection_name}' does not exist.",
            })

        # Check if already allowed
        allowed = get_allowed_connections(agent_id)
        if connection_name in allowed:
            return json.dumps({
                "success": True,
                "already_allowed": True,
                "message": f"You already have access to '{connection_name}'.",
            })
    except Exception:
        pass

    # Check for existing pending request
    existing = list_pending(agent_id=agent_id)
    for req in existing:
        if req.get("connection_name") == connection_name:
            return json.dumps({
                "success": True,
                "already_pending": True,
                "request_id": req["id"],
                "message": f"A permission request for '{connection_name}' is already pending.",
            })

    req = request_permission(agent_id, connection_name, reason)
    return json.dumps({
        "success": True,
        "request_id": req["id"],
        "message": (
            f"Permission request sent to the owner for '{connection_name}'. "
            "They will be notified and can approve or deny the request."
        ),
    })


REQUEST_CONNECTION_SCHEMA = {
    "name": "request_connection",
    "description": (
        "Request access to a connection you can see but aren't allowed to use. "
        "The owner will be notified and can approve or deny. "
        "Use this when you discover you need a connection that isn't on your allow list."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "connection_name": {
                "type": "string",
                "description": "Name of the connection to request access to",
            },
            "reason": {
                "type": "string",
                "description": "Why you need this connection (helps the owner decide)",
            },
        },
        "required": ["connection_name"],
    },
}


def _check_requirements() -> bool:
    return bool(
        os.getenv("VULTI_INTERACTIVE")
        or os.getenv("VULTI_GATEWAY_SESSION")
        or os.getenv("VULTI_EXEC_ASK")
        or os.getenv("VULTI_AGENT_ID")
    )


# --- Registry ---
from tools.registry import registry

registry.register(
    name="request_connection",
    toolset="connections",
    schema=REQUEST_CONNECTION_SCHEMA,
    handler=request_connection,
    check_fn=_check_requirements,
    emoji="🔑",
)


# ---------------------------------------------------------------------------
# manage_own_connections — add/remove connections from the agent's own allowlist
# ---------------------------------------------------------------------------

def manage_own_connections(args, **kw):
    """Add or remove connections from this agent's own allowlist.

    Use this after the user has confirmed which connections they want enabled.
    """
    action = args.get("action", "add")
    connection_names = args.get("connection_names", [])

    if not connection_names:
        return json.dumps({"success": False, "error": "connection_names is required"})

    agent_id = os.getenv("VULTI_AGENT_ID", "default")

    try:
        from vulti_cli.config import get_vulti_home
        from vulti_cli.connection_registry import ConnectionRegistry

        vulti_home = get_vulti_home()
        creg = ConnectionRegistry(vulti_home)

        # Validate connections exist
        all_conns = {c.name for c in creg.list_all()}
        invalid = [n for n in connection_names if n not in all_conns]
        if invalid:
            return json.dumps({
                "success": False,
                "error": f"Unknown connections: {', '.join(invalid)}",
            })

        current = set(get_allowed_connections(agent_id))

        if action == "add":
            current.update(connection_names)
        elif action == "remove":
            current -= set(connection_names)
        else:
            return json.dumps({"success": False, "error": f"Unknown action: {action}"})

        set_allowed_connections(agent_id, sorted(current))

        return json.dumps({
            "success": True,
            "action": action,
            "connections": connection_names,
            "allowed_connections": sorted(current),
            "message": f"{'Added' if action == 'add' else 'Removed'} {len(connection_names)} connection(s).",
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


MANAGE_OWN_CONNECTIONS_SCHEMA = {
    "name": "manage_own_connections",
    "description": (
        "Add or remove connections from your own allowlist. "
        "Use this after the user has confirmed which connections they want you to have. "
        "Pass action='add' to enable connections, action='remove' to disable them."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "remove"],
                "description": "Whether to add or remove connections from your allowlist",
            },
            "connection_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of connection names to add or remove",
            },
        },
        "required": ["action", "connection_names"],
    },
}

registry.register(
    name="manage_own_connections",
    toolset="connections",
    schema=MANAGE_OWN_CONNECTIONS_SCHEMA,
    handler=manage_own_connections,
    check_fn=_check_requirements,
    emoji="🔗",
)
