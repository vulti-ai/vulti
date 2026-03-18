"""
Send message extension — adds inter-agent messaging to upstream send_message tool.

Monkey-patches the upstream tools.send_message_tool to intercept
``target="agent:<agent_id>"`` and route through the orchestrator's agent bus.
Also patches the ``list`` action to include available agents.

Call ``patch_send_message()`` once at startup.
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_patched = False


def patch_send_message():
    """Monkey-patch the upstream send_message tool to support inter-agent messaging.

    Safe to call multiple times — patches only once.
    """
    global _patched
    if _patched:
        return

    try:
        import tools.send_message_tool as smt
    except ImportError:
        logger.debug("tools.send_message_tool not available — skipping patch")
        return

    # Save original handler
    _original_send_message = smt.send_message

    def _vulti_send_message(args: str) -> str:
        """Extended send_message that supports agent: targets."""
        parsed = json.loads(args) if isinstance(args, str) else args

        # Check for agent: target
        target = ""
        if isinstance(parsed, dict):
            target = parsed.get("target", "")
        elif isinstance(parsed, str):
            target = parsed

        if isinstance(target, str) and target.startswith("agent:"):
            agent_id = target[len("agent:"):]
            message = parsed.get("message", "") if isinstance(parsed, dict) else ""
            return _handle_agent_send(agent_id, message)

        # Check for list action
        action = parsed.get("action", "") if isinstance(parsed, dict) else ""
        if action == "list":
            return _handle_list_with_agents()

        # Delegate to upstream
        return _original_send_message(args)

    # Patch the module-level function
    smt.send_message = _vulti_send_message

    # Also patch the registry entry if tools use the registry
    try:
        from tools.registry import registry
        if "send_message" in registry._tools:
            registry._tools["send_message"]["function"] = _vulti_send_message
    except Exception:
        pass

    _patched = True
    logger.debug("Patched send_message tool with inter-agent support")


def _handle_agent_send(target_agent_id: str, message: str) -> str:
    """Send a message to another agent via the inter-agent bus."""
    from orchestrator.agent_context import AgentContext

    hop_count = AgentContext.current_hop_count()
    sender_agent_id = AgentContext.current_agent_id()

    if hop_count >= 3:
        return json.dumps({
            "error": "Max inter-agent hop count reached (3). "
            "Cannot send further inter-agent messages to prevent loops."
        })

    try:
        import asyncio
        from orchestrator.agent_bus import send_to_agent

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    asyncio.run,
                    send_to_agent(
                        target_agent_id=target_agent_id,
                        message=message,
                        sender_agent_id=sender_agent_id,
                        hop_count=hop_count,
                    ),
                ).result(timeout=180)
        else:
            result = asyncio.run(send_to_agent(
                target_agent_id=target_agent_id,
                message=message,
                sender_agent_id=sender_agent_id,
                hop_count=hop_count,
            ))

        return json.dumps(result)
    except Exception as e:
        logger.error("Inter-agent send to '%s' failed: %s", target_agent_id, e)
        return json.dumps({"error": f"Failed to send to agent '{target_agent_id}': {e}"})


def _handle_list_with_agents() -> str:
    """Return formatted list of messaging targets including agents."""
    result = {}

    # Get upstream channel directory
    try:
        from gateway.channel_directory import format_directory_for_display
        result["targets"] = format_directory_for_display()
    except Exception as e:
        result["targets"] = f"Failed to load channel directory: {e}"

    # Add available agents
    try:
        from orchestrator.agent_registry import AgentRegistry
        from orchestrator.agent_context import AgentContext

        registry = AgentRegistry()
        current_agent = AgentContext.current_agent_id()
        agents = [
            f"agent:{a.id} — {a.name} ({a.description})"
            for a in registry.list_agents()
            if a.id != current_agent and a.status == "active"
        ]
        if agents:
            result["agents"] = agents
    except Exception:
        pass

    return json.dumps(result)
