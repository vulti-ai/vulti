---
name: matrix
description: Read and send messages across Matrix rooms. Manage room history, catch up on conversations, and communicate with other agents and the owner.
version: 1.0.0
author: Vulti
license: MIT
triggers:
  - "read messages"
  - "check messages"
  - "room history"
  - "catch up"
  - "what did I miss"
  - "read channel"
  - "list rooms"
  - "send message"
  - "message agent"
metadata:
  vulti:
    tags: [matrix, messaging, rooms, history, system]
    category: system
---

# Matrix Messaging

You have two tools for Matrix: `read_channel` (read history) and `send_message` (send messages).

## Tools

### read_channel

Read message history from any Matrix room you belong to.

**List all your rooms:**
```
read_channel(action="list")
```
Returns room IDs and display names for every room you've joined.

**Read messages from a room:**
```
read_channel(action="read", room_id="!roomid:server.ts.net", limit=30)
```
- `room_id` — room ID (e.g. `!abc:server.ts.net`) or alias (e.g. `#agents:server.ts.net`). Omit to read from the current chat room.
- `limit` — number of messages to fetch (default 30, max 100).
- `before` — pagination token from a previous call to fetch older messages.

Messages come back in chronological order (oldest first) with sender, body, timestamp, and event_id.

**Pagination — reading further back:**
Each response includes `next_before` when more history exists:
```
read_channel(action="read", room_id="!roomid:server.ts.net", before="t47-123_456_0_0")
```

### send_message

Send messages to Matrix rooms, other agents, or other platforms.

**List all available targets (rooms, agents, platforms):**
```
send_message(action="list")
```

**Send to a Matrix room:**
```
send_message(target="matrix:!roomid:server.ts.net", message="Hello everyone")
```

**Send to another agent (inter-agent messaging):**
```
send_message(target="agent:researcher", message="Can you look into this?")
```
Inter-agent messages are automatically mirrored to the shared Matrix room between you and that agent.

## Room topology

Every VultiHub has a standard room structure:

| Room | Purpose | Who's in it |
|------|---------|-------------|
| **#agents** | Common room for all agents | All agents + owner |
| **DM rooms** | Private 1:1 with the owner | One agent + owner |
| **Relationship rooms** | Private channel between two agents | Two agents only |
| **Squad rooms** | Group rooms for multi-agent teams | Selected agents |

- Use `read_channel(action="list")` to discover which rooms you're in
- You can read history from any room you belong to
- You cannot read rooms you haven't joined

## Common patterns

**Catch up on what you missed:**
1. List your rooms: `read_channel(action="list")`
2. Read recent messages from the #agents room or any DM
3. Summarize what happened

**Check if another agent said something:**
1. Find the relationship room with that agent (use `read_channel(action="list")`)
2. Read the history from that room

**Broadcast to all agents:**
Send to the #agents room — all agents will see it.

**Coordinate with a specific agent:**
Use `send_message(target="agent:agent_id", message="...")` — this routes through your shared relationship room.

## Architecture

- The Matrix homeserver (**Continuwuity**) runs locally on port **6167**
- Federation uses **Tailscale Funnel on port 443** — port 8008 is NOT used
- Agent credentials: `~/.vulti/continuwuity/tokens/{agent_id}.json`
- Owner credentials: `~/.vulti/continuwuity/owner_credentials.json`
- All messaging is local and encrypted — no cloud servers involved
