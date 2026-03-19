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
)

logger = logging.getLogger(__name__)

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

        self.homeserver_url: str = config.extra.get("homeserver_url", "http://127.0.0.1:6167")
        self.user_id: str = config.extra.get("user_id", "")
        self.password: str = config.extra.get("password", "")
        self.access_token: str = config.extra.get("access_token", "")
        self.server_name: str = config.extra.get("server_name", "localhost")

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
            logger.error("Matrix: no agent credentials available")
            self._set_fatal_error("MATRIX_NO_USER", "Matrix user_id not configured", retryable=False)
            await self._notify_fatal_error()
            return False

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
                    return on_msg, on_img, on_audio, on_file, on_invite

                on_msg, on_img, on_audio, on_file, on_invite = make_callbacks(agent_id, client)
                client.add_event_callback(on_msg, nio.RoomMessageText)
                client.add_event_callback(on_img, nio.RoomMessageImage)
                client.add_event_callback(on_audio, nio.RoomMessageAudio)
                client.add_event_callback(on_file, nio.RoomMessageFile)
                client.add_event_callback(on_invite, nio.InviteMemberEvent)

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

            # Auto-set home channels: platform-wide #updates + per-agent channels
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

    async def _auto_set_home_channels(self) -> None:
        """Auto-set Matrix home channels: platform default + per-agent.

        Platform default: #updates room
        Per-agent: team room if managed by another agent, owner DM if solo
        Fallback: #updates
        """
        import nio

        # 1. Resolve #updates as platform-wide default
        updates_room_id = None
        try:
            alias = f"#updates:{self.server_name}"
            resp = await self._client.room_resolve_alias(alias)
            if isinstance(resp, nio.RoomResolveAliasResponse):
                updates_room_id = resp.room_id
                if not self.config.home_channel:
                    from gateway.config import HomeChannel
                    self.config.home_channel = HomeChannel(
                        platform=Platform.MATRIX,
                        chat_id=resp.room_id,
                        name="Updates",
                    )
                    os.environ["MATRIX_HOME_CHANNEL"] = resp.room_id
                    logger.info("Matrix: platform home channel → %s (%s)", alias, resp.room_id)
        except Exception as e:
            logger.debug("Matrix: could not resolve #updates: %s", e)

        # 2. Set per-agent home channels
        try:
            from vulti_cli.agent_registry import AgentRegistry
            reg = AgentRegistry()
            reg.ensure_initialized()
            # Read relationships directly from registry data
            reg_data = reg._load()
            relationships = reg_data.get("relationships", [])

            # Identify team-managed agents (managed by another agent, not owner)
            team_managed = set()
            for rel in relationships:
                if rel.get("rel_type") == "manages" and rel.get("from_agent_id") not in ("owner", ""):
                    team_managed.add(rel.get("to_agent_id"))

            for agent_id in self._agent_clients:
                agent = reg.get_agent(agent_id)
                if not agent:
                    continue
                existing = (agent.home_channels or {}).get("matrix")
                if existing and existing.get("chat_id"):
                    continue  # Already configured

                # Team-managed agents: use team room
                if agent_id in team_managed:
                    team_room = None
                    for rel in relationships:
                        if rel.get("to_agent_id") == agent_id and rel.get("from_agent_id") not in ("owner", ""):
                            team_room = rel.get("matrix_room_id")
                            if team_room:
                                break
                    if team_room:
                        reg.set_home_channel(agent_id, "matrix", team_room, name="Team")
                        logger.info("Matrix: %s home channel → team room %s", agent_id, team_room)
                    elif updates_room_id:
                        reg.set_home_channel(agent_id, "matrix", updates_room_id, name="Updates")
                        logger.info("Matrix: %s home channel → #updates (team room not set)", agent_id)
                    continue

                # Solo agent: find DM with owner
                owner_dm = None
                for rel in relationships:
                    if rel.get("from_agent_id") == "owner" and rel.get("to_agent_id") == agent_id:
                        owner_dm = rel.get("matrix_room_id")
                        if owner_dm:
                            break

                if owner_dm:
                    reg.set_home_channel(agent_id, "matrix", owner_dm, name="Owner DM")
                    logger.info("Matrix: %s home channel → owner DM %s", agent_id, owner_dm)
                elif updates_room_id:
                    reg.set_home_channel(agent_id, "matrix", updates_room_id, name="Updates")
                    logger.info("Matrix: %s home channel → #updates (fallback)", agent_id)

        except Exception as e:
            logger.debug("Matrix: per-agent home channel setup failed: %s", e)

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
                    self._last_sync_activity = time.time()
                    backoff = RETRY_DELAY_INITIAL

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    logger.warning("Matrix sync error for %s: %s (retry in %.0fs)", agent_id, e, backoff)

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

    def _detect_target_agent(self, room, sender: str, text: str, receiving_agent_id: str) -> Tuple[str, str]:
        """Detect which agent should handle this message.

        Returns (agent_id_hint, cleaned_text).
        For DMs, returns the agent that owns the DM room.
        For group rooms, parses @mentions.
        """
        chat_type = self._determine_chat_type(room)

        if chat_type == "dm":
            # In a DM, the target is the agent who is in this room
            return receiving_agent_id, text

        # Group room: translate Matrix mentions to gateway format
        translated = self._translate_mentions(text)
        return "", translated  # Let the gateway resolve from the translated @mention

    async def _on_room_message(self, room, event, agent_id: str, client) -> None:
        """Handle incoming text messages for a specific agent."""
        # Skip messages from any Vulti agent
        if event.sender in self._agent_user_ids:
            return

        # Skip old messages (before adapter started) using timestamp
        if event.server_timestamp and event.server_timestamp < self._connect_timestamp:
            return

        # In group rooms, only the primary agent processes (to avoid duplicates)
        chat_type = self._determine_chat_type(room)
        if chat_type == "group":
            primary_id = next(iter(self._agent_clients), None)
            if agent_id != primary_id:
                return  # Only primary agent processes group messages

        logger.info("Matrix: message from %s in %s (%s) → agent %s: %s",
                    event.sender, room.display_name or room.room_id, chat_type,
                    agent_id, (event.body or "")[:80])

        target_agent, cleaned_text = self._detect_target_agent(room, event.sender, event.body or "", agent_id)

        source = self.build_source(
            chat_id=room.room_id,
            chat_name=room.display_name or room.room_id,
            chat_type=chat_type,
            user_id=event.sender,
            user_name=room.user_name(event.sender) or event.sender,
        )

        # If we detected a specific agent for a DM, prefix the text with @agent_id
        # so the gateway routes it correctly
        final_text = cleaned_text
        if target_agent and chat_type == "dm":
            final_text = f"@{target_agent} {cleaned_text}"

        timestamp = datetime.fromtimestamp(
            event.server_timestamp / 1000, tz=timezone.utc
        ) if event.server_timestamp else datetime.now(tz=timezone.utc)

        msg_event = MessageEvent(
            source=source,
            text=final_text,
            message_type=MessageType.TEXT,
            message_id=event.event_id,
            timestamp=timestamp,
        )

        logger.info("Matrix: dispatching to gateway: text='%s' chat_id=%s chat_type=%s",
                     final_text[:100], room.room_id, chat_type)
        await self.handle_message(msg_event)

    async def _on_room_media(self, room, event, agent_id: str, client, msg_type: MessageType) -> None:
        """Handle incoming media messages for a specific agent."""
        if event.sender in self._agent_user_ids:
            return
        if event.server_timestamp and event.server_timestamp < self._connect_timestamp:
            return

        chat_type = self._determine_chat_type(room)
        if chat_type == "group":
            primary_id = next(iter(self._agent_clients), None)
            if agent_id != primary_id:
                return

        media_urls = []
        media_types = []

        try:
            import nio
            resp = await client.download(event.url)
            if isinstance(resp, nio.DownloadResponse):
                if msg_type == MessageType.PHOTO:
                    cached_path = cache_image_from_bytes(resp.body, ".jpg")
                    media_types.append("image/jpeg")
                elif msg_type == MessageType.VOICE:
                    cached_path = cache_audio_from_bytes(resp.body, ".ogg")
                    media_types.append("audio/ogg")
                else:
                    cached_path = cache_document_from_bytes(resp.body, event.body or "file")
                    media_types.append("application/octet-stream")
                media_urls.append(cached_path)
        except Exception as e:
            logger.warning("Matrix: failed to download media: %s", e)

        target_agent, _ = self._detect_target_agent(room, event.sender, "", agent_id)

        source = self.build_source(
            chat_id=room.room_id,
            chat_name=room.display_name or room.room_id,
            chat_type=chat_type,
            user_id=event.sender,
            user_name=room.user_name(event.sender) or event.sender,
        )

        text = event.body or ""
        if target_agent and chat_type == "dm":
            text = f"@{target_agent} {text}"

        msg_event = MessageEvent(
            source=source,
            text=text,
            message_type=msg_type,
            message_id=event.event_id,
            media_urls=media_urls,
            media_types=media_types,
        )

        await self.handle_message(msg_event)

    def _determine_chat_type(self, room) -> str:
        """Determine if a room is a DM or group chat."""
        if hasattr(room, "member_count"):
            return "dm" if room.member_count <= 2 else "group"
        if hasattr(room, "users"):
            return "dm" if len(room.users) <= 2 else "group"
        return "group"

    def _get_agent_client_for_room(self, room_id: str):
        """Find the correct agent client to use for sending to a room.

        For DM rooms, find which agent is in the room and use their client.
        For group rooms, use the active agent's client (from VULTI_AGENT_ID)
        so each agent sends as themselves.
        """
        # Check each agent's client to see if they're in this room
        for agent_id, info in self._agent_clients.items():
            cli = info.get("client")
            if cli and room_id in cli.rooms:
                room = cli.rooms[room_id]
                chat_type = self._determine_chat_type(room)
                if chat_type == "dm":
                    return cli

        # For group rooms, use the current agent's client if available
        current_agent = os.environ.get("VULTI_AGENT_ID", "")
        if current_agent and current_agent in self._agent_clients:
            cli = self._agent_clients[current_agent].get("client")
            if cli:
                return cli

        # Fallback to primary
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

            resp = await client.room_send(
                room_id=chat_id,
                message_type="m.room.message",
                content=msg_content,
            )

            if isinstance(resp, nio.RoomSendResponse):
                return SendResult(success=True, message_id=resp.event_id)
            else:
                error_msg = str(resp) if resp else "Unknown error"
                logger.warning("Matrix: send failed to %s: %s", chat_id, error_msg)
                return SendResult(success=False, error=error_msg)

        except Exception as e:
            logger.error("Matrix: send error: %s", e)
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
