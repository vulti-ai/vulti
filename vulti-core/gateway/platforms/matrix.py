"""
Matrix platform adapter.

Connects to a Matrix homeserver (Continuwuity or any other) via the
matrix-nio SDK. Receives messages from Matrix rooms and sends responses
back. Supports DMs, group rooms, and federated communication.

Multi-agent: syncs all registered agents so DMs to any agent are received.
Messages are routed to the correct agent via @mentions, DM room membership,
or default routing.
"""

import asyncio
import json as _json
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
    cache_image_from_bytes,
    cache_audio_from_bytes,
    cache_document_from_bytes,
    cache_image_for_agent,
    cache_audio_for_agent,
    cache_document_for_agent,
)

logger = logging.getLogger(__name__)

# Suppress noisy nio response validation warnings (Continuwuity compat)
logging.getLogger("nio.responses").setLevel(logging.ERROR)

# Retry constants
RETRY_DELAY_INITIAL = 2.0
RETRY_DELAY_MAX = 60.0
HEALTH_CHECK_INTERVAL = 30
HEALTH_CHECK_STALE_THRESHOLD = 120

MAX_MESSAGE_LENGTH = 65536


def check_matrix_requirements() -> bool:
    """Check if matrix-nio is installed."""
    try:
        import nio  # noqa: F401
        return True
    except ImportError:
        return False


class MatrixAdapter(BasePlatformAdapter):
    """Matrix platform adapter using matrix-nio.

    Syncs ALL registered agents so that DMs to any agent are received.
    Routes messages based on @mentions, DM room membership, or default routing.
    Sends responses using the correct agent's credentials.
    """

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.MATRIX)

        extra = config.extra if config and config.extra else {}
        self.homeserver_url: str = extra.get("homeserver_url") or "http://127.0.0.1:6167"
        self.user_id: str = extra.get("user_id") or ""
        self.password: str = extra.get("password") or ""
        self.access_token: str = extra.get("access_token") or ""
        self.server_name: str = extra.get("server_name") or "localhost"

        # Primary client (used for the main sync loop)
        self._client = None  # nio.AsyncClient

        # All agent clients: agent_id -> nio.AsyncClient (for sending as the right agent)
        self._agent_clients: Dict[str, Any] = {}
        # Map Matrix user_id -> agent_id for routing
        self._matrix_to_agent: Dict[str, str] = {}
        # Set of all agent Matrix user IDs (for filtering)
        self._agent_user_ids: set = set()

        self._sync_tasks: List[asyncio.Task] = []
        self._health_task: Optional[asyncio.Task] = None
        self._last_sync_activity: float = 0.0
        self._connect_timestamp: int = 0  # milliseconds, set on connect
        # Track which agent sent which event (for thread targeting)
        self._sent_event_to_agent: Dict[str, str] = {}
        # Dedup: track event_ids already processed for group fan-out
        self._processed_group_events: Dict[str, float] = {}

        self._load_agent_credentials()

    def _load_agent_credentials(self) -> None:
        """Load all registered agent Matrix credentials."""
        try:
            from gateway.matrix_agents import _tokens_dir
            tokens_dir = _tokens_dir()
            if tokens_dir.exists():
                for f in sorted(tokens_dir.iterdir()):
                    if f.suffix == ".json":
                        # Skip owner credentials — owner is not an agent
                        if f.stem.startswith("_"):
                            continue
                        try:
                            creds = _json.loads(f.read_text())
                            agent_id = f.stem
                            user_id = creds["user_id"]
                            self._agent_user_ids.add(user_id)
                            self._matrix_to_agent[user_id] = agent_id
                            self._agent_clients[agent_id] = {
                                "user_id": user_id,
                                "access_token": creds["access_token"],
                                "client": None,  # Created in connect()
                            }
                        except Exception:
                            pass
        except Exception:
            pass

    async def connect(self) -> bool:
        """Connect all agents to Matrix and start sync loops."""
        import nio

        if not self.user_id and not self._agent_clients:
            # No agents onboarded yet — start in dormant mode.
            # Agents will be connected later via hot_add_agent().
            logger.info("Matrix: no agent credentials yet — waiting for onboarding")
            self._mark_connected()
            return True

        try:
            # Create nio clients for ALL agents
            for agent_id, info in self._agent_clients.items():
                client = nio.AsyncClient(self.homeserver_url, info["user_id"])
                client.access_token = info["access_token"]
                client.user_id = info["user_id"]

                # Verify token
                resp = await client.whoami()
                if isinstance(resp, nio.responses.WhoamiError):
                    logger.warning("Matrix: token invalid for agent %s, skipping", agent_id)
                    continue

                info["client"] = client

                # Register callbacks on each client
                # Use a factory to capture agent_id in the closure
                def make_callbacks(aid, cli):
                    async def on_msg(room, event):
                        await self._on_room_message(room, event, aid, cli)
                    async def on_img(room, event):
                        await self._on_room_media(room, event, aid, cli, MessageType.PHOTO)
                    async def on_audio(room, event):
                        await self._on_room_media(room, event, aid, cli, MessageType.VOICE)
                    async def on_file(room, event):
                        await self._on_room_media(room, event, aid, cli, MessageType.DOCUMENT)
                    async def on_invite(room, event):
                        if event.state_key == cli.user_id:
                            logger.info("Matrix: %s accepting invite to %s", aid, room.room_id)
                            try:
                                await cli.join(room.room_id)
                            except Exception as e:
                                logger.warning("Matrix: %s failed to join %s: %s", aid, room.room_id, e)
                    async def on_member(room, event):
                        await self._on_member_change(room, event, aid, cli)
                    return on_msg, on_img, on_audio, on_file, on_invite, on_member

                on_msg, on_img, on_audio, on_file, on_invite, on_member = make_callbacks(agent_id, client)
                client.add_event_callback(on_msg, nio.RoomMessageText)
                client.add_event_callback(on_img, nio.RoomMessageImage)
                client.add_event_callback(on_audio, nio.RoomMessageAudio)
                client.add_event_callback(on_file, nio.RoomMessageFile)
                client.add_event_callback(on_invite, nio.InviteMemberEvent)
                client.add_event_callback(on_member, nio.RoomMemberEvent)

            # Use the primary agent's client as self._client (for compatibility)
            primary_agent_id = None
            if self.user_id:
                for aid, info in self._agent_clients.items():
                    if info["user_id"] == self.user_id and info["client"]:
                        self._client = info["client"]
                        primary_agent_id = aid
                        break
            if not self._client:
                # Use first available client
                for aid, info in self._agent_clients.items():
                    if info["client"]:
                        self._client = info["client"]
                        primary_agent_id = aid
                        break

            if not self._client:
                logger.error("Matrix: no agent clients could connect")
                self._set_fatal_error("MATRIX_CONNECT_FAILED", "No agent clients available", retryable=True)
                await self._notify_fatal_error()
                return False

            # Auto-set home channels: platform-wide #agents + per-agent channels
            if self._client:
                await self._auto_set_home_channels()

            # Start sync loops for ALL agents
            self._mark_connected()
            self._last_sync_activity = time.time()
            self._connect_timestamp = int(time.time() * 1000)  # ms for comparing with server_timestamp

            for agent_id, info in self._agent_clients.items():
                if info["client"]:
                    task = asyncio.create_task(self._sync_loop(agent_id, info["client"]))
                    self._sync_tasks.append(task)

            self._health_task = asyncio.create_task(self._health_monitor())

            connected_agents = [aid for aid, info in self._agent_clients.items() if info["client"]]
            logger.info("Matrix: connected to %s — syncing %d agent(s): %s",
                        self.homeserver_url, len(connected_agents), connected_agents)
            return True

        except Exception as e:
            logger.error("Matrix: connection failed: %s", e)
            self._set_fatal_error("MATRIX_CONNECT_FAILED", str(e), retryable=True)
            await self._notify_fatal_error()
            return False

    async def hot_add_agent(self, agent_id: str) -> bool:
        """Add and connect a newly onboarded agent at runtime."""
        import nio

        try:
            # Guard: skip if agent already has an active sync loop
            existing = self._agent_clients.get(agent_id)
            if existing and existing.get("client") is not None:
                logger.info("Matrix: hot_add_agent skipped for %s (already connected)", agent_id)
                return True

            from gateway.matrix_agents import get_agent_matrix_credentials
            creds = get_agent_matrix_credentials(agent_id)
            if not creds:
                return False

            user_id = creds["user_id"]
            self._agent_user_ids.add(user_id)
            self._matrix_to_agent[user_id] = agent_id
            self._agent_clients[agent_id] = {
                "user_id": user_id,
                "access_token": creds["access_token"],
                "client": None,
            }

            client = nio.AsyncClient(self.homeserver_url, user_id)
            client.access_token = creds["access_token"]
            client.user_id = user_id

            resp = await client.whoami()
            if isinstance(resp, nio.responses.WhoamiError):
                logger.warning("Matrix: hot_add_agent token invalid for %s", agent_id)
                return False

            self._agent_clients[agent_id]["client"] = client

            # Register callbacks
            def make_callbacks(aid, cli):
                async def on_msg(room, event):
                    await self._on_room_message(room, event, aid, cli)
                async def on_img(room, event):
                    await self._on_room_media(room, event, aid, cli, MessageType.PHOTO)
                async def on_audio(room, event):
                    await self._on_room_media(room, event, aid, cli, MessageType.VOICE)
                async def on_file(room, event):
                    await self._on_room_media(room, event, aid, cli, MessageType.DOCUMENT)
                async def on_invite(room, event):
                    if event.state_key == cli.user_id:
                        logger.info("Matrix: %s accepting invite to %s", aid, room.room_id)
                        try:
                            await cli.join(room.room_id)
                        except Exception as e:
                            logger.warning("Matrix: %s failed to join %s: %s", aid, room.room_id, e)
                async def on_member(room, event):
                    await self._on_member_change(room, event, aid, cli)
                return on_msg, on_img, on_audio, on_file, on_invite, on_member

            on_msg, on_img, on_audio, on_file, on_invite, on_member = make_callbacks(agent_id, client)
            client.add_event_callback(on_msg, nio.RoomMessageText)
            client.add_event_callback(on_img, nio.RoomMessageImage)
            client.add_event_callback(on_audio, nio.RoomMessageAudio)
            client.add_event_callback(on_file, nio.RoomMessageFile)
            client.add_event_callback(on_invite, nio.InviteMemberEvent)
            client.add_event_callback(on_member, nio.RoomMemberEvent)

            # Set as primary client if none exists
            if not self._client:
                self._client = client
                self.user_id = user_id

            # Start sync loop
            if not self._connect_timestamp:
                self._connect_timestamp = int(time.time() * 1000)
            task = asyncio.create_task(self._sync_loop(agent_id, client))
            self._sync_tasks.append(task)

            if not self._health_task:
                self._health_task = asyncio.create_task(self._health_monitor())

            # Set up home channels now that we have a connected client
            await self._auto_set_home_channels()

            logger.info("Matrix: hot-added agent %s (%s)", agent_id, user_id)
            return True

        except Exception as e:
            logger.warning("Matrix: failed to hot-add agent %s: %s", agent_id, e)
            return False

    async def _auto_set_home_channels(self) -> None:
        """Auto-set Matrix home channels.

        Platform default: #agents room
        Per-agent: DM room with owner (found by scanning joined rooms)
        """
        import nio

        # Resolve #agents as platform-wide default
        try:
            alias = f"#agents:{self.server_name}"
            resp = await self._client.room_resolve_alias(alias)
            if isinstance(resp, nio.RoomResolveAliasResponse):
                if not self.config.home_channel:
                    from gateway.config import HomeChannel
                    self.config.home_channel = HomeChannel(
                        platform=Platform.MATRIX,
                        chat_id=resp.room_id,
                        name="All Agents",
                    )
                    os.environ["MATRIX_HOME_CHANNEL"] = resp.room_id
                    logger.info("Matrix: platform home channel → %s (%s)", alias, resp.room_id)
        except Exception as e:
            logger.debug("Matrix: could not resolve #agents: %s", e)

        # Set per-agent home channels to their owner DM rooms
        try:
            from vulti_cli.agent_registry import AgentRegistry
            from gateway.matrix_agents import _get_owner_matrix_credentials
            reg = AgentRegistry()
            owner_creds = _get_owner_matrix_credentials()
            owner_user_id = owner_creds.get("user_id") if owner_creds else None

            if owner_user_id:
                for agent_id, info in self._agent_clients.items():
                    agent = reg.get_agent(agent_id)
                    if not agent:
                        continue
                    existing = (agent.home_channels or {}).get("matrix")
                    if existing and existing.get("chat_id"):
                        continue  # Already set

                    # Find the DM room: a room with exactly {agent, owner} and no name
                    agent_client = info.get("client")
                    if not agent_client:
                        continue
                    try:
                        rooms_resp = await agent_client.joined_rooms()
                        if hasattr(rooms_resp, "rooms"):
                            import httpx
                            agent_uid = info["user_id"]
                            async with httpx.AsyncClient(timeout=5.0) as hc:
                                for room_id in rooms_resp.rooms:
                                    # Skip named rooms (chatter, etc.)
                                    from urllib.parse import quote
                                    name_resp = await hc.get(
                                        f"{self.homeserver_url}/_matrix/client/v3/rooms/{quote(room_id, safe='')}/state/m.room.name",
                                        headers={"Authorization": f"Bearer {info['access_token']}"},
                                    )
                                    if name_resp.status_code == 200 and name_resp.json().get("name"):
                                        continue
                                    # Check members
                                    members_resp = await hc.get(
                                        f"{self.homeserver_url}/_matrix/client/v3/rooms/{quote(room_id, safe='')}/joined_members",
                                        headers={"Authorization": f"Bearer {info['access_token']}"},
                                    )
                                    if members_resp.status_code == 200:
                                        members = set(members_resp.json().get("joined", {}).keys())
                                        if members == {agent_uid, owner_user_id}:
                                            reg.set_home_channel(agent_id, "matrix", room_id, name="Owner DM")
                                            logger.info("Matrix: %s home channel → DM %s", agent_id, room_id)
                                            break
                    except Exception as e:
                        logger.debug("Matrix: could not find DM for %s: %s", agent_id, e)
        except Exception as e:
            logger.debug("Matrix: per-agent home channel setup: %s", e)

    async def _sync_loop(self, agent_id: str, client) -> None:
        """Sync loop for a single agent's client."""
        backoff = RETRY_DELAY_INITIAL
        initial_done = False

        while self._running:
            try:
                if not initial_done:
                    resp = await client.sync(timeout=10000, full_state=True)
                    if hasattr(resp, "next_batch"):
                        initial_done = True
                        self._last_sync_activity = time.time()
                        logger.info("Matrix: %s initial sync complete", agent_id)
                        backoff = RETRY_DELAY_INITIAL
                    else:
                        raise Exception(f"Initial sync failed for {agent_id}")

                while self._running:
                    resp = await client.sync(timeout=30000)
                    if not hasattr(resp, "next_batch"):
                        raise Exception(f"Sync returned {type(resp).__name__}: {getattr(resp, 'message', 'unknown error')}")
                    self._last_sync_activity = time.time()
                    backoff = RETRY_DELAY_INITIAL

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    logger.warning("Matrix sync error for %s: %s (retry in %.0fs)", agent_id, e, backoff)
                initial_done = False  # Re-do full sync on next attempt

            if self._running:
                jitter = backoff * 0.2 * random.random()
                await asyncio.sleep(backoff + jitter)
                backoff = min(backoff * 2, RETRY_DELAY_MAX)

    def _translate_mentions(self, text: str) -> str:
        """Translate Matrix @user:server mentions to @agent_id format for the gateway.

        Converts '@hector-vulti:server.name' → '@hector'
        """
        def replace_mention(match):
            local_part = match.group(1)
            # Strip the -vulti suffix to get agent_id
            if local_part.endswith("-vulti"):
                agent_id = local_part[:-len("-vulti")]
                return f"@{agent_id}"
            return match.group(0)

        # Match @localpart:server patterns
        return re.sub(
            r"@([a-z][a-z0-9\-]*):[\w.\-]+",
            replace_mention,
            text,
        )

    # ------------------------------------------------------------------
    # Message routing helpers
    # ------------------------------------------------------------------

    def _detect_mentioned_agents(self, text: str, formatted_body: str = None) -> List[str]:
        """Detect agents mentioned in message text.

        Checks (in order):
        1. Matrix HTML mentions in formatted_body (href containing @user:server)
        2. @agent_id syntax in plain text (with prefix matching)
        3. Plain-text agent name / display name matches
        """
        mentioned = []

        # 1. Extract user IDs from formatted_body HTML mentions
        #    e.g. <a href="https://matrix.to/#/@flowwy-bot-vulti:server">...</a>
        if formatted_body:
            for mxid in re.findall(r'matrix\.to/#/(@[^"&]+)', formatted_body):
                agent_id = self._matrix_to_agent.get(mxid)
                if agent_id and agent_id not in mentioned:
                    mentioned.append(agent_id)

        if mentioned:
            return mentioned

        # 2. @agent_id mentions in plain text (Matrix-style translated)
        translated = self._translate_mentions(text)
        for match in re.finditer(r"@([a-z][a-z0-9\-]*)", translated):
            candidate = match.group(1)
            if candidate in self._agent_clients and candidate not in mentioned:
                mentioned.append(candidate)
                continue
            # Prefix match: @flowwy → flowwy-bot
            for agent_id in self._agent_clients:
                if agent_id.startswith(candidate) and agent_id not in mentioned:
                    mentioned.append(agent_id)
                    break

        # 3. Plain-text agent name mentions (e.g., "Hector" or "hector")
        if not mentioned:
            text_lower = text.lower()
            for agent_id in self._agent_clients:
                if re.search(r'\b' + re.escape(agent_id) + r'\b', text_lower):
                    if agent_id not in mentioned:
                        mentioned.append(agent_id)
            # Also check display names from agent registry
            if not mentioned:
                try:
                    from vulti_cli.agent_registry import AgentRegistry
                    reg = AgentRegistry()
                    for agent_id in self._agent_clients:
                        agent = reg.get_agent(agent_id)
                        if agent and agent.name:
                            if re.search(r'\b' + re.escape(agent.name.lower()) + r'\b', text_lower):
                                if agent_id not in mentioned:
                                    mentioned.append(agent_id)
                except Exception:
                    pass
        return mentioned

    def _get_room_agent_ids(self, room) -> List[str]:
        """Return agent IDs that are members of this room."""
        agents = []
        if hasattr(room, "users"):
            for uid in room.users:
                agent_id = self._matrix_to_agent.get(uid)
                if agent_id and agent_id in self._agent_clients:
                    agents.append(agent_id)
        return agents

    def _get_owner_user_id(self) -> Optional[str]:
        """Get the owner's Matrix user_id."""
        if not hasattr(self, "_owner_user_id_cached"):
            self._owner_user_id_cached = None
            try:
                from gateway.matrix_agents import _tokens_dir
                owner_path = _tokens_dir() / "_owner.json"
                if owner_path.exists():
                    self._owner_user_id_cached = _json.loads(owner_path.read_text()).get("user_id")
            except Exception:
                pass
        return self._owner_user_id_cached

    def _detect_thread_target(self, event) -> Optional[str]:
        """If this message is a thread reply to an agent's message, return that agent_id."""
        content = getattr(event, "source", {}).get("content", {}) if hasattr(event, "source") else {}
        relates_to = content.get("m.relates_to", {})
        thread_root = relates_to.get("event_id") if relates_to.get("rel_type") == "m.thread" else None
        if not thread_root:
            return None
        return self._sent_event_to_agent.get(thread_root)

    def _track_sent_event(self, event_id: str, agent_id: str) -> None:
        """Record which agent sent an event (for thread targeting)."""
        self._sent_event_to_agent[event_id] = agent_id
        # Cap at 10k entries
        if len(self._sent_event_to_agent) > 10000:
            oldest = next(iter(self._sent_event_to_agent))
            del self._sent_event_to_agent[oldest]

    def _determine_chat_type(self, room) -> str:
        """Determine if a room is a DM or group chat.

        DM = exactly 1 human + 1 agent. Everything else is group.
        """
        if not hasattr(room, "users"):
            if hasattr(room, "member_count"):
                return "dm" if room.member_count <= 2 else "group"
            return "group"

        humans = 0
        agents = 0
        for uid in room.users:
            if uid in self._agent_user_ids:
                agents += 1
            else:
                humans += 1
        return "dm" if humans <= 1 and agents == 1 else "group"

    # ------------------------------------------------------------------
    # Message dispatch
    # ------------------------------------------------------------------

    async def _dispatch_to_agent(
        self, room, event, agent_id: str, chat_type: str,
        response_required: bool, msg_type: MessageType = MessageType.TEXT,
        media_urls: List[str] = None, media_types: List[str] = None,
    ) -> None:
        """Build a MessageEvent and dispatch to the gateway for a specific agent."""
        text = self._translate_mentions(event.body or "")

        # Thread detection
        thread_id = None
        content = getattr(event, "source", {}).get("content", {}) if hasattr(event, "source") else {}
        relates_to = content.get("m.relates_to", {})
        if relates_to.get("rel_type") == "m.thread":
            thread_id = relates_to.get("event_id")

        source = self.build_source(
            chat_id=room.room_id,
            chat_name=room.display_name or room.room_id,
            chat_type=chat_type,
            user_id=event.sender,
            user_name=room.user_name(event.sender) or event.sender,
            thread_id=thread_id,
        )

        timestamp = datetime.fromtimestamp(
            event.server_timestamp / 1000, tz=timezone.utc
        ) if event.server_timestamp else datetime.now(tz=timezone.utc)

        msg_event = MessageEvent(
            source=source,
            text=text,
            message_type=msg_type,
            message_id=event.event_id,
            timestamp=timestamp,
            target_agent_id=agent_id,
            response_required=response_required,
            media_urls=media_urls or [],
            media_types=media_types or [],
        )

        logger.info("Matrix: dispatch → %s (required=%s) chat=%s text='%s'",
                     agent_id, response_required, chat_type, text[:80])
        await self.handle_message(msg_event)

    async def _on_room_message(self, room, event, agent_id: str, client) -> None:
        """Handle incoming text messages.

        DMs: only the DM agent handles, must respond.
        Groups: fan out to all agents in the room. @mentioned agents and
        thread-reply targets must respond; others observe and may stay silent.
        Agent-to-agent: if an agent @mentions another agent in a group room,
        the mentioned agent receives the message and must respond concisely.
        """
        from_agent = event.sender in self._agent_user_ids
        if event.server_timestamp and event.server_timestamp < self._connect_timestamp:
            return

        chat_type = self._determine_chat_type(room)

        # DMs: ignore agent-sent messages (echo), dispatch human messages
        if chat_type == "dm":
            if from_agent:
                return
            await self._dispatch_to_agent(room, event, agent_id, chat_type, response_required=True)
            return

        # Group: check for @mentions before dropping agent messages
        mentioned = self._detect_mentioned_agents(
            event.body or "",
            formatted_body=getattr(event, "formatted_body", None),
        )
        thread_target = self._detect_thread_target(event)

        # Drop agent messages that don't tag anyone — prevents echo loops
        if from_agent and not mentioned and not thread_target:
            return

        # If an agent tags itself, ignore (prevents self-reply loops)
        sender_agent_id = None
        if from_agent:
            for aid, info in self._agent_clients.items():
                if info.get("user_id") == event.sender:
                    sender_agent_id = aid
                    break
            if sender_agent_id:
                mentioned = [m for m in mentioned if m != sender_agent_id]
                if not mentioned and thread_target == sender_agent_id:
                    return

        # Dedup — only the first callback to see this event does the fan-out
        if event.event_id in self._processed_group_events:
            return
        self._processed_group_events[event.event_id] = time.time()
        # Cap dedup cache
        if len(self._processed_group_events) > 5000:
            oldest = next(iter(self._processed_group_events))
            del self._processed_group_events[oldest]

        # Fan out to all agents in the room
        room_agents = self._get_room_agent_ids(room)
        if not room_agents:
            room_agents = [aid for aid, info in self._agent_clients.items() if info.get("client")]

        # When specific agents are @-mentioned or thread-targeted, only dispatch
        # to those agents — skip observers to prevent uninvited responses.
        targeted = set(mentioned)
        if thread_target:
            targeted.add(thread_target)

        for aid in room_agents:
            if targeted and aid not in targeted:
                continue
            # Don't dispatch back to the sender agent
            if aid == sender_agent_id:
                continue
            must_respond = (aid in mentioned) or (aid == thread_target)
            await self._dispatch_to_agent(room, event, aid, chat_type, response_required=must_respond)

    async def _on_room_media(self, room, event, agent_id: str, client, msg_type: MessageType) -> None:
        """Handle incoming media messages."""
        if event.sender in self._agent_user_ids:
            return
        if event.server_timestamp and event.server_timestamp < self._connect_timestamp:
            return

        # Download media
        media_urls = []
        media_types = []
        try:
            import nio
            resp = await client.download(event.url)
            if isinstance(resp, nio.DownloadResponse):
                if msg_type == MessageType.PHOTO:
                    cached_path = cache_image_for_agent(agent_id, resp.body, ".jpg")
                    media_types.append("image/jpeg")
                elif msg_type == MessageType.VOICE:
                    cached_path = cache_audio_for_agent(agent_id, resp.body, ".ogg")
                    media_types.append("audio/ogg")
                else:
                    cached_path = cache_document_for_agent(agent_id, resp.body, event.body or "file")
                    media_types.append("application/octet-stream")
                media_urls.append(cached_path)
        except Exception as e:
            logger.warning("Matrix: failed to download media: %s", e)

        chat_type = self._determine_chat_type(room)

        if chat_type == "dm":
            await self._dispatch_to_agent(
                room, event, agent_id, chat_type, response_required=True,
                msg_type=msg_type, media_urls=media_urls, media_types=media_types,
            )
            return

        # Group: dedup fan-out
        if event.event_id in self._processed_group_events:
            return
        self._processed_group_events[event.event_id] = time.time()

        room_agents = self._get_room_agent_ids(room)
        if not room_agents:
            room_agents = [aid for aid, info in self._agent_clients.items() if info.get("client")]
        for aid in room_agents:
            await self._dispatch_to_agent(
                room, event, aid, chat_type, response_required=False,
                msg_type=msg_type, media_urls=media_urls, media_types=media_types,
            )

    async def _on_member_change(self, room, event, agent_id: str, client) -> None:
        """Handle room membership changes.

        If the owner leaves a DM, the agent leaves too.
        """
        owner_uid = self._get_owner_user_id()
        if not owner_uid:
            return
        if event.state_key != owner_uid:
            return
        if getattr(event, "membership", "") != "leave":
            return

        chat_type = self._determine_chat_type(room)
        if chat_type != "dm":
            return

        try:
            await client.room_leave(room.room_id)
            logger.info("Matrix: %s left room %s (owner left DM)", agent_id, room.room_id)
        except Exception as e:
            logger.warning("Matrix: %s failed to leave %s: %s", agent_id, room.room_id, e)

    def _get_agent_client_for_room(self, room_id: str):
        """Find the correct agent client to use for sending to a room.

        Always prefer the current agent (VULTI_AGENT_ID) so each agent
        sends as themselves. Falls back to any agent in the room.
        """
        # Use the current agent's client (set by the gateway for each agent run)
        current_agent = os.environ.get("VULTI_AGENT_ID", "")
        if current_agent and current_agent in self._agent_clients:
            cli = self._agent_clients[current_agent].get("client")
            if cli:
                return cli

        # Fallback: find any agent that's in this room
        for agent_id, info in self._agent_clients.items():
            cli = info.get("client")
            if cli and room_id in cli.rooms:
                return cli

        # Last resort: primary client
        return self._client

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a text message to a Matrix room using the correct agent's client."""
        # Determine which client to use
        client = self._get_agent_client_for_room(chat_id)
        if not client:
            return SendResult(success=False, error="Not connected")

        try:
            import nio

            # Always send both plaintext body and HTML formatted_body
            # so Matrix clients render markdown (bold, lists, code, etc.)
            msg_content = {
                "msgtype": "m.text",
                "body": content,
            }

            try:
                import markdown
                html = markdown.markdown(
                    content,
                    extensions=["fenced_code", "tables", "nl2br"],
                )
                msg_content["format"] = "org.matrix.custom.html"
                msg_content["formatted_body"] = html
            except ImportError:
                pass

            # Thread support: if metadata contains a thread_id, attach
            # m.relates_to so the reply lands in the correct thread.
            thread_id = (metadata or {}).get("thread_id")
            if thread_id:
                msg_content["m.relates_to"] = {
                    "rel_type": "m.thread",
                    "event_id": thread_id,
                    "is_falling_back": True,
                    "m.in_reply_to": {"event_id": reply_to or thread_id},
                }

            resp = await client.room_send(
                room_id=chat_id,
                message_type="m.room.message",
                content=msg_content,
            )

            if isinstance(resp, nio.RoomSendResponse):
                # Track for thread targeting
                current_agent = os.environ.get("VULTI_AGENT_ID", "")
                if current_agent:
                    self._track_sent_event(resp.event_id, current_agent)
                return SendResult(success=True, message_id=resp.event_id)
            else:
                # nio failed (stale client state) — fall back to httpx direct send
                logger.warning("Matrix: nio send failed to %s (%s), trying httpx fallback",
                               chat_id, type(resp).__name__)
                return await self._send_via_httpx(client, chat_id, msg_content)

        except Exception as e:
            logger.error("Matrix: send error: %s", e)
            return SendResult(success=False, error=str(e))

    async def _send_via_httpx(self, client, room_id: str, content: dict) -> SendResult:
        """Fallback: send a message via httpx when nio room_send fails."""
        import httpx
        import uuid
        from urllib.parse import quote

        txn_id = str(uuid.uuid4())
        url = (
            f"{self.homeserver_url}/_matrix/client/v3/rooms/"
            f"{quote(room_id, safe='')}/send/m.room.message/{txn_id}"
        )
        headers = {"Authorization": f"Bearer {client.access_token}"}

        try:
            async with httpx.AsyncClient(timeout=15.0) as hc:
                resp = await hc.put(url, json=content, headers=headers)
            if resp.status_code == 200:
                event_id = resp.json().get("event_id", "")
                current_agent = os.environ.get("VULTI_AGENT_ID", "")
                if current_agent:
                    self._track_sent_event(event_id, current_agent)
                logger.info("Matrix: httpx fallback sent to %s (event %s)", room_id, event_id)
                return SendResult(success=True, message_id=event_id)
            else:
                error = resp.text[:200]
                logger.warning("Matrix: httpx fallback failed to %s: %s %s", room_id, resp.status_code, error)
                return SendResult(success=False, error=error)
        except Exception as e:
            logger.error("Matrix: httpx fallback error: %s", e)
            return SendResult(success=False, error=str(e))

    async def send_typing(self, chat_id: str, metadata=None) -> None:
        """Send typing indicator."""
        client = self._get_agent_client_for_room(chat_id) or self._client
        if client:
            try:
                await client.room_typing(chat_id, typing_state=True, timeout=10000)
            except Exception:
                pass

    async def send_image(
        self,
        chat_id: str,
        image_url: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send an image to a Matrix room."""
        client = self._get_agent_client_for_room(chat_id) or self._client
        if not client:
            return SendResult(success=False, error="Not connected")

        try:
            import nio

            image_data = None
            if image_url.startswith(("http://", "https://")):
                import httpx
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as http:
                    resp = await http.get(image_url)
                    resp.raise_for_status()
                    image_data = resp.content
            elif os.path.isfile(image_url):
                image_data = Path(image_url).read_bytes()

            if not image_data:
                return await self.send(chat_id, f"{caption}\n{image_url}" if caption else image_url)

            resp, _keys = await client.upload(
                image_data, content_type="image/jpeg", filename="image.jpg",
            )

            if not isinstance(resp, nio.UploadResponse):
                return SendResult(success=False, error="Upload failed")

            content = {
                "msgtype": "m.image",
                "body": caption or "image.jpg",
                "url": resp.content_uri,
                "info": {"mimetype": "image/jpeg", "size": len(image_data)},
            }

            thread_id = (metadata or {}).get("thread_id")
            if thread_id:
                content["m.relates_to"] = {
                    "rel_type": "m.thread",
                    "event_id": thread_id,
                    "is_falling_back": True,
                    "m.in_reply_to": {"event_id": thread_id},
                }

            send_resp = await client.room_send(
                room_id=chat_id, message_type="m.room.message", content=content,
            )

            if isinstance(send_resp, nio.RoomSendResponse):
                return SendResult(success=True, message_id=send_resp.event_id)
            return SendResult(success=False, error=str(send_resp))

        except Exception as e:
            logger.error("Matrix: send_image error: %s", e)
            return await self.send(chat_id, f"{caption}\n{image_url}" if caption else image_url)

    async def send_document(
        self,
        chat_id: str,
        file_path: str,
        caption: Optional[str] = None,
        file_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        **kwargs,
    ) -> SendResult:
        """Send a file to a Matrix room."""
        client = self._get_agent_client_for_room(chat_id) or self._client
        if not client or not os.path.isfile(file_path):
            return SendResult(success=False, error="Not connected or file not found")

        try:
            import nio
            import mimetypes

            file_data = Path(file_path).read_bytes()
            fname = file_name or Path(file_path).name
            mime_type = mimetypes.guess_type(fname)[0] or "application/octet-stream"

            resp, _keys = await client.upload(
                file_data, content_type=mime_type, filename=fname,
            )

            if not isinstance(resp, nio.UploadResponse):
                return SendResult(success=False, error="Upload failed")

            content = {
                "msgtype": "m.file",
                "body": caption or fname,
                "url": resp.content_uri,
                "filename": fname,
                "info": {"mimetype": mime_type, "size": len(file_data)},
            }

            metadata = kwargs.get("metadata")
            thread_id = (metadata or {}).get("thread_id")
            if thread_id:
                content["m.relates_to"] = {
                    "rel_type": "m.thread",
                    "event_id": thread_id,
                    "is_falling_back": True,
                    "m.in_reply_to": {"event_id": thread_id},
                }

            send_resp = await client.room_send(
                room_id=chat_id, message_type="m.room.message", content=content,
            )

            if isinstance(send_resp, nio.RoomSendResponse):
                return SendResult(success=True, message_id=send_resp.event_id)
            return SendResult(success=False, error=str(send_resp))

        except Exception as e:
            logger.error("Matrix: send_document error: %s", e)
            return SendResult(success=False, error=str(e))

    async def get_chat_info(self, chat_id: str) -> dict:
        """Return info about a Matrix room."""
        if not self._client:
            return {"name": chat_id, "type": "unknown", "chat_id": chat_id}

        try:
            rooms = self._client.rooms
            room = rooms.get(chat_id)
            if room:
                return {
                    "name": room.display_name or chat_id,
                    "type": self._determine_chat_type(room),
                    "chat_id": chat_id,
                    "member_count": getattr(room, "member_count", None),
                }
        except Exception:
            pass

        return {"name": chat_id, "type": "unknown", "chat_id": chat_id}

    async def disconnect(self) -> None:
        """Disconnect all agent clients from Matrix."""
        self._running = False

        for task in self._sync_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._sync_tasks.clear()

        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None

        # Close all agent clients
        for agent_id, info in self._agent_clients.items():
            cli = info.get("client")
            if cli:
                try:
                    await cli.close()
                except Exception:
                    pass
                info["client"] = None

        self._client = None
        self._mark_disconnected()
        logger.info("Matrix: disconnected")

    async def _health_monitor(self) -> None:
        """Monitor sync connection health."""
        while self._running:
            try:
                await asyncio.sleep(HEALTH_CHECK_INTERVAL)
                if not self._running:
                    break

                elapsed = time.time() - self._last_sync_activity
                if elapsed > HEALTH_CHECK_STALE_THRESHOLD:
                    logger.warning("Matrix: sync idle for %.0fs", elapsed)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Matrix health check error: %s", e)
