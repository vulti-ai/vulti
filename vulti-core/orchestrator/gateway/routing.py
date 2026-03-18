"""
Agent routing — resolves which agent should handle an incoming message.

Supports three resolution strategies in priority order:
1. @mention syntax: ``@agent-id message text``
2. Routing table: maps (platform, chat_id) → agent_id
3. Default agent: falls back to the registry's default agent

The routing table is stored in ~/.vulti/gateway.json under the
``agent_routing`` key.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from orchestrator.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)

# Matches @agent-id at the start of a message
_MENTION_RE = re.compile(r"^@([a-z][a-z0-9\-]{0,31})\b\s*(.*)", re.DOTALL)


def load_agent_routing(vulti_home: Optional[Path] = None) -> Dict[str, str]:
    """Load the agent routing table from gateway.json.

    Returns:
        Dict mapping ``"platform:chat_id"`` → ``agent_id``.
    """
    if vulti_home is None:
        from vulti_cli.config import get_vulti_home
        vulti_home = get_vulti_home()

    gateway_path = vulti_home / "gateway.json"
    if not gateway_path.exists():
        return {}

    try:
        with open(gateway_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("agent_routing", {})
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load agent routing: %s", e)
        return {}


def resolve_agent_for_message(
    platform: str,
    chat_id: str,
    message_text: str,
    registry: AgentRegistry,
    routing_table: Optional[Dict[str, str]] = None,
) -> Tuple[str, str]:
    """Determine which agent should handle a message.

    Args:
        platform: Platform name (e.g. "telegram", "discord").
        chat_id: Platform-specific chat/channel identifier.
        message_text: The raw message text.
        registry: Agent registry instance.
        routing_table: Optional pre-loaded routing table.

    Returns:
        Tuple of (agent_id, cleaned_message_text).
        If an @mention was found, the mention prefix is stripped from the message.
    """
    # 1. Check for @agent mention
    match = _MENTION_RE.match(message_text)
    if match:
        mentioned_id = match.group(1)
        rest = match.group(2)
        if registry.get_agent(mentioned_id) is not None:
            return mentioned_id, rest

    # 2. Check routing table
    if routing_table:
        key = f"{platform}:{chat_id}"
        routed = routing_table.get(key)
        if routed and registry.get_agent(routed) is not None:
            return routed, message_text

    # 3. Fall back to default agent
    return registry.default_agent_id, message_text
