"""Global connection registry for Vulti.

Manages named connections to external services (MCP servers, API keys, OAuth,
custom). All connections are defined globally in ``~/.vulti/connections.yaml``.
Each agent has an allow list controlling which connections it can use at runtime.

Agents can *see* all connections (names, descriptions, tags) for discovery,
but credentials are only injected for connections on the agent's allow list.
"""

import logging
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ConnectionEntry:
    """A single named connection to an external service."""

    name: str
    type: str  # mcp | api_key | oauth | custom
    description: str = ""
    tags: list[str] = field(default_factory=list)
    credentials: dict[str, str] = field(default_factory=dict)
    mcp: dict[str, Any] = field(default_factory=dict)
    provides_toolsets: list[str] = field(default_factory=list)
    tools: dict[str, Any] = field(default_factory=dict)  # MCP tool include/exclude
    enabled: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        # Drop empty optional fields for cleaner YAML
        for key in ("mcp", "provides_toolsets", "tools", "tags"):
            if not d.get(key):
                d.pop(key, None)
        if d.get("enabled") is True:
            d.pop("enabled", None)
        return d

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "ConnectionEntry":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        filtered["name"] = name
        return cls(**filtered)

    def visible_dict(self) -> dict:
        """Return metadata without credentials, for discovery prompts."""
        return {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "tags": self.tags,
            "provides_toolsets": self.provides_toolsets,
            "enabled": self.enabled,
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ConnectionRegistry:
    """Loads, validates, and provides access to ``connections.yaml``."""

    def __init__(self, vulti_home: Path):
        self._path = vulti_home / "connections.yaml"
        self._vulti_home = vulti_home
        self._cache: Optional[Dict[str, ConnectionEntry]] = None

    # -- I/O ----------------------------------------------------------------

    def load(self) -> Dict[str, ConnectionEntry]:
        """Parse ``connections.yaml`` and return ``{name: ConnectionEntry}``."""
        if self._cache is not None:
            return self._cache

        if not self._path.exists():
            self._cache = {}
            return self._cache

        try:
            import yaml

            raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            logger.warning("Failed to load connections.yaml: %s", e)
            self._cache = {}
            return self._cache

        connections = {}
        for name, entry_data in raw.get("connections", {}).items():
            if not isinstance(entry_data, dict):
                logger.warning("Skipping malformed connection '%s'", name)
                continue
            try:
                connections[name] = ConnectionEntry.from_dict(name, entry_data)
            except Exception as e:
                logger.warning("Skipping connection '%s': %s", name, e)
        self._cache = connections
        return self._cache

    def save(self, connections: Dict[str, ConnectionEntry]) -> None:
        """Write connections to ``connections.yaml`` with secure permissions."""
        import yaml

        data = {
            "version": 1,
            "connections": {name: entry.to_dict() for name, entry in connections.items()},
        }
        self._path.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass
        self._cache = connections

    def _invalidate(self):
        self._cache = None

    # -- CRUD ---------------------------------------------------------------

    def add(self, name: str, entry: ConnectionEntry) -> None:
        connections = self.load()
        if name in connections:
            raise ValueError(f"Connection '{name}' already exists")
        connections[name] = entry
        self.save(connections)

    def remove(self, name: str) -> bool:
        connections = self.load()
        if name not in connections:
            return False
        del connections[name]
        self.save(connections)
        return True

    def update(self, name: str, entry: ConnectionEntry) -> None:
        connections = self.load()
        if name not in connections:
            raise ValueError(f"Connection '{name}' not found")
        connections[name] = entry
        self.save(connections)

    def get(self, name: str) -> Optional[ConnectionEntry]:
        return self.load().get(name)

    def list_all(self) -> List[ConnectionEntry]:
        return list(self.load().values())

    def exists(self) -> bool:
        """Return True if ``connections.yaml`` exists and has entries."""
        return bool(self.load())

    # -- Agent-scoped queries -----------------------------------------------

    def _get_agent_allowed(self, agent_id: str) -> list[str]:
        """Return the allow list for an agent from the agent registry."""
        from vulti_cli.agent_registry import AgentRegistry

        reg = AgentRegistry(self._vulti_home)
        meta = reg.get_agent(agent_id)
        if meta is None:
            return []
        return meta.allowed_connections

    def get_for_agent(self, agent_id: str) -> List[ConnectionEntry]:
        """Return only the connections this agent is allowed to use."""
        allowed = self._get_agent_allowed(agent_id)
        if not allowed:
            return []
        connections = self.load()
        return [connections[n] for n in allowed if n in connections and connections[n].enabled]

    def get_visible_for_agent(self, agent_id: str) -> List[dict]:
        """Return all connections with metadata (no credentials) for discovery.

        Each entry is annotated with ``allowed: bool`` so the agent knows
        which connections it can use vs. which it can only see.
        """
        allowed = set(self._get_agent_allowed(agent_id))
        result = []
        for entry in self.load().values():
            d = entry.visible_dict()
            d["allowed"] = entry.name in allowed
            result.append(d)
        return result

    def get_credentials_for_agent(self, agent_id: str) -> Dict[str, str]:
        """Return merged ``{ENV_VAR: value}`` for all allowed connections."""
        creds: Dict[str, str] = {}
        for entry in self.get_for_agent(agent_id):
            creds.update(entry.credentials)
        return creds

    def get_mcp_configs_for_agent(self, agent_id: str) -> Dict[str, dict]:
        """Return MCP server configs with credentials injected for allowed connections.

        Returns a dict compatible with the existing ``mcp_servers`` config format.
        """
        result: Dict[str, dict] = {}
        for entry in self.get_for_agent(agent_id):
            if entry.type != "mcp":
                continue
            config = dict(entry.mcp)
            # Inject credentials into the env dict for stdio, or headers for HTTP
            if "url" in config:
                headers = config.setdefault("headers", {})
                headers.update(entry.credentials)
            else:
                env = config.setdefault("env", {})
                env.update(entry.credentials)
            # Apply tool filtering
            if entry.tools:
                config["tools"] = entry.tools
            result[entry.name] = config
        return result


# ---------------------------------------------------------------------------
# Credential injection context manager
# ---------------------------------------------------------------------------


@contextmanager
def inject_credentials(agent_id: Optional[str] = None):
    """Temporarily inject env vars from an agent's allowed connections.

    If ``agent_id`` is None or the agent has no connections configured,
    this is a no-op (existing ``.env`` behavior is preserved).

    Usage::

        with inject_credentials(agent_id):
            result = tool_handler(args)
    """
    if not agent_id:
        yield
        return

    from vulti_cli.config import get_vulti_home

    registry = ConnectionRegistry(get_vulti_home())

    # If no connections.yaml exists, fall through to legacy .env behavior
    if not registry.exists():
        yield
        return

    allowed = registry._get_agent_allowed(agent_id)
    # Empty allow list = legacy mode
    if not allowed:
        yield
        return

    creds = registry.get_credentials_for_agent(agent_id)
    if not creds:
        yield
        return

    # Save originals and inject
    originals: Dict[str, Optional[str]] = {}
    for key, value in creds.items():
        originals[key] = os.environ.get(key)
        os.environ[key] = value

    try:
        yield
    finally:
        # Restore originals
        for key, original in originals.items():
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original
