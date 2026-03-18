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
        return getattr(cls._local, "agent_id", "default")

    @classmethod
    def current_hop_count(cls) -> int:
        """Return the current inter-agent hop count."""
        return getattr(cls._local, "hop_count", 0)

    @classmethod
    @contextmanager
    def scope(cls, agent_id: str, hop_count: Optional[int] = None):
        """Context manager that sets the active agent for the current thread.

        Sets both the thread-local and the ``VULTI_AGENT_ID`` / ``VULTI_AGENT_HOP_COUNT``
        environment variables so that hermes-agent tools and modules that read
        from the environment continue to work.
        """
        # Save previous state
        prev_agent = getattr(cls._local, "agent_id", None)
        prev_hop = getattr(cls._local, "hop_count", None)
        prev_env_agent = os.environ.get("VULTI_AGENT_ID")
        prev_env_hop = os.environ.get("VULTI_AGENT_HOP_COUNT")

        # Set new state
        cls._local.agent_id = agent_id
        os.environ["VULTI_AGENT_ID"] = agent_id

        if hop_count is not None:
            cls._local.hop_count = hop_count
            os.environ["VULTI_AGENT_HOP_COUNT"] = str(hop_count)

        try:
            yield
        finally:
            # Restore previous state
            cls._local.agent_id = prev_agent
            cls._local.hop_count = prev_hop

            if prev_env_agent is None:
                os.environ.pop("VULTI_AGENT_ID", None)
            else:
                os.environ["VULTI_AGENT_ID"] = prev_env_agent

            if prev_env_hop is None:
                os.environ.pop("VULTI_AGENT_HOP_COUNT", None)
            else:
                os.environ["VULTI_AGENT_HOP_COUNT"] = prev_env_hop
