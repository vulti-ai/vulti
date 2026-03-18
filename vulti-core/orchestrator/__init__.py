"""
Vulti Orchestrator — multi-agent layer over Hermes Agent.

Provides agent lifecycle management, inter-agent messaging, rules engine,
cron scheduling, and gateway routing on top of hermes-agent's AIAgent.
"""

from orchestrator.agent_context import AgentContext
from orchestrator.agent_factory import AgentFactory
from orchestrator.agent_registry import AgentRegistry

__all__ = ["AgentContext", "AgentFactory", "AgentRegistry"]


def register_vulti_tools():
    """Register Vulti-specific tools into the hermes-agent tool registry.

    Call this once at startup before any AIAgent instances are created.
    Import-time side effects in each module trigger registry.register().
    """
    import orchestrator.tools.rule_tools  # noqa: F401
    import orchestrator.tools.cronjob_tools  # noqa: F401
    import orchestrator.tools.send_message_ext  # noqa: F401
