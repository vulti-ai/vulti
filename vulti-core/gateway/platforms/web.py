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
        # Track last streamed content per session for history storage
        self._last_streamed: Dict[str, str] = {}
        # Sessions with active streaming — send() uses "chunk" type instead
        # of "message" to avoid creating committed message bubbles mid-stream
        self._streaming_sessions: set = set()

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

        @app.post("/api/agents")
        async def create_agent(req: Request, authorization: str = Header("")):
            await get_current_user(authorization)
            data = await req.json()
            return adapter._create_agent(data)

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
                        base_url = f"https://{ts_name}:{port}"
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

            # Invite and join owner to all rooms
            try:
                import httpx
                server_name = os.getenv("MATRIX_SERVER_NAME", "localhost")
                tokens_dir = _continuwuity_dir() / "tokens"
                # Get an agent token for inviting
                agent_token = None
                for f in tokens_dir.iterdir():
                    if f.suffix == ".json":
                        agent_token = json.loads(f.read_text()).get("access_token")
                        break
                if agent_token:
                    owner_headers = {"Authorization": f"Bearer {result['access_token']}"}
                    agent_headers = {"Authorization": f"Bearer {agent_token}"}
                    async with httpx.AsyncClient(timeout=10.0) as hc:
                        for room_alias in ["chatter", "updates"]:
                            try:
                                resp = await hc.get(
                                    f"{homeserver_url}/_matrix/client/v3/directory/room/%23{room_alias}:{server_name}",
                                )
                                if resp.status_code == 200:
                                    room_id = resp.json().get("room_id")
                                    if room_id:
                                        await hc.post(
                                            f"{homeserver_url}/_matrix/client/v3/rooms/{room_id}/invite",
                                            headers=agent_headers,
                                            json={"user_id": result["user_id"]},
                                        )
                                        await hc.post(
                                            f"{homeserver_url}/_matrix/client/v3/join/{room_id}",
                                            headers=owner_headers,
                                            json={},
                                        )
                            except Exception:
                                pass
            except Exception:
                pass

            return {"user_id": result["user_id"], "username": username}

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

            if not agent_id or not agent_name:
                raise HTTPException(status_code=400, detail="agent_id and agent_name are required")

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

            if not agent_id or not agent_name:
                raise HTTPException(status_code=400, detail="agent_id and agent_name are required")

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

        # --- Agent Avatar (fetch) ---

        @app.get("/api/agents/{agent_id}/avatar")
        async def get_agent_avatar(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_agent_avatar(agent_id)

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

        # --- Pane Widgets ---

        @app.get("/api/agents/{agent_id}/pane")
        async def get_pane_widgets(agent_id: str, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._get_pane_widgets(agent_id)

        @app.delete("/api/agents/{agent_id}/pane")
        async def clear_pane_widgets(agent_id: str, tab: str = None, authorization: str = Header("")):
            await get_current_user(authorization)
            return adapter._clear_pane_widgets(agent_id, tab)

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
        session_id = chat_id.replace("web:", "", 1) if chat_id.startswith("web:") else chat_id
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
            # Mark session as actively streaming so send() routes as chunks
            self._streaming_sessions.add(session_id)
            # Track latest streamed content for history storage
            self._last_streamed[session_id] = content
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

    def _get_agent_registry(self):
        """Get or create the agent registry instance."""
        if not hasattr(self, "_agent_registry"):
            from vulti_cli.agent_registry import AgentRegistry
            self._agent_registry = AgentRegistry()
            self._agent_registry.ensure_initialized()
        return self._agent_registry

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
                "platforms": connected if a.id == registry.default_agent_id else [],
                "avatar": a.avatar,
                "description": a.description,
                "createdAt": a.created_at,
                "createdFrom": a.created_from,
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

        # Write personality to soul if provided
        if data.get("personality"):
            soul_path = registry.agent_soul_path(agent_id)
            soul_path.write_text(data["personality"], encoding="utf-8")

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

    def _update_agent(self, agent_id: str, data: dict) -> dict:
        """Update an agent's metadata."""
        registry = self._get_agent_registry()
        if registry.get_agent(agent_id) is None:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

        updates = {}
        for field in ("name", "role", "status", "avatar", "description"):
            if field in data:
                updates[field] = data[field]

        try:
            meta = registry.update_agent(agent_id, **updates) if updates else registry.get_agent(agent_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Update personality/soul if provided
        if "personality" in data:
            soul_path = registry.agent_soul_path(agent_id)
            soul_path.write_text(data["personality"], encoding="utf-8")

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

    def _get_rules(self, agent_id: str = None) -> list:
        """List rules, optionally filtered by agent."""
        try:
            from rules.rules import list_rules
            all_rules = list_rules(include_disabled=True)
            rules = all_rules
            if agent_id:
                rules = [r for r in all_rules if r.get("agent", "default") == agent_id]
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
            "matrix": {"name": "Matrix", "icon": "matrix", "category": "Messaging"},
        }
        for pid, info in platforms.items():
            if pid == "web":
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

    def _add_secret(self, key: str, value: str) -> dict:
        """Add or update an API key in ~/.vulti/.env."""
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise HTTPException(status_code=400, detail="Both key and value are required")

        # Validate key name format
        import re
        if not re.match(r'^[A-Z][A-Z0-9_]*$', key):
            raise HTTPException(status_code=400, detail="Key must be uppercase alphanumeric with underscores")

        from vulti_cli.config import save_env_value
        save_env_value(key, value)
        return {"ok": True, "key": key}

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
                "id": "openrouter",
                "name": "OpenRouter",
                "env_keys": ["OPENROUTER_API_KEY"],
                "models": [
                    "openrouter/anthropic/claude-opus-4",
                    "openrouter/anthropic/claude-sonnet-4",
                    "openrouter/google/gemini-2.5-pro",
                    "openrouter/openai/gpt-4o",
                    "openrouter/meta-llama/llama-4-maverick",
                    "openrouter/deepseek/deepseek-chat-v3",
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
        try:
            from vulti_cli.connection_registry import ConnectionRegistry
            reg = ConnectionRegistry(self._get_vulti_home())
            reg.load()
            return [
                {
                    "name": c.name,
                    "type": c.type,
                    "description": c.description,
                    "tags": c.tags or [],
                    "enabled": True,
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
        wallet_path = registry.agent_home(agent_id) / "wallet.json"
        if wallet_path.exists():
            try:
                return json.loads(wallet_path.read_text())
            except Exception:
                pass
        return {}

    def _save_agent_wallet(self, agent_id: str, data: dict) -> dict:
        registry = self._get_agent_registry()
        wallet_path = registry.agent_home(agent_id) / "wallet.json"
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
        registry = self._get_agent_registry()
        agent_home = registry.agent_home(agent_id)
        # Look for .vult files
        for f in agent_home.iterdir():
            if f.suffix == ".vult":
                try:
                    data = json.loads(f.read_text())
                    return {"vault_id": data.get("vault_id", f.stem), "name": data.get("name", f.stem), **data}
                except Exception:
                    return {"vault_id": f.stem, "name": f.stem}
        return {}

    def _delete_agent_vault(self, agent_id: str) -> dict:
        registry = self._get_agent_registry()
        agent_home = registry.agent_home(agent_id)
        deleted = False
        for f in agent_home.iterdir():
            if f.suffix == ".vult":
                f.unlink()
                deleted = True
        # Also clear crypto wallet from wallet.json
        wallet_path = agent_home / "wallet.json"
        if wallet_path.exists():
            try:
                w = json.loads(wallet_path.read_text())
                if "crypto" in w:
                    del w["crypto"]
                    wallet_path.write_text(json.dumps(w, indent=2))
            except Exception:
                pass
        return {"ok": True, "deleted": deleted}

    # --- Pane Widgets ---

    def _get_pane_widgets(self, agent_id: str) -> dict:
        registry = self._get_agent_registry()
        pane_path = registry.agent_home(agent_id) / "pane_widgets.json"
        if pane_path.exists():
            try:
                return json.loads(pane_path.read_text())
            except Exception:
                pass
        return {"version": 1, "tabs": {}}

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

