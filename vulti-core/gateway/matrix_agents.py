"""
Matrix agent registration and room topology.

Manages the mapping between Vulti agents and Matrix users on the local
Continuwuity homeserver. When the gateway starts, each registered agent
gets a corresponding Matrix user. Standard rooms are auto-created for
different communication patterns.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _tokens_dir() -> Path:
    """Return the tokens directory for agent Matrix credentials."""
    from vulti_cli.config import get_vulti_home
    d = get_vulti_home() / "continuwuity" / "tokens"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_agent_matrix_credentials(agent_id: str) -> Optional[Dict[str, Any]]:
    """Read stored Matrix credentials for an agent.

    Returns dict with user_id, access_token, homeserver_url or None.
    """
    token_file = _tokens_dir() / f"{agent_id}.json"
    if token_file.exists():
        try:
            return json.loads(token_file.read_text())
        except Exception as e:
            logger.warning("Failed to read Matrix credentials for %s: %s", agent_id, e)
    return None


def _save_agent_matrix_credentials(
    agent_id: str,
    user_id: str,
    access_token: str,
    homeserver_url: str,
) -> None:
    """Save Matrix credentials for an agent."""
    token_file = _tokens_dir() / f"{agent_id}.json"
    data = {
        "user_id": user_id,
        "access_token": access_token,
        "homeserver_url": homeserver_url,
    }
    token_file.write_text(json.dumps(data, indent=2))
    try:
        token_file.chmod(0o600)
    except OSError:
        pass


async def register_matrix_user(
    homeserver_url: str,
    username: str,
    password: str,
    registration_token: str = "",
) -> Optional[Dict[str, str]]:
    """Register a new Matrix user via the registration API.

    Supports both open registration (no token) and token-based registration.

    Args:
        homeserver_url: URL of the homeserver.
        username: Local part of the Matrix user ID.
        password: Password for the new user.
        registration_token: Token for registration (optional with open registration).

    Returns:
        Dict with user_id, access_token on success, None on failure.
    """
    import httpx

    url = f"{homeserver_url}/_matrix/client/v3/register"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Initial request — may succeed directly with open registration
            resp = await client.post(url, json={
                "username": username,
                "password": password,
                "inhibit_login": False,
            })

            if resp.status_code == 200:
                data = resp.json()
                return {
                    "user_id": data["user_id"],
                    "access_token": data["access_token"],
                }

            if resp.status_code == 401:
                flow_data = resp.json()
                session = flow_data.get("session", "")
                flows = flow_data.get("flows", [])

                # Check what auth type is required
                for flow in flows:
                    stages = flow.get("stages", [])

                    if "m.login.registration_token" in stages and registration_token:
                        resp2 = await client.post(url, json={
                            "username": username,
                            "password": password,
                            "inhibit_login": False,
                            "auth": {
                                "type": "m.login.registration_token",
                                "token": registration_token,
                                "session": session,
                            },
                        })
                        if resp2.status_code == 200:
                            data = resp2.json()
                            return {
                                "user_id": data["user_id"],
                                "access_token": data["access_token"],
                            }

                    elif "m.login.dummy" in stages:
                        resp2 = await client.post(url, json={
                            "username": username,
                            "password": password,
                            "inhibit_login": False,
                            "auth": {
                                "type": "m.login.dummy",
                                "session": session,
                            },
                        })
                        if resp2.status_code == 200:
                            data = resp2.json()
                            return {
                                "user_id": data["user_id"],
                                "access_token": data["access_token"],
                            }

                logger.warning(
                    "Matrix registration failed for %s: %s %s",
                    username, resp.status_code, resp.text[:200],
                )
            else:
                logger.warning(
                    "Matrix registration unexpected response for %s: %s",
                    username, resp.status_code,
                )

    except Exception as e:
        logger.error("Matrix registration error for %s: %s", username, e)

    return None


async def ensure_agent_matrix_user(
    agent_id: str,
    agent_name: str,
    homeserver_url: str,
    server_name: str,
    registration_token: str,
) -> Optional[str]:
    """Register or get existing Matrix user for an agent.

    Creates @vulti-{agent_id}:{server_name} if it doesn't exist.
    Returns the full Matrix user ID or None on failure.
    """
    import secrets

    matrix_user_id = f"@{agent_id}-vulti:{server_name}"

    # Check if we already have credentials
    creds = get_agent_matrix_credentials(agent_id)
    if creds and creds.get("user_id") == matrix_user_id:
        # Verify the token still works
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{homeserver_url}/_matrix/client/v3/account/whoami",
                    headers={"Authorization": f"Bearer {creds['access_token']}"},
                )
                if resp.status_code == 200:
                    logger.debug("Matrix: agent %s already registered as %s", agent_id, matrix_user_id)
                    return matrix_user_id
        except Exception:
            pass
        # Token invalid — re-register below

    # Register new user
    username = f"{agent_id}-vulti"
    password = secrets.token_urlsafe(32)

    result = await register_matrix_user(
        homeserver_url=homeserver_url,
        username=username,
        password=password,
        registration_token=registration_token,
    )

    if not result:
        logger.error("Matrix: failed to register agent %s as %s", agent_id, matrix_user_id)
        return None

    # Save credentials
    _save_agent_matrix_credentials(
        agent_id=agent_id,
        user_id=result["user_id"],
        access_token=result["access_token"],
        homeserver_url=homeserver_url,
    )

    # Set display name
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.put(
                f"{homeserver_url}/_matrix/client/v3/profile/{result['user_id']}/displayname",
                headers={"Authorization": f"Bearer {result['access_token']}"},
                json={"displayname": f"🤖 {agent_name}"},
            )
    except Exception as e:
        logger.warning("Matrix: failed to set display name for %s: %s", agent_id, e)

    logger.info("Matrix: registered agent %s as %s", agent_id, result["user_id"])
    return result["user_id"]


async def sync_agents_to_matrix(
    homeserver_url: str,
    server_name: str,
    registration_token: str,
) -> Dict[str, str]:
    """Register all agents as Matrix users.

    Returns dict mapping agent_id -> matrix_user_id for successfully
    registered agents.
    """
    from orchestrator.agent_registry import AgentRegistry

    registry = AgentRegistry()
    agents = registry.list_agents()
    registered = {}

    for agent in agents:
        if agent.status != "active":
            continue

        matrix_id = await ensure_agent_matrix_user(
            agent_id=agent.id,
            agent_name=agent.name,
            homeserver_url=homeserver_url,
            server_name=server_name,
            registration_token=registration_token,
        )
        if matrix_id:
            registered[agent.id] = matrix_id

    if registered:
        logger.info("Matrix: registered %d agent(s): %s", len(registered), list(registered.keys()))

    return registered


async def ensure_room_topology(
    homeserver_url: str,
    access_token: str,
    server_name: str,
    agent_matrix_ids: Dict[str, str],
) -> Dict[str, str]:
    """Create standard rooms for agent communication.

    Creates:
    - #hub:{server_name} — Main room for all agents + humans
    - #agents:{server_name} — Inter-agent coordination room

    Returns dict mapping room alias -> room_id.
    """
    import httpx

    rooms_created = {}
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        for alias_local, room_name, topic in [
            ("hub", "Vulti Hub", "Main communication hub for agents and humans"),
            ("agents", "Agent Coordination", "Inter-agent messaging and coordination"),
        ]:
            full_alias = f"#{alias_local}:{server_name}"

            # Check if room already exists
            try:
                resp = await client.get(
                    f"{homeserver_url}/_matrix/client/v3/directory/room/{full_alias}",
                    headers=headers,
                )
                if resp.status_code == 200:
                    room_id = resp.json().get("room_id")
                    rooms_created[full_alias] = room_id
                    logger.debug("Matrix: room %s already exists (%s)", full_alias, room_id)
                    continue
            except Exception:
                pass

            # Create room
            try:
                create_data = {
                    "room_alias_name": alias_local,
                    "name": room_name,
                    "topic": topic,
                    "visibility": "private",
                    "preset": "private_chat",
                    "initial_state": [
                        {
                            "type": "m.room.history_visibility",
                            "content": {"history_visibility": "shared"},
                        }
                    ],
                }

                resp = await client.post(
                    f"{homeserver_url}/_matrix/client/v3/createRoom",
                    headers=headers,
                    json=create_data,
                )

                if resp.status_code == 200:
                    room_id = resp.json()["room_id"]
                    rooms_created[full_alias] = room_id
                    logger.info("Matrix: created room %s (%s)", full_alias, room_id)
                else:
                    logger.warning(
                        "Matrix: failed to create room %s: %s",
                        full_alias, resp.text[:200],
                    )
            except Exception as e:
                logger.warning("Matrix: error creating room %s: %s", full_alias, e)

        # Invite all agents and have them join immediately
        for room_alias, room_id in rooms_created.items():
            for agent_id, matrix_id in agent_matrix_ids.items():
                agent_creds = get_agent_matrix_credentials(agent_id)
                if not agent_creds:
                    continue
                agent_headers = {"Authorization": f"Bearer {agent_creds['access_token']}"}

                try:
                    # Invite
                    await client.post(
                        f"{homeserver_url}/_matrix/client/v3/rooms/{room_id}/invite",
                        headers=headers,
                        json={"user_id": matrix_id},
                    )
                    # Join immediately using the agent's own token
                    await client.post(
                        f"{homeserver_url}/_matrix/client/v3/join/{room_id}",
                        headers=agent_headers,
                        json={},
                    )
                except Exception:
                    pass

    return rooms_created
