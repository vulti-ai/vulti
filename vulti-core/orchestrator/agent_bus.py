"""
Inter-agent messaging bus.

Allows agents to send messages to other agents via the orchestrator's
AgentFactory and AgentContext, replacing direct AIAgent instantiation
and environment variable manipulation.

Session keys for inter-agent messages use the format:
    agent:{target_agent_id}:interagent:{sender_agent_id}

This gives persistent conversation history between agent pairs.
"""

import logging
from typing import Any, Dict

from orchestrator.agent_context import AgentContext
from orchestrator.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)

MAX_HOP_COUNT = 3


async def send_to_agent(
    target_agent_id: str,
    message: str,
    sender_agent_id: str,
    hop_count: int = 0,
    timeout: int = 120,
) -> Dict[str, Any]:
    """Deliver a message to another agent and return the response.

    The target agent runs with its own identity (soul, memories, config)
    within a properly-scoped AgentContext. It processes the message in a
    persistent inter-agent session so conversation history accumulates.

    Args:
        target_agent_id: ID of the agent to message.
        message: The message text.
        sender_agent_id: ID of the sending agent.
        hop_count: Current hop count for circular prevention.
        timeout: Max seconds to wait for response.

    Returns:
        Dict with 'response', 'agent_id', and 'agent_name' keys,
        or 'error' key on failure.
    """
    if hop_count >= MAX_HOP_COUNT:
        return {
            "error": (
                f"Max inter-agent hop count reached ({MAX_HOP_COUNT}). "
                "This prevents infinite loops between agents."
            ),
            "agent_id": target_agent_id,
        }

    registry = AgentRegistry()
    target = registry.get_agent(target_agent_id)
    if target is None:
        return {
            "error": (
                f"Agent '{target_agent_id}' not found. "
                f"Available agents: {', '.join(a.id for a in registry.list_agents())}"
            ),
        }

    sender = registry.get_agent(sender_agent_id)
    sender_name = sender.name if sender else sender_agent_id

    # Build inter-agent session ID
    session_id = f"agent:{target_agent_id}:interagent:{sender_agent_id}"

    # Prepend context about who is messaging
    context_message = (
        f"[Inter-agent message from {sender_name} (agent:{sender_agent_id})]\n\n"
        f"{message}"
    )

    try:
        from orchestrator.agent_factory import AgentFactory

        factory = AgentFactory(registry)
        with AgentContext.scope(target_agent_id, hop_count=hop_count + 1):
            agent = factory.create_agent(
                target_agent_id,
                max_iterations=30,  # Limit inter-agent turns
                platform="interagent",
                session_id=session_id,
            )
            result = agent.run_conversation(context_message)

        response = result.get("final_response", "")
        if not response:
            response = "(No response generated)"

        return {
            "response": response,
            "agent_id": target_agent_id,
            "agent_name": target.name,
        }

    except Exception as e:
        logger.error("Inter-agent message to '%s' failed: %s", target_agent_id, e)
        return {
            "error": f"Failed to deliver message to agent '{target_agent_id}': {e}",
            "agent_id": target_agent_id,
        }
