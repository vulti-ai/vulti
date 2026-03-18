"""
VultiGatewayRunner — multi-agent gateway on top of upstream hermes-agent.

Subclasses hermes-agent's GatewayRunner to add:
  - Multi-agent routing (@mention, routing table, default agent)
  - AgentContext scoping per message
  - Per-agent AIAgent creation via AgentFactory
  - Agent registry initialization

The upstream GatewayRunner handles all platform adapters, session management,
command processing, and message delivery. We only override the parts that
need multi-agent awareness.
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional

from orchestrator.agent_context import AgentContext
from orchestrator.agent_factory import AgentFactory
from orchestrator.agent_registry import AgentRegistry
from orchestrator.gateway.routing import load_agent_routing, resolve_agent_for_message

logger = logging.getLogger(__name__)


class VultiGatewayRunner:
    """Multi-agent gateway runner wrapping hermes-agent's GatewayRunner.

    Usage::

        from orchestrator.gateway.runner import VultiGatewayRunner
        runner = VultiGatewayRunner()
        await runner.run()
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

        # Create the base gateway runner
        self._runner = GatewayRunner(self.config)

        # Monkey-patch the base runner's _handle_message to inject agent routing.
        # We save the original and wrap it with agent context scoping.
        self._original_handle_message = self._runner._handle_message
        self._runner._handle_message = self._handle_message_with_agent_routing

    async def _handle_message_with_agent_routing(self, event) -> Optional[str]:
        """Wrap upstream _handle_message with multi-agent routing and scoping.

        1. Resolve which agent should handle this message
        2. Strip @mention from message text if present
        3. Set AgentContext so all downstream code sees the correct agent
        4. Delegate to the upstream _handle_message
        """
        source = event.source
        platform_name = source.platform.value if hasattr(source.platform, "value") else str(source.platform)

        # Resolve target agent
        agent_id, clean_text = resolve_agent_for_message(
            platform=platform_name,
            chat_id=str(source.chat_id),
            message_text=event.text or "",
            registry=self.registry,
            routing_table=self.routing_table,
        )

        # Update event text if @mention was stripped
        if clean_text != (event.text or ""):
            event.text = clean_text

        # Store agent_id on event for downstream access
        event._agent_id = agent_id

        # Run the upstream handler within agent context scope.
        # AgentContext.scope() sets both thread-local and VULTI_AGENT_ID env var,
        # so hermes-agent code that reads the env var gets the right agent.
        with AgentContext.scope(agent_id, hop_count=0):
            return await self._original_handle_message(event)

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

    async def start(self):
        """Start the gateway."""
        return await self._runner.start()

    async def stop(self):
        """Stop the gateway."""
        return await self._runner.stop()

    async def run(self):
        """Run the gateway until stopped."""
        return await self._runner.run()

    def __getattr__(self, name):
        """Proxy attribute access to the base runner for compatibility."""
        return getattr(self._runner, name)
