"""
Agent config versioning — snapshot before writes, list revisions, rollback.

Stores timestamped copies in ``~/.vulti/agents/{agent_id}/config_history/``.
"""

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_VULTI_HOME = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))


def _history_dir(agent_id: str) -> Path:
    return _VULTI_HOME / "agents" / agent_id / "config_history"


def _config_path(agent_id: str) -> Path:
    return _VULTI_HOME / "agents" / agent_id / "config.yaml"


def snapshot_config(agent_id: str) -> Optional[str]:
    """Copy current config.yaml to config_history/{timestamp}.yaml.

    Returns the revision filename, or None if no config exists.
    """
    src = _config_path(agent_id)
    if not src.exists():
        return None

    history = _history_dir(agent_id)
    history.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    revision = f"{timestamp}.yaml"
    dest = history / revision

    # Avoid duplicate snapshots within the same second
    if dest.exists():
        return revision

    shutil.copy2(src, dest)
    logger.info("Config snapshot for '%s': %s", agent_id, revision)
    return revision


def list_revisions(agent_id: str) -> List[Dict[str, Any]]:
    """Return list of config revisions, newest first."""
    history = _history_dir(agent_id)
    if not history.exists():
        return []

    revisions = []
    for f in sorted(history.iterdir(), reverse=True):
        if f.suffix == ".yaml" and f.stem.replace("_", "").isdigit():
            try:
                # Parse timestamp from filename
                ts_str = f.stem  # e.g. "20260320_143022"
                ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
                revisions.append({
                    "revision": f.name,
                    "timestamp": ts.isoformat(),
                    "size": f.stat().st_size,
                })
            except (ValueError, OSError):
                revisions.append({
                    "revision": f.name,
                    "timestamp": "",
                    "size": f.stat().st_size if f.exists() else 0,
                })

    return revisions


def get_revision(agent_id: str, revision: str) -> Optional[str]:
    """Read and return the content of a specific revision."""
    path = _history_dir(agent_id) / revision
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def rollback(agent_id: str, revision: str) -> bool:
    """Rollback to a previous config revision.

    Saves current config as a new snapshot first, then copies the target
    revision back to config.yaml.

    Returns True if successful.
    """
    target = _history_dir(agent_id) / revision
    if not target.exists():
        logger.warning("Revision '%s' not found for agent '%s'", revision, agent_id)
        return False

    # Snapshot current before overwriting
    snapshot_config(agent_id)

    # Copy target revision back
    dest = _config_path(agent_id)
    shutil.copy2(target, dest)
    logger.info("Rolled back '%s' config to revision %s", agent_id, revision)

    # Emit audit event
    try:
        from orchestrator.audit import emit
        emit("config_rollback", agent_id=agent_id, details={"revision": revision})
    except Exception:
        pass

    return True
