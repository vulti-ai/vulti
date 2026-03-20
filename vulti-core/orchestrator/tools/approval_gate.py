"""
Approval gate tool — agents call this before high-stakes actions.

Registers ``request_approval`` into the hermes-agent tool registry.
The tool creates an approval request and waits for human resolution.
"""

import json
import os

from tool_registry import registry

from orchestrator.approvals import (
    request_approval,
    wait_for_approval,
    is_approval_required,
)


@registry.register(
    name="request_approval",
    description=(
        "Request human approval before performing a high-stakes action. "
        "Use this before: large crypto sends, deleting agents, overriding budgets, "
        "or any irreversible action. Returns approval status."
    ),
    parameters={
        "type": "object",
        "properties": {
            "action_type": {
                "type": "string",
                "description": "Type of action: crypto_send, agent_delete, budget_override, config_change",
            },
            "description": {
                "type": "string",
                "description": "Human-readable description of what you want to do and why",
            },
            "details": {
                "type": "object",
                "description": "Action-specific details (e.g. amount, chain, target)",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "How long to wait for approval (default: 300)",
            },
        },
        "required": ["action_type", "description"],
    },
    toolset="vulti-cli",
)
def request_approval_tool(
    action_type: str,
    description: str,
    details: dict = None,
    timeout_seconds: int = 300,
) -> str:
    agent_id = os.getenv("VULTI_AGENT_ID", "")
    if not agent_id:
        return json.dumps({"error": "No agent context — cannot request approval"})

    # Check if approval is even required for this action type
    if not is_approval_required(agent_id, action_type):
        return json.dumps({
            "approved": True,
            "note": f"Action '{action_type}' does not require approval for this agent",
        })

    approval = request_approval(
        agent_id=agent_id,
        action_type=action_type,
        description=description,
        details=details,
    )

    # Wait for resolution
    approved = wait_for_approval(approval["id"], timeout_seconds=timeout_seconds)

    return json.dumps({
        "approval_id": approval["id"],
        "approved": approved,
        "status": "approved" if approved else "denied_or_expired",
        "description": description,
    })
