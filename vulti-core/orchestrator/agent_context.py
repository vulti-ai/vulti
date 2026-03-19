"""
Thread-local agent context for multi-agent scoping.

Replaces the VULTI_AGENT_ID environment variable pattern with a
thread-safe context manager. Still sets the env var for backward
compatibility with hermes-agent internals and tools that read it.
"""

import os
import threading
from contextlib import contextmanager
from typing import Optional


class AgentContext:
    """Thread-local storage for the currently-active agent ID.

    Usage::

        with AgentContext.scope("my-agent"):
            # All code in this block sees agent_id = "my-agent"
            agent = factory.create_agent("my-agent")
            agent.run_conversation(message)
    """

    _local = threading.local()

    @classmethod
    def current_agent_id(cls) -> str:
        """Return the active agent ID, defaulting to 'default'."""
        return getattr(cls._local, "agent_id", None) or "default"

    @classmethod
    def current_hop_count(cls) -> int:
        """Return the current inter-agent hop count."""
        return getattr(cls._local, "hop_count", None) or 0

    @classmethod
    def current_trace_id(cls) -> Optional[str]:
        """Return the active trace ID for this thread."""
        return getattr(cls._local, "trace_id", None) or os.getenv("VULTI_TRACE_ID")

    @classmethod
    @contextmanager
    def scope(cls, agent_id: str, hop_count: Optional[int] = None,
              trace_id: Optional[str] = None):
        """Context manager that sets the active agent for the current thread.

        Sets both the thread-local and the ``VULTI_AGENT_ID`` / ``VULTI_AGENT_HOP_COUNT``
        environment variables so that hermes-agent tools and modules that read
        from the environment continue to work.

        If *trace_id* is provided, it is set on the thread-local and in the
        ``VULTI_TRACE_ID`` environment variable for propagation.  If omitted
        and no trace is already active, a new one is generated.
        """
        from orchestrator.audit import new_trace_id, set_trace_id, clear_trace_id, current_trace_id

        # Save previous state
        prev_agent = getattr(cls._local, "agent_id", None)
        prev_hop = getattr(cls._local, "hop_count", None)
        prev_trace = getattr(cls._local, "trace_id", None)
        prev_env_agent = os.environ.get("VULTI_AGENT_ID")
        prev_env_hop = os.environ.get("VULTI_AGENT_HOP_COUNT")
        prev_env_trace = os.environ.get("VULTI_TRACE_ID")

        # Set new state
        cls._local.agent_id = agent_id
        os.environ["VULTI_AGENT_ID"] = agent_id

        if hop_count is not None:
            cls._local.hop_count = hop_count
            os.environ["VULTI_AGENT_HOP_COUNT"] = str(hop_count)

        # Trace ID: use provided > inherit existing > generate new
        resolved_trace = trace_id or current_trace_id() or new_trace_id()
        cls._local.trace_id = resolved_trace
        set_trace_id(resolved_trace)

        try:
            yield
        finally:
            # Restore previous state
            cls._local.agent_id = prev_agent
            cls._local.hop_count = prev_hop
            cls._local.trace_id = prev_trace

            if prev_env_agent is None:
                os.environ.pop("VULTI_AGENT_ID", None)
            else:
                os.environ["VULTI_AGENT_ID"] = prev_env_agent

            if prev_env_hop is None:
                os.environ.pop("VULTI_AGENT_HOP_COUNT", None)
            else:
                os.environ["VULTI_AGENT_HOP_COUNT"] = prev_env_hop

            if prev_env_trace is None:
                os.environ.pop("VULTI_TRACE_ID", None)
            else:
                os.environ["VULTI_TRACE_ID"] = prev_env_trace

            if prev_trace:
                cls._local.trace_id = prev_trace
            else:
                clear_trace_id()
