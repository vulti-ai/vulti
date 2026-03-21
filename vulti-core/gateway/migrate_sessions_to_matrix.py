"""
One-time migration: sync existing web chat sessions to Matrix DM threads.

Reads all web sessions from ~/.vulti/web/, groups messages into
user/assistant pairs, and posts them as threads in the owner's Matrix DM
with each agent.

Usage:
    python -m gateway.migrate_sessions_to_matrix [--dry-run]
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def get_web_data_dir() -> Path:
    from vulti_cli.config import get_vulti_home
    return get_vulti_home() / "web"


def load_sessions() -> list:
    """Load all web session metadata, sorted by created_at."""
    sessions_dir = get_web_data_dir() / "sessions"
    if not sessions_dir.exists():
        return []
    sessions = []
    for f in sorted(sessions_dir.glob("*.json")):
        if f.stem.endswith("_widgets"):
            continue
        try:
            meta = json.loads(f.read_text())
            if meta.get("agent_id"):
                sessions.append(meta)
        except Exception:
            pass
    sessions.sort(key=lambda s: s.get("created_at", ""))
    return sessions


def load_history(session_id: str) -> list:
    """Load message history for a session."""
    f = get_web_data_dir() / "history" / f"{session_id}.jsonl"
    if not f.exists():
        return []
    messages = []
    for line in f.read_text().strip().split("\n"):
        if line.strip():
            try:
                messages.append(json.loads(line))
            except Exception:
                pass
    return messages


def extract_pairs(messages: list) -> List[Tuple[str, str]]:
    """Extract (user_text, assistant_text) pairs from message history."""
    pairs = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.get("role") == "user":
            user_text = msg.get("content", "")
            # Look for the next assistant message
            assistant_text = ""
            j = i + 1
            while j < len(messages):
                if messages[j].get("role") == "assistant":
                    assistant_text = messages[j].get("content", "")
                    i = j + 1
                    break
                j += 1
            else:
                i += 1
            if user_text and assistant_text:
                pairs.append((user_text, assistant_text))
        else:
            i += 1
    return pairs


# Cache: agent_id → dm_room_id (avoids re-querying Matrix for every session)
_dm_room_cache: Dict[str, Optional[str]] = {}


async def _get_dm_room(agent_id: str, homeserver_url: str, server_name: str) -> Optional[str]:
    if agent_id in _dm_room_cache:
        return _dm_room_cache[agent_id]
    from gateway.matrix_agents import create_owner_dm_room, get_agent_matrix_credentials
    if not get_agent_matrix_credentials(agent_id):
        _dm_room_cache[agent_id] = None
        return None
    room_id = await create_owner_dm_room(
        homeserver_url=homeserver_url,
        server_name=server_name,
        agent_id=agent_id,
    )
    _dm_room_cache[agent_id] = room_id
    return room_id


async def migrate_session(
    agent_id: str,
    session_id: str,
    session_name: str,
    pairs: List[Tuple[str, str]],
    dry_run: bool = False,
) -> bool:
    """Migrate a single session to a Matrix DM thread."""
    from gateway.matrix_agents import send_room_message

    homeserver_url = os.getenv("MATRIX_HOMESERVER_URL", "http://127.0.0.1:6167")
    server_name = os.getenv("MATRIX_SERVER_NAME", "localhost")

    dm_room_id = await _get_dm_room(agent_id, homeserver_url, server_name)
    if not dm_room_id:
        logger.warning("  skip: no DM room / credentials for %s", agent_id)
        return False

    if dry_run:
        logger.info("  [dry-run] would create thread with %d message pairs", len(pairs))
        return True

    # Create thread root
    thread_id = await send_room_message(
        homeserver_url=homeserver_url,
        agent_id=agent_id,
        room_id=dm_room_id,
        body=f"\U0001f4f1 {session_name}",
        msgtype="m.notice",
    )
    if not thread_id:
        logger.warning("  failed to create thread root")
        return False

    # Post each pair into the thread
    for user_text, assistant_text in pairs:
        await send_room_message(
            homeserver_url=homeserver_url,
            agent_id=agent_id,
            room_id=dm_room_id,
            body=f"> {user_text}",
            thread_id=thread_id,
            msgtype="m.notice",
        )
        await send_room_message(
            homeserver_url=homeserver_url,
            agent_id=agent_id,
            room_id=dm_room_id,
            body=assistant_text,
            thread_id=thread_id,
            msgtype="m.text",
        )
        # Small delay to avoid flooding
        await asyncio.sleep(0.1)

    return True


async def main():
    dry_run = "--dry-run" in sys.argv

    sessions = load_sessions()
    logger.info("Found %d web sessions", len(sessions))

    migrated = 0
    skipped = 0
    failed = 0

    for meta in sessions:
        session_id = meta["id"]
        agent_id = meta["agent_id"]
        session_name = meta.get("name") or "App session"

        history = load_history(session_id)
        pairs = extract_pairs(history)

        if not pairs:
            skipped += 1
            continue

        logger.info(
            "Migrating %s → %s (%d pairs) %s",
            session_id, agent_id, len(pairs), session_name[:40],
        )

        try:
            ok = await migrate_session(agent_id, session_id, session_name, pairs, dry_run)
            if ok:
                migrated += 1
            else:
                failed += 1
        except Exception as e:
            logger.error("  error: %s", e)
            failed += 1

    logger.info(
        "Done. migrated=%d skipped=%d (empty) failed=%d",
        migrated, skipped, failed,
    )


if __name__ == "__main__":
    asyncio.run(main())
