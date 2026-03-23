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


async def _hot_add_to_matrix(agent_id: str) -> None:
    """Hot-add an agent to the running Matrix adapter."""
    try:
        from gateway.run import _active_runner
        if _active_runner:
            matrix_adapter = _active_runner.adapters.get(Platform.MATRIX)
            if matrix_adapter and hasattr(matrix_adapter, 'hot_add_agent'):
                await matrix_adapter.hot_add_agent(agent_id)
    except Exception as e:
        logger.warning("[web] hot_add_to_matrix failed for %s: %s", agent_id, e)


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
        super().__init__(config, Platform.APP)
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
        # Track last streamed content per session for history storage
        self._last_streamed: Dict[str, str] = {}
        # Sessions with active streaming — send() uses "chunk" type instead
        # of "message" to avoid creating committed message bubbles mid-stream
        self._streaming_sessions: set = set()
        # Per-session tool progress callbacks for WebSocket clients
        self._ws_tool_callbacks: Dict[str, callable] = {}

    def _build_app(self):
        """Build the FastAPI application with all routes."""
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query, Header, Request
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

        # Track whether current request is from localhost
        from contextvars import ContextVar
        _is_localhost: ContextVar[bool] = ContextVar('_is_localhost', default=False)

        @app.middleware("http")
        async def localhost_auth_bypass(request: Request, call_next):
            host = request.client.host if request.client else ""
            token = _is_localhost.set(host in ("127.0.0.1", "::1"))
            try:
                return await call_next(request)
            finally:
                _is_localhost.reset(token)

        async def get_current_user(authorization: str = Header("")):
            if _is_localhost.get(False):
                return True
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

        class CreateRuleRequest(BaseModel):
            name: str = "Untitled Rule"
            condition: str
            action: str
            priority: int = 0
            max_triggers: Optional[int] = None
            cooldown_minutes: Optional[int] = None
            tags: Optional[list] = None

        class UpdateRuleRequest(BaseModel):
            name: Optional[str] = None
            condition: Optional[str] = None
            action: Optional[str] = None
            priority: Optional[int] = None
            max_triggers: Optional[int] = None
            cooldown_minutes: Optional[int] = None
            tags: Optional[list] = None
            enabled: Optional[bool] = None

        # --- Auth endpoint ---

        @app.post("/api/auth")
        async def auth(req: AuthRequest):
            if not verify_token(req.token):
                raise HTTPException(status_code=401, detail="Invalid token")
            return {"ok": True}

        @app.get("/api/bootstrap")
        async def bootstrap(request: Request):
            """Return auth token for local hub bootstrap (localhost only)."""
            host = request.client.host if request.client else ""
            if host not in ("127.0.0.1", "::1", "localhost"):
                raise HTTPException(status_code=403, detail="Local access only")
            return {"token": adapter._auth_token or ""}

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

        @app.patch("/api/sessions/{session_id}")
        async def update_session(session_id: str, req: Request, authorization: str = Header("")):
            await get_current_user(authorization)
            data = await req.json()
            meta = adapter._get_session_meta(session_id)
            if not meta:
                return {"ok": False, "error": "Session not found"}
            for field in ("name", "preview"):
                if field in data:
                    meta[field] = data[field]
            adapter._save_session_meta(session_id, meta)
            return meta

        @app.delete("/api/sessions/{session_id}")
        async def delete_session(session_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            adapter._delete_session_meta(session_id)
            return {"ok": True}

        @app.get("/api/sessions/{session_id}/history")
        async def get_history(session_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_history(session_id)

        @app.post("/api/sessions/{session_id}/generate-title")
        async def generate_session_title(session_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            title = await adapter._generate_session_title(session_id)
            if not title:
                return {"ok": False, "error": "Could not generate title"}
            meta = adapter._get_session_meta(session_id)
            if meta:
                meta["name"] = title
                adapter._save_session_meta(session_id, meta)
            return {"ok": True, "title": title}

        @app.post("/api/sessions/{session_id}/mark-read")
        async def mark_session_read(session_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            # Mark all inbox items for this session as read
            adapter._mark_session_inbox_read(session_id)
            return {"ok": True}

        @app.post("/api/inbox/{item_id}/read")
        async def mark_inbox_read(item_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            adapter._mark_inbox_item_read(item_id)
            return {"ok": True}

        # --- Agent endpoints ---

        @app.get("/api/agents")
        async def list_agents(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_agents()

        @app.post("/api/agents")
        async def create_agent(req: Request, authorization: str = Header("")):
            await get_current_user(authorization)
            data = await req.json()
            result = adapter._create_agent(data)
            # Register on Matrix and create owner DM in background
            asyncio.create_task(
                adapter._setup_agent_matrix(result["id"], result["name"])
            )
            return result

        @app.get("/api/agents/{agent_id}")
        async def get_agent(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_agent(agent_id)

        @app.put("/api/agents/{agent_id}")
        async def update_agent(agent_id: str, req: Request, authorization: str = Header("")):
            await get_current_user(authorization)
            data = await req.json()
            return adapter._update_agent(agent_id, data)

        @app.delete("/api/agents/{agent_id}")
        async def delete_agent(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return await adapter._delete_agent(agent_id)

        @app.post("/api/reset")
        async def reset_everything(authorization: str = Header("")):
            await get_current_user(authorization)
            return await adapter._reset_everything()

        @app.post("/api/reset/factory")
        async def factory_reset(authorization: str = Header("")):
            await get_current_user(authorization)
            return await adapter._factory_reset()

        # --- Agent-scoped resource endpoints ---

        @app.get("/api/agents/{agent_id}/memories")
        async def get_agent_memories(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_memories(agent_id=agent_id)

        @app.put("/api/agents/{agent_id}/memories")
        async def update_agent_memories(agent_id: str, req: Request, authorization: str = Header("")):
            await get_current_user(authorization)
            data = await req.json()
            return adapter._update_memory(data.get("file", "memory"), data.get("content", ""), agent_id=agent_id)

        @app.get("/api/agents/{agent_id}/soul")
        async def get_agent_soul(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_soul(agent_id=agent_id)

        @app.put("/api/agents/{agent_id}/soul")
        async def update_agent_soul(agent_id: str, req: Request, authorization: str = Header("")):
            await get_current_user(authorization)
            data = await req.json()
            return adapter._update_soul(data.get("content", ""), agent_id=agent_id)

        @app.post("/api/agents/{agent_id}/generate-avatar")
        async def generate_agent_avatar(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return await asyncio.to_thread(adapter._generate_avatar, agent_id)

        @app.post("/api/agents/{agent_id}/sync-avatar")
        async def sync_agent_avatar_endpoint(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            try:
                from gateway.matrix_agents import sync_agent_avatar
                from gateway.config import load_gateway_config
                config = load_gateway_config()
                hs = config.get("matrix", {}).get("homeserver_url")
                if not hs:
                    return {"ok": False, "error": "Matrix not configured"}
                ok = await sync_agent_avatar(agent_id, hs)
                return {"ok": ok}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        @app.get("/api/agents/{agent_id}/cron")
        async def get_agent_cron(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_cron_jobs(agent_id=agent_id)

        @app.get("/api/agents/{agent_id}/sessions")
        async def list_agent_sessions(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_agent_sessions(agent_id=agent_id)

        @app.post("/api/agents/{agent_id}/sessions")
        async def create_agent_session(agent_id: str, req: CreateSessionRequest, authorization: str = Header("")):
            await get_current_user(authorization)
            session_id = uuid.uuid4().hex[:12]
            name = req.name or f"Chat {datetime.now().strftime('%b %d %H:%M')}"
            session = {
                "id": session_id,
                "name": name,
                "agent_id": agent_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "preview": "",
            }
            adapter._save_session_meta(session_id, session)
            return session

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

        # --- Rules ---

        @app.get("/api/rules")
        async def list_rules(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_rules()

        @app.get("/api/agents/{agent_id}/rules")
        async def get_agent_rules(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_rules(agent_id=agent_id)

        @app.post("/api/rules")
        async def create_rule(req: CreateRuleRequest, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._create_rule(req.model_dump())

        @app.post("/api/agents/{agent_id}/rules")
        async def create_agent_rule(agent_id: str, req: CreateRuleRequest, authorization: str = Header("")):
            await get_current_user(authorization)
            data = req.model_dump()
            data["agent"] = agent_id
            return adapter._create_rule(data)

        @app.put("/api/rules/{rule_id}")
        async def update_rule(rule_id: str, req: UpdateRuleRequest, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._update_rule(rule_id, req.model_dump(exclude_none=True))

        @app.delete("/api/rules/{rule_id}")
        async def delete_rule(rule_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._delete_rule(rule_id)

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

        # --- Matrix Well-Known (no auth required — Element needs these) ---

        @app.get("/.well-known/matrix/client")
        async def matrix_well_known_client():
            """Serve Matrix client well-known for Element discovery."""
            port = int(os.getenv("MATRIX_CONTINUWUITY_PORT", "6167"))
            server_name = os.getenv("MATRIX_SERVER_NAME", "localhost")
            # Use the gateway's own host for the base URL
            base_url = f"http://localhost:{port}"
            # If Tailscale is available, use HTTPS
            try:
                import subprocess
                result = subprocess.run(
                    ["tailscale", "status", "--json"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    ts_data = json.loads(result.stdout)
                    ts_name = ts_data.get("Self", {}).get("DNSName", "").rstrip(".")
                    if ts_name:
                        base_url = f"https://{ts_name}"
            except Exception:
                pass
            return {
                "m.homeserver": {"base_url": base_url},
                "m.identity_server": {"base_url": "https://matrix.org"},
            }

        @app.get("/.well-known/matrix/server")
        async def matrix_well_known_server():
            """Serve Matrix server well-known for federation."""
            port = int(os.getenv("MATRIX_CONTINUWUITY_PORT", "6167"))
            server_name = os.getenv("MATRIX_SERVER_NAME", "localhost")
            return {"m.server": f"{server_name}:{port}"}

        # --- Matrix Account ---

        @app.post("/api/matrix/register")
        async def matrix_register(req: Request, authorization: str = Header("")):
            """Create the owner's Matrix account with a custom username and password."""
            await get_current_user(authorization)
            data = await req.json()
            username = data.get("username", "").strip()
            password = data.get("password", "").strip()
            display_name = data.get("display_name", "").strip()

            if not username or not password:
                raise HTTPException(status_code=400, detail="Username and password are required")
            if len(password) < 8:
                raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

            from gateway.continuwuity import _continuwuity_dir
            owner_creds_path = _continuwuity_dir() / "owner_credentials.json"
            if owner_creds_path.exists():
                raise HTTPException(status_code=409, detail="Owner account already exists")

            port = int(os.getenv("MATRIX_CONTINUWUITY_PORT", "6167"))
            homeserver_url = f"http://127.0.0.1:{port}"

            from gateway.matrix_agents import register_matrix_user
            result = await register_matrix_user(
                homeserver_url=homeserver_url,
                username=username,
                password=password,
            )
            if not result:
                raise HTTPException(status_code=500, detail="Registration failed")

            # Set display name
            if display_name:
                import httpx
                async with httpx.AsyncClient(timeout=5.0) as hc:
                    await hc.put(
                        f"{homeserver_url}/_matrix/client/v3/profile/{result['user_id']}/displayname",
                        headers={"Authorization": f"Bearer {result['access_token']}"},
                        json={"displayname": display_name},
                    )

            # Save credentials
            owner_creds_path.write_text(json.dumps({
                "username": username,
                "password": password,
                "user_id": result["user_id"],
                "access_token": result["access_token"],
            }, indent=2))

            # Create #chatter room (owner is the creator)
            try:
                import httpx
                from gateway.matrix_agents import _BASE_INITIAL_STATE, _POWER_LEVEL_OVERRIDE
                server_name = os.getenv("MATRIX_SERVER_NAME", "localhost")
                owner_headers = {"Authorization": f"Bearer {result['access_token']}"}
                async with httpx.AsyncClient(timeout=10.0) as hc:
                    # Check if #chatter already exists
                    resp = await hc.get(
                        f"{homeserver_url}/_matrix/client/v3/directory/room/%23chatter:{server_name}",
                    )
                    if resp.status_code == 200:
                        # Already exists — just join
                        room_id = resp.json().get("room_id")
                        if room_id:
                            await hc.post(
                                f"{homeserver_url}/_matrix/client/v3/join/{room_id}",
                                headers=owner_headers, json={},
                            )
                    else:
                        # Create it
                        resp = await hc.post(
                            f"{homeserver_url}/_matrix/client/v3/createRoom",
                            headers=owner_headers,
                            json={
                                "name": "Agent Chatter",
                                "topic": "Casual chat — agents talk freely, no restrictions",
                                "room_alias_name": "chatter",
                                "visibility": "private",
                                "preset": "private_chat",
                                "initial_state": _BASE_INITIAL_STATE,
                                "power_level_content_override": _POWER_LEVEL_OVERRIDE,
                            },
                        )
                        if resp.status_code == 200:
                            chatter_room_id = resp.json().get("room_id")
                            logger.info("[web] Created #chatter room")
                            # Set room avatar
                            try:
                                from gateway.matrix_agents import _render_emoji_to_png
                                avatar_data = _render_emoji_to_png("👥")
                                if avatar_data:
                                    up = await hc.post(
                                        f"{homeserver_url}/_matrix/media/v3/upload",
                                        headers={"Authorization": f"Bearer {result['access_token']}", "Content-Type": "image/png"},
                                        params={"filename": "chatter_avatar.png"},
                                        content=avatar_data,
                                    )
                                    if up.status_code == 200:
                                        mxc = up.json().get("content_uri")
                                        if mxc:
                                            await hc.put(
                                                f"{homeserver_url}/_matrix/client/v3/rooms/{chatter_room_id}/state/m.room.avatar",
                                                headers={"Authorization": f"Bearer {result['access_token']}"},
                                                json={"url": mxc},
                                            )
                            except Exception:
                                pass
            except Exception as e:
                logger.warning("[web] Failed to create #chatter: %s", e)

            return {"user_id": result["user_id"], "username": username}

        @app.put("/api/matrix/credentials")
        async def matrix_update_credentials(req: Request, authorization: str = Header("")):
            """Update the owner's Matrix username and/or password."""
            await get_current_user(authorization)
            data = await req.json()
            new_username = data.get("username", "").strip()
            new_password = data.get("password", "").strip()

            if not new_username and not new_password:
                raise HTTPException(status_code=400, detail="Provide username and/or password")
            if new_password and len(new_password) < 8:
                raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

            from gateway.continuwuity import _continuwuity_dir
            owner_creds_path = _continuwuity_dir() / "owner_credentials.json"
            if not owner_creds_path.exists():
                raise HTTPException(status_code=404, detail="No owner account found — register first")

            creds = json.loads(owner_creds_path.read_text())
            port = int(os.getenv("MATRIX_CONTINUWUITY_PORT", "6167"))
            homeserver_url = f"http://127.0.0.1:{port}"

            # Change password on the Matrix server
            if new_password and new_password != creds.get("password"):
                import httpx
                async with httpx.AsyncClient(timeout=15.0) as hc:
                    resp = await hc.post(
                        f"{homeserver_url}/_matrix/client/v3/account/password",
                        headers={"Authorization": f"Bearer {creds['access_token']}"},
                        json={
                            "new_password": new_password,
                            "logout_devices": False,
                            "auth": {
                                "type": "m.login.password",
                                "identifier": {"type": "m.id.user", "user": creds.get("username", "")},
                                "password": creds.get("password", ""),
                            },
                        },
                    )
                    if resp.status_code != 200:
                        raise HTTPException(status_code=500, detail=f"Failed to change password: {resp.text[:200]}")
                creds["password"] = new_password

            if new_username:
                creds["username"] = new_username

            owner_creds_path.write_text(json.dumps(creds, indent=2))

            # Also update the _owner.json token file
            token_file = _continuwuity_dir() / "tokens" / "_owner.json"
            if token_file.exists():
                token_data = json.loads(token_file.read_text())
                token_data["user_id"] = creds.get("user_id", token_data.get("user_id", ""))
                token_file.write_text(json.dumps(token_data, indent=2))

            return {"ok": True, "username": creds["username"]}

        @app.post("/api/matrix/relationship-room")
        async def create_relationship_room(req: Request, authorization: str = Header("")):
            """Create a private Matrix room for two agents to communicate."""
            await get_current_user(authorization)
            data = await req.json()
            from_agent_id = data.get("from_agent_id", "").strip()
            to_agent_id = data.get("to_agent_id", "").strip()
            rel_type = data.get("rel_type", "manages")

            if not from_agent_id or not to_agent_id:
                raise HTTPException(status_code=400, detail="from_agent_id and to_agent_id are required")

            port = int(os.getenv("MATRIX_CONTINUWUITY_PORT", "6167"))
            homeserver_url = f"http://127.0.0.1:{port}"
            server_name = os.getenv("MATRIX_SERVER_NAME", "localhost")

            from_agent_name = data.get("from_agent_name", "").strip()
            to_agent_name = data.get("to_agent_name", "").strip()

            from gateway.matrix_agents import create_relationship_room as _create_room
            room_id = await _create_room(
                homeserver_url=homeserver_url,
                server_name=server_name,
                agent_a_id=from_agent_id,
                agent_b_id=to_agent_id,
                agent_a_name=from_agent_name,
                agent_b_name=to_agent_name,
                purpose=rel_type,
            )

            if not room_id:
                raise HTTPException(status_code=500, detail="Failed to create Matrix room")

            return {"room_id": room_id}

        @app.post("/api/matrix/onboard-agent")
        async def matrix_onboard_agent(req: Request, authorization: str = Header("")):
            """Onboard an agent to Matrix: register, join global rooms, create owner DM, send greeting."""
            await get_current_user(authorization)
            data = await req.json()
            agent_id = data.get("agent_id", "").strip()
            agent_name = data.get("agent_name", "").strip()

            if not agent_id:
                raise HTTPException(status_code=400, detail="agent_id is required")

            # Look up agent name from registry if not provided
            if not agent_name:
                from vulti_cli.agent_registry import AgentRegistry
                meta = AgentRegistry().get_agent(agent_id)
                agent_name = meta.name if meta else agent_id.capitalize()

            port = int(os.getenv("MATRIX_CONTINUWUITY_PORT", "6167"))
            homeserver_url = f"http://127.0.0.1:{port}"
            server_name = os.getenv("MATRIX_SERVER_NAME", "localhost")

            from gateway.continuwuity import _continuwuity_dir
            reg_token_path = _continuwuity_dir() / "registration_token"
            registration_token = reg_token_path.read_text().strip() if reg_token_path.exists() else ""

            from gateway.matrix_agents import onboard_agent_to_matrix
            result = await onboard_agent_to_matrix(
                homeserver_url=homeserver_url,
                server_name=server_name,
                registration_token=registration_token,
                agent_id=agent_id,
                agent_name=agent_name,
            )

            # Hot-add agent to the running Matrix adapter
            if result.get("matrix_user_id"):
                await _hot_add_to_matrix(agent_id)

            return result

        @app.post("/api/matrix/reset-rooms")
        async def matrix_reset_rooms(authorization: str = Header("")):
            """Delete all Matrix rooms and recreate from scratch."""
            await get_current_user(authorization)

            port = int(os.getenv("MATRIX_CONTINUWUITY_PORT", "6167"))
            homeserver_url = f"http://127.0.0.1:{port}"
            server_name = os.getenv("MATRIX_SERVER_NAME", "localhost")

            from gateway.matrix_agents import reset_all_rooms
            result = await reset_all_rooms(
                homeserver_url=homeserver_url,
                server_name=server_name,
            )

            return result

        @app.post("/api/matrix/owner-dm")
        async def matrix_owner_dm(req: Request, authorization: str = Header("")):
            """Create a DM between the owner and an agent. Agent sends a greeting."""
            await get_current_user(authorization)
            data = await req.json()
            agent_id = data.get("agent_id", "").strip()
            agent_name = data.get("agent_name", "").strip()

            if not agent_id:
                raise HTTPException(status_code=400, detail="agent_id is required")

            if not agent_name:
                from vulti_cli.agent_registry import AgentRegistry
                meta = AgentRegistry().get_agent(agent_id)
                agent_name = meta.name if meta else agent_id.capitalize()

            port = int(os.getenv("MATRIX_CONTINUWUITY_PORT", "6167"))
            homeserver_url = f"http://127.0.0.1:{port}"
            server_name = os.getenv("MATRIX_SERVER_NAME", "localhost")

            from gateway.matrix_agents import create_owner_relationship
            dm_room_id = await create_owner_relationship(
                homeserver_url=homeserver_url,
                server_name=server_name,
                agent_id=agent_id,
                agent_name=agent_name,
            )

            if not dm_room_id:
                raise HTTPException(status_code=500, detail="Failed to create owner DM")

            return {"room_id": dm_room_id}

        @app.post("/api/matrix/squad-room")
        async def matrix_squad_room(req: Request, authorization: str = Header("")):
            """Create a group room for a squad of agents."""
            await get_current_user(authorization)
            data = await req.json()
            agent_ids = data.get("agent_ids", [])
            squad_name = data.get("squad_name", "").strip()
            topic = data.get("topic", "")

            if not agent_ids or len(agent_ids) < 2:
                raise HTTPException(status_code=400, detail="At least 2 agent_ids are required")
            if not squad_name:
                raise HTTPException(status_code=400, detail="squad_name is required")

            port = int(os.getenv("MATRIX_CONTINUWUITY_PORT", "6167"))
            homeserver_url = f"http://127.0.0.1:{port}"
            server_name = os.getenv("MATRIX_SERVER_NAME", "localhost")

            from gateway.matrix_agents import create_squad_room
            room_id = await create_squad_room(
                homeserver_url=homeserver_url,
                server_name=server_name,
                agent_ids=agent_ids,
                squad_name=squad_name,
                topic=topic,
            )

            if not room_id:
                raise HTTPException(status_code=500, detail="Failed to create squad room")

            return {"room_id": room_id}

        @app.post("/api/matrix/rooms/{room_id}/members")
        async def matrix_add_member(room_id: str, req: Request, authorization: str = Header("")):
            """Add an agent to a Matrix room."""
            await get_current_user(authorization)
            data = await req.json()
            agent_id = data.get("agent_id", "").strip()
            inviter_agent_id = data.get("inviter_agent_id", "").strip() or None

            if not agent_id:
                raise HTTPException(status_code=400, detail="agent_id is required")

            port = int(os.getenv("MATRIX_CONTINUWUITY_PORT", "6167"))
            homeserver_url = f"http://127.0.0.1:{port}"

            from gateway.matrix_agents import add_agent_to_room
            ok = await add_agent_to_room(
                homeserver_url=homeserver_url,
                agent_id=agent_id,
                room_id=room_id,
                inviter_agent_id=inviter_agent_id,
            )

            if not ok:
                raise HTTPException(status_code=500, detail="Failed to add agent to room")

            return {"ok": True}

        @app.delete("/api/matrix/rooms/{room_id}/members/{agent_id}")
        async def matrix_remove_member(room_id: str, agent_id: str, authorization: str = Header("")):
            """Remove an agent from a Matrix room."""
            await get_current_user(authorization)

            port = int(os.getenv("MATRIX_CONTINUWUITY_PORT", "6167"))
            homeserver_url = f"http://127.0.0.1:{port}"

            from gateway.matrix_agents import remove_agent_from_room
            ok = await remove_agent_from_room(
                homeserver_url=homeserver_url,
                agent_id=agent_id,
                room_id=room_id,
            )

            if not ok:
                raise HTTPException(status_code=500, detail="Failed to remove agent from room")

            return {"ok": True}

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

        @app.post("/api/secrets")
        async def add_secret(req: Request, authorization: str = Header("")):
            await get_current_user(authorization)
            data = await req.json()
            return adapter._add_secret(data.get("key", ""), data.get("value", ""))

        @app.delete("/api/secrets/{key}")
        async def delete_secret(key: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._delete_secret(key)

        @app.get("/api/providers")
        async def list_providers(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_providers()

        @app.get("/api/oauth")
        async def get_oauth(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_oauth_status()

        # --- Analytics ---

        @app.get("/api/analytics")
        async def get_analytics(days: int = 30, agent_id: str = None, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_analytics(days, agent_id=agent_id)

        # --- Connections ---

        @app.get("/api/connections")
        async def list_connections(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._list_connections()

        @app.post("/api/connections")
        async def add_connection(req: Request, authorization: str = Header("")):
            await get_current_user(authorization)
            data = await req.json()
            return adapter._add_connection(data)

        @app.put("/api/connections/{name}")
        async def update_connection(name: str, req: Request, authorization: str = Header("")):
            await get_current_user(authorization)
            data = await req.json()
            return adapter._update_connection(name, data)

        @app.delete("/api/connections/{name}")
        async def delete_connection(name: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._delete_connection(name)

        # --- Relationships ---

        @app.get("/api/relationships")
        async def list_relationships(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._list_relationships()

        @app.post("/api/relationships")
        async def create_relationship(req: Request, authorization: str = Header("")):
            await get_current_user(authorization)
            data = await req.json()
            return adapter._create_relationship(data)

        @app.put("/api/relationships/{rel_id}")
        async def update_relationship(rel_id: str, req: Request, authorization: str = Header("")):
            await get_current_user(authorization)
            data = await req.json()
            return adapter._update_relationship(rel_id, data)

        @app.delete("/api/relationships/{rel_id}")
        async def delete_relationship(rel_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._delete_relationship(rel_id)

        # --- Skills ---

        @app.get("/api/skills")
        async def list_available_skills(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._list_available_skills()

        @app.get("/api/agents/{agent_id}/skills")
        async def list_agent_skills(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._list_agent_skills(agent_id)

        @app.post("/api/agents/{agent_id}/skills")
        async def install_agent_skill(agent_id: str, req: Request, authorization: str = Header("")):
            await get_current_user(authorization)
            data = await req.json()
            return adapter._install_agent_skill(agent_id, data.get("name", ""))

        @app.delete("/api/agents/{agent_id}/skills/{skill_name}")
        async def remove_agent_skill(agent_id: str, skill_name: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._remove_agent_skill(agent_id, skill_name)

        # --- Audit ---

        @app.get("/api/audit")
        async def list_audit_events(
            n: int = 50,
            agent_id: str = None,
            trace_id: str = None,
            event_type: str = None,
            authorization: str = Header(""),
        ):
            await get_current_user(authorization)
            return adapter._list_audit_events(n, agent_id, trace_id, event_type)

        # --- Permissions ---

        @app.get("/api/permissions")
        async def list_permissions(agent_id: str = None, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._list_permissions(agent_id)

        @app.post("/api/permissions/{request_id}/resolve")
        async def resolve_permission(request_id: str, req: Request, authorization: str = Header("")):
            await get_current_user(authorization)
            data = await req.json()
            return adapter._resolve_permission(request_id, data.get("approved", False))

        # --- Owner ---

        @app.get("/api/owner")
        async def get_owner(authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_owner()

        @app.put("/api/owner")
        async def update_owner(req: Request, authorization: str = Header("")):
            await get_current_user(authorization)
            data = await req.json()
            return adapter._update_owner(data)

        @app.post("/api/owner/generate-avatar")
        async def generate_owner_avatar(authorization: str = Header("")):
            await get_current_user(authorization)
            return await asyncio.to_thread(adapter._generate_owner_avatar)

        # --- Agent Avatar (fetch) ---

        @app.get("/api/agents/{agent_id}/avatar")
        async def get_agent_avatar(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_agent_avatar(agent_id)

        # --- Agent Files ---

        @app.get("/api/agents/{agent_id}/files")
        async def list_agent_files(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._list_agent_files(agent_id)

        @app.get("/api/agents/{agent_id}/files/{file_path:path}")
        async def get_agent_file(agent_id: str, file_path: str, authorization: str = Header("")):
            from fastapi.responses import FileResponse
            await get_current_user(authorization)
            cache_dir = adapter._get_agent_cache_dir(agent_id)
            full_path = (cache_dir / file_path).resolve()
            if not full_path.is_relative_to(cache_dir.resolve()) or not full_path.is_file():
                raise HTTPException(status_code=404, detail="File not found")
            return FileResponse(full_path)

        @app.delete("/api/agents/{agent_id}/files/{file_path:path}")
        async def delete_agent_file(agent_id: str, file_path: str, authorization: str = Header("")):
            await get_current_user(authorization)
            cache_dir = adapter._get_agent_cache_dir(agent_id)
            full_path = (cache_dir / file_path).resolve()
            if not full_path.is_relative_to(cache_dir.resolve()) or not full_path.is_file():
                raise HTTPException(status_code=404, detail="File not found")
            full_path.unlink()
            return {"ok": True}

        # --- Agent Config ---

        @app.get("/api/agents/{agent_id}/config")
        async def get_agent_config(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_agent_config(agent_id)

        # --- Agent Wallet ---

        @app.get("/api/agents/{agent_id}/wallet")
        async def get_agent_wallet(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_agent_wallet(agent_id)

        @app.put("/api/agents/{agent_id}/wallet")
        async def save_agent_wallet(agent_id: str, req: Request, authorization: str = Header("")):
            await get_current_user(authorization)
            data = await req.json()
            return adapter._save_agent_wallet(agent_id, data)

        # --- Agent Vault ---

        @app.get("/api/agents/{agent_id}/vault")
        async def get_agent_vault(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_agent_vault(agent_id)

        @app.delete("/api/agents/{agent_id}/vault")
        async def delete_agent_vault(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._delete_agent_vault(agent_id)

        @app.get("/api/agents/{agent_id}/vault/portfolio")
        async def get_agent_vault_portfolio(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return await asyncio.to_thread(adapter._get_vault_portfolio, agent_id)

        # --- Pane Widgets ---

        @app.get("/api/agents/{agent_id}/pane")
        async def get_pane_widgets(agent_id: str, session_id: str = None, authorization: str = Header("")):
            await get_current_user(authorization)
            if session_id:
                # Return both home + chat widgets for the given session
                home = adapter._get_pane_widgets(agent_id)
                chat = adapter._get_session_pane_widgets(session_id)
                # Merge: home tab from agent, chat tab from session
                home_tabs = home.get("tabs", {})
                chat_tabs = chat.get("tabs", {})
                return {"version": 1, "tabs": {**home_tabs, "chat": chat_tabs.get("chat", [])}}
            return adapter._get_pane_widgets(agent_id)

        @app.get("/api/sessions/{session_id}/pane")
        async def get_session_pane(session_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_session_pane_widgets(session_id)

        @app.delete("/api/agents/{agent_id}/pane")
        async def clear_pane_widgets(agent_id: str, tab: str = None, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._clear_pane_widgets(agent_id, tab)

        @app.delete("/api/agents/{agent_id}/pane/widgets/{widget_id}")
        async def remove_pane_widget(agent_id: str, widget_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._remove_pane_widget(agent_id, widget_id)

        @app.put("/api/agents/{agent_id}/pane/reorder")
        async def reorder_pane_widgets(agent_id: str, req: Request, authorization: str = Header("")):
            await get_current_user(authorization)
            data = await req.json()
            widget_ids = data.get("widget_ids", [])
            return adapter._reorder_pane_widgets(agent_id, widget_ids)

        @app.post("/api/agents/{agent_id}/pane/reset-defaults")
        async def reset_default_widgets(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._reset_default_widgets(agent_id)

        # --- Finalize Onboarding ---

        @app.post("/api/agents/{agent_id}/finalize-onboarding")
        async def finalize_onboarding(agent_id: str, req: Request, authorization: str = Header("")):
            await get_current_user(authorization)
            data = await req.json()
            return adapter._finalize_onboarding(agent_id, data)

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

                        hub_channel = data.get("hub_channel", "")
                        _ws_agent_id = data.get("agent_id", "")

                        # Build source for gateway
                        source = SessionSource(
                            platform=Platform.APP,
                            chat_id=f"app:{session_id}",
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
                        # Pass hub channel to gateway for context-aware prompting
                        if hub_channel:
                            event._hub_channel = hub_channel
                        # Pass agent_id so gateway routes to the correct agent
                        if _ws_agent_id:
                            event._agent_id = _ws_agent_id

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
        # Mark session as streaming so any send() during processing routes
        # as "chunk" instead of committing a "message" bubble mid-stream.
        self._streaming_sessions.add(session_id)
        try:
            # Send typing indicator
            ws = self._connections.get(session_id)
            if ws:
                await ws.send_text(json.dumps({"type": "typing", "active": True}))

            # Set up tool progress callback for this session's WebSocket
            self._setup_tool_progress_ws(session_id)

            # Call gateway message handler
            if not callable(self._message_handler):
                logger.error("[web] _message_handler is not callable: type=%s value=%r", type(self._message_handler).__name__, self._message_handler)
                raise TypeError(f"_message_handler is {type(self._message_handler).__name__}, not callable")
            response = await self._message_handler(event)

            # Re-fetch WS (may have reconnected during processing)
            ws = self._connections.get(session_id)

            # Clear streaming flag so the commit message goes as "message" type
            self._streaming_sessions.discard(session_id)

            # Streaming path: handler returns None when chunks already delivered
            if response is None:
                streamed = self._last_streamed.pop(session_id, None)
                if ws:
                    msg_id = uuid.uuid4().hex[:12]
                    # Send commit message so frontend transitions from streaming to committed
                    await ws.send_text(json.dumps({
                        "type": "message",
                        "content": streamed or "",
                        "id": msg_id,
                    }))
                    if streamed:
                        self._append_history(session_id, {
                            "id": msg_id,
                            "role": "assistant",
                            "content": streamed,
                            "timestamp": datetime.now().isoformat(),
                        })
                        meta = self._get_session_meta(session_id)
                        if meta:
                            meta["preview"] = streamed[:100]
                            meta["updated_at"] = datetime.now().isoformat()
                            self._save_session_meta(session_id, meta)
                if streamed:
                    # Write unread inbox item
                    _agent_id = getattr(event, "_agent_id", "") or ""
                    if _agent_id:
                        self._append_inbox_item(session_id, _agent_id, streamed)
                return

            if not response:
                response = "(No response from agent)"
            if ws:
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

            # Write unread inbox item
            _agent_id = getattr(event, "_agent_id", "") or ""
            if _agent_id and response:
                self._append_inbox_item(session_id, _agent_id, response)

        except Exception as e:
            import traceback
            logger.error("[web] Error handling message: %s\n%s", e, traceback.format_exc())
            ws = self._connections.get(session_id)
            if ws:
                await ws.send_text(json.dumps({
                    "type": "error",
                    "content": f"Error: {e}",
                }))
        finally:
            # Clear streaming flag and tracked content
            self._streaming_sessions.discard(session_id)
            self._last_streamed.pop(session_id, None)
            # Always stop typing indicator
            ws = self._connections.get(session_id)
            if ws:
                try:
                    await ws.send_text(json.dumps({"type": "typing", "active": False}))
                except Exception:
                    pass

    # --- Tool progress for WebSocket clients ---

    def _setup_tool_progress_ws(self, session_id: str):
        """Install a tool_progress_callback that emits tool_use events over WebSocket."""
        print(f"[web] Setting up tool progress WS callback for session={session_id}", flush=True)
        """
        This runs in-band during the agent's tool execution. The callback is stored
        on the adapter so the gateway's progress_callback can find it for web sessions.
        """
        import asyncio as _asyncio

        ws = self._connections.get(session_id)
        if not ws:
            return

        loop = _asyncio.get_event_loop()

        def _ws_tool_progress(tool_name: str, preview: str = None, args: dict = None):
            from agent.display import get_tool_emoji
            emoji = get_tool_emoji(tool_name, default="⚙️")
            msg = {
                "type": "tool_use",
                "name": tool_name,
                "emoji": emoji,
                "preview": (preview[:80] + "...") if preview and len(preview) > 80 else (preview or ""),
            }
            print(f"[web] tool_use event: {tool_name} (session={session_id})", flush=True)
            current_ws = self._connections.get(session_id)
            if current_ws:
                try:
                    _asyncio.run_coroutine_threadsafe(
                        current_ws.send_text(json.dumps(msg)),
                        loop,
                    )
                except Exception as e:
                    logger.error("[web] Failed to send tool_use: %s", e)
            else:
                logger.warning("[web] No WS connection for session %s", session_id)

        # Store under both raw and web:-prefixed keys since the gateway
        # session store uses "web:{session_id}" as its session_id
        self._ws_tool_callbacks[session_id] = _ws_tool_progress
        self._ws_tool_callbacks[f"web:{session_id}"] = _ws_tool_progress

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
        session_id = chat_id.replace("app:", "", 1) if chat_id.startswith("app:") else chat_id
        ws = self._connections.get(session_id)
        if not ws:
            return SendResult(success=False, error="Client not connected")

        msg_id = uuid.uuid4().hex[:12]

        # During active streaming, route through "chunk" instead of committing
        # a "message" — prevents duplicate bubbles from stream consumer or
        # progress system calling send() mid-stream.
        if session_id in self._streaming_sessions:
            try:
                await ws.send_text(json.dumps({
                    "type": "chunk",
                    "content": content,
                    "id": msg_id,
                }))
                self._last_streamed[session_id] = content
                return SendResult(success=True, message_id=msg_id)
            except Exception as e:
                return SendResult(success=False, error=str(e))

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
        session_id = chat_id.replace("app:", "", 1) if chat_id.startswith("app:") else chat_id
        ws = self._connections.get(session_id)
        if not ws:
            return SendResult(success=False, error="Client not connected")

        try:
            await ws.send_text(json.dumps({
                "type": "chunk",
                "content": content,
                "id": message_id,
            }))
            # Mark session as actively streaming so send() routes as chunks
            self._streaming_sessions.add(session_id)
            # Track latest streamed content for history storage
            self._last_streamed[session_id] = content
            return SendResult(success=True, message_id=message_id)
        except Exception as e:
            return SendResult(success=False, error=str(e))

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Get info about a web chat session."""
        session_id = chat_id.replace("app:", "", 1) if chat_id.startswith("app:") else chat_id
        meta = self._get_session_meta(session_id)
        return {
            "name": meta.get("name", "Web Chat") if meta else "Web Chat",
            "type": "dm",
        }

    async def send_typing(self, chat_id: str, metadata=None) -> None:
        """Send typing indicator."""
        session_id = chat_id.replace("app:", "", 1) if chat_id.startswith("app:") else chat_id
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
            if f.stem.endswith("_widgets"):
                continue
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

    async def _generate_session_title(self, session_id: str) -> str | None:
        """Ask a fast LLM to name the conversation based on its first messages."""
        history = self._get_history(session_id)
        if not history:
            return None

        # Take the first 4 messages
        first_msgs = history[:4]
        transcript = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')[:200]}"
            for m in first_msgs
            if m.get("content")
        )
        if not transcript.strip():
            return None

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return None

        try:
            import urllib.request
            import json as _json

            body = _json.dumps({
                "model": "google/gemini-2.0-flash-001",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Generate a short conversation title (max 50 chars). "
                            "Return ONLY the title text, no quotes, no explanation."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Name this conversation:\n\n{transcript}",
                    },
                ],
                "max_tokens": 30,
            }).encode()

            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://vulti.ai",
                },
            )

            import asyncio
            loop = asyncio.get_running_loop()
            def _fetch():
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return _json.loads(resp.read())

            result = await loop.run_in_executor(None, _fetch)
            title = (
                result.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
                .strip('"\'')
            )
            return title[:60] if title else None
        except Exception as e:
            logger.debug("Session title generation failed: %s", e)
            return None

    def _append_inbox_item(self, session_id: str, agent_id: str, preview: str):
        """Write an unread inbox item when an agent responds."""
        d = self._get_data_dir()
        d.mkdir(parents=True, exist_ok=True)
        item = {
            "id": uuid.uuid4().hex[:12],
            "source": "app",
            "sender": agent_id,
            "preview": preview[:200] if preview else "",
            "timestamp": datetime.now().isoformat(),
            "read": False,
            "agent_id": agent_id,
            "session_id": session_id,
        }
        with open(d / "inbox.jsonl", "a") as f:
            f.write(json.dumps(item) + "\n")

    def _mark_session_inbox_read(self, session_id: str):
        """Mark all inbox items for a session as read."""
        f = self._get_data_dir() / "inbox.jsonl"
        if not f.exists():
            return
        lines = f.read_text().strip().split("\n")
        updated = []
        for line in lines:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                if item.get("session_id") == session_id:
                    item["read"] = True
                updated.append(json.dumps(item))
            except Exception:
                updated.append(line)
        f.write_text("\n".join(updated) + "\n" if updated else "")

    def _mark_inbox_item_read(self, item_id: str):
        """Mark a single inbox item as read by ID."""
        f = self._get_data_dir() / "inbox.jsonl"
        if not f.exists():
            return
        lines = f.read_text().strip().split("\n")
        updated = []
        for line in lines:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                if item.get("id") == item_id:
                    item["read"] = True
                updated.append(json.dumps(item))
            except Exception:
                updated.append(line)
        f.write_text("\n".join(updated) + "\n" if updated else "")

    def _append_history(self, session_id: str, message: dict):
        """Append a message to session history."""
        d = self._get_data_dir() / "history"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / f"{session_id}.jsonl", "a") as f:
            f.write(json.dumps(message) + "\n")

    def _get_agent_registry(self):
        """Get or create the agent registry instance.

        Always invalidates the in-memory cache so we pick up changes
        made by agent subprocesses (e.g. manage_own_connections,
        update_own_profile writing directly to registry.json).
        """
        if not hasattr(self, "_agent_registry"):
            from vulti_cli.agent_registry import AgentRegistry
            self._agent_registry = AgentRegistry()
            self._agent_registry.ensure_initialized()
        # Invalidate cache so we always read fresh data from disk
        self._agent_registry._data = None
        return self._agent_registry

    def _get_agent_allowed_connections(self, agent_id: str) -> list:
        """Read allowed connections from the agent's per-agent permissions.json."""
        try:
            from orchestrator.permissions import get_allowed_connections
            return get_allowed_connections(agent_id)
        except Exception:
            return []

    def _get_agents(self) -> list:
        """List all registered agents."""
        try:
            registry = self._get_agent_registry()
            agents = registry.list_agents()
            # Get connected platforms for context
            from gateway.config import load_gateway_config
            config = load_gateway_config()
            connected = [p.value for p in config.get_connected_platforms()]

            return [{
                "id": a.id,
                "name": a.name,
                "role": a.role,
                "url": f"http://{self._host}:{self._port}",
                "status": "connected" if self._running and a.status == "active" else a.status,
                "platforms": connected if a.status == "active" else [],
                "avatar": a.avatar,
                "description": a.description,
                "createdAt": a.created_at,
                "createdFrom": a.created_from,
                "allowed_connections": self._get_agent_allowed_connections(a.id),
            } for a in agents]
        except Exception as e:
            logger.error("[web] Failed to list agents: %s", e)
            return []

    def _get_agent(self, agent_id: str) -> dict:
        """Get a single agent by ID."""
        registry = self._get_agent_registry()
        agent = registry.get_agent(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
        return {
            "id": agent.id,
            "name": agent.name,
            "role": agent.role,
            "url": f"http://{self._host}:{self._port}",
            "status": agent.status,
            "avatar": agent.avatar,
            "description": agent.description,
            "createdAt": agent.created_at,
            "createdFrom": agent.created_from,
            "allowed_connections": self._get_agent_allowed_connections(agent.id),
        }

    def _create_agent(self, data: dict) -> dict:
        """Create a new agent."""
        registry = self._get_agent_registry()
        name = data.get("name", "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Agent name is required")

        # Generate agent_id from name
        import re
        agent_id = re.sub(r"[^a-z0-9\-]", "-", name.lower()).strip("-")[:32]
        if not agent_id:
            agent_id = "agent"

        # Deduplicate if needed
        base_id = agent_id
        counter = 2
        while registry.get_agent(agent_id) is not None:
            agent_id = f"{base_id}-{counter}"[:32]
            counter += 1

        try:
            meta = registry.create_agent(
                agent_id=agent_id,
                name=name,
                clone_from=data.get("inherit_from"),
                avatar=data.get("avatar"),
                description=data.get("description", ""),
                role=data.get("role", ""),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Write personality to soul if provided, otherwise clear default for clean onboarding
        soul_path = registry.agent_soul_path(agent_id)
        if data.get("personality"):
            soul_path.write_text(data["personality"], encoding="utf-8")
        else:
            # Empty soul so onboarding starts fresh — agent has no identity yet
            soul_path.write_text("", encoding="utf-8")

        # Write model to agent's config.yaml if provided
        if data.get("model"):
            try:
                import yaml
                config_path = registry.agent_config_path(agent_id)
                if config_path.exists():
                    with open(config_path, encoding="utf-8") as f:
                        agent_cfg = yaml.safe_load(f) or {}
                else:
                    agent_cfg = {}
                agent_cfg["model"] = data["model"]
                with open(config_path, "w", encoding="utf-8") as f:
                    yaml.dump(agent_cfg, f, default_flow_style=False, allow_unicode=True)
            except Exception as e:
                logger.debug("Failed to write model to agent config: %s", e)

        return {
            "id": meta.id,
            "name": meta.name,
            "role": meta.role,
            "url": f"http://{self._host}:{self._port}",
            "status": meta.status,
            "avatar": meta.avatar,
            "description": meta.description,
            "createdAt": meta.created_at,
            "createdFrom": meta.created_from,
        }

    async def _setup_agent_matrix(self, agent_id: str, agent_name: str) -> None:
        """Register a new agent on Matrix, join rooms, create owner DM."""
        try:
            from gateway.matrix_agents import onboard_agent_to_matrix
            from gateway.continuwuity import _get_or_create_registration_token

            homeserver_url = os.getenv("MATRIX_HOMESERVER_URL", "http://127.0.0.1:6167")
            server_name = os.getenv("MATRIX_SERVER_NAME", "localhost")
            registration_token = _get_or_create_registration_token()

            result = await onboard_agent_to_matrix(
                homeserver_url=homeserver_url,
                server_name=server_name,
                registration_token=registration_token,
                agent_id=agent_id,
                agent_name=agent_name,
            )
            if result.get("matrix_user_id"):
                logger.info("[web] Matrix onboarding complete for %s: %s", agent_id, result["matrix_user_id"])
                await _hot_add_to_matrix(agent_id)
            else:
                logger.warning("[web] Failed to register %s on Matrix", agent_id)
        except Exception as e:
            logger.warning("[web] Matrix setup failed for %s: %s", agent_id, e)

    def _update_agent(self, agent_id: str, data: dict) -> dict:
        """Update an agent's metadata."""
        registry = self._get_agent_registry()
        if registry.get_agent(agent_id) is None:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

        updates = {}
        for field in ("name", "role", "status", "avatar", "description"):
            if field in data:
                updates[field] = data[field]

        # Handle allowed_connections — write to per-agent permissions.json
        if "allowedConnections" in data or "allowed_connections" in data:
            raw = data.get("allowedConnections", data.get("allowed_connections", []))
            if isinstance(raw, str):
                new_conns = [c.strip() for c in raw.split(",") if c.strip()]
            elif isinstance(raw, list):
                new_conns = raw
            else:
                new_conns = []
            from orchestrator.permissions import set_allowed_connections
            set_allowed_connections(agent_id, new_conns)

        try:
            meta = registry.update_agent(agent_id, **updates) if updates else registry.get_agent(agent_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Update personality/soul if provided
        if "personality" in data:
            soul_path = registry.agent_soul_path(agent_id)
            soul_path.write_text(data["personality"], encoding="utf-8")

        # Update model in agent's config.yaml if provided
        if data.get("model"):
            try:
                import yaml
                config_path = registry.agent_config_path(agent_id)
                if config_path.exists():
                    with open(config_path, encoding="utf-8") as f:
                        agent_cfg = yaml.safe_load(f) or {}
                else:
                    agent_cfg = {}
                agent_cfg["model"] = data["model"]
                with open(config_path, "w", encoding="utf-8") as f:
                    yaml.dump(agent_cfg, f, default_flow_style=False, allow_unicode=True)
            except Exception as e:
                logger.debug("Failed to write model to agent config: %s", e)

        return {
            "id": meta.id,
            "name": meta.name,
            "role": meta.role,
            "status": meta.status,
            "avatar": meta.avatar,
            "description": meta.description,
        }

    async def _delete_agent(self, agent_id: str) -> dict:
        """Delete an agent and all its data, including Matrix cleanup."""
        from fastapi import HTTPException
        registry = self._get_agent_registry()

        # Clean up Matrix user before deleting agent data
        await self._cleanup_matrix_agent(agent_id)

        # Clean up web sessions belonging to this agent
        try:
            for session in self._get_agent_sessions(agent_id=agent_id):
                self._delete_session_meta(session.get("id", ""))
        except Exception:
            pass

        try:
            if not registry.delete_agent(agent_id):
                raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Invalidate cached registries on gateway runner so agent list refreshes
        runner = getattr(self, '_gateway_runner', None)
        if runner:
            if hasattr(runner, '_identity_agent_registry'):
                runner._identity_agent_registry = None
            if hasattr(runner, '_hub_agent_registry'):
                runner._hub_agent_registry = None

        return {"ok": True}

    async def _reset_everything(self) -> dict:
        """Factory reset: delete all agents, connections, skills, jobs, rules, sessions.

        Safety: every path is resolved and verified to be inside ~/.vulti/ before deletion.
        """
        import shutil
        home = self._get_vulti_home().resolve()

        def _safe_rmtree(path: Path) -> None:
            """Only delete if path is the vulti home directory or inside it."""
            resolved = path.resolve()
            if resolved != home and not str(resolved).startswith(str(home) + "/"):
                logger.warning("Reset safety: refusing to delete '%s' (outside %s)", resolved, home)
                return
            if resolved.exists():
                shutil.rmtree(resolved, ignore_errors=True)

        registry = self._get_agent_registry()
        deleted_agents = []
        errors = []

        # 1. Delete every agent (incl. Matrix cleanup, sessions, cron, rules, memories, skills, config)
        reg_data = registry._load()
        for agent_id in list(reg_data.get("agents", {}).keys()):
            try:
                await self._delete_agent(agent_id)
                deleted_agents.append(agent_id)
            except Exception as e:
                errors.append(f"agent {agent_id}: {e}")

        # 2. Wipe ~/.vulti/ except bin/ (installed binaries), .env (credentials), models/ (large downloads)
        preserve = {"bin", "models", ".env", "auth.json", "auth.lock", "web_token"}
        for item in home.iterdir():
            if item.name in preserve:
                continue
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)

        return {
            "ok": True,
            "deleted_agents": deleted_agents,
            "errors": errors if errors else None,
        }

    async def _factory_reset(self) -> dict:
        """Full factory reset: run normal reset, then also wipe .env, connections,
        user profile, models (whisper), and all remaining files. Returns the app
        to a fresh-install state."""
        import shutil

        # First do the normal reset (agents, sessions, cron, etc.)
        result = await self._reset_everything()

        home = self._get_vulti_home().resolve()

        # Now wipe everything that the normal reset preserves
        preserve_only = {"bin", "auth.json", "auth.lock", "web_token"}
        for item in home.iterdir():
            if item.name in preserve_only:
                continue
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)

        result["factory"] = True
        return result

    async def _cleanup_matrix_agent(self, agent_id: str) -> None:
        """Remove an agent's Matrix user: leave rooms, logout, delete credentials."""
        try:
            from gateway.matrix_agents import get_agent_matrix_credentials, _tokens_dir

            creds = get_agent_matrix_credentials(agent_id)
            if not creds:
                return

            access_token = creds.get("access_token", "")
            homeserver_url = creds.get("homeserver_url", "")
            user_id = creds.get("user_id", "")

            if access_token and homeserver_url:
                import httpx

                headers = {"Authorization": f"Bearer {access_token}"}
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # Leave and forget all joined rooms
                    try:
                        resp = await client.get(
                            f"{homeserver_url}/_matrix/client/v3/joined_rooms",
                            headers=headers,
                        )
                        if resp.status_code == 200:
                            for room_id in resp.json().get("joined_rooms", []):
                                try:
                                    await client.post(
                                        f"{homeserver_url}/_matrix/client/v3/rooms/{room_id}/leave",
                                        headers=headers,
                                        json={},
                                    )
                                    # Forget room so user is fully removed
                                    await client.post(
                                        f"{homeserver_url}/_matrix/client/v3/rooms/{room_id}/forget",
                                        headers=headers,
                                        json={},
                                    )
                                except Exception:
                                    pass
                            logger.info("Matrix cleanup: agent '%s' left %d room(s)", agent_id, len(resp.json().get("joined_rooms", [])))
                    except Exception as e:
                        logger.warning("Matrix cleanup: failed to leave rooms for %s: %s", agent_id, e)

                    # Deactivate the account (best-effort, may not be supported)
                    try:
                        await client.post(
                            f"{homeserver_url}/_matrix/client/v3/account/deactivate",
                            headers=headers,
                            json={"erase": True},
                        )
                    except Exception:
                        pass

                    # Logout all sessions to invalidate all access tokens
                    try:
                        await client.post(
                            f"{homeserver_url}/_matrix/client/v3/logout/all",
                            headers=headers,
                            json={},
                        )
                        logger.info("Matrix cleanup: logged out all sessions for agent '%s'", agent_id)
                    except Exception as e:
                        logger.warning("Matrix cleanup: failed to logout %s: %s", agent_id, e)

            # Remove token file so the agent can't be re-registered on restart
            token_file = _tokens_dir() / f"{agent_id}.json"
            if token_file.exists():
                token_file.unlink()

            # Update the Matrix adapter's agent filter so it stops ignoring this user_id
            if user_id:
                from gateway.config import Platform
                matrix_adapter = self._gateway_runner and self._gateway_runner.adapters.get(Platform.MATRIX) if hasattr(self, '_gateway_runner') else None
                if matrix_adapter and hasattr(matrix_adapter, '_agent_user_ids'):
                    matrix_adapter._agent_user_ids.discard(user_id)

            logger.info("Matrix cleanup: agent '%s' fully removed (left rooms, logged out, credentials deleted)", agent_id)

        except ImportError:
            pass  # Matrix not configured
        except Exception as e:
            logger.warning("Matrix cleanup failed for agent '%s': %s", agent_id, e)

    def _get_memories(self, agent_id: str = None) -> dict:
        """Get memory files for an agent."""
        if agent_id:
            registry = self._get_agent_registry()
            mem_dir = registry.agent_memories_dir(agent_id)
        else:
            from vulti_cli.config import get_vulti_home
            mem_dir = get_vulti_home() / "memories"

        memory = ""
        user = ""
        try:
            mem_file = mem_dir / "MEMORY.md"
            if mem_file.exists():
                memory = mem_file.read_text(encoding="utf-8")
        except Exception:
            pass
        try:
            user_file = mem_dir / "USER.md"
            if user_file.exists():
                user = user_file.read_text(encoding="utf-8")
        except Exception:
            pass
        return {"memory": memory, "user": user}

    def _update_memory(self, file: str, content: str, agent_id: str = None) -> dict:
        """Update a memory file for an agent."""
        if agent_id:
            registry = self._get_agent_registry()
            mem_dir = registry.agent_memories_dir(agent_id)
        else:
            from vulti_cli.config import get_vulti_home
            mem_dir = get_vulti_home() / "memories"

        mem_dir.mkdir(parents=True, exist_ok=True)
        filename = "MEMORY.md" if file == "memory" else "USER.md"
        (mem_dir / filename).write_text(content, encoding="utf-8")
        return {"ok": True}

    def _get_soul(self, agent_id: str = None) -> dict:
        """Get the soul/personality file for an agent."""
        if agent_id:
            registry = self._get_agent_registry()
            soul_path = registry.agent_soul_path(agent_id)
        else:
            from vulti_cli.config import get_vulti_home
            soul_path = get_vulti_home() / "SOUL.md"

        content = ""
        if soul_path.exists():
            content = soul_path.read_text(encoding="utf-8")
        return {"content": content}

    def _update_soul(self, content: str, agent_id: str = None) -> dict:
        """Update the soul/personality file for an agent."""
        if agent_id:
            registry = self._get_agent_registry()
            soul_path = registry.agent_soul_path(agent_id)
        else:
            from vulti_cli.config import get_vulti_home
            soul_path = get_vulti_home() / "SOUL.md"

        soul_path.parent.mkdir(parents=True, exist_ok=True)
        soul_path.write_text(content, encoding="utf-8")
        return {"ok": True}

    def _generate_avatar(self, agent_id: str) -> dict:
        """Generate a profile avatar for an agent using fal or OpenRouter."""
        registry = self._get_agent_registry()
        meta = registry.get_agent(agent_id)
        if not meta:
            return {"ok": False, "error": f"Agent '{agent_id}' not found"}

        # Read a snippet of SOUL.md for prompt context
        soul_path = registry.agent_soul_path(agent_id)
        soul_snippet = ""
        if soul_path.exists():
            soul_snippet = soul_path.read_text(encoding="utf-8")[:500]

        # Build avatar prompt
        role = meta.role or "assistant"
        name = meta.name or agent_id
        prompt = (
            f"A minimalist, stylized profile avatar icon for an AI agent named '{name}' "
            f"with the role of '{role}'. "
            f"Clean digital art style, simple geometric shapes, muted professional colors, "
            f"abstract representation — not a face or person. "
            f"Suitable as a small square profile picture. White or transparent background."
        )
        if soul_snippet:
            first_line = soul_snippet.split("\n")[0].strip("# ").strip()
            if first_line and first_line != name:
                prompt += f" Visual theme inspired by: {first_line}."

        avatar_path = registry.agent_home(agent_id) / "avatar.png"

        # Try fal first, then OpenRouter
        image_url = self._try_fal_image(prompt, agent_id) or self._try_openrouter_image(prompt)

        if not image_url:
            # No image gen available — fall back to a role-appropriate emoji
            emoji = self._role_emoji(role)
            registry.update_agent(agent_id, avatar=emoji)
            return {"ok": True, "avatar": emoji, "fallback": "emoji"}

        try:
            import urllib.request
            urllib.request.urlretrieve(image_url, str(avatar_path))
            logger.info("Generated avatar for agent '%s' at %s", agent_id, avatar_path)

            # Sync to Matrix in the background
            self._sync_avatar_to_matrix_bg(agent_id)

            return {"ok": True, "path": str(avatar_path)}
        except Exception as e:
            logger.error("Avatar generation failed for '%s': %s", agent_id, e)
            return {"ok": False, "error": str(e)}

    def _try_fal_image(self, prompt: str, agent_id: str) -> Optional[str]:
        """Try generating an image via fal.ai. Returns image URL or None."""
        from vulti_cli.connection_registry import inject_credentials

        with inject_credentials(agent_id):
            if not os.getenv("FAL_KEY"):
                return None
            try:
                import fal_client
                handler = fal_client.submit(
                    "fal-ai/flux-2-pro",
                    arguments={
                        "prompt": prompt,
                        "image_size": "square",
                        "num_inference_steps": 30,
                        "guidance_scale": 4.5,
                        "num_images": 1,
                        "output_format": "png",
                        "enable_safety_checker": False,
                    },
                )
                result = handler.get()
                if result and result.get("images"):
                    return result["images"][0].get("url")
            except Exception as e:
                logger.debug("fal image generation failed: %s", e)
        return None

    def _try_openrouter_image(self, prompt: str) -> Optional[str]:
        """Try generating an image via OpenRouter (Gemini image model). Returns image URL or None."""
        import base64 as _b64
        import tempfile

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return None
        try:
            import urllib.request
            import json as _json

            body = _json.dumps({
                "model": "google/gemini-3.1-flash-image-preview",
                "messages": [{"role": "user", "content": prompt}],
                "modalities": ["image", "text"],
                "max_tokens": 4096,
            }).encode()

            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://vulti.ai",
                },
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = _json.loads(resp.read())

            msg = result.get("choices", [{}])[0].get("message", {})
            images = msg.get("images", [])
            if images:
                img = images[0]
                # Could be a dict with url/b64_json, or a raw base64 string
                if isinstance(img, dict):
                    return img.get("url")
                elif isinstance(img, str):
                    if img.startswith("http"):
                        return img
                    # Raw base64 — save to temp file and return path as file:// URL
                    data = _b64.b64decode(img)
                    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                    tmp.write(data)
                    tmp.close()
                    return f"file://{tmp.name}"
        except Exception as e:
            logger.debug("OpenRouter image generation failed: %s", e)
        return None

    def _sync_avatar_to_matrix_bg(self, agent_id: str) -> None:
        """Fire-and-forget Matrix avatar sync after image generation."""
        try:
            from gateway.matrix_agents import sync_agent_avatar
            from gateway.config import load_gateway_config

            config = load_gateway_config()
            matrix_cfg = config.get("matrix", {})
            homeserver_url = matrix_cfg.get("homeserver_url")
            if not homeserver_url:
                return

            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(sync_agent_avatar(agent_id, homeserver_url))
            except RuntimeError:
                # No running loop — run synchronously in a new one
                asyncio.run(sync_agent_avatar(agent_id, homeserver_url))
        except Exception as e:
            logger.debug("Matrix avatar sync skipped for %s: %s", agent_id, e)

    @staticmethod
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
        }.get(role, "◇")

    def _get_agent_sessions(self, agent_id: str = None) -> list:
        """Get sessions, optionally filtered by agent."""
        sessions = self._get_sessions()
        if agent_id:
            # Filter to sessions belonging to this agent
            return [s for s in sessions if s.get("agent_id") == agent_id or not s.get("agent_id")]
        return sessions

    def _get_cron_jobs(self, agent_id: str = None) -> list:
        """List cron jobs, optionally filtered by agent."""
        try:
            # Per-agent: read directly from agent's cron/jobs.json
            if agent_id:
                jobs_file = self._get_vulti_home() / "agents" / agent_id / "cron" / "jobs.json"
                if jobs_file.exists():
                    data = json.loads(jobs_file.read_text())
                    jobs = data.get("jobs", [])
                    result = []
                    for j in jobs:
                        sched = j.get("schedule_display") or j.get("schedule", "")
                        if isinstance(sched, dict):
                            sched = sched.get("display", sched.get("expr", str(sched)))
                        result.append({
                            "id": j.get("id", ""),
                            "name": j.get("name", ""),
                            "prompt": j.get("prompt", ""),
                            "schedule": sched,
                            "status": j.get("state", "active" if j.get("enabled", True) else "paused"),
                            "enabled": j.get("enabled", True),
                            "last_run": j.get("last_run_at"),
                            "last_output": j.get("last_output"),
                        })
                    return result
                return []

            # Global: use scheduler singleton
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

    def _get_rules(self, agent_id: str = None) -> list:
        """List rules, optionally filtered by agent."""
        try:
            from rules.rules import load_rules, load_all_rules
            rules = load_rules(agent_id) if agent_id else load_all_rules()
            return [{
                "id": r.get("id", ""),
                "name": r.get("name", ""),
                "condition": r.get("condition", ""),
                "action": r.get("action", ""),
                "enabled": r.get("enabled", True),
                "priority": r.get("priority", 0),
                "trigger_count": r.get("trigger_count", 0),
                "max_triggers": r.get("max_triggers"),
                "cooldown_minutes": r.get("cooldown_minutes"),
                "last_triggered_at": r.get("last_triggered_at"),
                "tags": r.get("tags", []),
            } for r in rules]
        except Exception as e:
            logger.debug("[web] Could not load rules: %s", e)
        return []

    def _create_rule(self, data: dict) -> dict:
        """Create a rule."""
        try:
            from rules.rules import create_rule
            new_rule = create_rule(
                condition=data.get("condition", ""),
                action=data.get("action", ""),
                name=data.get("name"),
                priority=data.get("priority", 0),
                max_triggers=data.get("max_triggers"),
                cooldown_minutes=data.get("cooldown_minutes"),
                tags=data.get("tags"),
                agent=data.get("agent"),
            )
            return {"success": True, "rule_id": new_rule["id"], "name": new_rule["name"], "rule": new_rule}
        except Exception as e:
            return {"error": str(e)}

    def _update_rule(self, rule_id: str, updates: dict) -> dict:
        """Update a rule."""
        try:
            from tools.rule_tools import rule
            if "enabled" in updates:
                action = "enable" if updates.pop("enabled") else "disable"
                if not updates:
                    result = rule(action=action, rule_id=rule_id)
                    return json.loads(result) if isinstance(result, str) else result

            # Map 'action' field to 'action_prompt' to avoid collision
            if "action" in updates:
                updates["action_prompt"] = updates.pop("action")

            result = rule(action="update", rule_id=rule_id, **updates)
            return json.loads(result) if isinstance(result, str) else result
        except Exception as e:
            return {"error": str(e)}

    def _delete_rule(self, rule_id: str) -> dict:
        """Delete a rule."""
        try:
            from tools.rule_tools import rule
            result = rule(action="remove", rule_id=rule_id)
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
        """Get all integrations from the connection registry + live gateway status."""
        home = self._get_vulti_home()
        integrations = []
        seen_ids: set = set()

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
            "matrix": {"name": "Matrix", "icon": "matrix", "category": "Messaging"},
        }
        for pid, info in platforms.items():
            if pid in ("app", "web"):
                continue
            meta = platform_meta.get(pid, {"name": pid.title(), "icon": pid, "category": "Platform"})
            details = {}

            # Enrich Matrix integration with Continuwuity details
            if pid == "matrix":
                try:
                    from gateway.continuwuity import _continuwuity_dir
                    import os
                    server_name = os.getenv("MATRIX_SERVER_NAME", "localhost")
                    port = int(os.getenv("MATRIX_CONTINUWUITY_PORT", "6167"))
                    https_url = f"https://{server_name}" if server_name != "localhost" else f"http://localhost:{port}"
                    details = {
                        "server_name": server_name,
                        "homeserver_url": https_url,
                        "port": port,
                    }
                    # Count registered agents
                    tokens_dir = _continuwuity_dir() / "tokens"
                    if tokens_dir.exists():
                        details["registered_agents"] = len([f for f in tokens_dir.iterdir() if f.suffix == ".json"])

                    # Include owner credentials if they exist
                    owner_creds_path = _continuwuity_dir() / "owner_credentials.json"
                    if owner_creds_path.exists():
                        try:
                            owner = json.loads(owner_creds_path.read_text())
                            details["owner_username"] = owner.get("username", "")
                            details["owner_password"] = owner.get("password", "")
                        except Exception:
                            pass
                except Exception:
                    pass

            integrations.append({
                "id": pid,
                "name": meta["name"],
                "category": meta["category"],
                "status": info.get("state", "unknown"),
                "details": details,
                "updated_at": info.get("updated_at"),
            })
            seen_ids.add(pid)

        try:
            from vulti_cli.connection_registry import ConnectionRegistry
            registry = ConnectionRegistry(home)
            tag_categories = {
                "messaging": "Messaging", "email": "Messaging", "communication": "Messaging",
                "social": "Social",
                "productivity": "Productivity", "notes": "Productivity", "knowledge": "Productivity",
                "project-management": "Productivity", "calendar": "Productivity",
                "voice": "Voice & SMS", "telephony": "Voice & SMS",
                "web": "Tools", "scraping": "Tools", "browser": "Tools",
                "smart-home": "Smart Home", "iot": "Smart Home",
                "llm": "LLM", "ai": "LLM", "ml": "Analytics",
                "google": "Cloud", "apple": "Apple",
            }
            for conn in registry.list_all():
                if conn.name in seen_ids or not conn.enabled:
                    continue
                category = "Tools"
                for tag in conn.tags:
                    if tag in tag_categories:
                        category = tag_categories[tag]
                        break
                display_name = conn.description.split(" \u2014 ")[0] if " \u2014 " in conn.description else conn.name.replace("-", " ").title()
                integrations.append({
                    "id": conn.name,
                    "name": display_name,
                    "category": category,
                    "status": "connected",
                    "details": {"skill": conn.skill} if conn.skill else {},
                })
                seen_ids.add(conn.name)
        except Exception as e:
            logger.debug("[web] Could not load connection registry for integrations: %s", e)

        return integrations

    # --- Memories & Soul ---

    def _get_vulti_home(self) -> Path:
        from vulti_cli.config import get_vulti_home
        return get_vulti_home()

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

            _NON_SECRET_KEYS = {"VULTI_DEFAULT_MODEL", "VULTI_DEFAULT_PROVIDER"}
            masked = value if key in _NON_SECRET_KEYS else (self._mask_value(value) if value else "")
            secrets.append({
                "key": key,
                "masked_value": masked,
                "is_set": bool(value),
                "category": category,
            })
        return secrets

    # Map of env var keys → connection entries to auto-create
    # Map env var keys to connection entries. LLM providers (OpenRouter, Anthropic, etc.)
    # are NOT connections — they're infrastructure managed in the Providers settings.
    # Maps env var name → (connection_name, type, description, tags, credential_keys)
    _ENV_TO_CONNECTION = {
        "FIRECRAWL_API_KEY": ("firecrawl", "api_key", "Firecrawl — web scraping", ["web", "scraping"], ["FIRECRAWL_API_KEY"]),
        "FAL_KEY": ("fal-ai", "api_key", "FAL.ai — image generation", ["media", "images"], ["FAL_KEY"]),
        "BROWSERBASE_API_KEY": ("browserbase", "api_key", "Browserbase — browser automation", ["web", "browser"], ["BROWSERBASE_API_KEY"]),
        "ELEVENLABS_API_KEY": ("elevenlabs", "api_key", "ElevenLabs — text-to-speech", ["voice", "tts"], ["ELEVENLABS_API_KEY"]),
        "VOICE_TOOLS_OPENAI_KEY": ("openai-voice", "api_key", "OpenAI — TTS and speech-to-text", ["voice", "tts", "stt"], ["VOICE_TOOLS_OPENAI_KEY"]),
        "TELEGRAM_BOT_TOKEN": ("telegram", "api_key", "Telegram — bot messaging", ["messaging", "bot"], ["TELEGRAM_BOT_TOKEN"]),
        "BLAND_API_KEY": ("bland-ai", "api_key", "Bland.ai — AI phone calls", ["voice", "ai"], ["BLAND_API_KEY"]),
        "TWILIO_ACCOUNT_SID": ("twilio", "api_key", "Twilio — SMS, MMS, and voice calls", ["phone", "sms", "voice"], ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"]),
        "TWILIO_AUTH_TOKEN": ("twilio", "api_key", "Twilio — SMS, MMS, and voice calls", ["phone", "sms", "voice"], ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"]),
        "TWILIO_PHONE_NUMBER": ("twilio", "api_key", "Twilio — SMS, MMS, and voice calls", ["phone", "sms", "voice"], ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"]),
        "WANDB_API_KEY": ("wandb", "api_key", "Weights & Biases — ML tracking", ["analytics", "ml"], ["WANDB_API_KEY"]),
    }

    def _add_secret(self, key: str, value: str) -> dict:
        """Add or update an API key in ~/.vulti/.env and create a connection entry."""
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise HTTPException(status_code=400, detail="Both key and value are required")

        import re
        if not re.match(r'^[A-Z][A-Z0-9_]*$', key):
            raise HTTPException(status_code=400, detail="Key must be uppercase alphanumeric with underscores")

        from vulti_cli.config import save_env_value
        save_env_value(key, value)

        # Auto-create connection entry if this is a known key
        if key in self._ENV_TO_CONNECTION:
            self._ensure_connection(*self._ENV_TO_CONNECTION[key])

        # Always ensure matrix connection exists (default messaging bus)
        self._ensure_connection("matrix", "custom", "Matrix — agent communication bus", ["messaging", "internal"])

        return {"ok": True, "key": key}

    def _ensure_connection(self, name: str, conn_type: str, description: str, tags: list, credential_keys: list = None) -> None:
        """Create a connection entry if it doesn't already exist, with credentials."""
        try:
            from vulti_cli.connection_registry import ConnectionRegistry, ConnectionEntry
            registry = ConnectionRegistry(self._get_vulti_home())
            existing = registry.get(name)
            if existing is not None:
                # Update credentials if they're empty but we have keys now
                if credential_keys and not existing.credentials:
                    cred_dict = {k: k for k in credential_keys}
                    connections = registry.load()
                    connections[name].credentials = cred_dict
                    registry.save(connections)
                return
            # Don't re-add if user explicitly deleted it
            if name in registry._get_deleted():
                return
            cred_dict = {k: k for k in (credential_keys or [])}
            registry.add(name, ConnectionEntry(
                name=name, type=conn_type, description=description, tags=tags,
                credentials=cred_dict,
            ))
        except Exception as e:
            logger.debug("Could not auto-create connection '%s': %s", name, e)

    def _delete_secret(self, key: str) -> dict:
        """Remove an API key from ~/.vulti/.env."""
        key = key.strip()
        if not key:
            raise HTTPException(status_code=400, detail="Key is required")

        from vulti_cli.config import save_env_value
        save_env_value(key, "")
        return {"ok": True}

    def _get_providers(self) -> list:
        """Return available LLM providers with auth status and model lists."""
        # Load all keys from .env file directly (same source as _get_masked_secrets)
        configured_keys = set()
        home = self._get_vulti_home()
        env_file = home / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if value:
                    configured_keys.add(key)

        # Also check live env vars
        import os
        for k in list(os.environ.keys()):
            if os.environ[k].strip():
                configured_keys.add(k)

        provider_defs = [
            {
                "id": "claude-code",
                "name": "Claude Code (OAuth)",
                "env_keys": ["CLAUDE_CODE_OAUTH_TOKEN"],
                "models": [
                    "anthropic/claude-opus-4.6",
                    "anthropic/claude-sonnet-4.6",
                    "anthropic/claude-opus-4",
                    "anthropic/claude-sonnet-4",
                    "anthropic/claude-haiku-4.5",
                ],
            },
            {
                "id": "anthropic",
                "name": "Anthropic",
                "env_keys": ["ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN"],
                "models": [
                    "anthropic/claude-opus-4.6",
                    "anthropic/claude-sonnet-4.6",
                    "anthropic/claude-haiku-4.5",
                ],
            },
            {
                "id": "venice",
                "name": "Venice",
                "env_keys": ["VENICE_API_KEY"],
                "models": [
                    "venice/llama-3.3-70b",
                    "venice/deepseek-r1-671b",
                    "venice/qwen-2.5-vl",
                ],
            },
            {
                "id": "openrouter",
                "name": "OpenRouter",
                "env_keys": ["OPENROUTER_API_KEY"],
                "models": [
                    "anthropic/claude-opus-4",
                    "anthropic/claude-sonnet-4",
                    "google/gemini-2.5-pro",
                    "openai/gpt-4o",
                    "meta-llama/llama-4-maverick",
                    "deepseek/deepseek-chat-v3.1",
                ],
            },
            {
                "id": "openai",
                "name": "OpenAI",
                "env_keys": ["OPENAI_API_KEY"],
                "models": [
                    "openai/gpt-4o",
                    "openai/gpt-4.1",
                    "openai/o3",
                ],
            },
            {
                "id": "deepseek",
                "name": "DeepSeek",
                "env_keys": ["DEEPSEEK_API_KEY"],
                "models": [
                    "deepseek/deepseek-chat",
                    "deepseek/deepseek-reasoner",
                ],
            },
            {
                "id": "google",
                "name": "Google AI",
                "env_keys": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
                "models": [
                    "google/gemini-2.5-pro",
                    "google/gemini-2.5-flash",
                ],
            },
        ]

        result = []
        for p in provider_defs:
            authenticated = any(k in configured_keys for k in p["env_keys"])
            result.append({
                "id": p["id"],
                "name": p["name"],
                "authenticated": authenticated,
                "models": p["models"],
                "env_keys": p["env_keys"],
            })
        return result

    def _get_oauth_status(self) -> list:
        """Check OAuth token files for validity."""
        home = self._get_vulti_home()
        tokens = []

        # Google OAuth — only show if token file exists
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

        # X/Twitter OAuth — only show if token file exists
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

        # Telegram session — only show if session file exists
        telegram_session = home / "telegram_user_session.session"
        if telegram_session.exists():
            tokens.append({
                "service": "Telegram (User Session)",
                "valid": True,
            })

        return tokens

    # --- Analytics ---

    def _get_analytics(self, days: int = 30, agent_id: str = None) -> dict:
        """Get usage analytics from InsightsEngine, optionally filtered by agent."""
        try:
            from agent.insights import InsightsEngine
            from vulti_state import SessionDB
            db = SessionDB()
            engine = InsightsEngine(db)
            return engine.generate(days=days, agent_id=agent_id)
        except Exception as e:
            logger.debug("[web] Could not load analytics: %s", e)
            return {"error": str(e), "empty": True}

    # --- Connections ---

    def _list_connections(self) -> list:
        """List all global connections from connections.yaml."""
        try:
            from vulti_cli.connection_registry import ConnectionRegistry
            reg = ConnectionRegistry(self._get_vulti_home())
            return [
                {
                    "name": c.name,
                    "type": c.type,
                    "description": c.description,
                    "tags": c.tags or [],
                    "enabled": c.enabled,
                }
                for c in reg.list_all()
            ]
        except Exception as e:
            logger.debug("[web] Could not load connections: %s", e)
            return []

    def _add_connection(self, data: dict) -> dict:
        from fastapi import HTTPException
        from vulti_cli.connection_registry import ConnectionRegistry, ConnectionEntry
        name = data.get("name", "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Connection name is required")
        reg = ConnectionRegistry(self._get_vulti_home())
        reg.load()
        entry = ConnectionEntry(
            name=name,
            type=data.get("type", ""),
            description=data.get("description", ""),
            tags=data.get("tags"),
            credentials=data.get("credentials"),
        )
        reg.add(name, entry)
        return {"ok": True, "name": name}

    def _update_connection(self, name: str, data: dict) -> dict:
        from vulti_cli.connection_registry import ConnectionRegistry
        reg = ConnectionRegistry(self._get_vulti_home())
        reg.load()
        existing = reg.get(name)
        if not existing:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=f"Connection '{name}' not found")
        for field in ("type", "description", "tags", "credentials"):
            if field in data:
                setattr(existing, field, data[field])
        reg.update(name, existing)
        return {"ok": True, "name": name}

    def _delete_connection(self, name: str) -> dict:
        from vulti_cli.connection_registry import ConnectionRegistry
        reg = ConnectionRegistry(self._get_vulti_home())
        reg.load()
        reg.remove(name)
        return {"ok": True}

    # --- Relationships ---

    def _list_relationships(self) -> list:
        registry = self._get_agent_registry()
        data = registry._load()
        return data.get("relationships", [])

    def _create_relationship(self, data: dict) -> dict:
        from fastapi import HTTPException
        from_id = data.get("from_agent_id", "").strip()
        to_id = data.get("to_agent_id", "").strip()
        rel_type = data.get("type", "manages")
        if not from_id or not to_id:
            raise HTTPException(status_code=400, detail="from_agent_id and to_agent_id required")
        registry = self._get_agent_registry()
        reg_data = registry._load()
        rels = reg_data.setdefault("relationships", [])
        rel_id = uuid.uuid4().hex[:12]
        new_rel = {
            "id": rel_id,
            "from_agent_id": from_id,
            "to_agent_id": to_id,
            "type": rel_type,
        }
        if data.get("matrix_room_id"):
            new_rel["matrix_room_id"] = data["matrix_room_id"]
        rels.append(new_rel)
        registry._save()
        return new_rel

    def _update_relationship(self, rel_id: str, data: dict) -> dict:
        from fastapi import HTTPException
        registry = self._get_agent_registry()
        reg_data = registry._load()
        rels = reg_data.get("relationships", [])
        for rel in rels:
            if rel.get("id") == rel_id:
                for k, v in data.items():
                    rel[k] = v
                registry._save()
                return rel
        raise HTTPException(status_code=404, detail=f"Relationship '{rel_id}' not found")

    def _delete_relationship(self, rel_id: str) -> dict:
        registry = self._get_agent_registry()
        reg_data = registry._load()
        reg_data["relationships"] = [r for r in reg_data.get("relationships", []) if r.get("id") != rel_id]
        registry._save()
        return {"ok": True}

    # --- Skills ---

    def _list_available_skills(self) -> list:
        try:
            skills_dir = self._get_vulti_home() / "skills"
            if not skills_dir.exists():
                return []
            result = []
            for d in skills_dir.iterdir():
                if d.is_dir():
                    skill_file = d / "SKILL.md"
                    meta = {"name": d.name, "description": "", "category": ""}
                    if skill_file.exists():
                        content = skill_file.read_text(encoding="utf-8")
                        for line in content.splitlines():
                            if line.startswith("# "):
                                meta["name"] = line[2:].strip()
                            elif line.lower().startswith("category:"):
                                meta["category"] = line.split(":", 1)[1].strip()
                            elif not meta["description"] and line.strip() and not line.startswith("#"):
                                meta["description"] = line.strip()
                    result.append(meta)
            return result
        except Exception as e:
            logger.debug("[web] Could not list skills: %s", e)
            return []

    def _list_agent_skills(self, agent_id: str) -> list:
        registry = self._get_agent_registry()
        skills_dir = registry.agent_skills_dir(agent_id)
        if not skills_dir.exists():
            return []
        result = []
        for d in skills_dir.iterdir():
            if d.is_dir() or d.is_symlink():
                meta = {"name": d.name, "description": "", "category": ""}
                skill_file = d / "SKILL.md" if d.is_dir() else (d.resolve() / "SKILL.md" if d.is_symlink() else None)
                if skill_file and skill_file.exists():
                    content = skill_file.read_text(encoding="utf-8")
                    for line in content.splitlines():
                        if line.startswith("# "):
                            meta["name"] = line[2:].strip()
                        elif not meta["description"] and line.strip() and not line.startswith("#"):
                            meta["description"] = line.strip()
                result.append(meta)
        return result

    def _install_agent_skill(self, agent_id: str, skill_name: str) -> dict:
        from fastapi import HTTPException
        if not skill_name:
            raise HTTPException(status_code=400, detail="Skill name is required")
        registry = self._get_agent_registry()
        source = self._get_vulti_home() / "skills" / skill_name
        if not source.exists():
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
        dest = registry.agent_skills_dir(agent_id)
        dest.mkdir(parents=True, exist_ok=True)
        link = dest / skill_name
        if link.exists() or link.is_symlink():
            return {"ok": True, "name": skill_name, "already_installed": True}
        link.symlink_to(source)
        # Sync skill-declared connection into the global registry
        try:
            from vulti_cli.connection_registry import ConnectionRegistry
            ConnectionRegistry(self._get_vulti_home()).sync_skill_connections()
        except Exception:
            pass
        return {"ok": True, "name": skill_name}

    def _remove_agent_skill(self, agent_id: str, skill_name: str) -> dict:
        registry = self._get_agent_registry()
        link = registry.agent_skills_dir(agent_id) / skill_name
        if link.exists() or link.is_symlink():
            if link.is_symlink():
                link.unlink()
            else:
                import shutil
                shutil.rmtree(link)
        return {"ok": True}

    # --- Audit ---

    def _list_audit_events(self, n: int = 50, agent_id: str = None, trace_id: str = None, event_type: str = None) -> list:
        try:
            from orchestrator.audit import tail
            return tail(n=n, agent_id=agent_id, trace_id=trace_id, event_type=event_type)
        except Exception as e:
            logger.debug("[web] Could not load audit events: %s", e)
            return []

    # --- Permissions ---

    def _list_permissions(self, agent_id: str = None) -> list:
        try:
            from orchestrator.permissions import list_pending
            return list_pending(agent_id=agent_id)
        except Exception as e:
            logger.debug("[web] Could not load permissions: %s", e)
            return []

    def _resolve_permission(self, request_id: str, approved: bool) -> dict:
        try:
            from orchestrator.permissions import approve, deny
            if approved:
                approve(request_id)
            else:
                deny(request_id)
            return {"ok": True, "request_id": request_id, "approved": approved}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # --- Owner ---

    def _get_owner(self) -> dict:
        home = self._get_vulti_home()
        owner_file = home / "owner.json"
        if owner_file.exists():
            try:
                return json.loads(owner_file.read_text())
            except Exception:
                pass
        return {"name": "", "about": ""}

    def _update_owner(self, data: dict) -> dict:
        home = self._get_vulti_home()
        owner_file = home / "owner.json"
        current = {}
        if owner_file.exists():
            try:
                current = json.loads(owner_file.read_text())
            except Exception:
                pass
        for field in ("name", "about", "avatar"):
            if field in data:
                current[field] = data[field]
        owner_file.write_text(json.dumps(current, indent=2))
        return current

    def _generate_owner_avatar(self) -> dict:
        """Generate a profile avatar for the owner using their name and about.

        Owner has blanket permissions — all secrets from .env are injected
        so any image gen provider that's configured will work.
        """
        owner = self._get_owner()
        name = owner.get("name", "").strip() or "Human"
        about = owner.get("about", "").strip()

        prompt = (
            f"A minimalist, stylized profile avatar for a person named '{name}'. "
            f"Clean digital art style, warm and approachable, muted professional colors. "
            f"Suitable as a small circular profile picture. White or transparent background."
        )
        if about:
            prompt += f" About them: {about[:200]}."

        home = self._get_vulti_home()
        avatar_path = home / "owner_avatar.png"

        # Owner has blanket access — inject ALL secrets from .env
        env_file = home / ".env"
        originals = {}
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip("'\"")
                if value:
                    originals[key] = os.environ.get(key)
                    os.environ[key] = value

        try:
            image_url = self._try_openrouter_image(prompt)
            if not image_url:
                # fal needs no agent context when env vars are already set
                fal_key = os.getenv("FAL_KEY")
                if fal_key:
                    try:
                        import fal_client
                        handler = fal_client.submit(
                            "fal-ai/flux-2-pro",
                            arguments={
                                "prompt": prompt,
                                "image_size": "square",
                                "num_inference_steps": 30,
                                "guidance_scale": 4.5,
                                "num_images": 1,
                                "output_format": "png",
                                "enable_safety_checker": False,
                            },
                        )
                        result = handler.get()
                        if result and result.get("images"):
                            image_url = result["images"][0]["url"]
                    except Exception as e:
                        logger.warning("fal image gen failed for owner: %s", e)

            if not image_url:
                return {"ok": False, "error": "No image generation provider available"}

            import urllib.request, base64
            urllib.request.urlretrieve(image_url, str(avatar_path))
            logger.info("Generated owner avatar at %s", avatar_path)

            with open(avatar_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            self._update_owner({"avatar": b64})

            return {"ok": True, "path": str(avatar_path)}
        except Exception as e:
            logger.error("Owner avatar generation failed: %s", e)
            return {"ok": False, "error": str(e)}
        finally:
            # Restore original env
            for key, original in originals.items():
                if original is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original

    # --- Agent Avatar (fetch) ---

    def _get_agent_avatar(self, agent_id: str) -> dict:
        import base64
        registry = self._get_agent_registry()
        avatar_path = registry.agent_home(agent_id) / "avatar.png"
        if avatar_path.exists():
            data = avatar_path.read_bytes()
            return {"avatar": base64.b64encode(data).decode(), "format": "png"}
        meta = registry.get_agent(agent_id)
        if meta and meta.avatar:
            return {"avatar": meta.avatar, "format": "emoji"}
        return {"avatar": None}

    # --- Agent Files ---

    def _get_agent_cache_dir(self, agent_id: str) -> Path:
        from vulti_cli.config import get_vulti_home
        return get_vulti_home() / "agents" / agent_id / "cache"

    def _list_agent_files(self, agent_id: str) -> list:
        cache_dir = self._get_agent_cache_dir(agent_id)
        if not cache_dir.exists():
            return []
        files = []
        for f in sorted(cache_dir.rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
            if not f.is_file():
                continue
            rel = f.relative_to(cache_dir)
            ext = f.suffix.lower()
            if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                category = "image"
            elif ext in (".ogg", ".opus", ".mp3", ".wav", ".m4a"):
                category = "audio"
            elif ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
                category = "video"
            else:
                category = "document"
            files.append({
                "name": f.name,
                "path": str(rel),
                "category": category,
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
        return files

    # --- Agent Config ---

    def _get_agent_config(self, agent_id: str) -> dict:
        registry = self._get_agent_registry()
        config_path = registry.agent_config_path(agent_id)
        if config_path.exists():
            try:
                import yaml
                return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            except Exception:
                pass
        return {}

    # --- Agent Wallet ---

    def _get_agent_wallet(self, agent_id: str) -> dict:
        registry = self._get_agent_registry()
        wallet_path = registry.agent_home(agent_id) / "creditcard.json"
        if wallet_path.exists():
            try:
                return json.loads(wallet_path.read_text())
            except Exception:
                pass
        return {}

    def _save_agent_wallet(self, agent_id: str, data: dict) -> dict:
        registry = self._get_agent_registry()
        wallet_path = registry.agent_home(agent_id) / "creditcard.json"
        wallet_path.parent.mkdir(parents=True, exist_ok=True)
        # Merge with existing
        current = {}
        if wallet_path.exists():
            try:
                current = json.loads(wallet_path.read_text())
            except Exception:
                pass
        current.update(data)
        wallet_path.write_text(json.dumps(current, indent=2))
        return {"ok": True}

    # --- Agent Vault ---

    def _get_agent_vault(self, agent_id: str) -> dict:
        """Get vault info. The .vult file is encrypted — use CLI for metadata."""
        registry = self._get_agent_registry()
        agent_home = registry.agent_home(agent_id)
        # Find .vult keyshare — its stem is the vault name
        vault_name = None
        try:
            for f in agent_home.iterdir():
                if f.suffix == ".vult":
                    vault_name = f.stem
                    break
        except FileNotFoundError:
            pass
        if not vault_name:
            return {}
        # Query CLI for vault ID and metadata
        try:
            import subprocess
            vbin = str(self._vulti_home / "vultisig-cli" / "node_modules" / ".bin" / "vultisig")
            result = subprocess.run(
                [vbin, "vaults", "-o", "json", "--silent"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                # Normalize for comparison: lowercase, strip hyphens/spaces
                def _norm(s: str) -> str:
                    return s.lower().replace("-", "").replace("_", "").replace(" ", "")
                norm_name = _norm(vault_name)
                for v in data.get("data", {}).get("vaults", []):
                    cli_name = v.get("name", "")
                    if _norm(cli_name) == norm_name or cli_name == vault_name:
                        vid = v.get("id", "")
                        resp = {
                            "vault_id": vid,
                            "name": v.get("name", vault_name),
                            "type": v.get("type", ""),
                            "chains": v.get("chains", 0),
                            "createdAt": v.get("createdAt"),
                        }
                        # Fetch addresses
                        if vid:
                            try:
                                addr_result = subprocess.run(
                                    [vbin, "addresses", "--vault", vid, "-o", "json", "--silent"],
                                    capture_output=True, text=True, timeout=10,
                                )
                                if addr_result.returncode == 0:
                                    addr_data = json.loads(addr_result.stdout)
                                    resp["addresses"] = addr_data.get("data", {}).get("addresses", {})
                            except Exception:
                                pass
                        return resp
        except Exception:
            pass
        return {"vault_id": "", "name": vault_name}

    def _get_vault_portfolio(self, agent_id: str) -> dict:
        """Get vault portfolio by wrapping vultisig CLI."""
        vault_info = self._get_agent_vault(agent_id)
        vault_id = vault_info.get("vault_id")
        if not vault_id:
            return {}
        try:
            import subprocess
            vbin = str(self._vulti_home / "vultisig-cli" / "node_modules" / ".bin" / "vultisig")
            result = subprocess.run(
                [vbin, "portfolio", "--vault", vault_id, "-o", "json", "--silent"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception:
            pass
        return {}

    def _delete_agent_vault(self, agent_id: str) -> dict:
        registry = self._get_agent_registry()
        agent_home = registry.agent_home(agent_id)
        deleted = False
        try:
            for f in agent_home.iterdir():
                if f.suffix == ".vult":
                    f.unlink()
                    deleted = True
        except FileNotFoundError:
            pass
        return {"ok": True, "deleted": deleted}

    # --- Pane Widgets ---

    def _build_default_widgets(self, agent_id: str) -> list:
        """Build the 9 default home widgets from the agent's current state."""
        registry = self._get_agent_registry()
        agent_home = registry.agent_home(agent_id)
        meta = registry.get_agent(agent_id)
        mem_dir = registry.agent_memories_dir(agent_id)
        soul_path = registry.agent_soul_path(agent_id)

        widgets = []

        # 1. Profile card — compact card with avatar, name, role, and drill links
        soul_content = ""
        if soul_path.exists():
            soul_content = soul_path.read_text(encoding="utf-8").strip()

        user_path = mem_dir / "USER.md"
        user_count = 0
        if user_path.exists():
            raw = user_path.read_text(encoding="utf-8").strip()
            if raw:
                user_count = len([e for e in raw.split("\u00a7") if e.strip()])

        memory_path = mem_dir / "MEMORY.md"
        memory_count = 0
        if memory_path.exists():
            raw = memory_path.read_text(encoding="utf-8").strip()
            if raw:
                memory_count = len([e for e in raw.split("\u00a7") if e.strip()])

        widgets.append({
            "id": "default_profile",
            "type": "profile",
            "title": meta.name if meta else agent_id,
            "data": {
                "role": meta.role if meta and meta.role else "",
                "avatar": meta.avatar if meta and meta.avatar else "",
                "has_soul": bool(soul_content),
                "user_count": user_count,
                "memory_count": memory_count,
                "size": "large",
            },
        })

        # 2. Connections — only show allowed connections for this agent
        all_connections = self._list_connections()
        allowed = set(self._get_agent_allowed_connections(agent_id))
        conn_entries = []
        for c in all_connections:
            if c["name"] in allowed:
                conn_entries.append({"key": c["name"], "value": "\u2713"})
        widgets.append({
            "id": "default_connections",
            "type": "kv",
            "title": "\U0001f50c Connections" + (f" ({len(conn_entries)})" if conn_entries else ""),
            "data": {
                "entries": conn_entries if conn_entries else [{"key": "\u2014", "value": "No connections allowed"}],
                "drill": "connections",
            },
        })

        # 3. Jobs — list with name + schedule
        job_entries = []
        try:
            cron_file = agent_home / "cron" / "jobs.json"
            if cron_file.exists():
                jobs_data = json.loads(cron_file.read_text(encoding="utf-8"))
                job_list = jobs_data if isinstance(jobs_data, list) else jobs_data.get("jobs", [])
                for j in job_list:
                    name = j.get("name", j.get("id", "unnamed"))
                    sched = j.get("schedule", "")
                    if isinstance(sched, dict):
                        sched = sched.get("display", sched.get("expr", ""))
                    status = "\u2713" if j.get("enabled", True) else "\u23f8"
                    job_entries.append({"key": name, "value": f"{sched}  {status}"})
        except Exception:
            pass
        widgets.append({
            "id": "default_jobs",
            "type": "kv",
            "title": "\u23f0 Jobs" + (f" ({len(job_entries)})" if job_entries else ""),
            "data": {
                "entries": job_entries if job_entries else [{"key": "\u2014", "value": "None scheduled"}],
                "drill": "jobs",
                "size": "half",
            },
        })

        # 4. Rules — list with name + condition
        rule_entries = []
        try:
            from vulti_cli.config import get_vulti_home
            rules_file = get_vulti_home() / "rules" / "rules.json"
            if rules_file.exists():
                rules_data = json.loads(rules_file.read_text(encoding="utf-8"))
                rule_list = rules_data if isinstance(rules_data, list) else rules_data.get("rules", [])
                for r in rule_list:
                    r_agent = r.get("agent_id", r.get("agent", ""))
                    if r_agent and r_agent != agent_id:
                        continue
                    name = r.get("name", r.get("id", "unnamed"))
                    status = "\u2713" if r.get("enabled", True) else "\u23f8"
                    rule_entries.append({"key": name, "value": status})
        except Exception:
            pass
        widgets.append({
            "id": "default_rules",
            "type": "kv",
            "title": "\U0001f4d0 Rules" + (f" ({len(rule_entries)})" if rule_entries else ""),
            "data": {
                "entries": rule_entries if rule_entries else [{"key": "\u2014", "value": "None configured"}],
                "drill": "rules",
                "size": "half",
            },
        })

        # 5. Skills — show installed (agent-specific) vs available (global)
        installed_names = []
        available_count = 0
        try:
            skills_dir = agent_home / "skills"
            if skills_dir.exists():
                installed_names = [d.name for d in sorted(skills_dir.iterdir()) if d.is_dir()]
        except Exception:
            pass
        try:
            from vulti_cli.config import get_vulti_home
            global_skills = get_vulti_home() / "skills"
            if global_skills.exists():
                # Count actual skills (dirs containing SKILL.md), not category folders
                for _root, _dirs, _files in os.walk(str(global_skills)):
                    if "SKILL.md" in _files:
                        available_count += 1
        except Exception:
            pass
        installed_count = len(installed_names)
        skill_detail = ", ".join(installed_names[:3])
        if len(installed_names) > 3:
            skill_detail += f" +{len(installed_names) - 3}"
        label = f"{installed_count} installed"
        if available_count:
            label += f" / {available_count} available"
        widgets.append({
            "id": "default_skills",
            "type": "status",
            "title": "\U0001f9e9 Skills",
            "data": {
                "label": label if installed_count else f"0 installed / {available_count} available",
                "variant": "success" if installed_count else "info",
                "detail": skill_detail if skill_detail else "No skills installed yet",
                "drill": "skills",
            },
        })

        # 6. Wallet — credit card from creditcard.json, vault from .vult keyshare
        card_name = ""
        card_last4 = ""
        card_expiry = ""
        vault_id = ""
        vault_name = ""
        try:
            cc_path = agent_home / "creditcard.json"
            if cc_path.exists():
                w = json.loads(cc_path.read_text(encoding="utf-8"))
                cc = w.get("credit_card", {})
                if cc.get("number"):
                    card_name = cc.get("cardholder_name", cc.get("name", ""))
                    card_last4 = cc["number"][-4:]
                    card_expiry = cc.get("expiry", "")
        except Exception:
            pass

        # Vault: .vult file is encrypted — use filename as name, CLI for ID
        try:
            for f in agent_home.iterdir():
                if f.suffix == ".vult":
                    vault_name = f.stem
                    # Get vault ID from CLI
                    vault_info = self._get_agent_vault(agent_id)
                    vault_id = vault_info.get("vault_id", "")
                    break
        except Exception:
            pass

        widgets.append({
            "id": "default_wallet",
            "type": "kv",  # Rendered specially by frontend when it sees wallet data fields
            "title": "\U0001f4b3 Wallet",
            "data": {
                "card_name": card_name,
                "card_last4": card_last4,
                "card_expiry": card_expiry,
                "vault_id": vault_id,
                "vault_name": vault_name,
                "entries": [] if (card_name or vault_id) else [{"key": "\u2014", "value": "No card or vault set up"}],
                "drill": "wallet",
                "size": "half",
            },
        })

        # 7. Analytics — cost, sessions, tokens
        session_count = 0
        total_tokens = 0
        try:
            from vulti_cli.config import get_vulti_home
            sessions_dir = get_vulti_home() / "web" / "sessions"
            if sessions_dir.exists():
                session_count = len([f for f in sessions_dir.glob("*.json") if "_widgets" not in f.name])
        except Exception:
            pass
        try:
            audit_dir = get_vulti_home() / "audit"
            if audit_dir.exists():
                for f in sorted(audit_dir.glob("*.jsonl"), reverse=True)[:1]:
                    for line in f.read_text(encoding="utf-8").strip().splitlines()[-50:]:
                        try:
                            evt = json.loads(line)
                            if evt.get("agent_id") == agent_id:
                                tokens = evt.get("details", {}).get("total_tokens", 0)
                                if tokens:
                                    total_tokens += int(tokens)
                        except Exception:
                            pass
        except Exception:
            pass
        widgets.append({
            "id": "default_analytics",
            "type": "stat_grid",
            "title": "\U0001f4ca Analytics",
            "data": {
                "stats": [
                    {"label": "Sessions", "value": str(session_count)},
                    {"label": "Tokens", "value": f"{total_tokens:,}" if total_tokens else "0"},
                    {"label": "Est. Cost", "value": f"${total_tokens * 0.000003:.2f}" if total_tokens else "$0.00"},
                ],
                "drill": "analytics",
                "size": "half",
            },
        })

        return widgets

    def _reset_default_widgets(self, agent_id: str) -> dict:
        """Reset pane to default widgets built from agent's current state."""
        registry = self._get_agent_registry()
        pane_path = registry.agent_home(agent_id) / "pane_widgets.json"
        widgets = self._build_default_widgets(agent_id)
        data = {"version": 1, "tabs": {"home": widgets}}
        pane_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data

    def _get_session_pane_widgets(self, session_id: str) -> dict:
        """Get per-session (chat tab) widgets."""
        from vulti_cli.config import get_vulti_home
        path = get_vulti_home() / "web" / "sessions" / f"{session_id}_widgets.json"
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                pass
        return {"version": 1, "tabs": {}}

    def _get_pane_widgets(self, agent_id: str) -> dict:
        registry = self._get_agent_registry()
        # Sync role.txt → registry if agent wrote role.txt but registry is behind
        self._sync_role_from_file(agent_id, registry)
        pane_path = registry.agent_home(agent_id) / "pane_widgets.json"
        if pane_path.exists():
            try:
                data = json.loads(pane_path.read_text())
                # Refresh default widget titles/entries from live data so counts stay current
                self._refresh_default_widget_data(agent_id, data)
                return data
            except Exception:
                pass
        # No pane file — generate and persist defaults
        return self._reset_default_widgets(agent_id)

    def _refresh_default_widget_data(self, agent_id: str, data: dict) -> None:
        """Refresh default widget titles and entries from live data so counts stay current."""
        try:
            fresh = self._build_default_widgets(agent_id)
            fresh_by_id = {w["id"]: w for w in fresh}

            for tab_name, tab_data in data.get("tabs", {}).items():
                widgets = tab_data if isinstance(tab_data, list) else tab_data.get("widgets", [])
                for widget in widgets:
                    wid = widget.get("id", "")
                    if wid in fresh_by_id:
                        fresh_w = fresh_by_id[wid]
                        widget["title"] = fresh_w["title"]
                        if "data" in fresh_w and "entries" in fresh_w["data"]:
                            widget.setdefault("data", {})["entries"] = fresh_w["data"]["entries"]
        except Exception:
            pass

    def _sync_role_from_file(self, agent_id: str, registry=None) -> None:
        """If the agent wrote role.txt but the registry role is empty/different, sync it."""
        try:
            if registry is None:
                registry = self._get_agent_registry()
            role_path = registry.agent_home(agent_id) / "role.txt"
            if not role_path.exists():
                return
            file_role = role_path.read_text(encoding="utf-8").strip()
            if not file_role:
                return
            meta = registry.get_agent(agent_id)
            if meta and meta.role != file_role:
                registry.update_agent(agent_id, role=file_role)
        except Exception:
            pass

    def _clear_pane_widgets(self, agent_id: str, tab: str = None) -> dict:
        registry = self._get_agent_registry()
        pane_path = registry.agent_home(agent_id) / "pane_widgets.json"
        if tab:
            if pane_path.exists():
                try:
                    data = json.loads(pane_path.read_text())
                    tabs = data.get("tabs", {})
                    if tab in tabs:
                        del tabs[tab]
                    data["tabs"] = tabs
                    pane_path.write_text(json.dumps(data, indent=2))
                except Exception:
                    pass
        else:
            if pane_path.exists():
                pane_path.unlink()
        return {"ok": True}

    def _remove_pane_widget(self, agent_id: str, widget_id: str) -> dict:
        """Remove a single widget by ID from the pane."""
        registry = self._get_agent_registry()
        pane_path = registry.agent_home(agent_id) / "pane_widgets.json"
        if pane_path.exists():
            try:
                data = json.loads(pane_path.read_text())
                tabs = data.get("tabs", {})
                for tab_name, widgets in tabs.items():
                    tabs[tab_name] = [w for w in widgets if w.get("id") != widget_id]
                data["tabs"] = tabs
                pane_path.write_text(json.dumps(data, indent=2))
            except Exception:
                pass
        return {"ok": True}

    def _reorder_pane_widgets(self, agent_id: str, widget_ids: list) -> dict:
        """Reorder widgets on the home tab by the given ID order."""
        registry = self._get_agent_registry()
        pane_path = registry.agent_home(agent_id) / "pane_widgets.json"
        if pane_path.exists():
            try:
                data = json.loads(pane_path.read_text())
                tabs = data.get("tabs", {})
                home = tabs.get("home", [])
                # Build index by id
                by_id = {w.get("id"): w for w in home}
                # Reorder: put known IDs first in order, then any unknown ones
                reordered = []
                for wid in widget_ids:
                    if wid in by_id:
                        reordered.append(by_id.pop(wid))
                # Append any remaining widgets not in the order list
                reordered.extend(by_id.values())
                tabs["home"] = reordered
                data["tabs"] = tabs
                pane_path.write_text(json.dumps(data, indent=2))
            except Exception:
                pass
        return {"ok": True}

    # --- Finalize Onboarding ---

    def _finalize_onboarding(self, agent_id: str, data: dict) -> dict:
        registry = self._get_agent_registry()
        meta = registry.get_agent(agent_id)
        if not meta:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
        # Update role from onboarding data if provided
        updates = {}
        if data.get("role"):
            updates["role"] = data["role"]
        updates["status"] = "active"
        if updates:
            meta = registry.update_agent(agent_id, **updates)
        return {"ok": True, "role": meta.role, "agent": {"id": meta.id, "name": meta.name, "role": meta.role}}

