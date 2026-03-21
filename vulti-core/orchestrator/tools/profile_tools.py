"""
Agent self-profile tool — allows agents to update their own metadata
(role, name, description, avatar).

Registered into hermes-agent's tool registry so agents can call
``update_own_profile(role='researcher')`` to update their profile
without asking the user to run CLI commands.
"""

import json
import os

from tools.registry import registry


def update_own_profile(args, **kw):
    """Update this agent's own profile metadata (role, name, description, avatar)."""
    agent_id = os.getenv("VULTI_AGENT_ID", "")

    # Only allow safe fields
    allowed = {"role", "name", "description", "avatar"}
    updates = {k: v for k, v in args.items() if k in allowed and v}

    if not updates:
        return json.dumps({
            "success": False,
            "error": f"No valid fields provided. Allowed: {', '.join(sorted(allowed))}",
        })

    try:
        from vulti_cli.config import get_vulti_home
        from vulti_cli.agent_registry import AgentRegistry

        areg = AgentRegistry(get_vulti_home())
        meta = areg.get_agent(agent_id)
        if meta is None:
            return json.dumps({"success": False, "error": f"Agent '{agent_id}' not found"})

        areg.update_agent(agent_id, **updates)

        return json.dumps({
            "success": True,
            "updated": updates,
            "message": f"Updated {', '.join(updates.keys())} for agent '{agent_id}'.",
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


UPDATE_OWN_PROFILE_SCHEMA = {
    "name": "update_own_profile",
    "description": (
        "Update your own agent profile metadata. "
        "Use this to set your role, name, description, or avatar. "
        "Call this whenever the user tells you your role or purpose."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "role": {
                "type": "string",
                "description": "Your role or purpose (e.g. 'researcher', 'assistant', 'coder')",
            },
            "name": {
                "type": "string",
                "description": "Your display name",
            },
            "description": {
                "type": "string",
                "description": "A short description of what you do",
            },
            "avatar": {
                "type": "string",
                "description": "URL to your avatar image",
            },
        },
    },
}


def _check_requirements() -> bool:
    return bool(
        os.getenv("VULTI_INTERACTIVE")
        or os.getenv("VULTI_GATEWAY_SESSION")
        or os.getenv("VULTI_EXEC_ASK")
        or os.getenv("VULTI_AGENT_ID")
    )


registry.register(
    name="update_own_profile",
    toolset="connections",
    schema=UPDATE_OWN_PROFILE_SCHEMA,
    handler=update_own_profile,
    check_fn=_check_requirements,
    emoji="🪪",
)
