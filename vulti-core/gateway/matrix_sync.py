"""
Matrix DM thread sync for app chat sessions.

When a user chats with an agent in the app (web platform), this module
mirrors the exchange to the owner's Matrix DM with that agent as a thread.
Messages are sent by the agent so the Matrix adapter ignores them (no loops).
User messages use m.notice msgtype to suppress notifications.
"""

import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# session_id → thread root event_id
_session_threads: Dict[str, str] = {}


async def sync_message_to_matrix(
    agent_id: str,
    session_id: str,
    user_text: str,
    agent_response: str,
    session_name: Optional[str] = None,
) -> None:
    """Sync a web session message exchange to a Matrix DM thread.

    Creates a thread on first call for a session, then posts the user message
    (as m.notice) and agent response (as m.text) into that thread.

    All errors are caught — this is never fatal.
    """
    try:
        from gateway.matrix_agents import (
            create_owner_dm_room,
            send_room_message,
            get_agent_matrix_credentials,
        )

        homeserver_url = os.getenv("MATRIX_HOMESERVER_URL", "http://127.0.0.1:6167")
        server_name = os.getenv("MATRIX_SERVER_NAME", "localhost")

        # Check agent has Matrix credentials
        if not get_agent_matrix_credentials(agent_id):
            return

        # Find or create the DM room
        dm_room_id = await create_owner_dm_room(
            homeserver_url=homeserver_url,
            server_name=server_name,
            agent_id=agent_id,
        )
        if not dm_room_id:
            logger.debug("Matrix sync: no DM room for agent %s", agent_id)
            return

        # Create thread root on first message in this session
        thread_id = _session_threads.get(session_id)
        if not thread_id:
            label = session_name or "App session"
            thread_id = await send_room_message(
                homeserver_url=homeserver_url,
                agent_id=agent_id,
                room_id=dm_room_id,
                body=f"\U0001f4f1 {label}",
                msgtype="m.notice",
            )
            if not thread_id:
                logger.debug("Matrix sync: failed to create thread root for session %s", session_id)
                return
            _session_threads[session_id] = thread_id

        # Post user message as notice (suppresses notifications)
        await send_room_message(
            homeserver_url=homeserver_url,
            agent_id=agent_id,
            room_id=dm_room_id,
            body=f"> {user_text}",
            thread_id=thread_id,
            msgtype="m.notice",
        )

        # Post agent response
        await send_room_message(
            homeserver_url=homeserver_url,
            agent_id=agent_id,
            room_id=dm_room_id,
            body=agent_response,
            thread_id=thread_id,
            msgtype="m.text",
        )

    except Exception as e:
        logger.debug("Matrix sync failed for session %s: %s", session_id, e)


def clear_session_thread(session_id: str) -> None:
    """Remove thread tracking for a session (e.g. on session delete)."""
    _session_threads.pop(session_id, None)
