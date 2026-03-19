"""
Inter-agent messaging bus — gateway compatibility shim.

This module re-exports the canonical implementation from
``orchestrator.agent_bus`` so that existing gateway code that imports
``gateway.agent_bus.send_to_agent`` continues to work unchanged.
"""

from orchestrator.agent_bus import send_to_agent, MAX_HOP_COUNT  # noqa: F401
