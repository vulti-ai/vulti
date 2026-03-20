"""
Atomic task checkout — file-based locks to prevent duplicate work.

When multiple agents see the same message in a group room, only one should
claim and process it. Uses O_CREAT|O_EXCL for atomic lock file creation.

Lock files live in ``~/.vulti/locks/`` with TTL-based expiry.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_VULTI_HOME = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))
_LOCKS_DIR = _VULTI_HOME / "locks"


def _lock_path(lock_key: str) -> Path:
    """Sanitize lock key into a safe filename."""
    safe = lock_key.replace("/", "_").replace(":", "_").replace("!", "_")
    return _LOCKS_DIR / f"{safe}.json"


def _ensure_locks_dir() -> None:
    _LOCKS_DIR.mkdir(parents=True, exist_ok=True)


def try_claim(lock_key: str, agent_id: str, ttl_seconds: int = 300) -> bool:
    """Atomically claim a lock. Returns True if this agent claimed it.

    If the lock exists but is expired, cleans it up and retries.
    """
    _ensure_locks_dir()
    path = _lock_path(lock_key)

    # Check for expired lock first
    if path.exists():
        try:
            with open(path) as f:
                existing = json.load(f)
            expires_at = existing.get("expires_at", 0)
            if time.time() > expires_at:
                # Expired — clean up
                try:
                    os.unlink(path)
                except OSError:
                    pass
            else:
                # Still held by someone
                return existing.get("agent_id") == agent_id
        except (json.JSONDecodeError, OSError):
            # Corrupt lock file — remove it
            try:
                os.unlink(path)
            except OSError:
                pass

    # Attempt atomic creation
    lock_data = {
        "agent_id": agent_id,
        "claimed_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": time.time() + ttl_seconds,
        "lock_key": lock_key,
    }

    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, json.dumps(lock_data).encode())
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        # Another agent beat us to it
        return False
    except OSError as e:
        logger.warning("Lock claim failed for '%s': %s", lock_key, e)
        return False


def release(lock_key: str, agent_id: str) -> None:
    """Release a lock if held by this agent."""
    path = _lock_path(lock_key)
    if not path.exists():
        return
    try:
        with open(path) as f:
            data = json.load(f)
        if data.get("agent_id") == agent_id:
            os.unlink(path)
    except (json.JSONDecodeError, OSError):
        # Best-effort cleanup
        try:
            os.unlink(path)
        except OSError:
            pass


def is_claimed(lock_key: str) -> Optional[str]:
    """Return the claiming agent_id, or None if not claimed / expired."""
    path = _lock_path(lock_key)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        if time.time() > data.get("expires_at", 0):
            # Expired
            try:
                os.unlink(path)
            except OSError:
                pass
            return None
        return data.get("agent_id")
    except (json.JSONDecodeError, OSError):
        return None


def cleanup_expired() -> int:
    """Remove all expired lock files. Returns count of cleaned locks."""
    if not _LOCKS_DIR.exists():
        return 0
    count = 0
    now = time.time()
    for f in _LOCKS_DIR.iterdir():
        if f.suffix != ".json":
            continue
        try:
            with open(f) as fh:
                data = json.load(fh)
            if now > data.get("expires_at", 0):
                os.unlink(f)
                count += 1
        except (json.JSONDecodeError, OSError):
            try:
                os.unlink(f)
                count += 1
            except OSError:
                pass
    return count
