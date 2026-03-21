"""
Coroutine-safe agent context for multi-agent scoping.

Uses ``contextvars.ContextVar`` so that each asyncio Task (coroutine)
gets its own agent identity — critical when multiple agents handle
messages concurrently on the same event loop thread.

Still sets ``os.environ["VULTI_AGENT_ID"]`` for backward compatibility
with hermes-agent internals and tools that read the env var, but the
**authoritative** source is now ``AgentContext.current_agent_id()``
which reads the ContextVar.
"""

import contextvars
import os
from contextlib import contextmanager
from typing import Optional


# ContextVars — per-coroutine (asyncio-safe) and per-thread (sync-safe)
_agent_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "vulti_agent_id", default=None
)
_hop_count_var: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "vulti_hop_count", default=None
)
_trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "vulti_trace_id", default=None
)


class AgentContext:
    """Coroutine-safe storage for the currently-active agent ID.

    Usage::

        with AgentContext.scope("my-agent"):
            # All code in this block sees agent_id = "my-agent"
            agent = factory.create_agent("my-agent")
            agent.run_conversation(message)

    In asyncio, each coroutine gets its own copy of the context vars
    so concurrent agents don't interfere with each other.
    """

    @classmethod
    def current_agent_id(cls) -> str:
        """Return the active agent ID.

        Priority: ContextVar > env var > empty string.
        """
        return _agent_id_var.get() or os.getenv("VULTI_AGENT_ID") or ""

    @classmethod
    def current_hop_count(cls) -> int:
        """Return the current inter-agent hop count."""
        return _hop_count_var.get() or 0

    @classmethod
    def current_trace_id(cls) -> Optional[str]:
        """Return the active trace ID."""
        return _trace_id_var.get() or os.getenv("VULTI_TRACE_ID")

    @classmethod
    @contextmanager
    def scope(cls, agent_id: str, hop_count: Optional[int] = None,
              trace_id: Optional[str] = None):
        """Context manager that sets the active agent for the current context.

        Sets both the ContextVar and the ``VULTI_AGENT_ID`` environment variable
        so that hermes-agent tools and modules that read from the environment
        continue to work.

        If *trace_id* is provided, it is set on the ContextVar and in the
        ``VULTI_TRACE_ID`` environment variable for propagation.  If omitted
        and no trace is already active, a new one is generated.
        """
        from orchestrator.audit import new_trace_id, set_trace_id, clear_trace_id, current_trace_id

        # Save previous env state (for backward-compat env var management)
        prev_env_agent = os.environ.get("VULTI_AGENT_ID")
        prev_env_hop = os.environ.get("VULTI_AGENT_HOP_COUNT")
        prev_env_trace = os.environ.get("VULTI_TRACE_ID")

        # Set ContextVars (coroutine-safe)
        token_agent = _agent_id_var.set(agent_id)
        token_hop = None
        token_trace = None

        # Set env vars (backward compat — not coroutine-safe but many tools read these)
        os.environ["VULTI_AGENT_ID"] = agent_id

        if hop_count is not None:
            token_hop = _hop_count_var.set(hop_count)
            os.environ["VULTI_AGENT_HOP_COUNT"] = str(hop_count)

        # Trace ID: use provided > inherit existing > generate new
        resolved_trace = trace_id or current_trace_id() or new_trace_id()
        token_trace = _trace_id_var.set(resolved_trace)
        set_trace_id(resolved_trace)

        try:
            yield
        finally:
            # Restore ContextVars
            _agent_id_var.reset(token_agent)
            if token_hop is not None:
                _hop_count_var.reset(token_hop)
            if token_trace is not None:
                _trace_id_var.reset(token_trace)

            # Restore env vars
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

            if _trace_id_var.get() is None:
                clear_trace_id()
