"""
Prompt hooks — enriches upstream AIAgent system prompts with per-agent context.

Monkey-patches AIAgent._build_system_prompt to append:
  - Per-agent SOUL.md (if VULTI_AGENT_ID is set)
  - Active rules block (condition/action pairs)
  - Agent identity context (list of peer agents)

Call ``patch_prompt_builder()`` once at startup.

The upstream _build_system_prompt already reads env vars for some context.
AgentContext.scope() sets VULTI_AGENT_ID, which the upstream prompt_builder
may not read — so we append our content after the upstream builds its prompt.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from orchestrator.agent_context import AgentContext

logger = logging.getLogger(__name__)

_patched = False


def patch_prompt_builder():
    """Monkey-patch AIAgent._build_system_prompt to inject vulti-specific context.

    Safe to call multiple times — patches only once.
    """
    global _patched
    if _patched:
        return

    try:
        from run_agent import AIAgent
    except ImportError:
        logger.debug("run_agent.AIAgent not available — skipping prompt patch")
        return

    _original_build = AIAgent._build_system_prompt

    def _vulti_build_system_prompt(self, system_message=None):
        """Build system prompt with vulti multi-agent enrichment."""
        # Call upstream to get the base prompt
        base_prompt = _original_build(self, system_message)

        # Enrich with per-agent context
        agent_id = AgentContext.current_agent_id()
        extra_parts = []

        # Per-agent SOUL.md (if not already loaded by upstream)
        soul = get_agent_soul(agent_id)
        if soul and soul not in base_prompt:
            extra_parts.append(soul)

        # Active rules
        rules = get_agent_rules_prompt(agent_id)
        if rules:
            extra_parts.append(rules)

        # Agent identity context (peer agents)
        identity = get_agent_identity_context(agent_id)
        if identity:
            extra_parts.append(identity)

        if extra_parts:
            return base_prompt + "\n\n" + "\n\n".join(extra_parts)
        return base_prompt

    AIAgent._build_system_prompt = _vulti_build_system_prompt
    _patched = True
    logger.debug("Patched AIAgent._build_system_prompt with vulti enrichment")


def get_agent_soul(agent_id: Optional[str] = None) -> str:
    """Load the SOUL.md content for a specific agent.

    Checks per-agent directory first, falls back to global SOUL.md.
    Returns empty string if no soul file exists.
    """
    agent_id = agent_id or AgentContext.current_agent_id()
    vulti_home = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))

    # Per-agent soul
    if agent_id:
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
    """Build the active rules block for a specific agent."""
    agent_id = agent_id or AgentContext.current_agent_id()
    try:
        from rules.rules import get_active_rules
    except ImportError:
        return ""

    rules = get_active_rules(agent_id)
    if not rules:
        return ""

    MAX_RULES = 20
    MAX_CHARS = 200

    shown = rules[:MAX_RULES]
    lines = []
    for r in shown:
        name = r.get("name", "unnamed")
        rid = r["id"]
        cond = r.get("condition", "").strip().replace("\n", " ")[:MAX_CHARS]
        act = r.get("action", "").strip().replace("\n", " ")[:MAX_CHARS]
        lines.append(f'  [p={r.get("priority", 0)}] {name} (id:{rid}): IF "{cond}" THEN "{act}"')

    rules_block = "\n".join(lines)
    overflow = ""
    if len(rules) > MAX_RULES:
        overflow = f"\n  ({len(rules) - MAX_RULES} more rules not shown)"

    return (
        "## Active Rules\n\n"
        "You have conditional rules. For EVERY incoming message, silently evaluate whether\n"
        "any rule's condition matches. If a rule matches, execute its action using your\n"
        "tools BEFORE composing your normal response. Multiple rules can match the same message.\n"
        "Execute them in priority order (lowest number first). After executing a rule's action,\n"
        "call rule(action='record', rule_id='...') to log the trigger.\n"
        "Do not mention rule evaluation to the user unless the rule's action produces a visible result.\n"
        "If no rules match, proceed normally without mentioning rules.\n\n"
        "<rules>\n"
        f"{rules_block}{overflow}\n"
        "</rules>"
    )


def get_agent_identity_context(agent_id: Optional[str] = None) -> str:
    """Build an identity context block listing other available agents."""
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
