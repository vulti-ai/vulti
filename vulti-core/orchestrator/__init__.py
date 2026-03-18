"""
Vulti Orchestrator — multi-agent layer over hermes-agent.

Provides agent lifecycle management, inter-agent messaging, rules engine,
cron scheduling, and gateway routing on top of hermes-agent's AIAgent.

Usage::

    import orchestrator
    orchestrator.init()  # Call once at startup

    # Then use VultiGatewayRunner instead of GatewayRunner
    from orchestrator.gateway.runner import VultiGatewayRunner
    runner = VultiGatewayRunner()
    await runner.run()
"""

from orchestrator.agent_context import AgentContext
from orchestrator.agent_factory import AgentFactory
from orchestrator.agent_registry import AgentRegistry

__all__ = ["AgentContext", "AgentFactory", "AgentRegistry", "init"]

_initialized = False


def init():
    """Initialize the orchestrator — call once at startup.

    This:
    1. Registers vulti-specific tools into hermes-agent's tool registry
    2. Monkey-patches send_message to support inter-agent messaging
    3. Monkey-patches AIAgent._build_system_prompt for per-agent enrichment
    4. Ensures the agent registry is initialized

    Safe to call multiple times — initializes only once.
    """
    global _initialized
    if _initialized:
        return

    # 1. Register vulti-specific tools
    _register_vulti_tools()

    # 2. Patch send_message for inter-agent messaging
    from orchestrator.tools.send_message_ext import patch_send_message
    patch_send_message()

    # 3. Patch prompt builder for per-agent enrichment
    from orchestrator.hooks.prompt_hook import patch_prompt_builder
    patch_prompt_builder()

    # 4. Ensure agent registry exists
    registry = AgentRegistry()
    registry.ensure_initialized()

    _initialized = True


def _register_vulti_tools():
    """Register Vulti-specific tools into the hermes-agent tool registry.

    Import-time side effects in each module trigger registry.register().
    """
    try:
        import orchestrator.tools.rule_tools  # noqa: F401
    except ImportError:
        pass
    try:
        import orchestrator.tools.cronjob_tools  # noqa: F401
    except ImportError:
        pass
