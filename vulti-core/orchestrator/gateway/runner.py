"""
VultiGatewayRunner — multi-agent gateway built on hermes-agent's GatewayRunner.

Phase 1: Thin subclass that adds orchestrator-aware agent resolution and
AgentContext scoping. The base GatewayRunner already contains the multi-agent
code inline; this module extracts the pattern so that in Phase 2 (when
hermes-agent becomes a clean external dependency) we can override without
modifying upstream code.

Phase 2 plan: Override _handle_message to wrap agent execution in
AgentContext.scope(), and override _create_agent (once contributed upstream)
to use AgentFactory.
"""

import logging
from typing import Dict, Optional

from orchestrator.agent_context import AgentContext
from orchestrator.agent_factory import AgentFactory
from orchestrator.agent_registry import AgentRegistry
from orchestrator.gateway.routing import load_agent_routing, resolve_agent_for_message

logger = logging.getLogger(__name__)


class VultiGatewayRunner:
    """Multi-agent gateway runner.

    In Phase 1, this is a composition wrapper around the existing GatewayRunner.
    It initializes orchestrator components and provides the same public interface.

    In Phase 2, this will subclass hermes-agent's GatewayRunner directly and
    override key methods for agent scoping.
    """

    def __init__(self, config=None):
        from gateway.run import GatewayRunner
        from gateway.config import load_gateway_config

        self.config = config or load_gateway_config()

        # Orchestrator components
        self.registry = AgentRegistry()
        self.registry.ensure_initialized()
        self.routing_table = load_agent_routing()
        self.factory = AgentFactory(self.registry)

        # Delegate to base gateway runner
        self._runner = GatewayRunner(self.config)

    def resolve_agent(self, platform: str, chat_id: str, message_text: str):
        """Resolve which agent should handle a message.

        Returns (agent_id, cleaned_message_text).
        """
        return resolve_agent_for_message(
            platform=platform,
            chat_id=chat_id,
            message_text=message_text,
            registry=self.registry,
            routing_table=self.routing_table,
        )

    def create_agent_for_turn(self, agent_id: str, **kwargs):
        """Create an AIAgent instance configured for a specific agent.

        The returned agent should be run within an AgentContext.scope().
        """
        return self.factory.create_agent(agent_id, **kwargs)

    async def start(self):
        """Start the gateway (delegates to base runner)."""
        return await self._runner.start()

    async def stop(self):
        """Stop the gateway (delegates to base runner)."""
        return await self._runner.stop()

    async def run(self):
        """Run the gateway until stopped (delegates to base runner)."""
        return await self._runner.run()
