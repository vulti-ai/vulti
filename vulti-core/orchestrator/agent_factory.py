"""
Agent factory — creates AIAgent instances configured for specific registered agents.

Reads per-agent config from the registry, resolves provider credentials,
and returns a properly-configured AIAgent wrapped in an AgentContext scope.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from orchestrator.agent_context import AgentContext
from orchestrator.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)


class AgentFactory:
    """Creates AIAgent instances scoped to registered agents."""

    def __init__(self, registry: Optional[AgentRegistry] = None):
        self.registry = registry or AgentRegistry()

    def create_agent(self, agent_id: str, **overrides) -> "AIAgent":
        """Build an AIAgent configured for a specific registered agent.

        Loads the agent's config.yaml, resolves provider credentials, and
        returns a ready-to-use AIAgent instance. The caller is responsible
        for wrapping execution in ``AgentContext.scope(agent_id)``.

        Args:
            agent_id: ID of the registered agent.
            **overrides: Keyword arguments passed directly to AIAgent,
                         overriding values from config.

        Returns:
            A configured AIAgent instance.
        """
        from run_agent import AIAgent
        from vulti_cli.config import load_config

        config = load_config(agent_id=agent_id)

        # Resolve model — agent config > user default > hardcoded fallback
        import os
        _user_default = os.getenv("VULTI_DEFAULT_MODEL") or "anthropic/claude-opus-4.6"
        model_cfg = config.get("model", {})
        if isinstance(model_cfg, str):
            model = model_cfg
        elif isinstance(model_cfg, dict):
            model = model_cfg.get("default", _user_default)
        else:
            model = _user_default

        # Resolve provider credentials
        runtime = self._resolve_runtime(config, overrides)

        # Agent-level settings
        agent_cfg = config.get("agent", {})
        max_iterations = overrides.pop("max_iterations", None) or agent_cfg.get("max_turns", 90)

        # Reasoning config
        reasoning_config = overrides.pop("reasoning_config", None)
        if reasoning_config is None:
            effort = str(agent_cfg.get("reasoning_effort", "")).strip()
            if effort and effort.lower() != "none":
                valid = ("xhigh", "high", "medium", "low", "minimal")
                if effort.lower() in valid:
                    reasoning_config = {"enabled": True, "effort": effort.lower()}
            elif effort.lower() == "none":
                reasoning_config = {"enabled": False}

        # Toolsets — handle both dict format {"enabled": [...]} and plain list format
        enabled_toolsets = overrides.pop("enabled_toolsets", None)
        disabled_toolsets = overrides.pop("disabled_toolsets", None)
        if enabled_toolsets is None:
            ts_cfg = config.get("toolsets", {})
            if isinstance(ts_cfg, list):
                enabled_toolsets = ts_cfg
            elif isinstance(ts_cfg, dict):
                enabled_toolsets = ts_cfg.get("enabled")
        if disabled_toolsets is None:
            ts_cfg = config.get("toolsets", {})
            if isinstance(ts_cfg, dict):
                disabled_toolsets = ts_cfg.get("disabled")

        # Session DB
        session_db = overrides.pop("session_db", None)
        if session_db is None:
            try:
                from vulti_state import SessionDB
                session_db = SessionDB()
            except Exception:
                pass

        agent = AIAgent(
            model=overrides.pop("model", model),
            api_key=runtime.get("api_key"),
            base_url=runtime.get("base_url"),
            provider=runtime.get("provider"),
            api_mode=runtime.get("api_mode"),
            max_iterations=max_iterations,
            reasoning_config=reasoning_config,
            enabled_toolsets=enabled_toolsets,
            disabled_toolsets=disabled_toolsets,
            quiet_mode=overrides.pop("quiet_mode", True),
            session_db=session_db,
            **overrides,
        )
        return agent

    def run_in_context(
        self,
        agent_id: str,
        message: str,
        hop_count: int = 0,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create an agent and run a conversation within the proper agent context.

        This is the primary high-level API for running an agent turn.

        Args:
            agent_id: Registered agent ID.
            message: User message to process.
            hop_count: Inter-agent hop count (for circular prevention).
            **kwargs: Additional overrides for create_agent.

        Returns:
            The result dict from AIAgent.run_conversation().
        """
        # Check budget before running
        from orchestrator.budget import check_budget, record_usage
        budget_error = check_budget(agent_id)
        if budget_error:
            return {"final_response": f"[Budget exceeded] {budget_error}", "error": budget_error}

        with AgentContext.scope(agent_id, hop_count=hop_count):
            agent = self.create_agent(agent_id, **kwargs)
            result = agent.run_conversation(message)

            # Record usage from the result
            usage = result.get("usage", {})
            if usage:
                record_usage(
                    agent_id,
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    model=result.get("model", ""),
                )

            return result

    def _resolve_runtime(
        self, config: Dict[str, Any], overrides: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Resolve provider credentials from config + environment."""
        from vulti_cli.runtime_provider import (
            resolve_runtime_provider,
            format_runtime_provider_error,
        )

        try:
            runtime_kwargs = {
                "requested": overrides.pop("provider_requested", None)
                or os.getenv("VULTI_INFERENCE_PROVIDER"),
            }
            explicit_base_url = overrides.pop("explicit_base_url", None)
            if explicit_base_url:
                runtime_kwargs["explicit_base_url"] = explicit_base_url

            return resolve_runtime_provider(**runtime_kwargs)
        except Exception as exc:
            message = format_runtime_provider_error(exc)
            raise RuntimeError(message) from exc
