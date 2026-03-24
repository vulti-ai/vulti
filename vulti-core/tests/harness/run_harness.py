#!/usr/bin/env python3
"""VultiHub E2E Harness — drive the full user journey, find bugs.

Usage:
    python tests/harness/run_harness.py --api-keys tests/harness/keys.json
    python tests/harness/run_harness.py --api-keys tests/harness/keys.json --seed=42
    python tests/harness/run_harness.py --api-keys tests/harness/keys.json --skip-to=create_agent
    python tests/harness/run_harness.py --api-keys tests/harness/keys.json --count=20

Steps:
  Phase A: Bootstrap (1-2)
  Phase B: Onboarding — identity, intelligence, providers, Hector (3-12)
  Phase C: Create agent — manual or via Hector chat (13-14)
  Phase D: Chat with agent — real AI conversations (15-16)
  Phase E: Configure — soul, cron, rules via chat (17)
  Phase F: Agent profile — update name/role/description/model (18)
  Phase G: Skills — install/verify/remove (19)
  Phase H: Connections — list/add/verify (20)
  Phase I: Wallet & vault — save/fetch credit card, check vault (21)
  Phase J: Avatar — generate agent + owner avatar (22)
  Phase K: Relationships — create agent-to-agent link (23)
  Phase L: Pane widgets — fetch/verify defaults (24)
  Phase M: Analytics & audit — fetch and verify data (25)
  Phase N: Integrations, permissions, contacts, inbox (26)
  Phase O: Final verify & cleanup (27)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from personas import Persona, generate_persona

# ── Constants ──

TOTAL_STEPS = 27

SKIP_POINTS = {
    "health_check": 1,
    "bootstrap": 2,
    "set_owner": 3,
    "add_ai_key": 6,
    "activate_hector": 11,
    "create_agent": 13,
    "chat": 15,
    "configure": 17,
    "profile": 18,
    "skills": 19,
    "connections": 20,
    "wallet": 21,
    "avatar": 22,
    "relationships": 23,
    "widgets": 24,
    "analytics": 25,
    "integrations": 26,
    "verify": 27,
}

# ── Step runner ──


class StepError(Exception):
    def __init__(self, method: str = "", path: str = "", status: int = 0, body: str = "", cause: str = ""):
        self.method = method
        self.path = path
        self.status = status
        self.body = body
        self.cause = cause
        parts = []
        if method and path:
            parts.append(f"{method} {path} → {status}")
        if body:
            display = body[:500] + ("..." if len(body) > 500 else "")
            parts.append(display)
        if cause:
            parts.append(cause)
        super().__init__("\n         ".join(parts))


def _check(r: httpx.Response) -> dict | list | str:
    if r.status_code >= 400:
        raise StepError(method=r.request.method, path=str(r.request.url.path), status=r.status_code, body=r.text[:1000])
    try:
        return r.json()
    except Exception:
        return r.text


def _soft_check(r: httpx.Response, label: str = "") -> dict | list | str | None:
    """Like _check but returns None instead of raising on error. Prints warning."""
    if r.status_code >= 400:
        print(f"         ({label or r.request.url.path}: {r.status_code}, continuing)")
        return None
    try:
        return r.json()
    except Exception:
        return r.text


class Harness:
    def __init__(self, persona: Persona, base: str, skip_to: int = 0):
        self.p = persona
        self.base = base
        self.skip_to = skip_to
        self.step_n = 0
        self.token: str = ""
        self.agent_id: str = ""
        self.agent2_id: str = ""  # second agent for relationships
        self.session_id: str = ""
        self.audit_issues: list[str] = []  # accumulated across all steps
        self._start_time = time.monotonic()

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def step(self, name: str, coro):
        self.step_n += 1
        if self.step_n < self.skip_to:
            print(f"[{self.step_n:02d}/{TOTAL_STEPS:02d}] {name:.<50s} SKIP")
            return None
        t0 = time.monotonic()
        try:
            result = await coro
            ms = (time.monotonic() - t0) * 1000
            print(f"[{self.step_n:02d}/{TOTAL_STEPS:02d}] {name:.<50s} PASS ({ms:.0f}ms)")
            return result
        except StepError:
            ms = (time.monotonic() - t0) * 1000
            print(f"[{self.step_n:02d}/{TOTAL_STEPS:02d}] {name:.<50s} FAIL ({ms:.0f}ms)")
            traceback.print_exc()
            print(f"         ─── STOPPING. Fix and re-run. ───")
            sys.exit(1)
        except Exception as e:
            ms = (time.monotonic() - t0) * 1000
            print(f"[{self.step_n:02d}/{TOTAL_STEPS:02d}] {name:.<50s} FAIL ({ms:.0f}ms)")
            print(f"         {type(e).__name__}: {e}")
            traceback.print_exc()
            print(f"         ─── STOPPING. Fix and re-run. ───")
            sys.exit(1)

    # ═══════════════════════════════════════════════════
    # Phase A: Bootstrap
    # ═══════════════════════════════════════════════════

    async def health_check(self, http: httpx.AsyncClient):
        r = await http.get(f"{self.base}/api/status", headers=self._headers())
        data = _check(r)
        state = data.get("gateway_state", "?") if isinstance(data, dict) else "?"
        print(f"         (gateway: {state})")
        return data

    async def bootstrap(self, http: httpx.AsyncClient):
        r = await http.get(f"{self.base}/api/bootstrap", headers=self._headers())
        data = _check(r)
        token = data.get("token") if isinstance(data, dict) else None
        if not token:
            raise StepError(cause=f"No token in response: {data}")
        self.token = token
        return token

    # ═══════════════════════════════════════════════════
    # Phase B: Onboarding
    # ═══════════════════════════════════════════════════

    async def set_owner(self, http: httpx.AsyncClient):
        r = await http.put(f"{self.base}/api/owner", json={"name": self.p.owner.name, "about": self.p.owner.about}, headers=self._headers())
        return _check(r)

    async def verify_owner(self, http: httpx.AsyncClient):
        r = await http.get(f"{self.base}/api/owner", headers=self._headers())
        data = _check(r)
        got_name = data.get("name", "") if isinstance(data, dict) else ""
        if got_name != self.p.owner.name:
            raise StepError(cause=f"Owner name mismatch: expected '{self.p.owner.name}', got '{got_name}'")
        return data

    async def matrix_register(self, http: httpx.AsyncClient):
        r = await http.post(f"{self.base}/api/matrix/register", json={"username": self.p.owner.username, "password": self.p.owner.password}, headers=self._headers())
        if r.status_code == 409:
            print(f"         (owner already registered, OK)")
            return {"already_exists": True}
        if r.status_code >= 500:
            print(f"         (Matrix not available — {r.status_code}, continuing)")
            return {"skipped": True}
        return _check(r)

    async def add_ai_key(self, http: httpx.AsyncClient):
        if not self.p.ai_key_name or not self.p.ai_key_value:
            raise StepError(cause="No AI provider key in keys.json")
        r = await http.post(f"{self.base}/api/secrets", json={"key": self.p.ai_key_name, "value": self.p.ai_key_value}, headers=self._headers())
        return _check(r)

    async def verify_secrets(self, http: httpx.AsyncClient):
        r = await http.get(f"{self.base}/api/secrets", headers=self._headers())
        data = _check(r)
        found = any(s.get("key") == self.p.ai_key_name and s.get("is_set") for s in (data if isinstance(data, list) else []))
        if not found:
            raise StepError(cause=f"Key '{self.p.ai_key_name}' not set")
        return data

    async def list_providers(self, http: httpx.AsyncClient):
        r = await http.get(f"{self.base}/api/providers", headers=self._headers())
        data = _check(r)
        authenticated = [p for p in (data if isinstance(data, list) else []) if p.get("authenticated")]
        if not authenticated:
            raise StepError(cause=f"No authenticated providers")
        print(f"         ({len(authenticated)} provider(s): {[p.get('name') for p in authenticated]})")
        return data

    async def set_default_model(self, http: httpx.AsyncClient):
        r = await http.post(f"{self.base}/api/secrets", json={"key": "VULTI_DEFAULT_MODEL", "value": self.p.default_model}, headers=self._headers())
        return _check(r)

    async def add_optional_keys(self, http: httpx.AsyncClient):
        added = []
        for key, value in self.p.optional_keys.items():
            r = await http.post(f"{self.base}/api/secrets", json={"key": key, "value": value}, headers=self._headers())
            _check(r)
            added.append(key)
        print(f"         ({len(added)} optional key(s): {added})" if added else "         (no optional keys)")
        return added

    async def activate_hector(self, http: httpx.AsyncClient):
        r = await http.put(f"{self.base}/api/agents/hector", json={"allowedConnections": "matrix"}, headers=self._headers())
        _check(r)
        # Matrix skill (may not exist)
        r = await http.post(f"{self.base}/api/agents/hector/skills", json={"name": "matrix"}, headers=self._headers())
        if r.status_code >= 400:
            print(f"         (matrix skill — {r.status_code}, OK)")
        # Matrix onboard (may fail)
        r = await http.post(f"{self.base}/api/matrix/onboard-agent", json={"agent_id": "hector"}, headers=self._headers())
        if r.status_code >= 400:
            print(f"         (Matrix onboard — {r.status_code}, OK)")
        # Finalize
        r = await http.post(f"{self.base}/api/agents/hector/finalize-onboarding", json={"role": "wizard"}, headers=self._headers())
        return _check(r)

    async def verify_hector(self, http: httpx.AsyncClient):
        r = await http.get(f"{self.base}/api/agents/hector", headers=self._headers())
        data = _check(r)
        status = data.get("status", "") if isinstance(data, dict) else ""
        print(f"         (status: {status})")
        return data

    # ═══════════════════════════════════════════════════
    # Phase C: Create Agent via Hector (the intended flow)
    # ═══════════════════════════════════════════════════

    VALID_ROLES = {"assistant", "engineer", "researcher", "analyst", "writer", "therapist", "coach", "creative", "ops", "wizard"}

    async def create_agent(self, http: httpx.AsyncClient):
        """Ask Hector to create an agent, then audit the result."""
        # First ensure we have a session with Hector
        r = await http.post(f"{self.base}/api/agents/hector/sessions", json={"name": f"Agent creation (seed={self.p.seed})"}, headers=self._headers())
        data = _check(r)
        hector_session = data.get("id") if isinstance(data, dict) else None
        if not hector_session:
            raise StepError(cause=f"No Hector session: {data}")

        # Store original session_id and use Hector's
        orig_session = self.session_id
        orig_agent = self.agent_id
        self.session_id = hector_session
        self.agent_id = "hector"

        # Snapshot current agents so we can find the new one after
        r = await http.get(f"{self.base}/api/agents", headers=self._headers())
        before_agents = {a.get("id") for a in (_check(r) if isinstance(_check(r), list) else [])}
        # Re-fetch since _check consumed it
        r = await http.get(f"{self.base}/api/agents", headers=self._headers())
        before_ids = {a.get("id") for a in (r.json() if r.status_code == 200 and isinstance(r.json(), list) else [])}

        # Ask Hector to create the agent using the persona's natural-language style
        create_msg = self.p.hector_create_msg
        print(f"         → [{self.p.user_style}] \"{create_msg[:100]}{'...' if len(create_msg) > 100 else ''}\"")
        print(f"         (expecting: name={self.p.agent.name}, role={self.p.agent.role})")
        frames = await self._ws_send(create_msg, timeout=180)
        response = self._last_response(frames)
        print(f"         ← \"{response[:120]}{'...' if len(response) > 120 else ''}\"")

        # Restore session state
        self.session_id = orig_session

        # Find the created agent — try exact name, partial match, or most recently created
        r = await http.get(f"{self.base}/api/agents", headers=self._headers())
        agents = _check(r)
        agent_list = agents if isinstance(agents, list) else []
        new_agent = None

        # Exact name match
        for a in agent_list:
            if a.get("name") == self.p.agent.name or a.get("id") == self.p.agent.name.lower().replace(" ", "-"):
                new_agent = a
                break

        # Partial match
        if not new_agent:
            name_lower = self.p.agent.name.lower()
            for a in agent_list:
                if name_lower in (a.get("name", "").lower()) and a.get("id") != "hector":
                    new_agent = a
                    break

        # Fallback: find NEW agent (not in before_ids)
        if not new_agent:
            new_ids = [a for a in agent_list if a.get("id") not in before_ids]
            if new_ids:
                new_agent = new_ids[0]
                print(f"         ⚠ Hector used different name: expected '{self.p.agent.name}', got '{new_agent.get('name')}'")
                self.audit_issues.append(f"NAME MISMATCH: asked for '{self.p.agent.name}', Hector created '{new_agent.get('name')}'")

        if not new_agent:
            agent_names = [a.get("name") for a in agent_list]
            raise StepError(cause=f"Hector did not create any new agent. Before: {before_ids}, After: {agent_names}")

        self.agent_id = new_agent["id"]
        print(f"         (created: id={self.agent_id}, status={new_agent.get('status')})")
        return new_agent

    async def verify_agent(self, http: httpx.AsyncClient):
        """Deep audit of agent against the agent-creation spec."""
        if not self.agent_id:
            raise StepError(cause="No agent_id to verify")

        issues = []

        # 1. Registry check — status should be "active"
        r = await http.get(f"{self.base}/api/agents/{self.agent_id}", headers=self._headers())
        data = _check(r)
        status = data.get("status", "") if isinstance(data, dict) else ""
        name = data.get("name", "?") if isinstance(data, dict) else "?"
        role_api = data.get("role", "") if isinstance(data, dict) else ""

        if status != "active":
            issues.append(f"STATUS: '{status}' (expected 'active')")
        print(f"         1. Registry: {name} status={status}")

        # 2. Role check — must be single word from valid set
        if role_api:
            role_words = role_api.strip().split()
            if len(role_words) != 1:
                issues.append(f"ROLE: '{role_api}' is {len(role_words)} words (must be 1)")
            elif role_api.strip().lower() not in self.VALID_ROLES:
                issues.append(f"ROLE: '{role_api}' not in valid roles: {self.VALID_ROLES}")
            print(f"         2. Role: '{role_api}' {'✓' if not any('ROLE' in i for i in issues) else '✗'}")
        else:
            issues.append("ROLE: empty/missing in API response")
            print(f"         2. Role: MISSING ✗")

        # 3. SOUL.md — check via API
        r = await http.get(f"{self.base}/api/agents/{self.agent_id}/soul", headers=self._headers())
        soul = _soft_check(r, "soul")
        soul_content = soul.get("content", "") if isinstance(soul, dict) else ""
        if not soul_content or len(soul_content.strip()) < 20:
            issues.append(f"SOUL.md: empty or too short ({len(soul_content)} chars)")
            print(f"         3. SOUL.md: EMPTY/SHORT ({len(soul_content)} chars) ✗")
        else:
            print(f"         3. SOUL.md: {len(soul_content)} chars ✓")

        # 4. Config — model should be set
        r = await http.get(f"{self.base}/api/agents/{self.agent_id}/config", headers=self._headers())
        config = _soft_check(r, "config")
        model = ""
        if isinstance(config, dict):
            model = config.get("model", "")
        if not model:
            issues.append("MODEL: not set in config.yaml")
            print(f"         4. Model: NOT SET ✗")
        else:
            print(f"         4. Model: {model} ✓")

        # 5. Memories — should have user profile
        r = await http.get(f"{self.base}/api/agents/{self.agent_id}/memories", headers=self._headers())
        memories = _soft_check(r, "memories")
        mem_content = memories.get("memory", "") if isinstance(memories, dict) else ""
        user_content = memories.get("user", "") if isinstance(memories, dict) else ""
        print(f"         5. Memory: {len(mem_content)} chars, User: {len(user_content)} chars")

        # 6. Skills — should have at least something
        r = await http.get(f"{self.base}/api/agents/{self.agent_id}/skills", headers=self._headers())
        skills = _soft_check(r, "skills")
        n_skills = len(skills) if isinstance(skills, list) else 0
        print(f"         6. Skills: {n_skills} installed")

        # 7. Data trail — does the owner info flow through?
        # Check if SOUL.md or memories reference the owner
        owner_name = self.p.owner.name.split()[0].lower()  # first name
        owner_about_fragment = self.p.owner.about[:30].lower()
        soul_lower = soul_content.lower() if soul_content else ""
        user_lower = user_content.lower() if user_content else ""
        data_trail_found = owner_name in soul_lower or owner_name in user_lower or owner_about_fragment in user_lower
        if data_trail_found:
            print(f"         7. Data trail: owner info found in agent context ✓")
        else:
            print(f"         7. Data trail: owner '{self.p.owner.name}' NOT found in soul/memory")
            # Not a hard failure — just notable

        # Report
        if issues:
            print(f"\n         ╔══ AGENT AUDIT ISSUES ({len(issues)}) ══")
            for issue in issues:
                print(f"         ║  ✗ {issue}")
            print(f"         ╚{'═' * 40}")
            self.audit_issues.extend(issues)
            # Don't raise — report but continue so we find ALL issues
            print(f"         (continuing despite {len(issues)} issue(s))")
        else:
            print(f"         ✓ All audit checks passed")

        return {"issues": issues, "data": data}

    # ═══════════════════════════════════════════════════
    # Phase D: Chat with agent (real AI via WebSocket)
    # ═══════════════════════════════════════════════════

    async def chat_with_agent(self, http: httpx.AsyncClient):
        if not self.agent_id:
            raise StepError(cause="No agent_id")
        r = await http.post(f"{self.base}/api/agents/{self.agent_id}/sessions", json={"name": f"Harness (seed={self.p.seed})"}, headers=self._headers())
        data = _check(r)
        self.session_id = data.get("id") if isinstance(data, dict) else None
        if not self.session_id:
            raise StepError(cause=f"No session_id: {data}")
        print(f"         (session: {self.session_id})")

        for i, message in enumerate(self.p.agent.conversation):
            print(f"         → [{i+1}/{len(self.p.agent.conversation)}] \"{message[:60]}{'...' if len(message) > 60 else ''}\"")
            frames = await self._ws_send(message, timeout=90)
            last = self._last_response(frames)
            print(f"         ← \"{last[:80]}{'...' if len(last) > 80 else ''}\"")
            if i < len(self.p.agent.conversation) - 1:
                await asyncio.sleep(1)
        return True

    async def verify_history(self, http: httpx.AsyncClient):
        if not self.session_id:
            raise StepError(cause="No session_id")
        r = await http.get(f"{self.base}/api/sessions/{self.session_id}/history", headers=self._headers())
        data = _check(r)
        msgs = data if isinstance(data, list) else []
        n_user = sum(1 for m in msgs if m.get("role") == "user")
        n_asst = sum(1 for m in msgs if m.get("role") == "assistant")
        print(f"         ({len(msgs)} messages: {n_user} user, {n_asst} assistant)")
        if n_user < len(self.p.agent.conversation):
            raise StepError(cause=f"Expected >= {len(self.p.agent.conversation)} user msgs, got {n_user}")
        return data

    # ═══════════════════════════════════════════════════
    # Phase E: Configure — soul, cron, rules (via chat)
    # ═══════════════════════════════════════════════════

    async def configure(self, http: httpx.AsyncClient):
        if not self.agent_id:
            raise StepError(cause="No agent_id")

        # Soul via REST
        r = await http.put(f"{self.base}/api/agents/{self.agent_id}/soul", json={"content": self.p.agent.personality}, headers=self._headers())
        _check(r)
        print(f"         (soul updated)")

        # Verify soul
        r = await http.get(f"{self.base}/api/agents/{self.agent_id}/soul", headers=self._headers())
        soul = _check(r)
        if isinstance(soul, dict) and not soul.get("content"):
            raise StepError(cause="Soul empty after update")

        # Update memory
        r = await http.put(f"{self.base}/api/agents/{self.agent_id}/memories", json={"file": "user", "content": f"# User\nName: {self.p.owner.name}\nAbout: {self.p.owner.about}"}, headers=self._headers())
        _check(r)
        print(f"         (memory updated)")

        # Ensure session
        if not self.session_id:
            r = await http.post(f"{self.base}/api/agents/{self.agent_id}/sessions", json={"name": "Config"}, headers=self._headers())
            data = _check(r)
            self.session_id = data.get("id") if isinstance(data, dict) else None

        # Cron via chat
        cron = self.p.cron
        print(f"         → cron: \"{cron['name']}\"")
        frames = await self._ws_send(f"Create a cron job named \"{cron['name']}\" with schedule \"{cron['schedule']}\" and prompt \"{cron['prompt']}\"", timeout=90)
        print(f"         ← \"{self._last_response(frames)[:80]}...\"")

        # Rule via chat
        rule = self.p.rule
        print(f"         → rule: \"{rule['name']}\"")
        frames = await self._ws_send(f"Create a rule named \"{rule['name']}\" with condition \"{rule['condition']}\" and action \"{rule['action']}\"", timeout=90)
        print(f"         ← \"{self._last_response(frames)[:80]}...\"")

        # Verify
        r = await http.get(f"{self.base}/api/agents/{self.agent_id}/cron", headers=self._headers())
        crons = _check(r)
        r = await http.get(f"{self.base}/api/agents/{self.agent_id}/rules", headers=self._headers())
        rules = _check(r)
        nc = len(crons) if isinstance(crons, list) else 0
        nr = len(rules) if isinstance(rules, list) else 0
        print(f"         ({nc} cron, {nr} rules)")
        return True

    # ═══════════════════════════════════════════════════
    # Phase F: Agent profile — update name, role, description, model
    # ═══════════════════════════════════════════════════

    async def update_agent_profile(self, http: httpx.AsyncClient):
        if not self.agent_id:
            raise StepError(cause="No agent_id")

        # Update role
        r = await http.put(f"{self.base}/api/agents/{self.agent_id}", json={"role": self.p.agent.role}, headers=self._headers())
        _check(r)
        print(f"         (role → {self.p.agent.role})")

        # Update description
        desc = f"Harness-tested {self.p.agent.role} agent (seed={self.p.seed})"
        r = await http.put(f"{self.base}/api/agents/{self.agent_id}", json={"description": desc}, headers=self._headers())
        _check(r)
        print(f"         (description updated)")

        # Get agent config
        r = await http.get(f"{self.base}/api/agents/{self.agent_id}/config", headers=self._headers())
        config = _soft_check(r, "agent config")
        if config:
            print(f"         (config keys: {list(config.keys()) if isinstance(config, dict) else '?'})")

        # Verify updates
        r = await http.get(f"{self.base}/api/agents/{self.agent_id}", headers=self._headers())
        data = _check(r)
        if isinstance(data, dict):
            if data.get("role") != self.p.agent.role:
                raise StepError(cause=f"Role mismatch: {data.get('role')} != {self.p.agent.role}")
        return data

    # ═══════════════════════════════════════════════════
    # Phase G: Skills — install, verify, list, remove
    # ═══════════════════════════════════════════════════

    async def manage_skills(self, http: httpx.AsyncClient):
        if not self.agent_id:
            raise StepError(cause="No agent_id")

        # List available
        r = await http.get(f"{self.base}/api/skills", headers=self._headers())
        available = _check(r)
        n_avail = len(available) if isinstance(available, list) else 0
        print(f"         ({n_avail} available skills)")

        # List installed
        r = await http.get(f"{self.base}/api/agents/{self.agent_id}/skills", headers=self._headers())
        installed = _check(r)
        installed_names = [s.get("name") for s in (installed if isinstance(installed, list) else [])]
        print(f"         (installed: {installed_names})")

        # Install a new skill (pick one not already installed)
        available_names = [s.get("name") for s in (available if isinstance(available, list) else [])]
        to_install = None
        for skill in ["research", "productivity", "software-development", "creative"]:
            if skill in available_names and skill not in installed_names:
                to_install = skill
                break

        if to_install:
            r = await http.post(f"{self.base}/api/agents/{self.agent_id}/skills", json={"name": to_install}, headers=self._headers())
            result = _soft_check(r, f"install {to_install}")
            if result:
                print(f"         (installed: {to_install})")
                # Remove it to clean up
                r = await http.delete(f"{self.base}/api/agents/{self.agent_id}/skills/{to_install}", headers=self._headers())
                _soft_check(r, f"remove {to_install}")
                print(f"         (removed: {to_install})")
        else:
            print(f"         (no new skill to install)")

        return True

    # ═══════════════════════════════════════════════════
    # Phase H: Connections — list, add, verify, delete
    # ═══════════════════════════════════════════════════

    async def manage_connections(self, http: httpx.AsyncClient):
        # List
        r = await http.get(f"{self.base}/api/connections", headers=self._headers())
        conns = _check(r)
        n = len(conns) if isinstance(conns, list) else 0
        print(f"         ({n} existing connection(s))")

        # Add a test connection
        r = await http.post(f"{self.base}/api/connections", json={
            "name": "harness-test-conn",
            "type": "api_key",
            "description": "Temporary test connection from harness",
            "tags": ["test", "harness"],
        }, headers=self._headers())
        result = _soft_check(r, "add connection")
        if result:
            print(f"         (added: harness-test-conn)")

            # Verify
            r = await http.get(f"{self.base}/api/connections", headers=self._headers())
            conns2 = _check(r)
            found = any(c.get("name") == "harness-test-conn" for c in (conns2 if isinstance(conns2, list) else []))
            if found:
                print(f"         (verified in list)")
            else:
                print(f"         (WARNING: not found in list after add)")

            # Delete
            r = await http.delete(f"{self.base}/api/connections/harness-test-conn", headers=self._headers())
            _soft_check(r, "delete connection")
            print(f"         (deleted: harness-test-conn)")

        return True

    # ═══════════════════════════════════════════════════
    # Phase I: Wallet & Vault
    # ═══════════════════════════════════════════════════

    async def wallet_and_vault(self, http: httpx.AsyncClient):
        if not self.agent_id:
            raise StepError(cause="No agent_id")

        # Save wallet (credit card)
        card_data = {
            "credit_card": {
                "number": "4111111111111111",
                "expiry": "12/28",
                "cardholder_name": self.p.owner.name,
                "cvv": "123",
            }
        }
        r = await http.put(f"{self.base}/api/agents/{self.agent_id}/wallet", json=card_data, headers=self._headers())
        result = _soft_check(r, "save wallet")
        if result:
            print(f"         (wallet saved)")

        # Read wallet back
        r = await http.get(f"{self.base}/api/agents/{self.agent_id}/wallet", headers=self._headers())
        wallet = _soft_check(r, "get wallet")
        if wallet and isinstance(wallet, dict):
            print(f"         (wallet keys: {list(wallet.keys())})")

        # Check vault (may not be configured)
        r = await http.get(f"{self.base}/api/agents/{self.agent_id}/vault", headers=self._headers())
        vault = _soft_check(r, "get vault")
        if vault and isinstance(vault, dict):
            vid = vault.get("vault_id", vault.get("name", "none"))
            print(f"         (vault: {vid})")
        else:
            print(f"         (no vault configured)")

        return True

    # ═══════════════════════════════════════════════════
    # Phase J: Avatar generation
    # ═══════════════════════════════════════════════════

    async def generate_avatars(self, http: httpx.AsyncClient):
        if not self.agent_id:
            raise StepError(cause="No agent_id")

        # Generate agent avatar — uses flux/schnell (~2-5s) or emoji fallback
        r = await http.post(f"{self.base}/api/agents/{self.agent_id}/generate-avatar", json={}, headers=self._headers(), timeout=30)
        result = _soft_check(r, "agent avatar")
        if result and isinstance(result, dict):
            ok = result.get("ok", False)
            fallback = result.get("fallback", "")
            path = result.get("path", "")
            print(f"         (agent avatar: ok={ok}{f', fallback={fallback}' if fallback else ''}{f', path={path}' if path else ''})")
            if not ok:
                self.audit_issues.append(f"AVATAR: agent generate failed: {result}")

        # Verify avatar is retrievable
        r = await http.get(f"{self.base}/api/agents/{self.agent_id}/avatar", headers=self._headers())
        avatar = _soft_check(r, "get avatar")
        if avatar and isinstance(avatar, dict):
            has_img = bool(avatar.get("avatar"))
            print(f"         (has avatar: {has_img})")

        # Generate owner avatar
        r = await http.post(f"{self.base}/api/owner/generate-avatar", json={}, headers=self._headers(), timeout=30)
        result = _soft_check(r, "owner avatar")
        if result and isinstance(result, dict):
            print(f"         (owner avatar: ok={result.get('ok', '?')})")

        return True

    # ═══════════════════════════════════════════════════
    # Phase K: Relationships — create agent-to-agent
    # ═══════════════════════════════════════════════════

    async def manage_relationships(self, http: httpx.AsyncClient):
        if not self.agent_id:
            raise StepError(cause="No agent_id")

        # Create a second agent for relationship
        r = await http.post(f"{self.base}/api/agents", json={
            "name": f"{self.p.agent.name}-helper",
            "model": self.p.agent.model,
            "role": "assistant",
        }, headers=self._headers())
        data = _check(r)
        self.agent2_id = data.get("id", "")
        print(f"         (created helper agent: {self.agent2_id})")

        # Create relationship
        r = await http.post(f"{self.base}/api/relationships", json={
            "from_agent_id": self.agent_id,
            "to_agent_id": self.agent2_id,
            "type": "manages",
        }, headers=self._headers())
        rel = _soft_check(r, "create relationship")
        if rel:
            rel_id = rel.get("id", "?") if isinstance(rel, dict) else "?"
            print(f"         (relationship: {self.agent_id} → {self.agent2_id}, id={rel_id})")

        # List relationships
        r = await http.get(f"{self.base}/api/relationships", headers=self._headers())
        rels = _check(r)
        n = len(rels) if isinstance(rels, list) else 0
        print(f"         ({n} relationship(s))")

        # Cleanup: delete relationship and helper agent
        if rel and isinstance(rel, dict) and rel.get("id"):
            r = await http.delete(f"{self.base}/api/relationships/{rel['id']}", headers=self._headers())
            _soft_check(r, "delete relationship")

        if self.agent2_id:
            r = await http.delete(f"{self.base}/api/agents/{self.agent2_id}", headers=self._headers())
            _soft_check(r, "delete helper agent")
            print(f"         (cleaned up helper agent)")

        return True

    # ═══════════════════════════════════════════════════
    # Phase L: Pane widgets
    # ═══════════════════════════════════════════════════

    async def check_pane_widgets(self, http: httpx.AsyncClient):
        if not self.agent_id:
            raise StepError(cause="No agent_id")

        # Get pane widgets
        r = await http.get(f"{self.base}/api/agents/{self.agent_id}/pane", headers=self._headers())
        pane = _soft_check(r, "pane widgets")
        if pane and isinstance(pane, dict):
            tabs = pane.get("tabs", {})
            home = tabs.get("home", [])
            print(f"         (tabs: {list(tabs.keys())}, home widgets: {len(home)})")
            for w in home[:5]:
                print(f"           • {w.get('id', '?')}: {w.get('type', '?')} — {w.get('title', '?')}")
            if len(home) > 5:
                print(f"           ... and {len(home) - 5} more")
        else:
            print(f"         (no pane data)")

        # Get session pane if we have one
        if self.session_id:
            r = await http.get(f"{self.base}/api/sessions/{self.session_id}/pane", headers=self._headers())
            spane = _soft_check(r, "session pane")
            if spane and isinstance(spane, dict):
                stabs = spane.get("tabs", {})
                print(f"         (session pane tabs: {list(stabs.keys())})")

        return True

    # ═══════════════════════════════════════════════════
    # Phase M: Analytics & Audit
    # ═══════════════════════════════════════════════════

    async def check_analytics(self, http: httpx.AsyncClient):
        # Analytics
        r = await http.get(f"{self.base}/api/analytics?days=30", headers=self._headers())
        analytics = _soft_check(r, "analytics")
        if analytics and isinstance(analytics, dict):
            overview = analytics.get("overview", {})
            sessions = overview.get("total_sessions", 0)
            tokens = overview.get("total_tokens", 0)
            cost = overview.get("estimated_cost", 0)
            models = analytics.get("models", [])
            print(f"         (sessions: {sessions}, tokens: {tokens}, cost: ${cost:.4f}, models: {len(models)})")
        else:
            print(f"         (no analytics)")

        # Audit
        r = await http.get(f"{self.base}/api/audit?n=100", headers=self._headers())
        audit = _check(r)
        n_events = len(audit) if isinstance(audit, list) else 0
        print(f"         (audit: {n_events} events)")

        # Agent-specific audit
        if self.agent_id:
            r = await http.get(f"{self.base}/api/audit?n=20&agent_id={self.agent_id}", headers=self._headers())
            agent_audit = _check(r)
            n_agent = len(agent_audit) if isinstance(agent_audit, list) else 0
            print(f"         (agent audit: {n_agent} events)")

        return True

    # ═══════════════════════════════════════════════════
    # Phase N: Integrations, permissions, contacts, inbox
    # ═══════════════════════════════════════════════════

    async def check_system_endpoints(self, http: httpx.AsyncClient):
        # Integrations
        r = await http.get(f"{self.base}/api/integrations", headers=self._headers())
        integ = _soft_check(r, "integrations")
        if integ and isinstance(integ, list):
            names = [i.get("name", i.get("id", "?")) for i in integ]
            print(f"         (integrations: {names})")

        # Permissions
        r = await http.get(f"{self.base}/api/permissions", headers=self._headers())
        perms = _soft_check(r, "permissions")
        n_perms = len(perms) if isinstance(perms, list) else 0
        print(f"         (pending permissions: {n_perms})")

        # Contacts
        r = await http.get(f"{self.base}/api/contacts", headers=self._headers())
        contacts = _soft_check(r, "contacts")
        n_contacts = len(contacts) if isinstance(contacts, list) else 0
        print(f"         (contacts: {n_contacts})")

        # Inbox
        r = await http.get(f"{self.base}/api/inbox", headers=self._headers())
        inbox = _soft_check(r, "inbox")
        n_inbox = len(inbox) if isinstance(inbox, list) else 0
        print(f"         (inbox: {n_inbox} items)")

        # Channels
        r = await http.get(f"{self.base}/api/channels", headers=self._headers())
        channels = _soft_check(r, "channels")
        print(f"         (channels: {type(channels).__name__})")

        # OAuth
        r = await http.get(f"{self.base}/api/oauth", headers=self._headers())
        oauth = _soft_check(r, "oauth")
        if oauth and isinstance(oauth, list):
            print(f"         (oauth: {[o.get('service') for o in oauth]})")

        # Agent files
        if self.agent_id:
            r = await http.get(f"{self.base}/api/agents/{self.agent_id}/files", headers=self._headers())
            files = _soft_check(r, "agent files")
            n_files = len(files) if isinstance(files, list) else 0
            print(f"         (agent files: {n_files})")

        return True

    # ═══════════════════════════════════════════════════
    # Phase O: Final verify & cleanup
    # ═══════════════════════════════════════════════════

    async def final_verify(self, http: httpx.AsyncClient):
        # All agents
        r = await http.get(f"{self.base}/api/agents", headers=self._headers())
        agents = _check(r)
        if isinstance(agents, list):
            for a in agents:
                print(f"         • {a.get('name')} ({a.get('id')}): {a.get('status')}")

        # All sessions
        r = await http.get(f"{self.base}/api/sessions", headers=self._headers())
        sessions = _check(r)
        n_sessions = len(sessions) if isinstance(sessions, list) else 0
        print(f"         ({n_sessions} session(s))")

        # Cleanup test agent
        if self.agent_id:
            r = await http.delete(f"{self.base}/api/agents/{self.agent_id}", headers=self._headers())
            if r.status_code < 400:
                print(f"         (deleted {self.agent_id})")
            else:
                print(f"         (cleanup: {r.status_code})")

        elapsed = time.monotonic() - self._start_time
        return {"elapsed": elapsed}

    # ═══════════════════════════════════════════════════
    # WebSocket helper
    # ═══════════════════════════════════════════════════

    async def _ws_send(self, message: str, timeout: float = 90, retries: int = 2) -> list:
        import websockets
        port = self.base.split(":")[-1]
        ws_url = f"ws://127.0.0.1:{port}/ws/{self.session_id}?token={self.token}"

        for attempt in range(retries + 1):
            frames = []
            try:
                async with websockets.connect(ws_url, close_timeout=5) as ws:
                    await ws.send(json.dumps({"type": "message", "content": message, "agent_id": self.agent_id}))
                    deadline = time.monotonic() + timeout
                    while time.monotonic() < deadline:
                        try:
                            remaining = deadline - time.monotonic()
                            raw = await asyncio.wait_for(ws.recv(), timeout=min(10.0, remaining))
                            frame = json.loads(raw)
                            frames.append(frame)
                            ftype = frame.get("type", "")
                            if ftype == "message":
                                return frames
                            elif ftype == "error":
                                return frames
                            elif ftype == "tool_use":
                                print(f"         ⚡ tool: {frame.get('name', '?')}")
                        except asyncio.TimeoutError:
                            if frames:
                                return frames
                            raise StepError(cause=f"WS timeout after {timeout}s")
                    return frames
            except websockets.exceptions.ConnectionClosed as e:
                if attempt < retries:
                    code = e.rcvd.code if e.rcvd else 0
                    print(f"         (WS closed {code} — waiting for gateway, retry {attempt+1}/{retries})")
                    # Gateway may be restarting — wait longer
                    for _ in range(15):
                        await asyncio.sleep(2)
                        try:
                            async with httpx.AsyncClient(timeout=5) as probe:
                                r = await probe.get(f"http://127.0.0.1:{port}/api/status")
                                if r.status_code == 200:
                                    break
                        except Exception:
                            pass
                    continue
                raise StepError(cause=f"WS closed: {e}")
            except StepError:
                raise
            except Exception as e:
                if attempt < retries:
                    print(f"         (WS error: {e} — waiting for gateway, retry {attempt+1}/{retries})")
                    for _ in range(15):
                        await asyncio.sleep(2)
                        try:
                            async with httpx.AsyncClient(timeout=5) as probe:
                                r = await probe.get(f"http://127.0.0.1:{port}/api/status")
                                if r.status_code == 200:
                                    break
                        except Exception:
                            pass
                    continue
                raise StepError(cause=f"WS error: {e}")
        return frames

    @staticmethod
    def _last_response(frames: list) -> str:
        for f in reversed(frames):
            if f.get("type") == "message" and f.get("content"):
                return f["content"]
            if f.get("type") == "chunk" and f.get("content"):
                return f["content"]
        return "(no content)"

    # ═══════════════════════════════════════════════════
    # State recovery for --skip-to
    # ═══════════════════════════════════════════════════

    async def _recover_state(self, http: httpx.AsyncClient):
        if self.skip_to <= 1:
            return
        try:
            r = await http.get(f"{self.base}/api/bootstrap")
            data = r.json() if r.status_code == 200 else {}
            self.token = data.get("token", "")
        except Exception:
            pass
        if self.skip_to <= 13:
            return
        try:
            r = await http.get(f"{self.base}/api/agents", headers=self._headers())
            agents = r.json() if r.status_code == 200 else []
            for a in reversed(agents if isinstance(agents, list) else []):
                if a.get("id") != "hector":
                    self.agent_id = a["id"]
                    print(f"         (recovered agent: {self.agent_id} — {a.get('name')})")
                    break
        except Exception:
            pass
        if self.skip_to <= 15 or not self.agent_id:
            return
        try:
            r = await http.get(f"{self.base}/api/agents/{self.agent_id}/sessions", headers=self._headers())
            sessions = r.json() if r.status_code == 200 else []
            if isinstance(sessions, list) and sessions:
                self.session_id = sessions[-1].get("id", "")
                print(f"         (recovered session: {self.session_id})")
        except Exception:
            pass

    # ═══════════════════════════════════════════════════
    # Run all
    # ═══════════════════════════════════════════════════

    async def run(self, http: httpx.AsyncClient):
        print(f"\n{'─'*60}")
        print(f"Persona: {self.p.owner.name} ({self.p.owner.username})")
        print(f"About:   {self.p.owner.about}")
        print(f"Style:   {self.p.user_style}")
        print(f"Agent:   {self.p.agent.name} ({self.p.agent.role})")
        print(f"Model:   {self.p.default_model}")
        print(f"Skills:  {self.p.agent.skills}")
        print(f"Seed:    {self.p.seed}")
        print(f"{'─'*60}\n")

        if self.skip_to > 1:
            await self._recover_state(http)

        # A: Bootstrap
        await self.step("health_check", self.health_check(http))
        await self.step("bootstrap", self.bootstrap(http))

        # B: Onboarding — Identity
        await self.step(f'set_owner "{self.p.owner.name}"', self.set_owner(http))
        await self.step("verify_owner", self.verify_owner(http))
        await self.step(f'matrix_register "{self.p.owner.username}"', self.matrix_register(http))

        # B: Intelligence
        await self.step(f'add_ai_key "{self.p.ai_key_name}"', self.add_ai_key(http))
        await self.step("verify_secrets", self.verify_secrets(http))
        await self.step("list_providers", self.list_providers(http))
        await self.step(f'set_default_model "{self.p.default_model}"', self.set_default_model(http))

        # B: Optional providers
        await self.step("add_optional_keys", self.add_optional_keys(http))

        # B: Hector
        await self.step("activate_hector", self.activate_hector(http))
        await self.step("verify_hector", self.verify_hector(http))

        # C: Create agent via Hector + deep audit
        await self.step(f'create_agent "{self.p.agent.name}" (via Hector)', self.create_agent(http))
        await self.step("audit_agent", self.verify_agent(http))

        # D: Chat
        await self.step("chat_with_agent", self.chat_with_agent(http))
        await self.step("verify_history", self.verify_history(http))

        # E: Configure (soul, memory, cron, rules)
        await self.step("configure", self.configure(http))

        # F: Agent profile updates
        await self.step("update_agent_profile", self.update_agent_profile(http))

        # G: Skills
        await self.step("manage_skills", self.manage_skills(http))

        # H: Connections
        await self.step("manage_connections", self.manage_connections(http))

        # I: Wallet & vault
        await self.step("wallet_and_vault", self.wallet_and_vault(http))

        # J: Avatar generation
        await self.step("generate_avatars", self.generate_avatars(http))

        # K: Relationships
        await self.step("manage_relationships", self.manage_relationships(http))

        # L: Pane widgets
        await self.step("check_pane_widgets", self.check_pane_widgets(http))

        # M: Analytics & audit
        await self.step("check_analytics", self.check_analytics(http))

        # N: Integrations, permissions, contacts, inbox
        await self.step("check_system_endpoints", self.check_system_endpoints(http))

        # O: Final verify & cleanup
        await self.step("final_verify", self.final_verify(http))

        elapsed = time.monotonic() - self._start_time
        print(f"\n{'═'*60}")
        print(f"ALL {TOTAL_STEPS} STEPS PASSED (seed={self.p.seed}, {elapsed:.1f}s)")
        print(f"Persona: {self.p.owner.name} → Agent: {self.p.agent.name}")
        print(f"{'═'*60}")


# ── Scratchpad ──

SCRATCHPAD_PATH = Path(__file__).parent / "scratchpad.md"

def scratchpad_write(seed: int, persona: Persona, step_failed: str | None, step_n: int,
                     issues: list[str] | None = None, error_msg: str = ""):
    """Append a run result to the scratchpad file."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    passed = step_failed is None
    status = "PASS" if passed else f"FAIL at step {step_n}: {step_failed}"

    lines = [
        f"\n## Run seed={seed} — {ts}",
        f"- **Status**: {status}",
        f"- **Persona**: {persona.owner.name} ({persona.user_style})",
        f"- **About**: {persona.owner.about}",
        f"- **Agent**: {persona.agent.name} ({persona.agent.role})",
        f"- **Model**: {persona.default_model}",
        f"- **Hector msg**: \"{persona.hector_create_msg[:120]}{'...' if len(persona.hector_create_msg) > 120 else ''}\"",
    ]

    if error_msg:
        lines.append(f"- **Error**: `{error_msg[:200]}`")

    if issues:
        lines.append(f"- **Audit issues** ({len(issues)}):")
        for issue in issues:
            lines.append(f"  - {issue}")

    lines.append("")

    with open(SCRATCHPAD_PATH, "a") as f:
        f.write("\n".join(lines) + "\n")


def scratchpad_init():
    """Write header if scratchpad doesn't exist."""
    if not SCRATCHPAD_PATH.exists():
        with open(SCRATCHPAD_PATH, "w") as f:
            f.write("# VultiHub E2E Harness — Scratchpad\n\nRunning log of all harness runs, findings, and bugs.\n")


# ── Entrypoint ──

async def main():
    parser = argparse.ArgumentParser(description="VultiHub E2E Harness")
    parser.add_argument("--api-keys", required=True, help="Path to keys.json")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--port", type=int, default=8080, help="Gateway port")
    parser.add_argument("--skip-to", default=None, choices=list(SKIP_POINTS.keys()), help="Skip to step")
    parser.add_argument("--count", type=int, default=1, help="Number of personas")
    args = parser.parse_args()

    keys_path = Path(args.api_keys)
    if not keys_path.exists():
        print(f"ERROR: {keys_path} not found")
        sys.exit(1)

    api_keys = json.loads(keys_path.read_text())
    base = f"http://127.0.0.1:{args.port}"
    skip_to = SKIP_POINTS.get(args.skip_to, 0) if args.skip_to else 0

    scratchpad_init()

    print(f"VultiHub E2E Harness ({TOTAL_STEPS} steps)")
    print(f"Target: {base}")
    print(f"Count:  {args.count}")
    print(f"Scratchpad: {SCRATCHPAD_PATH}")
    if args.skip_to:
        print(f"Skip:   → {args.skip_to} (step {skip_to})")

    passed = 0
    failed = 0

    for i in range(args.count):
        seed = args.seed if args.seed is not None else (i + int(time.time()) % 100000)
        persona = generate_persona(seed=seed, api_keys=api_keys)
        async with httpx.AsyncClient(timeout=30) as http:
            harness = Harness(persona=persona, base=base, skip_to=skip_to)
            try:
                await harness.run(http)
                passed += 1
                scratchpad_write(seed, persona, step_failed=None, step_n=TOTAL_STEPS, issues=harness.audit_issues)
            except SystemExit:
                failed += 1
                scratchpad_write(seed, persona, step_failed=f"step_{harness.step_n}", step_n=harness.step_n, issues=harness.audit_issues)
                if args.count == 1:
                    sys.exit(1)
                print(f"\n(Continuing to next persona...)\n")

    if args.count > 1:
        print(f"\n{'═'*60}")
        print(f"BATCH: {passed}/{args.count} passed, {failed} failed")
        print(f"{'═'*60}")
        if failed > 0:
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
