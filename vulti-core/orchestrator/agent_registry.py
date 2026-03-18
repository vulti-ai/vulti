"""
Multi-agent registry for Vulti.

Re-exports from vulti_cli.agent_registry for the orchestrator package.
In Phase 2 (dependency flip), this becomes the canonical location and
vulti_cli.agent_registry is removed.
"""

# Phase 1: re-export from existing location to avoid duplicate code.
# All consumers should import from orchestrator.agent_registry going forward.
from vulti_cli.agent_registry import (  # noqa: F401
    AgentMeta,
    AgentRegistry,
    DEFAULT_AGENT_ID,
    get_default_agent_id,
)
