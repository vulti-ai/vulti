"""
Inter-agent messaging bus (canonical implementation).

Allows agents to send messages to other agents via the orchestrator's
AgentFactory and AgentContext. Optionally mirrors exchanges to Matrix
when both agents have credentials.

Session keys for inter-agent messages use the format:
    agent:{target_agent_id}:interagent:{sender_agent_id}

This gives persistent conversation history between agent pairs.
"""

import logging
import os
from typing import Any, Dict, Optional

from orchestrator.agent_context import AgentContext
from orchestrator.audit import emit as audit_emit
from orchestrator.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)

MAX_HOP_COUNT = 1


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

    After a successful exchange, the messages are mirrored to Matrix if
    both agents have Matrix credentials.

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
                "Inter-agent nesting not allowed. "
                "Agents cannot forward messages to other agents within an inter-agent call. "
                "If you need another agent's help, note it in your response and initiate "
                "a separate conversation on your own."
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

        audit_emit("interagent_send", agent_id=sender_agent_id, details={
            "target": target_agent_id,
            "message_preview": message[:200],
        })

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

        audit_emit("interagent_receive", agent_id=target_agent_id, details={
            "sender": sender_agent_id,
            "response_preview": response[:200],
        })

        # Mirror to Matrix if both agents have credentials
        try:
            _mirror_to_matrix(sender_agent_id, target_agent_id, message, response)
        except Exception as e:
            logger.debug("Matrix mirror for inter-agent msg skipped: %s", e)

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


# ── Matrix mirroring ─────────────────────────────────────────────────

def _mirror_to_matrix(
    sender_agent_id: str,
    target_agent_id: str,
    sent_message: str,
    response: str,
) -> None:
    """Mirror an inter-agent exchange to the appropriate Matrix room.

    Finds the best room: relationship channel > team room > Agent Chatter.
    Posts the sender's message and the target's response.
    """
    import asyncio

    from gateway.matrix_agents import (
        get_agent_matrix_credentials,
        send_room_message,
    )

    sender_creds = get_agent_matrix_credentials(sender_agent_id)
    target_creds = get_agent_matrix_credentials(target_agent_id)
    if not sender_creds or not target_creds:
        return

    homeserver_url = sender_creds.get("homeserver_url", "http://127.0.0.1:6167")

    room_id = _find_shared_room(sender_agent_id, target_agent_id, homeserver_url)
    if not room_id:
        return

    async def _post():
        await send_room_message(homeserver_url, sender_agent_id, room_id, sent_message)
        await send_room_message(homeserver_url, target_agent_id, room_id, response)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            pool.submit(asyncio.run, _post()).result(timeout=15)
    else:
        asyncio.run(_post())


def _find_shared_room(
    agent_a_id: str,
    agent_b_id: str,
    homeserver_url: str,
) -> Optional[str]:
    """Find a Matrix room shared by two agents.

    Checks relationship rooms from the registry first,
    then falls back to the #chatter room.
    """
    try:
        registry = AgentRegistry()
        reg_data = registry._load_registry()
        for rel in reg_data.get("relationships", []):
            room_id = rel.get("matrix_room_id")
            if not room_id:
                continue
            from_id = rel.get("from_agent_id", "")
            to_id = rel.get("to_agent_id", "")
            if {from_id, to_id} == {agent_a_id, agent_b_id}:
                return room_id
    except Exception:
        pass

    # Fall back to #chatter
    try:
        import httpx
        from gateway.matrix_agents import get_agent_matrix_credentials
        creds = get_agent_matrix_credentials(agent_a_id)
        if not creds:
            return None
        server_name = os.getenv("MATRIX_SERVER_NAME", "localhost")
        resp = httpx.get(
            f"{homeserver_url}/_matrix/client/v3/directory/room/%23chatter:{server_name}",
            headers={"Authorization": f"Bearer {creds['access_token']}"},
            timeout=5.0,
        )
        if resp.status_code == 200:
            return resp.json().get("room_id")
    except Exception:
        pass

    return None
