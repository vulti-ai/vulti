"""
Permission request tool — allows agents to request access to connections.

Registered into hermes-agent's tool registry so agents can call
``request_connection(connection_name='github', reason='Need to check PRs')``
when they discover they don't have access to a connection they need.
"""

import json
import os

from orchestrator.permissions import request_permission, list_pending


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
        allowed = registry._get_agent_allowed(agent_id)
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
