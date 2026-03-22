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
_RESERVED_IDS = frozenset({"agent", "agents", "api", "ws", "system", "interagent", "everyone", "default"})

HECTOR_AGENT_ID = "hector"


def _role_emoji(role: str) -> str:
    """Pick an emoji that fits the agent's role."""
    return {
        "assistant": "✦",
        "engineer": "⚙",
        "researcher": "◎",
        "analyst": "◆",
        "writer": "✎",
        "therapist": "☯",
        "coach": "⚑",
        "creative": "✧",
        "ops": "⚿",
        "wizard": "🧙",
    }.get((role or "").lower(), "◇")


@dataclass
class AgentMeta:
    """Metadata for a registered agent."""

    id: str
    name: str
    role: str = ""  # assistant | therapist | researcher | engineer | writer | analyst | coach | creative | ops
    status: str = "active"  # onboarding | active | stopped | error
    created_at: str = ""
    created_from: Optional[str] = None
    avatar: Optional[str] = None
    description: str = ""
    home_channels: dict = field(default_factory=dict)  # {"matrix": {"chat_id": "!...", "name": "..."}, ...}

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
                self._data = {"version": 2, "agents": {}}
        else:
            self._data = {"version": 2, "agents": {}}
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

    def list_active_agents(self) -> list[AgentMeta]:
        """List agents with status 'active'."""
        return [a for a in self.list_agents() if a.status == "active"]

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
        role: str = "",
    ) -> AgentMeta:
        """Create a new agent. Optionally clone config/soul from an existing agent."""
        self._validate_agent_id(agent_id)
        data = self._load()

        if agent_id in data.get("agents", {}):
            raise ValueError(f"Agent '{agent_id}' already exists")

        if clone_from and clone_from not in data.get("agents", {}):
            raise ValueError(f"Source agent '{clone_from}' not found")

        now = datetime.now(timezone.utc).isoformat()

        # Assign a role-based emoji if no avatar provided
        if not avatar:
            avatar = _role_emoji(role)

        meta = AgentMeta(
            id=agent_id,
            name=name,
            role=role,
            status="onboarding",
            created_at=now,
            created_from=clone_from,
            avatar=avatar,
            description=description,
        )

        # Create directory structure
        agent_home = self.agent_home(agent_id)
        for subdir in ("memories", "cron", "sessions", "skills"):
            (agent_home / subdir).mkdir(parents=True, exist_ok=True)

        # Seed empty permissions file
        perm_path = self.agent_permissions_path(agent_id)
        if not perm_path.exists():
            perm_path.write_text(
                json.dumps({"allowed_connections": [], "pending_requests": []}, indent=2) + "\n",
                encoding="utf-8",
            )
            try:
                os.chmod(perm_path, 0o600)
            except OSError:
                pass

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
        """Delete an agent and all its data."""
        data = self._load()

        if agent_id not in data.get("agents", {}):
            return False

        if agent_id == HECTOR_AGENT_ID:
            raise ValueError("Cannot delete the hector system agent")

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

        allowed_fields = {"name", "role", "status", "avatar", "description", "home_channels"}
        for key in updates:
            if key not in allowed_fields:
                raise ValueError(f"Cannot update field '{key}' via registry")

        entry = data["agents"][agent_id]
        entry.update(updates)
        self._save()

        return AgentMeta.from_dict(entry)

    def set_home_channel(self, agent_id: str, platform: str, chat_id: str, name: str = "Home") -> None:
        """Set a per-agent home channel for a platform."""
        data = self._load()
        entry = data.get("agents", {}).get(agent_id)
        if not entry:
            return
        channels = entry.get("home_channels", {})
        channels[platform] = {"chat_id": chat_id, "name": name}
        entry["home_channels"] = channels
        self._save()

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

    def agent_permissions_path(self, agent_id: str) -> Path:
        return self.agent_home(agent_id) / "permissions.json"

    def agent_gateway_path(self, agent_id: str) -> Path:
        return self.agent_home(agent_id) / "gateway.json"

    # ------------------------------------------------------------------
    # Migration from single-agent layout
    # ------------------------------------------------------------------

    def needs_migration(self) -> bool:
        """Check if we need to migrate from single-agent to multi-agent layout."""
        # If agents dir already has a registry, no migration needed
        if self._registry_path.exists():
            return False
        # If the agents directory already exists (e.g. after a reset), skip migration
        if (self._home / "agents").exists():
            return False
        # Only real files (not symlinks) at root indicate a genuine old single-agent install.
        # The migration itself leaves symlinks, so symlinks should not re-trigger it.
        config_real = (self._home / "config.yaml").exists() and not (self._home / "config.yaml").is_symlink()
        soul_real = (self._home / "SOUL.md").exists() and not (self._home / "SOUL.md").is_symlink()
        return config_real or soul_real

    def migrate_single_agent(self) -> str:
        """Migrate existing single-agent installation to multi-agent layout.

        Moves config, soul, memories, cron into agents/vulti/.
        Leaves symlinks at old locations for backward compatibility.

        Returns the agent_id of the migrated agent.
        """
        agent_id = "vulti"
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
            "version": 2,
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

        logger.info("Migration complete. Agent: '%s'", agent_id)
        return agent_id

    def ensure_initialized(self) -> None:
        """Ensure the agent registry is initialized. Migrates if needed."""
        if self.needs_migration():
            self.migrate_single_agent()
        elif not self._registry_path.exists():
            self._seed_fresh_install()

        # v1 → v2: remove default_agent concept
        self._migrate_v1_to_v2()

        # Ensure hector exists (covers migrations and upgrades)
        self._seed_hector()

        # Migrate allowed_connections from registry to per-agent permissions.json
        self._migrate_permissions()

    def _migrate_v1_to_v2(self) -> None:
        """Remove default_agent key from v1 registries."""
        data = self._load()
        if data.get("version", 1) >= 2:
            return

        data.pop("default_agent", None)
        data["version"] = 2
        self._save()

        # Backfill agent field on cron jobs that lack one
        for agent_id in data.get("agents", {}):
            jobs_path = self.agent_cron_dir(agent_id) / "jobs.json"
            if not jobs_path.exists():
                continue
            try:
                jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
                changed = False
                for job in jobs if isinstance(jobs, list) else jobs.values():
                    if not job.get("agent"):
                        job["agent"] = agent_id
                        changed = True
                if changed:
                    jobs_path.write_text(
                        json.dumps(jobs, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
            except Exception:
                pass

        logger.info("Migrated registry v1 → v2: removed default_agent concept")

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

    def _seed_defaults(self, agent_id: str, soul_md: str = None) -> None:
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
            soul_path.write_text(soul_md or DEFAULT_SOUL_MD, encoding="utf-8")

    def _seed_fresh_install(self) -> None:
        """Create empty registry with hector for fresh installations.

        No default agent is created — the user must create their first agent
        explicitly through onboarding.
        """
        self._data = {
            "version": 2,
            "agents": {},
        }
        self._save()
        logger.info("Fresh install: created empty registry (no default agent)")

        # Seed the hector system agent
        self._seed_hector()

    def _seed_hector(self) -> None:
        """Create the hector system agent if it doesn't already exist."""
        hector_id = HECTOR_AGENT_ID
        data = self._load()

        if hector_id in data.get("agents", {}):
            return  # Already exists

        from vulti_cli.default_soul import HECTOR_CRON_JOBS, HECTOR_SOUL_MD

        # Create directory structure
        agent_home = self.agent_home(hector_id)
        for subdir in ("memories", "cron", "sessions", "skills"):
            (agent_home / subdir).mkdir(parents=True, exist_ok=True)

        self._seed_defaults(hector_id, soul_md=HECTOR_SOUL_MD)

        # Write role.txt
        role_path = agent_home / "role.txt"
        if not role_path.exists():
            role_path.write_text("wizard", encoding="utf-8")

        # Install default skills
        self._install_hector_skills(agent_home)

        # Seed default cron jobs
        self._seed_hector_cron(hector_id)

        # Register
        now = datetime.now(timezone.utc).isoformat()
        if "agents" not in data:
            data["agents"] = {}
        data["agents"][hector_id] = {
            "id": hector_id,
            "name": "Hector",
            "role": "wizard",
            "status": "active",
            "created_at": now,
            "created_from": None,
            "avatar": "🧙",
            "description": "System wizard. Runs daily checks, cleans up, and reports issues.",
        }
        self._save()
        logger.info("Seeded hector agent '%s'", hector_id)

    @staticmethod
    def _install_hector_skills(agent_home: Path) -> None:
        """Symlink default skills into Hector's skills directory."""
        skills_dir = agent_home / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        # Find the optional-skills directory relative to the package
        import vulti_cli
        pkg_root = Path(vulti_cli.__file__).resolve().parent.parent
        default_skills = [
            ("agent-creation", pkg_root / "optional-skills" / "system" / "agent-creation"),
            ("whatsapp-reader", pkg_root / "optional-skills" / "productivity" / "whatsapp-reader"),
        ]
        for name, src in default_skills:
            dest = skills_dir / name
            if not dest.exists() and src.exists():
                dest.symlink_to(src)
                logger.debug("Installed skill '%s' for hector", name)

    def _seed_hector_cron(self, agent_id: str) -> None:
        """Seed default cron jobs for the hector agent."""
        import uuid

        from vulti_cli.default_soul import HECTOR_CRON_JOBS

        jobs_path = self.agent_cron_dir(agent_id) / "jobs.json"
        if jobs_path.exists():
            return  # Don't overwrite existing jobs

        now = datetime.now(timezone.utc).isoformat()
        jobs = []
        for template in HECTOR_CRON_JOBS:
            job = {
                "id": uuid.uuid4().hex[:12],
                "name": template["name"],
                "prompt": template["prompt"],
                "skills": [],
                "skill": None,
                "model": None,
                "provider": None,
                "base_url": None,
                "schedule": {
                    "kind": "cron",
                    "expr": template["schedule"],
                    "display": template["schedule"],
                },
                "schedule_display": template["schedule"],
                "repeat": {"times": None, "completed": 0},
                "enabled": True,
                "state": "scheduled",
                "paused_at": None,
                "paused_reason": None,
                "created_at": now,
                "next_run_at": None,
                "last_run_at": None,
                "last_status": None,
                "last_error": None,
                "deliver": "matrix",
                "origin": None,
                "agent": agent_id,
            }
            jobs.append(job)

        jobs_path.write_text(
            json.dumps({"jobs": jobs}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _migrate_permissions(self) -> None:
        """Migrate allowed_connections from registry.json to per-agent permissions.json.

        One-time migration: if any agent entry in registry.json still has
        ``allowed_connections``, move it into the agent's own permissions file
        and strip the field from the registry.
        """
        data = self._load()
        agents = data.get("agents", {})
        dirty = False

        # Also migrate old global pending.json
        old_pending_path = self._home / "permissions" / "pending.json"
        old_pending = []
        if old_pending_path.exists():
            try:
                with open(old_pending_path, encoding="utf-8") as f:
                    old_pending = json.load(f)
            except Exception:
                old_pending = []

        for agent_id, agent_data in agents.items():
            old_allowed = agent_data.get("allowed_connections")
            if old_allowed is None and not old_pending:
                continue

            perm_path = self.agent_permissions_path(agent_id)
            if perm_path.exists():
                # Already migrated — just clean registry field
                if "allowed_connections" in agent_data:
                    del agent_data["allowed_connections"]
                    dirty = True
                continue

            # Collect pending requests for this agent
            agent_pending = [
                {k: v for k, v in req.items() if k != "agent_id"}
                for req in old_pending
                if req.get("agent_id") == agent_id
            ]

            perm_data = {
                "allowed_connections": sorted(old_allowed or []),
                "pending_requests": agent_pending,
            }

            perm_path.parent.mkdir(parents=True, exist_ok=True)
            perm_path.write_text(
                json.dumps(perm_data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            try:
                os.chmod(perm_path, 0o600)
            except OSError:
                pass

            if "allowed_connections" in agent_data:
                del agent_data["allowed_connections"]
                dirty = True

        if dirty:
            self._save()

        # Clean up old global pending file
        if old_pending_path.exists():
            try:
                old_pending_path.unlink()
                old_dir = old_pending_path.parent
                if old_dir.exists() and not any(old_dir.iterdir()):
                    old_dir.rmdir()
            except OSError:
                pass
