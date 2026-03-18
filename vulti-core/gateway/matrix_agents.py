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
    from vulti_cli.agent_registry import AgentRegistry

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


async def create_relationship_room(
    homeserver_url: str,
    server_name: str,
    agent_a_id: str,
    agent_b_id: str,
    agent_a_name: str = "",
    agent_b_name: str = "",
    purpose: str = "manages",
) -> Optional[str]:
    """Create a private channel for agents with a direct relationship.

    Room is named "{AgentA} & {AgentB} Channel". Owner is also invited.
    Returns the room_id on success, None on failure.
    """
    import httpx

    creds_a = get_agent_matrix_credentials(agent_a_id)
    creds_b = get_agent_matrix_credentials(agent_b_id)

    if not creds_a or not creds_b:
        logger.warning(
            "Matrix: cannot create relationship room — missing credentials for %s or %s",
            agent_a_id, agent_b_id,
        )
        return None

    headers_a = {"Authorization": f"Bearer {creds_a['access_token']}"}
    headers_b = {"Authorization": f"Bearer {creds_b['access_token']}"}

    name_a = agent_a_name or agent_a_id.capitalize()
    name_b = agent_b_name or agent_b_id.capitalize()
    room_name = f"{name_a} & {name_b} Channel"
    topic = f"Direct channel: {purpose}"

    invite_list = [creds_b["user_id"]]

    # Also invite owner
    owner_creds = _get_owner_matrix_credentials()
    if owner_creds:
        invite_list.append(owner_creds["user_id"])

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{homeserver_url}/_matrix/client/v3/createRoom",
                headers=headers_a,
                json={
                    "name": room_name,
                    "topic": topic,
                    "visibility": "private",
                    "preset": "private_chat",
                    "invite": invite_list,
                    "initial_state": [
                        {
                            "type": "m.room.history_visibility",
                            "content": {"history_visibility": "shared"},
                        }
                    ],
                },
            )

            if resp.status_code != 200:
                logger.warning(
                    "Matrix: failed to create relationship room: %s",
                    resp.text[:200],
                )
                return None

            room_id = resp.json()["room_id"]

            # Agent B joins
            await client.post(
                f"{homeserver_url}/_matrix/client/v3/join/{room_id}",
                headers=headers_b,
                json={},
            )

            # Owner joins
            if owner_creds:
                await client.post(
                    f"{homeserver_url}/_matrix/client/v3/join/{room_id}",
                    headers={"Authorization": f"Bearer {owner_creds['access_token']}"},
                    json={},
                )

            logger.info(
                "Matrix: created relationship channel %s for %s & %s (%s)",
                room_id, name_a, name_b, purpose,
            )
            return room_id

    except Exception as e:
        logger.error("Matrix: error creating relationship room: %s", e)
        return None


async def ensure_room_topology(
    homeserver_url: str,
    access_token: str,
    server_name: str,
    agent_matrix_ids: Dict[str, str],
) -> Dict[str, str]:
    """Create standard rooms for agent communication.

    Creates:
    - #chatter:{server_name} — Agent Chatter: casual, agents talk freely
    - #daily:{server_name} — VultiSquad Daily: formal daily updates from all agents
    - #coordination:{server_name} — Agent Coordination: human talking to all agents

    Returns dict mapping room alias -> room_id.
    """
    import httpx

    rooms_created = {}
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        for alias_local, room_name, topic in [
            ("chatter", "Agent Chatter", "Casual chat — agents talk freely, no restrictions"),
            ("daily", "VultiSquad Daily", "Formal daily updates from all agents"),
            ("coordination", "Agent Coordination", "Human talking to all agents at once"),
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


def _get_owner_matrix_credentials() -> Optional[Dict[str, Any]]:
    """Read stored Matrix credentials for the owner."""
    from gateway.continuwuity import _continuwuity_dir
    owner_creds_path = _continuwuity_dir() / "owner_credentials.json"
    if owner_creds_path.exists():
        try:
            return json.loads(owner_creds_path.read_text())
        except Exception as e:
            logger.warning("Failed to read owner Matrix credentials: %s", e)
    return None


async def create_owner_dm_room(
    homeserver_url: str,
    server_name: str,
    agent_id: str,
) -> Optional[str]:
    """Create a DM room between an agent and the owner.

    Returns the room_id on success, None on failure.
    """
    import httpx

    agent_creds = get_agent_matrix_credentials(agent_id)
    owner_creds = _get_owner_matrix_credentials()

    if not agent_creds:
        logger.warning("Matrix: cannot create owner DM — missing agent credentials for %s", agent_id)
        return None

    if not owner_creds:
        logger.warning("Matrix: cannot create owner DM — owner not registered on Matrix")
        return None

    agent_headers = {"Authorization": f"Bearer {agent_creds['access_token']}"}
    owner_headers = {"Authorization": f"Bearer {owner_creds['access_token']}"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{homeserver_url}/_matrix/client/v3/createRoom",
                headers=agent_headers,
                json={
                    "is_direct": True,
                    "visibility": "private",
                    "preset": "trusted_private_chat",
                    "invite": [owner_creds["user_id"]],
                    "initial_state": [
                        {
                            "type": "m.room.history_visibility",
                            "content": {"history_visibility": "shared"},
                        }
                    ],
                },
            )

            if resp.status_code != 200:
                logger.warning("Matrix: failed to create owner DM for %s: %s", agent_id, resp.text[:200])
                return None

            room_id = resp.json()["room_id"]

            # Owner auto-joins the DM
            await client.post(
                f"{homeserver_url}/_matrix/client/v3/join/{room_id}",
                headers=owner_headers,
                json={},
            )

            logger.info("Matrix: created owner DM %s for agent %s", room_id, agent_id)
            return room_id

    except Exception as e:
        logger.error("Matrix: error creating owner DM for %s: %s", agent_id, e)
        return None


async def send_room_message(
    homeserver_url: str,
    agent_id: str,
    room_id: str,
    body: str,
) -> bool:
    """Send a text message to a Matrix room as the given agent.

    Returns True on success.
    """
    import httpx
    import uuid

    creds = get_agent_matrix_credentials(agent_id)
    if not creds:
        return False

    headers = {"Authorization": f"Bearer {creds['access_token']}"}
    txn_id = str(uuid.uuid4())

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.put(
                f"{homeserver_url}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}",
                headers=headers,
                json={
                    "msgtype": "m.text",
                    "body": body,
                },
            )
            return resp.status_code == 200
    except Exception as e:
        logger.warning("Matrix: failed to send message for %s in %s: %s", agent_id, room_id, e)
        return False


async def create_squad_room(
    homeserver_url: str,
    server_name: str,
    agent_ids: List[str],
    squad_name: str,
    topic: str = "",
) -> Optional[str]:
    """Create a group room for a squad of agents.

    The first agent creates the room and invites the others.
    Returns the room_id on success, None on failure.
    """
    import httpx

    if len(agent_ids) < 2:
        logger.warning("Matrix: squad room needs at least 2 agents")
        return None

    all_creds = {}
    for aid in agent_ids:
        c = get_agent_matrix_credentials(aid)
        if not c:
            logger.warning("Matrix: missing credentials for %s, skipping squad room", aid)
            return None
        all_creds[aid] = c

    creator_id = agent_ids[0]
    creator_creds = all_creds[creator_id]
    creator_headers = {"Authorization": f"Bearer {creator_creds['access_token']}"}

    invite_ids = [all_creds[aid]["user_id"] for aid in agent_ids[1:]]

    # Also invite owner if registered
    owner_creds = _get_owner_matrix_credentials()
    if owner_creds:
        invite_ids.append(owner_creds["user_id"])

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{homeserver_url}/_matrix/client/v3/createRoom",
                headers=creator_headers,
                json={
                    "name": squad_name,
                    "topic": topic or f"Squad: {squad_name}",
                    "visibility": "private",
                    "preset": "private_chat",
                    "invite": invite_ids,
                    "initial_state": [
                        {
                            "type": "m.room.history_visibility",
                            "content": {"history_visibility": "shared"},
                        }
                    ],
                },
            )

            if resp.status_code != 200:
                logger.warning("Matrix: failed to create squad room '%s': %s", squad_name, resp.text[:200])
                return None

            room_id = resp.json()["room_id"]

            # All invited agents join immediately
            for aid in agent_ids[1:]:
                c = all_creds[aid]
                await client.post(
                    f"{homeserver_url}/_matrix/client/v3/join/{room_id}",
                    headers={"Authorization": f"Bearer {c['access_token']}"},
                    json={},
                )

            # Owner joins if registered
            if owner_creds:
                await client.post(
                    f"{homeserver_url}/_matrix/client/v3/join/{room_id}",
                    headers={"Authorization": f"Bearer {owner_creds['access_token']}"},
                    json={},
                )

            logger.info("Matrix: created squad room '%s' (%s) with %d agents", squad_name, room_id, len(agent_ids))
            return room_id

    except Exception as e:
        logger.error("Matrix: error creating squad room '%s': %s", squad_name, e)
        return None


async def add_agent_to_room(
    homeserver_url: str,
    agent_id: str,
    room_id: str,
    inviter_agent_id: Optional[str] = None,
) -> bool:
    """Add an agent to an existing Matrix room.

    If inviter_agent_id is given, that agent sends the invite.
    Otherwise the owner's credentials are used.
    Returns True on success.
    """
    import httpx

    agent_creds = get_agent_matrix_credentials(agent_id)
    if not agent_creds:
        logger.warning("Matrix: cannot add agent %s — no credentials", agent_id)
        return False

    # Determine who sends the invite
    if inviter_agent_id:
        inviter_creds = get_agent_matrix_credentials(inviter_agent_id)
    else:
        inviter_creds = _get_owner_matrix_credentials()

    if not inviter_creds:
        # Fall back: try any agent token from the tokens dir
        for f in _tokens_dir().iterdir():
            if f.suffix == ".json" and f.stem != agent_id:
                try:
                    inviter_creds = json.loads(f.read_text())
                    break
                except Exception:
                    pass

    if not inviter_creds:
        logger.warning("Matrix: no inviter credentials available to add %s to room", agent_id)
        return False

    inviter_headers = {"Authorization": f"Bearer {inviter_creds['access_token']}"}
    agent_headers = {"Authorization": f"Bearer {agent_creds['access_token']}"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Invite
            resp = await client.post(
                f"{homeserver_url}/_matrix/client/v3/rooms/{room_id}/invite",
                headers=inviter_headers,
                json={"user_id": agent_creds["user_id"]},
            )
            if resp.status_code not in (200, 403):  # 403 = already in room
                logger.warning("Matrix: invite failed for %s to %s: %s", agent_id, room_id, resp.status_code)
                return False

            # Join
            resp = await client.post(
                f"{homeserver_url}/_matrix/client/v3/join/{room_id}",
                headers=agent_headers,
                json={},
            )
            ok = resp.status_code == 200
            if ok:
                logger.info("Matrix: agent %s joined room %s", agent_id, room_id)
            return ok

    except Exception as e:
        logger.error("Matrix: error adding agent %s to room %s: %s", agent_id, room_id, e)
        return False


async def remove_agent_from_room(
    homeserver_url: str,
    agent_id: str,
    room_id: str,
) -> bool:
    """Remove an agent from a Matrix room (leave + forget).

    Returns True on success.
    """
    import httpx

    creds = get_agent_matrix_credentials(agent_id)
    if not creds:
        logger.warning("Matrix: cannot remove agent %s — no credentials", agent_id)
        return False

    headers = {"Authorization": f"Bearer {creds['access_token']}"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{homeserver_url}/_matrix/client/v3/rooms/{room_id}/leave",
                headers=headers,
                json={},
            )
            if resp.status_code not in (200, 403):
                logger.warning("Matrix: leave failed for %s from %s: %s", agent_id, room_id, resp.status_code)
                return False

            # Forget the room so it doesn't show up in sync
            await client.post(
                f"{homeserver_url}/_matrix/client/v3/rooms/{room_id}/forget",
                headers=headers,
                json={},
            )

            logger.info("Matrix: agent %s left room %s", agent_id, room_id)
            return True

    except Exception as e:
        logger.error("Matrix: error removing agent %s from room %s: %s", agent_id, room_id, e)
        return False


async def onboard_agent_to_matrix(
    homeserver_url: str,
    server_name: str,
    registration_token: str,
    agent_id: str,
    agent_name: str,
) -> Dict[str, Any]:
    """Full Matrix onboarding for a newly created agent.

    1. Register as Matrix user
    2. Join the 3 global rooms (chatter, daily, coordination)
    3. Say hi in Agent Chatter

    DMs with the owner are only created when the user explicitly creates
    a relationship between the owner and the agent.

    Returns dict with matrix_user_id.
    """
    result: Dict[str, Any] = {"matrix_user_id": None}

    # Step 1: Register
    matrix_user_id = await ensure_agent_matrix_user(
        agent_id=agent_id,
        agent_name=agent_name,
        homeserver_url=homeserver_url,
        server_name=server_name,
        registration_token=registration_token,
    )
    if not matrix_user_id:
        return result
    result["matrix_user_id"] = matrix_user_id

    import httpx

    # Step 2: Join all 3 global rooms (chatter, daily, coordination)
    chatter_room_id = None
    creds = get_agent_matrix_credentials(agent_id)
    if creds:
        agent_headers = {"Authorization": f"Bearer {creds['access_token']}"}
        inviter_creds = _get_owner_matrix_credentials()
        if not inviter_creds:
            for f in _tokens_dir().iterdir():
                if f.suffix == ".json" and f.stem != agent_id:
                    try:
                        inviter_creds = json.loads(f.read_text())
                        break
                    except Exception:
                        pass

        if inviter_creds:
            inviter_headers = {"Authorization": f"Bearer {inviter_creds['access_token']}"}
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    for room_alias in ["chatter", "daily", "coordination"]:
                        try:
                            resp = await client.get(
                                f"{homeserver_url}/_matrix/client/v3/directory/room/%23{room_alias}:{server_name}",
                            )
                            if resp.status_code == 200:
                                rid = resp.json().get("room_id")
                                if rid:
                                    await client.post(
                                        f"{homeserver_url}/_matrix/client/v3/rooms/{rid}/invite",
                                        headers=inviter_headers,
                                        json={"user_id": matrix_user_id},
                                    )
                                    await client.post(
                                        f"{homeserver_url}/_matrix/client/v3/join/{rid}",
                                        headers=agent_headers,
                                        json={},
                                    )
                                    if room_alias == "chatter":
                                        chatter_room_id = rid
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("Matrix: error joining global rooms for %s: %s", agent_id, e)

    # Step 3: Say hi in Agent Chatter
    if chatter_room_id:
        await send_room_message(
            homeserver_url=homeserver_url,
            agent_id=agent_id,
            room_id=chatter_room_id,
            body=f"Hey everyone, {agent_name} here. Just joined the squad!",
        )

    return result


async def create_owner_relationship(
    homeserver_url: str,
    server_name: str,
    agent_id: str,
    agent_name: str,
) -> Optional[str]:
    """Create a DM room between the owner and an agent.

    Called when the user explicitly creates a relationship with an agent.
    The agent sends a greeting in the DM.

    Returns dm_room_id or None.
    """
    dm_room_id = await create_owner_dm_room(
        homeserver_url=homeserver_url,
        server_name=server_name,
        agent_id=agent_id,
    )

    if dm_room_id:
        await send_room_message(
            homeserver_url=homeserver_url,
            agent_id=agent_id,
            room_id=dm_room_id,
            body=f"Hey! I'm {agent_name}, and I'm ready to go. What can I help you with?",
        )

    return dm_room_id
