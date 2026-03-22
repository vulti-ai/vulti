---
name: agent-creation
description: Create and configure new agents via the gateway API. Handles registry, SOUL.md, role.txt, Matrix onboarding, permissions, cron, and verification.
version: 2.0.0
author: Vulti
license: MIT
triggers:
  - "create agent"
  - "new agent"
  - "make an agent"
  - "set up an agent"
  - "add an agent"
metadata:
  vulti:
    tags: [agent, creation, setup, onboarding, system]
    category: system
---

# Agent Creation Procedure

Follow every step. Do not skip any. Verify at the end.

## Step 1: Create agent via API

```bash
curl -X POST http://localhost:8080/api/agents \
  -H "Authorization: Bearer $(cat ~/.vulti/web_token)" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "AgentName",
    "model": "anthropic/claude-sonnet-4",
    "role": "researcher",
    "personality": "Brief description of what this agent does"
  }'
```

Agent ID rules: lowercase, letters/numbers/hyphens, starts with letter, max 32 chars.

## Step 2: Write SOUL.md

Create `~/.vulti/agents/{id}/SOUL.md` with the agent's full personality, role, instructions, tone, and responsibilities.

## Step 3: Write role.txt

Create `~/.vulti/agents/{id}/role.txt` containing a SINGLE WORD — the agent's role. This file MUST exist.

```bash
echo -n "researcher" > ~/.vulti/agents/{id}/role.txt
```

Valid roles: assistant, engineer, researcher, analyst, writer, therapist, coach, creative, ops, wizard.

## Step 4: Matrix onboarding

```bash
curl -X POST http://localhost:8080/api/agents/{id}/onboard-to-matrix \
  -H "Authorization: Bearer $(cat ~/.vulti/web_token)"
```

This creates the agent's Matrix account and DM room with the owner. Without this, the agent cannot communicate.

## Step 5: Set permissions

Ensure `~/.vulti/agents/{id}/permissions.json` has `"allowed_connections": ["matrix"]`.

## Step 6: Set model in config.yaml

```bash
python3 -c "
import yaml
path = '$HOME/.vulti/agents/{id}/config.yaml'
with open(path) as f:
    cfg = yaml.safe_load(f) or {}
cfg['model'] = 'anthropic/claude-sonnet-4'
with open(path, 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False)
"
```

## Step 7: Finalize onboarding

```bash
curl -X POST http://localhost:8080/api/agents/{id}/finalize-onboarding \
  -H "Authorization: Bearer $(cat ~/.vulti/web_token)" \
  -H "Content-Type: application/json" \
  -d '{"role": "researcher"}'
```

This moves status from "onboarding" to "active". Agents stuck in "onboarding" have limited UI.

## Step 8: Add cron jobs (if needed)

```bash
curl -X POST http://localhost:8080/api/cron \
  -H "Authorization: Bearer $(cat ~/.vulti/web_token)" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "{id}",
    "name": "Daily task name",
    "prompt": "What the agent should do on schedule",
    "schedule": "0 9 * * *",
    "deliver": "matrix"
  }'
```

ALWAYS set `"deliver": "matrix"`. Never use "local".

## Verification checklist

Run this EVERY TIME after creating an agent. Do not report success until all checks pass.

```bash
AGENT_ID="{id}"
echo "=== Agent $AGENT_ID Checklist ==="

# 1. Registry — must be "active"
python3 -c "from vulti_cli.agent_registry import AgentRegistry; a=AgentRegistry().get_agent('$AGENT_ID'); print(f'1. Registry: {a.status}' if a else '1. Registry: MISSING')"

# 2. SOUL.md — must exist and not be empty
test -s ~/.vulti/agents/$AGENT_ID/SOUL.md && echo "2. SOUL.md: OK" || echo "2. SOUL.md: MISSING"

# 3. role.txt — must exist with a single word
test -s ~/.vulti/agents/$AGENT_ID/role.txt && echo "3. role.txt: $(cat ~/.vulti/agents/$AGENT_ID/role.txt)" || echo "3. role.txt: MISSING"

# 4. permissions.json — must have matrix
python3 -c "import json; d=json.load(open('$HOME/.vulti/agents/$AGENT_ID/permissions.json')); print('4. Matrix perm:', 'matrix' in d.get('allowed_connections',[]))"

# 5. Model — must be set
python3 -c "import yaml; c=yaml.safe_load(open('$HOME/.vulti/agents/$AGENT_ID/config.yaml')); print('5. Model:', c.get('model','NOT SET'))"

# 6. Matrix account — check credentials exist
test -f ~/.vulti/continuwuity/tokens/$AGENT_ID.json && echo "6. Matrix creds: OK" || echo "6. Matrix creds: MISSING"
```

If ANY check fails, fix it before telling the user the agent is ready.
