"""
Multi-agent registry for Vulti.

Manages agent definitions, per-agent filesystem layout, and migration
from single-agent installations. Each agent owns its own config, soul,
memories, cron jobs, sessions, and skills.

Storage layout:
  ~/.vulti/agents/
    registry.json              # Central index
    {agent_id}/                # Per-agent directory
      config.yaml
      SOUL.md
      gateway.json
      memories/
        MEMORY.md
        USER.md
      cron/
        jobs.json
      sessions/
      skills/
"""

import json
import logging
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Validation
_AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9\-]{0,31}$")
_RESERVED_IDS = frozenset({"agent", "agents", "api", "ws", "system", "interagent"})

DEFAULT_AGENT_ID = "default"


@dataclass
class AgentMeta:
    """Metadata for a registered agent."""

    id: str
    name: str
    status: str = "active"  # active | stopped | error
    created_at: str = ""
    created_from: Optional[str] = None
    avatar: Optional[str] = None
    description: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMeta":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


class AgentRegistry:
    """Manages the multi-agent registry and per-agent filesystem layout."""

    def __init__(self, vulti_home: Path = None):
        from vulti_cli.config import get_vulti_home

        self._home = Path(vulti_home) if vulti_home else get_vulti_home()
        self._agents_dir = self._home / "agents"
        self._registry_path = self._agents_dir / "registry.json"
        self._data: Optional[dict] = None

    # ------------------------------------------------------------------
    # Registry I/O
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        if self._data is not None:
            return self._data
        if self._registry_path.exists():
            try:
                self._data = json.loads(
                    self._registry_path.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load agent registry: %s", e)
                self._data = {"version": 1, "default_agent": DEFAULT_AGENT_ID, "agents": {}}
        else:
            self._data = {"version": 1, "default_agent": DEFAULT_AGENT_ID, "agents": {}}
        return self._data

    def _save(self) -> None:
        self._agents_dir.mkdir(parents=True, exist_ok=True)
        self._registry_path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        try:
            os.chmod(self._registry_path, 0o600)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_agents(self) -> list[AgentMeta]:
        """List all registered agents."""
        data = self._load()
        return [AgentMeta.from_dict(v) for v in data.get("agents", {}).values()]

    def get_agent(self, agent_id: str) -> Optional[AgentMeta]:
        """Get a single agent by ID. Returns None if not found."""
        data = self._load()
        entry = data.get("agents", {}).get(agent_id)
        if entry is None:
            return None
        return AgentMeta.from_dict(entry)

    def create_agent(
        self,
        agent_id: str,
        name: str,
        clone_from: Optional[str] = None,
        avatar: Optional[str] = None,
        description: str = "",
    ) -> AgentMeta:
        """Create a new agent. Optionally clone config/soul from an existing agent."""
        self._validate_agent_id(agent_id)
        data = self._load()

        if agent_id in data.get("agents", {}):
            raise ValueError(f"Agent '{agent_id}' already exists")

        if clone_from and clone_from not in data.get("agents", {}):
            raise ValueError(f"Source agent '{clone_from}' not found")

        now = datetime.now(timezone.utc).isoformat()
        meta = AgentMeta(
            id=agent_id,
            name=name,
            status="active",
            created_at=now,
            created_from=clone_from,
            avatar=avatar,
            description=description,
        )

        # Create directory structure
        agent_home = self.agent_home(agent_id)
        for subdir in ("memories", "cron", "sessions", "skills"):
            (agent_home / subdir).mkdir(parents=True, exist_ok=True)

        if clone_from:
            self._clone_from(clone_from, agent_id)
        else:
            self._seed_defaults(agent_id)

        # Register
        if "agents" not in data:
            data["agents"] = {}
        data["agents"][agent_id] = meta.to_dict()
        self._save()

        logger.info("Created agent '%s' (cloned from: %s)", agent_id, clone_from or "none")
        return meta

    def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent and all its data. Cannot delete the default agent."""
        data = self._load()

        if agent_id not in data.get("agents", {}):
            return False

        if agent_id == data.get("default_agent", DEFAULT_AGENT_ID):
            raise ValueError(f"Cannot delete the default agent '{agent_id}'")

        # Remove directory
        agent_home = self.agent_home(agent_id)
        if agent_home.exists():
            shutil.rmtree(agent_home)

        del data["agents"][agent_id]
        self._save()

        logger.info("Deleted agent '%s'", agent_id)
        return True

    def update_agent(self, agent_id: str, **updates) -> AgentMeta:
        """Update agent metadata fields."""
        data = self._load()

        if agent_id not in data.get("agents", {}):
            raise ValueError(f"Agent '{agent_id}' not found")

        allowed_fields = {"name", "status", "avatar", "description"}
        for key in updates:
            if key not in allowed_fields:
                raise ValueError(f"Cannot update field '{key}' via registry")

        entry = data["agents"][agent_id]
        entry.update(updates)
        self._save()

        return AgentMeta.from_dict(entry)

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    def agent_home(self, agent_id: str) -> Path:
        return self._agents_dir / agent_id

    def agent_config_path(self, agent_id: str) -> Path:
        return self.agent_home(agent_id) / "config.yaml"

    def agent_soul_path(self, agent_id: str) -> Path:
        return self.agent_home(agent_id) / "SOUL.md"

    def agent_memories_dir(self, agent_id: str) -> Path:
        return self.agent_home(agent_id) / "memories"

    def agent_cron_dir(self, agent_id: str) -> Path:
        return self.agent_home(agent_id) / "cron"

    def agent_sessions_dir(self, agent_id: str) -> Path:
        return self.agent_home(agent_id) / "sessions"

    def agent_skills_dir(self, agent_id: str) -> Path:
        return self.agent_home(agent_id) / "skills"

    def agent_gateway_path(self, agent_id: str) -> Path:
        return self.agent_home(agent_id) / "gateway.json"

    # ------------------------------------------------------------------
    # Default agent
    # ------------------------------------------------------------------

    @property
    def default_agent_id(self) -> str:
        data = self._load()
        return data.get("default_agent", DEFAULT_AGENT_ID)

    # ------------------------------------------------------------------
    # Migration from single-agent layout
    # ------------------------------------------------------------------

    def needs_migration(self) -> bool:
        """Check if we need to migrate from single-agent to multi-agent layout."""
        # If agents dir already has a registry, no migration needed
        if self._registry_path.exists():
            return False
        # If there are config files at the root level, migration is needed
        return (self._home / "config.yaml").exists() or (self._home / "SOUL.md").exists()

    def migrate_single_agent(self) -> str:
        """Migrate existing single-agent installation to multi-agent layout.

        Moves config, soul, memories, cron into agents/default/.
        Leaves symlinks at old locations for backward compatibility.

        Returns the agent_id of the migrated agent.
        """
        agent_id = DEFAULT_AGENT_ID
        agent_home = self.agent_home(agent_id)

        logger.info("Migrating single-agent installation to multi-agent layout...")

        # Create directory structure
        for subdir in ("memories", "cron", "sessions", "skills"):
            (agent_home / subdir).mkdir(parents=True, exist_ok=True)

        # Move files and leave symlinks
        migrations = [
            ("config.yaml", "config.yaml"),
            ("SOUL.md", "SOUL.md"),
        ]
        for src_rel, dst_rel in migrations:
            src = self._home / src_rel
            dst = agent_home / dst_rel
            if src.exists() and not src.is_symlink():
                shutil.copy2(str(src), str(dst))
                src.unlink()
                src.symlink_to(dst)
                logger.debug("Migrated %s -> %s (symlinked)", src_rel, dst)

        # Move directories and leave symlinks
        dir_migrations = [
            ("memories", "memories"),
            ("cron", "cron"),
        ]
        for src_rel, dst_rel in dir_migrations:
            src = self._home / src_rel
            dst = agent_home / dst_rel
            if src.exists() and not src.is_symlink():
                # Copy contents, not the directory itself
                for item in src.iterdir():
                    dst_item = dst / item.name
                    if item.is_file():
                        shutil.copy2(str(item), str(dst_item))
                    elif item.is_dir():
                        if dst_item.exists():
                            shutil.rmtree(dst_item)
                        shutil.copytree(str(item), str(dst_item))
                # Remove original and symlink
                shutil.rmtree(src)
                src.symlink_to(dst)
                logger.debug("Migrated %s/ -> %s/ (symlinked)", src_rel, dst)

        # Read agent name from config.yaml if set
        agent_name = "Vulti"
        try:
            import yaml
            config_path = self.agent_home(agent_id) / "config.yaml"
            if config_path.exists():
                with open(config_path, encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                agent_name = cfg.get("agent_name", agent_name)
        except Exception:
            pass

        # Create registry
        now = datetime.now(timezone.utc).isoformat()
        self._data = {
            "version": 1,
            "default_agent": agent_id,
            "agents": {
                agent_id: {
                    "id": agent_id,
                    "name": agent_name,
                    "status": "active",
                    "created_at": now,
                    "created_from": None,
                    "avatar": None,
                    "description": "Primary agent (migrated from single-agent install)",
                }
            },
        }
        self._save()

        logger.info("Migration complete. Default agent: '%s'", agent_id)
        return agent_id

    def ensure_initialized(self) -> None:
        """Ensure the agent registry is initialized. Migrates if needed."""
        if self.needs_migration():
            self.migrate_single_agent()
        elif not self._registry_path.exists():
            # Fresh install -- create default agent
            self._seed_fresh_install()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_agent_id(agent_id: str) -> None:
        if not _AGENT_ID_RE.match(agent_id):
            raise ValueError(
                f"Invalid agent ID '{agent_id}'. Must be lowercase alphanumeric "
                f"with hyphens, 1-32 chars, starting with a letter."
            )
        if agent_id in _RESERVED_IDS:
            raise ValueError(f"Agent ID '{agent_id}' is reserved")

    def _clone_from(self, source_id: str, target_id: str) -> None:
        """Copy config and soul from source agent to target. Does NOT copy memories/sessions/cron."""
        src = self.agent_home(source_id)
        dst = self.agent_home(target_id)

        for filename in ("config.yaml", "SOUL.md", "gateway.json"):
            src_file = src / filename
            if src_file.exists():
                shutil.copy2(str(src_file), str(dst / filename))

    def _seed_defaults(self, agent_id: str) -> None:
        """Create default config and soul for a brand new agent."""
        from vulti_cli.config import DEFAULT_CONFIG
        from vulti_cli.default_soul import DEFAULT_SOUL_MD

        import yaml

        agent_home = self.agent_home(agent_id)

        # Default config
        config_path = agent_home / "config.yaml"
        if not config_path.exists():
            config_path.write_text(
                yaml.dump(DEFAULT_CONFIG, default_flow_style=False, allow_unicode=True),
                encoding="utf-8",
            )

        # Default soul
        soul_path = agent_home / "SOUL.md"
        if not soul_path.exists():
            soul_path.write_text(DEFAULT_SOUL_MD, encoding="utf-8")

    def _seed_fresh_install(self) -> None:
        """Create registry with a default agent for fresh installations."""
        agent_id = DEFAULT_AGENT_ID
        agent_home = self.agent_home(agent_id)

        for subdir in ("memories", "cron", "sessions", "skills"):
            (agent_home / subdir).mkdir(parents=True, exist_ok=True)

        self._seed_defaults(agent_id)

        now = datetime.now(timezone.utc).isoformat()
        self._data = {
            "version": 1,
            "default_agent": agent_id,
            "agents": {
                agent_id: {
                    "id": agent_id,
                    "name": "Vulti",
                    "status": "active",
                    "created_at": now,
                    "created_from": None,
                    "avatar": None,
                    "description": "Primary agent",
                }
            },
        }
        self._save()
        logger.info("Fresh install: created default agent '%s'", agent_id)
