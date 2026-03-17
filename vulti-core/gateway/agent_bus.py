"""
Inter-agent messaging bus.

Allows agents to send messages to other agents. Unlike the delegate_tool
(which creates anonymous, isolated child agents), the agent bus delivers
messages to fully-formed agents with their own identity, personality,
memories, and persistent inter-agent sessions.

Session keys for inter-agent messages use the format:
    agent:{target_agent_id}:interagent:{sender_agent_id}

This gives persistent conversation history between agent pairs.
"""

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAX_HOP_COUNT = 3


async def send_to_agent(
    target_agent_id: str,
    message: str,
    sender_agent_id: str,
    hop_count: int = 0,
    timeout: int = 120,
) -> dict:
    """Deliver a message to another agent and return the response.

    The target agent runs with its own identity (soul, memories, config).
    It processes the message in a persistent inter-agent session so
    conversation history accumulates across exchanges.

    Args:
        target_agent_id: ID of the agent to message.
        message: The message text.
        sender_agent_id: ID of the sending agent.
        hop_count: Current hop count for circular prevention.
        timeout: Max seconds to wait for response.

    Returns:
        Dict with 'response', 'agent_id', and 'agent_name' keys.

    Raises:
        ValueError: If target agent not found or hop limit exceeded.
    """
    if hop_count >= MAX_HOP_COUNT:
        return {
            "error": f"Max inter-agent hop count reached ({MAX_HOP_COUNT}). "
            "This prevents infinite loops between agents.",
            "agent_id": target_agent_id,
        }

    from vulti_cli.agent_registry import AgentRegistry

    registry = AgentRegistry()
    target = registry.get_agent(target_agent_id)
    if target is None:
        return {
            "error": f"Agent '{target_agent_id}' not found. "
            f"Available agents: {', '.join(a.id for a in registry.list_agents())}",
        }

    sender = registry.get_agent(sender_agent_id)
    sender_name = sender.name if sender else sender_agent_id

    # Build inter-agent session ID
    session_id = f"agent:{target_agent_id}:interagent:{sender_agent_id}"

    # Load target agent's config
    from vulti_cli.config import load_config

    agent_config = load_config(agent_id=target_agent_id)
    model = agent_config.get("model", "anthropic/claude-opus-4.6")

    # Load target agent's soul and memory for context
    soul_path = registry.agent_soul_path(target_agent_id)
    memory_dir = registry.agent_memories_dir(target_agent_id)

    # Prepare environment for the target agent
    agent_env = {
        "VULTI_AGENT_ID": target_agent_id,
        "VULTI_AGENT_HOP_COUNT": str(hop_count + 1),
    }

    # Set env vars for the agent run
    old_env = {}
    for k, v in agent_env.items():
        old_env[k] = os.environ.get(k)
        os.environ[k] = v

    try:
        from run_agent import AIAgent

        agent = AIAgent(
            model=model,
            max_iterations=30,  # Limit inter-agent turns
            quiet_mode=True,
            platform="interagent",
            session_id=session_id,
        )

        # Prepend context about who is messaging
        context_message = (
            f"[Inter-agent message from {sender_name} (agent:{sender_agent_id})]\n\n"
            f"{message}"
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

    finally:
        # Restore environment
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
