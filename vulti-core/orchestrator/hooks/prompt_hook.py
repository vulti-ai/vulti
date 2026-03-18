"""
Prompt hooks — enriches AIAgent system prompts with per-agent context.

In the current architecture, hermes-agent's prompt_builder.py already
contains the vulti-specific code inline (build_rules_prompt, per-agent
SOUL.md resolution). It reads VULTI_AGENT_ID from the environment,
which AgentContext.scope() sets automatically.

This module provides higher-level functions for when we need to
programmatically inject agent-specific context outside of the
standard _build_system_prompt() flow.

Phase 2 plan: When hermes-agent becomes an external dependency with
an unmodified prompt_builder, these hooks will be called by
VultiGatewayRunner to augment the base system prompt with:
  - Per-agent SOUL.md
  - Active rules block
  - Agent identity context (other available agents)
"""

import logging
import os
from pathlib import Path
from typing import Optional

from orchestrator.agent_context import AgentContext

logger = logging.getLogger(__name__)


def get_agent_soul(agent_id: Optional[str] = None) -> str:
    """Load the SOUL.md content for a specific agent.

    Checks per-agent directory first, falls back to global SOUL.md.
    Returns empty string if no soul file exists.
    """
    agent_id = agent_id or AgentContext.current_agent_id()
    vulti_home = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))

    # Per-agent soul
    if agent_id and agent_id != "default":
        agent_soul = vulti_home / "agents" / agent_id / "SOUL.md"
        if agent_soul.exists():
            try:
                return agent_soul.read_text(encoding="utf-8").strip()
            except Exception as e:
                logger.debug("Could not read agent SOUL.md for %s: %s", agent_id, e)

    # Global fallback
    global_soul = vulti_home / "SOUL.md"
    if global_soul.exists():
        try:
            return global_soul.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.debug("Could not read global SOUL.md: %s", e)

    return ""


def get_agent_rules_prompt(agent_id: Optional[str] = None) -> str:
    """Build the active rules block for a specific agent.

    Delegates to the rules engine's build_rules_prompt.
    """
    agent_id = agent_id or AgentContext.current_agent_id()
    try:
        from agent.prompt_builder import build_rules_prompt
        return build_rules_prompt(agent_id=agent_id)
    except ImportError:
        return ""


def get_agent_identity_context(agent_id: Optional[str] = None) -> str:
    """Build an identity context block listing other available agents.

    This helps agents know about their peers for inter-agent messaging.
    """
    agent_id = agent_id or AgentContext.current_agent_id()

    try:
        from orchestrator.agent_registry import AgentRegistry
        registry = AgentRegistry()
        agents = registry.list_agents()
    except Exception:
        return ""

    others = [a for a in agents if a.id != agent_id and a.status == "active"]
    if not others:
        return ""

    lines = [f"You are agent '{agent_id}'. Other available agents:"]
    for a in others:
        desc = f" — {a.description}" if a.description else ""
        lines.append(f"  - @{a.id} ({a.name}){desc}")
    lines.append("Use send_message(target='agent:<id>', message='...') to communicate with them.")

    return "\n".join(lines)


def enrich_system_prompt(
    base_prompt: str,
    agent_id: Optional[str] = None,
    include_rules: bool = True,
    include_identity: bool = True,
) -> str:
    """Enrich a base system prompt with per-agent orchestrator context.

    This is the main hook for Phase 2, when hermes-agent builds the base
    prompt and the orchestrator adds multi-agent features on top.

    Args:
        base_prompt: The system prompt from hermes-agent's prompt builder.
        agent_id: Agent ID (defaults to AgentContext.current_agent_id()).
        include_rules: Whether to inject the rules block.
        include_identity: Whether to inject the agent identity context.

    Returns:
        The enriched system prompt.
    """
    agent_id = agent_id or AgentContext.current_agent_id()
    parts = [base_prompt]

    if include_rules:
        rules = get_agent_rules_prompt(agent_id)
        if rules:
            parts.append(rules)

    if include_identity:
        identity = get_agent_identity_context(agent_id)
        if identity:
            parts.append(identity)

    return "\n\n".join(parts)
