"""
Web platform adapter.

Provides a FastAPI server with WebSocket for real-time chat
and REST endpoints for session/cron/inbox management.
Serves as the backend for the Vulti PWA frontend.
"""

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)
from gateway.session import SessionSource


def check_web_requirements() -> bool:
    """Check if FastAPI and uvicorn are available."""
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
        return True
    except ImportError:
        return False


class WebAdapter(BasePlatformAdapter):
    """
    Web platform adapter using FastAPI + WebSocket.

    Provides:
    - WebSocket endpoint for real-time chat with streaming
    - REST API for session, cron, inbox, contacts management
    - Token-based authentication
    - CORS support for PWA frontend
    """

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.WEB)
        self._host = config.extra.get("host", "0.0.0.0")
        self._port = config.extra.get("port", 8080)
        self._auth_token = config.extra.get("auth_token", "")
        self._cors_origins = [
            o.strip()
            for o in config.extra.get("cors_origins", "http://localhost:5173").split(",")
            if o.strip()
        ]

        # Active WebSocket connections: session_id -> WebSocket
        self._connections: Dict[str, Any] = {}
        # Reverse map: session_id -> chat_id used in gateway
        self._session_chat_map: Dict[str, str] = {}

        self._app = None
        self._server = None
        self._server_task = None

    def _build_app(self):
        """Build the FastAPI application with all routes."""
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query, Header
        from fastapi.middleware.cors import CORSMiddleware
        from pydantic import BaseModel

        app = FastAPI(title="Vulti Web Gateway", version="1.0.0")

        app.add_middleware(
            CORSMiddleware,
            allow_origins=self._cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        adapter = self

        # --- Auth helpers ---

        def verify_token(token: str) -> bool:
            if not adapter._auth_token:
                return True  # No token configured = open access
            return token == adapter._auth_token

        async def get_current_user(authorization: str = Header("")):
            # Accept token from Authorization HTTP header
            token = ""
            if authorization.startswith("Bearer "):
                token = authorization[7:]
            if not verify_token(token):
                raise HTTPException(status_code=401, detail="Invalid token")
            return True

        # --- Request models ---

        class AuthRequest(BaseModel):
            token: str

        class CreateSessionRequest(BaseModel):
            name: Optional[str] = None

        class SendMessageRequest(BaseModel):
            content: str
            attachments: Optional[List[str]] = None

        class CreateCronRequest(BaseModel):
            name: str = "Untitled Job"
            prompt: str
            schedule: str

        class UpdateCronRequest(BaseModel):
            name: Optional[str] = None
            prompt: Optional[str] = None
            schedule: Optional[str] = None
            status: Optional[str] = None

        # --- Auth endpoint ---

        @app.post("/api/auth")
        async def auth(req: AuthRequest):
            if not verify_token(req.token):
                raise HTTPException(status_code=401, detail="Invalid token")
            return {"ok": True}

        # --- Session endpoints ---

        @app.get("/api/sessions")
        async def list_sessions(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_sessions()

        @app.post("/api/sessions")
        async def create_session(req: CreateSessionRequest, authorization: str = Header("")):
            await get_current_user(authorization)
            session_id = uuid.uuid4().hex[:12]
            name = req.name or f"Chat {datetime.now().strftime('%b %d %H:%M')}"
            session = {
                "id": session_id,
                "name": name,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "preview": "",
            }
            adapter._save_session_meta(session_id, session)
            return session

        @app.delete("/api/sessions/{session_id}")
        async def delete_session(session_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            adapter._delete_session_meta(session_id)
            return {"ok": True}

        @app.get("/api/sessions/{session_id}/history")
        async def get_history(session_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_history(session_id)

        # --- Agent endpoints ---

        @app.get("/api/agents")
        async def list_agents(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_agents()

        # --- Cron endpoints ---

        @app.get("/api/cron")
        async def list_cron(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_cron_jobs()

        @app.post("/api/cron")
        async def create_cron(req: CreateCronRequest, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._create_cron_job(req.name, req.prompt, req.schedule)

        @app.put("/api/cron/{job_id}")
        async def update_cron(job_id: str, req: UpdateCronRequest, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._update_cron_job(job_id, req.model_dump(exclude_none=True))

        @app.delete("/api/cron/{job_id}")
        async def delete_cron(job_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._delete_cron_job(job_id)

        # --- Inbox & Contacts ---

        @app.get("/api/inbox")
        async def get_inbox(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_inbox()

        @app.get("/api/contacts")
        async def get_contacts(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_contacts()

        # --- Integrations ---

        @app.get("/api/integrations")
        async def get_integrations(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_integrations()

        # --- Memories & Soul ---

        class MemoryUpdateRequest(BaseModel):
            file: str  # "memory" or "user"
            content: str

        class SoulUpdateRequest(BaseModel):
            content: str

        @app.get("/api/memories")
        async def get_memories(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_memories()

        @app.put("/api/memories")
        async def update_memories(req: MemoryUpdateRequest, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._update_memory(req.file, req.content)

        @app.get("/api/soul")
        async def get_soul(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_soul()

        @app.put("/api/soul")
        async def update_soul(req: SoulUpdateRequest, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._update_soul(req.content)

        # --- System Status ---

        @app.get("/api/status")
        async def get_status(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_system_status()

        @app.get("/api/channels")
        async def get_channels(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_channel_directory()

        # --- Secrets & OAuth ---

        @app.get("/api/secrets")
        async def get_secrets(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_masked_secrets()

        @app.get("/api/oauth")
        async def get_oauth(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_oauth_status()

        # --- Analytics ---

        @app.get("/api/analytics")
        async def get_analytics(days: int = 30, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_analytics(days)

        # --- WebSocket ---

        @app.websocket("/ws/{session_id}")
        async def websocket_endpoint(websocket: WebSocket, session_id: str, token: str = Query("")):
            # Auth check
            if not verify_token(token):
                await websocket.close(code=4001, reason="Unauthorized")
                return

            await websocket.accept()
            adapter._connections[session_id] = websocket
            logger.info("[web] WebSocket connected: session=%s", session_id)

            try:
                while True:
                    raw = await websocket.receive_text()
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    msg_type = data.get("type", "")

                    if msg_type == "message":
                        content = data.get("content", "").strip()
                        if not content:
                            continue

                        # Build source for gateway
                        source = SessionSource(
                            platform=Platform.WEB,
                            chat_id=f"web:{session_id}",
                            chat_type="dm",
                            user_id="web_user",
                            user_name="Web User",
                        )

                        event = MessageEvent(
                            text=content,
                            message_type=MessageType.TEXT,
                            source=source,
                            message_id=uuid.uuid4().hex[:12],
                            timestamp=datetime.now(),
                        )

                        # Store message in history
                        adapter._append_history(session_id, {
                            "id": event.message_id,
                            "role": "user",
                            "content": content,
                            "timestamp": event.timestamp.isoformat(),
                        })

                        # Route through gateway message handler
                        if adapter._message_handler:
                            # Run in background so we don't block WS receive loop
                            task = asyncio.create_task(
                                adapter._handle_and_respond(session_id, event)
                            )
                            adapter._background_tasks.add(task)
                            task.add_done_callback(adapter._background_tasks.discard)

                    elif msg_type == "action":
                        # Handle notification actions
                        notification_id = data.get("notification_id", "")
                        action = data.get("action", "")
                        logger.info(
                            "[web] Action on notification %s: %s",
                            notification_id, action,
                        )

            except WebSocketDisconnect:
                logger.info("[web] WebSocket disconnected: session=%s", session_id)
            except Exception as e:
                logger.error("[web] WebSocket error: %s", e)
            finally:
                adapter._connections.pop(session_id, None)

        self._app = app
        return app

    async def _handle_and_respond(self, session_id: str, event: MessageEvent):
        """Handle a message event through the gateway and stream response."""
        try:
            # Send typing indicator
            ws = self._connections.get(session_id)
            if ws:
                await ws.send_text(json.dumps({"type": "typing", "active": True}))

            # Call gateway message handler
            response = await self._message_handler(event)

            if response and ws:
                msg_id = uuid.uuid4().hex[:12]
                # Send complete message
                await ws.send_text(json.dumps({
                    "type": "message",
                    "content": response,
                    "id": msg_id,
                }))

                # Store in history
                self._append_history(session_id, {
                    "id": msg_id,
                    "role": "assistant",
                    "content": response,
                    "timestamp": datetime.now().isoformat(),
                })

                # Update session preview
                preview = response[:100] if response else ""
                meta = self._get_session_meta(session_id)
                if meta:
                    meta["preview"] = preview
                    meta["updated_at"] = datetime.now().isoformat()
                    self._save_session_meta(session_id, meta)

        except Exception as e:
            logger.error("[web] Error handling message: %s", e)
            ws = self._connections.get(session_id)
            if ws:
                await ws.send_text(json.dumps({
                    "type": "error",
                    "content": f"Error: {e}",
                }))

    # --- BasePlatformAdapter implementation ---

    async def connect(self) -> bool:
        """Start the FastAPI server."""
        import uvicorn

        if self._app is None:
            self._build_app()

        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level="info",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        # Run server in background task
        self._server_task = asyncio.create_task(self._server.serve())
        self._mark_connected()
        logger.info("[web] Web adapter started on %s:%s", self._host, self._port)

        # Print QR code for easy mobile connection
        self._print_connect_qr()

        return True

    async def disconnect(self) -> None:
        """Stop the FastAPI server."""
        # Close all WebSocket connections
        for session_id, ws in list(self._connections.items()):
            try:
                await ws.close()
            except Exception:
                pass
        self._connections.clear()

        # Shutdown server
        if self._server:
            self._server.should_exit = True
            if self._server_task:
                try:
                    await asyncio.wait_for(self._server_task, timeout=5.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    self._server_task.cancel()

        self._mark_disconnected()
        logger.info("[web] Web adapter stopped")

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a message to a web client via WebSocket."""
        # chat_id format: "web:{session_id}"
        session_id = chat_id.replace("web:", "", 1) if chat_id.startswith("web:") else chat_id
        ws = self._connections.get(session_id)
        if not ws:
            return SendResult(success=False, error="Client not connected")

        msg_id = uuid.uuid4().hex[:12]
        try:
            await ws.send_text(json.dumps({
                "type": "message",
                "content": content,
                "id": msg_id,
            }))

            self._append_history(session_id, {
                "id": msg_id,
                "role": "assistant",
                "content": content,
                "timestamp": datetime.now().isoformat(),
            })

            return SendResult(success=True, message_id=msg_id)
        except Exception as e:
            return SendResult(success=False, error=str(e))

    async def edit_message(
        self,
        chat_id: str,
        message_id: str,
        content: str,
    ) -> SendResult:
        """Edit a message (used for streaming token updates)."""
        session_id = chat_id.replace("web:", "", 1) if chat_id.startswith("web:") else chat_id
        ws = self._connections.get(session_id)
        if not ws:
            return SendResult(success=False, error="Client not connected")

        try:
            await ws.send_text(json.dumps({
                "type": "chunk",
                "content": content,
                "id": message_id,
            }))
            return SendResult(success=True, message_id=message_id)
        except Exception as e:
            return SendResult(success=False, error=str(e))

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Get info about a web chat session."""
        session_id = chat_id.replace("web:", "", 1) if chat_id.startswith("web:") else chat_id
        meta = self._get_session_meta(session_id)
        return {
            "name": meta.get("name", "Web Chat") if meta else "Web Chat",
            "type": "dm",
        }

    async def send_typing(self, chat_id: str, metadata=None) -> None:
        """Send typing indicator."""
        session_id = chat_id.replace("web:", "", 1) if chat_id.startswith("web:") else chat_id
        ws = self._connections.get(session_id)
        if ws:
            try:
                await ws.send_text(json.dumps({"type": "typing", "active": True}))
            except Exception:
                pass

    # --- Notification forwarding ---

    async def broadcast_notification(self, source: str, summary: str, actions: List[str] = None):
        """Send a notification to all connected web clients."""
        notification = {
            "type": "notification",
            "source": source,
            "summary": summary,
            "actions": actions or [],
            "notification_id": uuid.uuid4().hex[:12],
        }
        msg = json.dumps(notification)
        for session_id, ws in list(self._connections.items()):
            try:
                await ws.send_text(msg)
            except Exception:
                pass

    # --- Data access helpers ---
    # These use simple JSON file storage under ~/.vulti/web/

    def _get_data_dir(self):
        from vulti_cli.config import get_vulti_home
        d = get_vulti_home() / "web"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _get_sessions(self) -> list:
        """List all web sessions."""
        data_dir = self._get_data_dir() / "sessions"
        if not data_dir.exists():
            return []
        sessions = []
        for f in sorted(data_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                sessions.append(json.loads(f.read_text()))
            except Exception:
                pass
        return sessions

    def _get_session_meta(self, session_id: str) -> Optional[dict]:
        f = self._get_data_dir() / "sessions" / f"{session_id}.json"
        if f.exists():
            return json.loads(f.read_text())
        return None

    def _save_session_meta(self, session_id: str, meta: dict):
        d = self._get_data_dir() / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{session_id}.json").write_text(json.dumps(meta))

    def _delete_session_meta(self, session_id: str):
        f = self._get_data_dir() / "sessions" / f"{session_id}.json"
        if f.exists():
            f.unlink()
        # Also delete history
        h = self._get_data_dir() / "history" / f"{session_id}.jsonl"
        if h.exists():
            h.unlink()

    def _get_history(self, session_id: str) -> list:
        """Get conversation history for a session."""
        f = self._get_data_dir() / "history" / f"{session_id}.jsonl"
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

    def _append_history(self, session_id: str, message: dict):
        """Append a message to session history."""
        d = self._get_data_dir() / "history"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / f"{session_id}.jsonl", "a") as f:
            f.write(json.dumps(message) + "\n")

    def _get_agents(self) -> list:
        """List connected agents/platforms from gateway config."""
        try:
            from gateway.config import load_gateway_config
            config = load_gateway_config()
            platforms = config.get_connected_platforms()
            return [{
                "id": "local",
                "name": "Vulti",
                "url": f"http://{self._host}:{self._port}",
                "status": "connected" if self._running else "disconnected",
                "platforms": [p.value for p in platforms],
            }]
        except Exception:
            return []

    def _get_cron_jobs(self) -> list:
        """List cron jobs from the cron system."""
        try:
            from cron.scheduler import CronScheduler
            scheduler = CronScheduler.get_instance()
            if scheduler:
                jobs = scheduler.list_jobs()
                return [{
                    "id": j.get("id", ""),
                    "name": j.get("name", ""),
                    "prompt": j.get("prompt", ""),
                    "schedule": j.get("schedule", ""),
                    "status": "active" if not j.get("paused") else "paused",
                    "last_run": j.get("last_run"),
                    "last_output": j.get("last_output"),
                } for j in jobs]
        except Exception as e:
            logger.debug("[web] Could not load cron jobs: %s", e)
        return []

    def _create_cron_job(self, name: str, prompt: str, schedule: str) -> dict:
        """Create a cron job via the cron tool."""
        try:
            from tools.cronjob_tools import cronjob
            result = cronjob(
                action="create",
                name=name,
                prompt=prompt,
                schedule=schedule,
            )
            return json.loads(result) if isinstance(result, str) else result
        except Exception as e:
            return {"error": str(e)}

    def _update_cron_job(self, job_id: str, updates: dict) -> dict:
        """Update a cron job."""
        try:
            from tools.cronjob_tools import cronjob
            action = "update"
            if "status" in updates:
                action = "pause" if updates["status"] == "paused" else "resume"
                del updates["status"]

            result = cronjob(action=action, job_id=job_id, **updates)
            return json.loads(result) if isinstance(result, str) else result
        except Exception as e:
            return {"error": str(e)}

    def _delete_cron_job(self, job_id: str) -> dict:
        """Delete a cron job."""
        try:
            from tools.cronjob_tools import cronjob
            result = cronjob(action="remove", job_id=job_id)
            return json.loads(result) if isinstance(result, str) else result
        except Exception as e:
            return {"error": str(e)}

    def _get_inbox(self) -> list:
        """Get unified inbox from cross-platform messages."""
        # Inbox items are stored when notifications are forwarded
        f = self._get_data_dir() / "inbox.jsonl"
        if not f.exists():
            return []
        items = []
        for line in f.read_text().strip().split("\n"):
            if line.strip():
                try:
                    items.append(json.loads(line))
                except Exception:
                    pass
        # Return most recent first
        return sorted(items, key=lambda x: x.get("timestamp", ""), reverse=True)[:100]

    def _get_contacts(self) -> list:
        """Get contacts built from interactions."""
        f = self._get_data_dir() / "contacts.json"
        if f.exists():
            try:
                return json.loads(f.read_text())
            except Exception:
                pass
        return []

    def _get_integrations(self) -> list:
        """Get all integrations aggregated from multiple sources."""
        home = self._get_vulti_home()
        integrations = []

        # 1. Gateway platform connections (live status)
        gateway_status = self._get_system_status()
        platforms = gateway_status.get("platforms", {})
        platform_meta = {
            "telegram": {"name": "Telegram", "icon": "telegram", "category": "Messaging"},
            "discord": {"name": "Discord", "icon": "discord", "category": "Messaging"},
            "whatsapp": {"name": "WhatsApp", "icon": "whatsapp", "category": "Messaging"},
            "slack": {"name": "Slack", "icon": "slack", "category": "Messaging"},
            "signal": {"name": "Signal", "icon": "signal", "category": "Messaging"},
            "email": {"name": "Email", "icon": "email", "category": "Messaging"},
            "homeassistant": {"name": "Home Assistant", "icon": "homeassistant", "category": "Smart Home"},
        }
        for pid, info in platforms.items():
            if pid == "web":
                continue
            meta = platform_meta.get(pid, {"name": pid.title(), "icon": pid, "category": "Platform"})
            integrations.append({
                "id": pid,
                "name": meta["name"],
                "category": meta["category"],
                "status": info.get("state", "unknown"),
                "details": {},
                "updated_at": info.get("updated_at"),
            })

        # 2. Parse MEMORY.md for additional integrations
        mem_file = home / "memories" / "MEMORY.md"
        if mem_file.exists():
            mem = mem_file.read_text()
            sections = mem.split("§")
            for section in sections:
                s = section.strip()
                if not s:
                    continue

                if "Google Cloud" in s or "Google Workspace" in s:
                    # Only add if not already from gateway
                    if not any(i["id"] == "google" for i in integrations):
                        integrations.append({
                            "id": "google",
                            "name": "Google Workspace",
                            "category": "Cloud",
                            "status": "connected" if (home / "google_token.json").exists() else "configured",
                            "details": self._extract_details(s, [
                                "Gmail", "Calendar", "Drive", "Contacts", "Sheets", "Docs",
                            ]),
                        })

                if "iCloud Mail" in s or "himalaya" in s:
                    if not any(i["id"] == "icloud" for i in integrations):
                        integrations.append({
                            "id": "icloud",
                            "name": "iCloud Mail",
                            "category": "Messaging",
                            "status": "connected",
                            "details": {"account": self._extract_field(s, r"Account:\s*(\S+)")},
                        })

                if "Telegram Client API" in s or "Telethon" in s:
                    # Enrich existing telegram entry
                    for i in integrations:
                        if i["id"] == "telegram":
                            i["details"]["user"] = self._extract_field(s, r"User:\s*(@\S+)")
                            i["details"]["user_id"] = self._extract_field(s, r"id:(\d+)")
                            break

                if "WhatsApp" in s and "Mac app" in s:
                    # Enrich or add WhatsApp
                    existing = next((i for i in integrations if i["id"] == "whatsapp"), None)
                    if existing:
                        existing["details"]["method"] = "Mac SQLite DB"
                    else:
                        integrations.append({
                            "id": "whatsapp",
                            "name": "WhatsApp",
                            "category": "Messaging",
                            "status": "configured",
                            "details": {"method": "Mac SQLite DB"},
                        })

                if "X/Twitter" in s or "x-cli" in s:
                    if not any(i["id"] == "x-twitter" for i in integrations):
                        handle = self._extract_field(s, r"handle:\s*(@\S+)")
                        has_credits = "CreditsDepleted" not in s
                        integrations.append({
                            "id": "x-twitter",
                            "name": "X / Twitter",
                            "category": "Social",
                            "status": "connected" if has_credits else "degraded",
                            "details": {
                                "handle": handle,
                                "note": "CreditsDepleted — needs paid plan" if not has_credits else "",
                            },
                        })

                if "Twilio" in s:
                    if not any(i["id"] == "twilio" for i in integrations):
                        acct = self._extract_field(s, r"account\s*\((\w+\.\.\.?\w+)\)")
                        integrations.append({
                            "id": "twilio",
                            "name": "Twilio",
                            "category": "Voice & SMS",
                            "status": "connected" if "reactivated" in s else "configured",
                            "details": {"account": acct, "note": "Reactivated 17 Mar 2026" if "reactivated" in s else ""},
                        })

                if "Bland.ai" in s or "bland" in s.lower():
                    if not any(i["id"] == "bland" for i in integrations):
                        integrations.append({
                            "id": "bland",
                            "name": "Bland.ai",
                            "category": "Voice & SMS",
                            "status": "connected",
                            "details": {
                                "voices": "mason (working), sophie-australian (broken)",
                                "note": "Twilio voice server at twilio_voice_server.py",
                            },
                        })

        # 3. OAuth tokens as integrations
        if (home / "google_token.json").exists():
            # Enrich Google entry with OAuth details
            for i in integrations:
                if i["id"] == "google":
                    try:
                        data = json.loads((home / "google_token.json").read_text())
                        i["details"]["scopes"] = len(data.get("scopes", []))
                        i["details"]["has_refresh"] = bool(data.get("refresh_token"))
                    except Exception:
                        pass

        if (home / "x_oauth2_token.json").exists():
            for i in integrations:
                if i["id"] == "x-twitter":
                    try:
                        data = json.loads((home / "x_oauth2_token.json").read_text())
                        i["details"]["oauth"] = "valid" if data.get("access_token") else "expired"
                    except Exception:
                        pass

        # 4. Check for Firecrawl, FAL, Browserbase from .env
        env_file = home / ".env"
        if env_file.exists():
            env_text = env_file.read_text()
            tool_services = [
                ("firecrawl", "Firecrawl", "Tools", "FIRECRAWL_API_KEY"),
                ("fal", "FAL.ai", "Tools", "FAL_KEY"),
                ("browserbase", "Browserbase", "Tools", "BROWSERBASE_API_KEY"),
                ("openrouter", "OpenRouter", "LLM", "OPENROUTER_API_KEY"),
                ("groq", "Groq", "LLM", "GROQ_API_KEY"),
            ]
            for sid, sname, scat, env_key in tool_services:
                if not any(i["id"] == sid for i in integrations):
                    # Check if key is set (non-empty, non-commented)
                    is_set = False
                    for line in env_text.splitlines():
                        line = line.strip()
                        if line.startswith(env_key + "="):
                            val = line.split("=", 1)[1].strip().strip("'\"")
                            if val:
                                is_set = True
                            break
                    if is_set:
                        integrations.append({
                            "id": sid,
                            "name": sname,
                            "category": scat,
                            "status": "connected",
                            "details": {},
                        })

        return integrations

    @staticmethod
    def _extract_field(text: str, pattern: str) -> str:
        """Extract a field from text using regex."""
        m = re.search(pattern, text)
        return m.group(1) if m else ""

    @staticmethod
    def _extract_details(text: str, keywords: list) -> dict:
        """Check which keywords appear in text."""
        found = [k for k in keywords if k.lower() in text.lower()]
        return {"services": found} if found else {}

    # --- Memories & Soul ---

    def _get_vulti_home(self) -> Path:
        from vulti_cli.config import get_vulti_home
        return get_vulti_home()

    def _get_memories(self) -> dict:
        """Read MEMORY.md and USER.md from ~/.vulti/memories/."""
        home = self._get_vulti_home()
        mem_dir = home / "memories"
        result = {"memory": "", "user": ""}
        for key, fname in [("memory", "MEMORY.md"), ("user", "USER.md")]:
            f = mem_dir / fname
            if f.exists():
                result[key] = f.read_text()
        return result

    def _update_memory(self, file_key: str, content: str) -> dict:
        """Update MEMORY.md or USER.md."""
        if file_key not in ("memory", "user"):
            return {"error": "Invalid file key. Use 'memory' or 'user'."}
        home = self._get_vulti_home()
        mem_dir = home / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        fname = "MEMORY.md" if file_key == "memory" else "USER.md"
        (mem_dir / fname).write_text(content)
        return {"ok": True}

    def _get_soul(self) -> dict:
        """Read SOUL.md."""
        home = self._get_vulti_home()
        f = home / "SOUL.md"
        return {"content": f.read_text() if f.exists() else ""}

    def _update_soul(self, content: str) -> dict:
        """Update SOUL.md."""
        home = self._get_vulti_home()
        (home / "SOUL.md").write_text(content)
        return {"ok": True}

    # --- System Status ---

    def _get_system_status(self) -> dict:
        """Read gateway_state.json for platform connection status."""
        home = self._get_vulti_home()
        f = home / "gateway_state.json"
        if f.exists():
            try:
                return json.loads(f.read_text())
            except Exception:
                pass
        return {"gateway_state": "unknown", "platforms": {}}

    def _get_channel_directory(self) -> dict:
        """Read channel_directory.json."""
        home = self._get_vulti_home()
        f = home / "channel_directory.json"
        if f.exists():
            try:
                return json.loads(f.read_text())
            except Exception:
                pass
        return {"platforms": {}}

    # --- Secrets & OAuth ---

    @staticmethod
    def _mask_value(value: str) -> str:
        """Mask a secret value, showing first 5 and last 4 chars."""
        if len(value) <= 12:
            return value[:3] + "..." + value[-2:] if len(value) > 5 else "***"
        return value[:5] + "..." + value[-4:]

    def _get_masked_secrets(self) -> list:
        """Read .env and return keys with masked values."""
        home = self._get_vulti_home()
        env_file = home / ".env"
        if not env_file.exists():
            return []

        secrets = []
        # Categorize keys
        categories = {
            "LLM Providers": ["OPENROUTER", "OPENAI", "GLM", "KIMI", "MINIMAX", "OPENCODE", "GROQ", "ANTHROPIC"],
            "Messaging": ["TELEGRAM", "DISCORD", "WHATSAPP", "SLACK", "SIGNAL", "EMAIL"],
            "Tools": ["FIRECRAWL", "FAL", "BROWSERBASE", "HONCHO", "TINKER", "GITHUB"],
            "Voice & Audio": ["VOICE_TOOLS", "WHISPER", "ELEVENLABS", "TTS"],
            "Analytics & ML": ["WANDB", "TINKER"],
            "Google": ["GOOGLE"],
            "Other": [],
        }

        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")

            # Determine category
            category = "Other"
            for cat_name, prefixes in categories.items():
                if any(key.upper().startswith(p) for p in prefixes):
                    category = cat_name
                    break

            secrets.append({
                "key": key,
                "masked_value": self._mask_value(value) if value else "",
                "is_set": bool(value),
                "category": category,
            })
        return secrets

    def _get_oauth_status(self) -> list:
        """Check OAuth token files for validity."""
        home = self._get_vulti_home()
        tokens = []

        # Google OAuth
        google_token = home / "google_token.json"
        if google_token.exists():
            try:
                data = json.loads(google_token.read_text())
                tokens.append({
                    "service": "Google",
                    "valid": bool(data.get("token")),
                    "scopes": data.get("scopes", []),
                    "has_refresh": bool(data.get("refresh_token")),
                })
            except Exception:
                tokens.append({"service": "Google", "valid": False})
        else:
            tokens.append({"service": "Google", "valid": False})

        # X/Twitter OAuth
        x_token = home / "x_oauth2_token.json"
        if x_token.exists():
            try:
                data = json.loads(x_token.read_text())
                tokens.append({
                    "service": "X / Twitter",
                    "valid": bool(data.get("access_token")),
                    "has_refresh": bool(data.get("refresh_token")),
                })
            except Exception:
                tokens.append({"service": "X / Twitter", "valid": False})
        else:
            tokens.append({"service": "X / Twitter", "valid": False})

        # Telegram session
        telegram_session = home / "telegram_user_session.session"
        tokens.append({
            "service": "Telegram (User Session)",
            "valid": telegram_session.exists(),
        })

        return tokens

    # --- Analytics ---

    def _get_analytics(self, days: int = 30) -> dict:
        """Get usage analytics from InsightsEngine."""
        try:
            from agent.insights import InsightsEngine
            from vulti_state import SessionDB
            db = SessionDB()
            engine = InsightsEngine(db)
            return engine.generate(days=days)
        except Exception as e:
            logger.debug("[web] Could not load analytics: %s", e)
            return {"error": str(e), "empty": True}

    # --- QR Code ---

    def _print_connect_qr(self):
        """Print a QR code to the terminal for easy connection."""
        web_url = self.config.extra.get("web_url", "")
        if not web_url:
            # Default to localhost frontend
            web_url = f"http://localhost:5173"

        connect_url = f"{web_url}?token={self._auth_token}"

        try:
            import qrcode
            qr = qrcode.QRCode(box_size=1, border=1)
            qr.add_data(connect_url)
            qr.make(fit=True)

            print("\n" + "=" * 50)
            print("  Vulti Web Portal")
            print("=" * 50)
            print("\n  Scan to connect:\n")
            qr.print_ascii(invert=True)
            print(f"\n  Or open: {connect_url}")
            print("=" * 50 + "\n")
        except ImportError:
            # qrcode not installed, just print URL
            print(f"\n[web] Connect at: {connect_url}\n")
