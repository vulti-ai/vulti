---
name: validate-connections
description: Validate all configured API keys and ensure each working connection has a matching skill installed.
version: 1.0.0
author: Vulti
license: MIT
triggers:
  - "check connections"
  - "validate keys"
  - "validate connections"
  - "test apis"
  - "check api keys"
metadata:
  vulti:
    tags: [connections, validation, health, system]
    category: system
---

# Validate Connections

Run this checklist for every connection. The goal: every API key works, every working connection has a skill, every agent that needs a connection has access.

**Target: 1 terminal call per key to test, 1 call to check skills. Keep it fast.**

## Step 1: Inventory keys

```bash
grep -v '^#' ~/.vulti/.env | grep -v '^$' | grep '=' | while IFS='=' read -r key value; do
  value=$(echo "$value" | xargs)
  if [ -n "$value" ]; then echo "SET   $key"; else echo "EMPTY $key"; fi
done
```

Skip system keys that don't need validation:
- `LLM_MODEL`, `VULTI_DEFAULT_MODEL`, `VULTI_DEFAULT_PROVIDER`
- `TERMINAL_*`, `BROWSER_SESSION_TIMEOUT`, `BROWSER_INACTIVITY_TIMEOUT`
- `*_DEBUG` flags
- `HERMES_*` config keys
- `MATRIX_*` (managed by the app)
- `TELEGRAM_*`, `SLACK_*`, `DISCORD_*` (platform tokens, not API keys)

Focus on service API keys: `*_API_KEY`, `*_KEY`, `*_TOKEN` (except platform tokens).

## Step 2: Test each key

For each key with a value, verify it works:

1. Identify the service from the key name (e.g. `FAL_KEY` → fal.ai)
2. Look up a lightweight read-only endpoint for that service — something like "list models", "get user", "get account status". If you don't know the endpoint, do a quick web search for "{service} API authentication test".
3. Hit the endpoint with curl. Check for 200 vs 401/403.

```bash
# Example pattern — adapt per service
curl -s -o /dev/null -w "%{http_code}" https://api.service.com/v1/me -H "Authorization: Bearer $KEY"
```

- **200-299**: Key is live ✔
- **401/403**: Key is dead or invalid ✘
- **Other**: Service may be down, note it

## Step 3: Check skill coverage

For each working connection, check if there's a matching skill:

```bash
curl -s http://localhost:8080/api/skills -H "Authorization: Bearer $(cat ~/.vulti/web_token)"
```

Cross-reference:
- Connection has a key ✔ + matching skill exists ✔ → fully covered
- Connection has a key ✔ + no matching skill → **gap** — agents can authenticate but don't know how to use the API
- Connection has no key → skip

Skills to look for per connection:
- `FAL_KEY` → look for a "fal-ai" or "image generation" skill
- `FIRECRAWL_API_KEY` → look for a "firecrawl" or "web scraping" skill
- `BLAND_API_KEY` → look for a "bland" or "voice/telephony" skill
- `ELEVENLABS_API_KEY` → look for a "speech" or "tts" skill
- Other keys → search by service name

## Step 4: Install missing skills

For each gap found in Step 3:

1. Check if the skill exists in the available skills list (`GET /api/skills`) but isn't installed for agents that need it
2. If it exists: install it via `POST /api/agents/{id}/skills` with `{"name": "skill-name"}`
3. If it doesn't exist: **create it.** Write a SKILL.md to `~/.vulti/skills/{skill-name}/SKILL.md` (flat top-level directory, NOT nested in a category). Then install it for the agents that need it.

**Skill directory layout is FLAT** — every skill is at `~/.vulti/skills/{name}/SKILL.md`. No category subdirectories for the install API.

## Step 5: Report

Output a summary table:

```
◆ Connection Validation Report

Key                    Status    Skill Coverage
─────────────────────  ────────  ──────────────
OPENROUTER_API_KEY     ✔ live    (system LLM — no skill needed)
FAL_KEY                ✔ live    ✘ no skill — agents can't use FAL API
FIRECRAWL_API_KEY      ✘ empty   —
BLAND_API_KEY          ✔ live    ✔ bland-ai skill installed
ELEVENLABS_API_KEY     ✘ empty   —

Gaps: 1 (FAL.ai — key works but no skill teaches agents how to use it)
```
