"""
Send message extension — adds inter-agent messaging (agent: targets).

In Phase 2, this will hook into hermes-agent's send_message tool
to add the ``target="agent:agent_id"`` routing via the orchestrator's
agent bus.
"""

try:
    import tools.send_message_tool  # noqa: F401
except ImportError:
    pass
