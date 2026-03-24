---
name: agent-creation
description: Create and configure new agents via the gateway API.
version: 3.0.0
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

# Agent Creation — Fast Path

**Target: 6 tool calls. Not 30. Every extra call wastes time and money.**

The server handles: role validation, owner profile seeding, model writing, auto-finalize, avatar emoji, permissions. You only do what the server can't.

If the user is vague, fill in sensible defaults. Ask at most ONE question, then build.

## Step 1: Look up the model ID (1 tool call)

```bash
curl -s http://localhost:8080/api/providers -H "Authorization: Bearer $(cat ~/.vulti/web_token)" | python3 -c "import json,sys; [print(m) for p in json.load(sys.stdin) if p.get('authenticated') for m in (p.get('models') or [])]"
```

Pick the model that matches what the user asked for. If they said "gemini flash" or "cheap", pick the cheapest. If they didn't specify, use `anthropic/claude-sonnet-4`. **Use the EXACT ID from this list. Do not guess.**

## Step 2: Create agent (1 tool call)

```bash
curl -s -X POST http://localhost:8080/api/agents \
  -H "Authorization: Bearer $(cat ~/.vulti/web_token)" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "AgentName",
    "model": "exact/model-id-from-step-1",
    "role": "SINGLE_WORD",
    "description": "One sentence about what this agent does"
  }'
```

**Role MUST be exactly one of:** assistant, engineer, researcher, analyst, writer, therapist, coach, creative, ops

The server automatically: sets status to active, seeds the owner profile, validates the role, writes the model to config, sets permissions to matrix, assigns an emoji avatar, registers the agent on Matrix and creates the owner DM room.

**Matrix onboarding runs in the background and takes 5-10 seconds.** Do NOT check for Matrix credentials immediately after creating the agent — they won't be there yet. Do NOT debug Matrix registration. Do NOT write Python scripts for Matrix. Do NOT curl port 6167. The server handles all of it. Just move on to writing SOUL.md, installing skills, creating cron/rules.

## Step 3: Write SOUL.md (1 tool call)

Use `write_file` to create `~/.vulti/agents/{id}/SOUL.md`.

**Requirements:**
- Start with `# AgentName`
- At least 4 sections: identity, responsibilities, reporting format, tone
- Only reference tools/skills the agent actually has
- 1000+ characters minimum

## Step 4: Install skills (1 tool call)

```bash
curl -s -X POST http://localhost:8080/api/agents/{id}/skills \
  -H "Authorization: Bearer $(cat ~/.vulti/web_token)" \
  -H "Content-Type: application/json" \
  -d '{"name": "skill-name"}'
```

Run once per skill. Available skills: research, productivity, software-development, creative, data-science, feeds, media, self-improvement, smart-home, system, domain, note-taking.

## Step 5: Cron jobs (1 tool call per job)

**IMPORTANT: Set agent_id to the NEW agent's ID so the job is created on the new agent, not on you.**

```
cronjob(action="create", name="Job name", prompt="What to do", schedule="0 */6 * * *", deliver="matrix", agent_id="{id}")
```

## Step 6: Rules (1 tool call per rule)

**IMPORTANT: Set agent_id to the NEW agent's ID.**

```
rule(action="create", condition="...", action_prompt="...", name="...", agent_id="{id}")
```

## That's it.

Do NOT:
- Run `execute_code` with Python scripts — use `terminal` with curl or `write_file`
- Write role.txt manually — the server handles it
- Write permissions.json manually — the server handles it
- Write config.yaml manually — the server handles it via the model field in Step 2
- Run a matrix registration script — the server does this automatically
- Run a verification checklist with 7 separate commands — just check `GET /api/agents/{id}` and confirm status=active

## Quick verify (1 tool call)

```bash
curl -s http://localhost:8080/api/agents/{id} -H "Authorization: Bearer $(cat ~/.vulti/web_token)"
```

Confirm: status=active, role is correct, model is set. Done.
