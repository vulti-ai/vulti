"""Tests for orchestrator/agent_bus.py — inter-agent messaging."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from orchestrator.agent_bus import MAX_HOP_COUNT, send_to_agent


class TestHopLimit:
    def test_max_hop_count_is_one(self):
        assert MAX_HOP_COUNT == 1

    @pytest.mark.asyncio
    async def test_rejects_nested_hops(self):
        result = await send_to_agent(
            target_agent_id="researcher",
            message="hello",
            sender_agent_id="scout",
            hop_count=1,  # Already at max
        )
        assert "error" in result
        assert "nesting not allowed" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_allows_first_hop(self):
        mock_meta = MagicMock()
        mock_meta.id = "researcher"
        mock_meta.name = "Researcher"

        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = mock_meta
        mock_registry.list_agents.return_value = [mock_meta]

        mock_agent = MagicMock()
        mock_agent.run_conversation.return_value = {"final_response": "Got it!"}

        mock_factory_instance = MagicMock()
        mock_factory_instance.create_agent.return_value = mock_agent

        with patch("orchestrator.agent_bus.AgentRegistry", return_value=mock_registry), \
             patch("orchestrator.agent_factory.AgentFactory", return_value=mock_factory_instance), \
             patch("orchestrator.agent_bus.audit_emit"), \
             patch("orchestrator.agent_bus._mirror_to_matrix"):
            result = await send_to_agent(
                target_agent_id="researcher",
                message="hello",
                sender_agent_id="scout",
                hop_count=0,
            )

        assert result["response"] == "Got it!"
        assert result["agent_name"] == "Researcher"

    @pytest.mark.asyncio
    async def test_unknown_agent_returns_error(self):
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = None
        mock_registry.list_agents.return_value = []

        with patch("orchestrator.agent_bus.AgentRegistry", return_value=mock_registry):
            result = await send_to_agent(
                target_agent_id="nonexistent",
                message="hello",
                sender_agent_id="scout",
                hop_count=0,
            )

        assert "error" in result
        assert "not found" in result["error"]
