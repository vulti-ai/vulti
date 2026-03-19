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
import copy
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

        # Also patch _resolve_agent_for_source so the base _handle_message
        # uses proper routing instead of the stub that returns "default".
        self._runner._resolve_agent_for_source = self._resolve_agent_for_source

    def _is_broadcast_room(self, chat_id: str) -> bool:
        """Check if a chat_id is the #updates room (broadcast to all agents)."""
        from gateway.config import Platform
        matrix_config = self._runner.config.platforms.get(Platform.MATRIX)
        if matrix_config and matrix_config.home_channel:
            return str(chat_id) == str(matrix_config.home_channel.chat_id)
        return False

    async def _handle_message_with_agent_routing(self, event) -> Optional[str]:
        """Wrap upstream _handle_message with multi-agent routing and scoping.

        1. Resolve which agent should handle this message
        2. Strip @mention from message text if present
        3. Set AgentContext so all downstream code sees the correct agent
        4. Delegate to the upstream _handle_message

        For broadcast rooms (#updates): if no @mention, fan out to all agents
        concurrently. Each agent decides independently whether to respond.
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

        # Broadcast: if message is in #updates with no @mention, fan out to all agents
        has_mention = clean_text != (event.text or "")
        if not has_mention and self._is_broadcast_room(str(source.chat_id)):
            agents = self.registry.list_agents()
            active_ids = [a.id for a in agents if a.status == "active"]
            if len(active_ids) > 1:
                logger.info("Matrix: broadcasting to %d agents in #updates", len(active_ids))

                async def _dispatch_to_agent(aid: str):
                    agent_event = copy.copy(event)
                    agent_event._agent_id = aid
                    with AgentContext.scope(aid, hop_count=0):
                        try:
                            await self._original_handle_message(agent_event)
                        except Exception as e:
                            logger.warning("Matrix: broadcast to %s failed: %s", aid, e)

                await asyncio.gather(*[_dispatch_to_agent(aid) for aid in active_ids])
                return None

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

    def _resolve_agent_for_source(self, source, message_text: str = ""):
        """Override the base runner's stub to use proper multi-agent routing."""
        platform_name = source.platform.value if hasattr(source.platform, "value") else str(source.platform)
        return resolve_agent_for_message(
            platform=platform_name,
            chat_id=str(source.chat_id),
            message_text=message_text,
            registry=self.registry,
            routing_table=self.routing_table,
        )

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
