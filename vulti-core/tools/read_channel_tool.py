"""Read Channel Tool -- read message history from Matrix rooms.

Allows agents to read past messages from any Matrix room they belong to.
Supports pagination via the `before` token for reading further back in history.
"""

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

READ_CHANNEL_SCHEMA = {
    "name": "read_channel",
    "description": (
        "Read message history from a Matrix room or channel.\n\n"
        "Use this to catch up on conversations, review what was discussed, "
        "or find specific messages. Returns messages in chronological order.\n"
        "If you know the room ID or alias, read directly. Use action='list' only to discover rooms."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "list"],
                "description": "Action to perform. 'read' fetches message history from a room. 'list' returns all rooms the agent has joined."
            },
            "room_id": {
                "type": "string",
                "description": "The Matrix room ID (e.g. '!abc123:server.ts.net') or room alias (e.g. '#agents:server.ts.net'). Required for 'read' action."
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of messages to return (default: 30, max: 100)."
            },
            "before": {
                "type": "string",
                "description": "Pagination token from a previous read_channel call. Pass this to fetch older messages."
            },
        },
        "required": []
    }
}


def read_channel_tool(args, **kw):
    action = args.get("action", "read")

    if action == "list":
        return _run_async(_list_rooms())
    elif action == "read":
        room_id = args.get("room_id", "")
        if not room_id:
            # Default to current chat room if available
            room_id = os.getenv("VULTI_SESSION_CHAT_ID", "")
        if not room_id:
            return {"error": "room_id is required. Use action='list' to see available rooms."}
        limit = min(int(args.get("limit", 30)), 100)
        before = args.get("before")
        return _run_async(_read_room(room_id, limit, before))
    else:
        return {"error": f"Unknown action: {action}"}


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return loop.run_in_executor(pool, lambda: asyncio.run(coro))
    except RuntimeError:
        return asyncio.run(coro)


def _get_matrix_client():
    """Create an authenticated nio client for the current agent."""
    import nio

    homeserver_url = os.getenv("MATRIX_HOMESERVER_URL", "http://127.0.0.1:6167")
    agent_id = os.getenv("VULTI_AGENT_ID", "")
    access_token = ""
    user_id = ""

    if agent_id:
        try:
            from gateway.matrix_agents import get_agent_matrix_credentials
            creds = get_agent_matrix_credentials(agent_id)
            if creds:
                access_token = creds["access_token"]
                user_id = creds["user_id"]
                homeserver_url = creds.get("homeserver_url", homeserver_url)
        except Exception:
            pass

    if not access_token:
        return None, "Matrix not configured (no credentials for this agent)"

    client = nio.AsyncClient(homeserver_url, user_id)
    client.access_token = access_token
    client.user_id = user_id
    return client, None


async def _list_rooms():
    """List all rooms the agent has joined."""
    client, error = _get_matrix_client()
    if error:
        return {"error": error}

    try:
        import nio
        resp = await client.joined_rooms()
        if not isinstance(resp, nio.JoinedRoomsResponse):
            return {"error": f"Failed to list rooms: {resp}"}

        rooms = []
        for room_id in resp.rooms:
            # Try to get room display name
            name = room_id
            try:
                state_resp = await client.room_get_state_event(room_id, "m.room.name")
                if hasattr(state_resp, "content") and "name" in state_resp.content:
                    name = state_resp.content["name"]
            except Exception:
                pass

            rooms.append({"room_id": room_id, "name": name})

        return {"rooms": rooms, "count": len(rooms)}
    finally:
        await client.close()


async def _read_room(room_id: str, limit: int, before: Optional[str] = None):
    """Read message history from a Matrix room."""
    client, error = _get_matrix_client()
    if error:
        return {"error": error}

    try:
        import nio

        # Resolve room alias to ID if needed
        if room_id.startswith("#"):
            alias_resp = await client.room_resolve_alias(room_id)
            if isinstance(alias_resp, nio.RoomResolveAliasResponse):
                room_id = alias_resp.room_id
            else:
                return {"error": f"Could not resolve room alias '{room_id}': {alias_resp}"}

        # If no pagination token, we need to get one from a sync
        start_token = before
        if not start_token:
            sync_resp = await client.sync(timeout=5000, sync_filter={
                "room": {
                    "rooms": [room_id],
                    "timeline": {"limit": 0}
                }
            })
            if isinstance(sync_resp, nio.SyncResponse):
                room_data = sync_resp.rooms.join.get(room_id)
                if room_data:
                    start_token = room_data.timeline.prev_batch
                else:
                    # Try from the full sync next_batch
                    start_token = sync_resp.next_batch

        if not start_token:
            return {"error": "Could not get sync token for room. Is the agent a member?"}

        # Fetch messages
        resp = await client.room_messages(
            room_id=room_id,
            start=start_token,
            limit=limit,
            direction=nio.Api.MessageDirection.back,
        )

        if not isinstance(resp, nio.RoomMessagesResponse):
            return {"error": f"Failed to read messages: {resp}"}

        messages = []
        for event in resp.chunk:
            if isinstance(event, nio.RoomMessageText):
                messages.append({
                    "sender": event.sender,
                    "body": event.body,
                    "timestamp": event.server_timestamp,
                    "event_id": event.event_id,
                })
            elif isinstance(event, (nio.RoomMessageImage, nio.RoomMessageAudio, nio.RoomMessageFile)):
                messages.append({
                    "sender": event.sender,
                    "body": f"[{event.__class__.__name__}: {getattr(event, 'body', 'media')}]",
                    "timestamp": event.server_timestamp,
                    "event_id": event.event_id,
                })

        # Reverse so oldest is first (more natural reading order)
        messages.reverse()

        result = {
            "room_id": room_id,
            "messages": messages,
            "count": len(messages),
        }

        # Include pagination token for fetching older messages
        if resp.end:
            result["next_before"] = resp.end
            result["has_more"] = len(resp.chunk) >= limit

        return result
    finally:
        await client.close()


def _check_read_channel():
    """Gate read_channel on being inside a gateway/agent context."""
    if os.getenv("VULTI_GATEWAY_PID"):
        return True
    if os.getenv("VULTI_AGENT_ID"):
        return True
    platform = os.getenv("VULTI_SESSION_PLATFORM", "")
    if platform and platform != "local":
        return True
    try:
        from gateway.status import is_gateway_running
        return is_gateway_running()
    except Exception:
        return False


# --- Registry ---
from tools.registry import registry

registry.register(
    name="read_channel",
    toolset="messaging",
    schema=READ_CHANNEL_SCHEMA,
    handler=read_channel_tool,
    check_fn=_check_read_channel,
    is_async=True,
    emoji="📖",
)
