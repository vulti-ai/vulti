"""
Inter-agent messaging bus.

Delegates to orchestrator.agent_bus which uses AgentContext and AgentFactory
for proper thread-safe agent scoping instead of raw environment variables.

Session keys for inter-agent messages use the format:
    agent:{target_agent_id}:interagent:{sender_agent_id}
"""

# Re-export from orchestrator — all callers of gateway.agent_bus continue to work.
from orchestrator.agent_bus import send_to_agent, MAX_HOP_COUNT  # noqa: F401
