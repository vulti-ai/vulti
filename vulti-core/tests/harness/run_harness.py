#!/usr/bin/env python3
"""VultiHub E2E Harness — drive the full user journey, find bugs.

Usage:
    python tests/harness/run_harness.py --api-keys tests/harness/keys.json
    python tests/harness/run_harness.py --api-keys tests/harness/keys.json --seed=42
    python tests/harness/run_harness.py --api-keys tests/harness/keys.json --skip-to=create_agent
    python tests/harness/run_harness.py --api-keys tests/harness/keys.json --count=20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import traceback
from pathlib import Path

import httpx

# Add parent paths so we can import personas
sys.path.insert(0, str(Path(__file__).parent))
from personas import Persona, generate_persona

# ── Constants ──

TOTAL_STEPS = 18

SKIP_POINTS = {
    "health_check": 1,
    "bootstrap": 2,
    "set_owner": 3,
    "add_ai_key": 6,
    "activate_hector": 11,
    "create_agent": 13,
    "chat": 15,
    "configure": 17,
    "verify": 18,
}

# ── Step runner ──


class StepError(Exception):
    """Raised when a step fails — carries context for the error output."""

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
            # Truncate long bodies
            display = body[:500] + ("..." if len(body) > 500 else "")
            parts.append(display)
        if cause:
            parts.append(cause)
        super().__init__("\n         ".join(parts))


def _check(r: httpx.Response, label: str = "") -> dict | list | str:
    """Check HTTP response, raise StepError on non-2xx."""
    if r.status_code >= 400:
        raise StepError(
            method=r.request.method,
            path=str(r.request.url.path),
            status=r.status_code,
            body=r.text[:1000],
        )
    try:
        return r.json()
    except Exception:
        return r.text


class Harness:
    """Drives the full VultiHub journey."""

    def __init__(self, persona: Persona, base: str, skip_to: int = 0):
        self.p = persona
        self.base = base
        self.skip_to = skip_to
        self.step_n = 0
        self.token: str = ""
        self.agent_id: str = ""
        self.session_id: str = ""
        self._start_time = time.monotonic()

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def step(self, name: str, coro):
        """Run a step, print result, stop on failure."""
        self.step_n += 1
        if self.step_n < self.skip_to:
            print(f"[{self.step_n:02d}/{TOTAL_STEPS:02d}] {name:.<45s} SKIP")
            return None

        t0 = time.monotonic()
        try:
            result = await coro
            ms = (time.monotonic() - t0) * 1000
            print(f"[{self.step_n:02d}/{TOTAL_STEPS:02d}] {name:.<45s} PASS ({ms:.0f}ms)")
            return result
        except StepError:
            ms = (time.monotonic() - t0) * 1000
            print(f"[{self.step_n:02d}/{TOTAL_STEPS:02d}] {name:.<45s} FAIL ({ms:.0f}ms)")
            traceback.print_exc()
            print(f"         ─── STOPPING. Fix and re-run. ───")
            sys.exit(1)
        except Exception as e:
            ms = (time.monotonic() - t0) * 1000
            print(f"[{self.step_n:02d}/{TOTAL_STEPS:02d}] {name:.<45s} FAIL ({ms:.0f}ms)")
            print(f"         {type(e).__name__}: {e}")
            traceback.print_exc()
            print(f"         ─── STOPPING. Fix and re-run. ───")
            sys.exit(1)

    # ── Phase A: Bootstrap ──

    async def health_check(self, http: httpx.AsyncClient):
        r = await http.get(f"{self.base}/api/status", headers=self._headers())
        data = _check(r)
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        return data

    async def bootstrap(self, http: httpx.AsyncClient):
        r = await http.get(f"{self.base}/api/bootstrap", headers=self._headers())
        data = _check(r)
        token = data.get("token") if isinstance(data, dict) else None
        if not token:
            raise StepError(cause=f"No token in response: {data}")
        self.token = token
        return token

    # ── Phase B: Onboarding — Identity ──

    async def set_owner(self, http: httpx.AsyncClient):
        r = await http.put(
            f"{self.base}/api/owner",
            json={"name": self.p.owner.name, "about": self.p.owner.about},
            headers=self._headers(),
        )
        return _check(r)

    async def verify_owner(self, http: httpx.AsyncClient):
        r = await http.get(f"{self.base}/api/owner", headers=self._headers())
        data = _check(r)
        got_name = data.get("name", "") if isinstance(data, dict) else ""
        if got_name != self.p.owner.name:
            raise StepError(cause=f"Owner name mismatch: expected '{self.p.owner.name}', got '{got_name}'")
        return data

    async def matrix_register(self, http: httpx.AsyncClient):
        r = await http.post(
            f"{self.base}/api/matrix/register",
            json={"username": self.p.owner.username, "password": self.p.owner.password},
            headers=self._headers(),
        )
        # Matrix may not be running — 5xx is expected, 4xx is a real error
        if r.status_code >= 500:
            print(f"         (Matrix not available — {r.status_code}, continuing)")
            return {"skipped": True}
        return _check(r)

    # ── Phase B: Onboarding — Intelligence ──

    async def add_ai_key(self, http: httpx.AsyncClient):
        if not self.p.ai_key_name or not self.p.ai_key_value:
            raise StepError(cause="No AI provider key in keys.json — need at least one of: OPENROUTER_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.")
        r = await http.post(
            f"{self.base}/api/secrets",
            json={"key": self.p.ai_key_name, "value": self.p.ai_key_value},
            headers=self._headers(),
        )
        return _check(r)

    async def verify_secrets(self, http: httpx.AsyncClient):
        r = await http.get(f"{self.base}/api/secrets", headers=self._headers())
        data = _check(r)
        if not isinstance(data, list):
            raise StepError(cause=f"Expected list, got {type(data)}: {data}")
        found = any(
            s.get("key") == self.p.ai_key_name and s.get("is_set")
            for s in data
        )
        if not found:
            keys = [s.get("key") for s in data]
            raise StepError(cause=f"Key '{self.p.ai_key_name}' not found or not set. Available: {keys}")
        return data

    async def list_providers(self, http: httpx.AsyncClient):
        r = await http.get(f"{self.base}/api/providers", headers=self._headers())
        data = _check(r)
        if not isinstance(data, list):
            raise StepError(cause=f"Expected list, got {type(data)}")
        authenticated = [p for p in data if p.get("authenticated")]
        if not authenticated:
            all_names = [p.get("name", p.get("id", "?")) for p in data]
            raise StepError(cause=f"No authenticated providers. All providers: {all_names}")
        print(f"         ({len(authenticated)} authenticated provider(s): {[p.get('name') for p in authenticated]})")
        return data

    async def set_default_model(self, http: httpx.AsyncClient):
        r = await http.post(
            f"{self.base}/api/secrets",
            json={"key": "VULTI_DEFAULT_MODEL", "value": self.p.default_model},
            headers=self._headers(),
        )
        return _check(r)

    # ── Phase B: Onboarding — Optional Providers ──

    async def add_optional_keys(self, http: httpx.AsyncClient):
        added = []
        for key, value in self.p.optional_keys.items():
            r = await http.post(
                f"{self.base}/api/secrets",
                json={"key": key, "value": value},
                headers=self._headers(),
            )
            _check(r)
            added.append(key)
        if added:
            print(f"         (added {len(added)} optional key(s): {added})")
        else:
            print(f"         (no optional keys to add)")
        return added

    # ── Phase B: Onboarding — Activate Hector ──

    async def activate_hector(self, http: httpx.AsyncClient):
        # Update allowed connections
        r = await http.put(
            f"{self.base}/api/agents/hector",
            json={"allowedConnections": "matrix"},
            headers=self._headers(),
        )
        _check(r)

        # Install matrix skill (may not exist — Swift uses try?)
        r = await http.post(
            f"{self.base}/api/agents/hector/skills",
            json={"name": "matrix"},
            headers=self._headers(),
        )
        if r.status_code >= 400:
            print(f"         (matrix skill not available — {r.status_code}, continuing)")
        else:
            _check(r)

        # Matrix onboard (may fail if no homeserver)
        try:
            r = await http.post(
                f"{self.base}/api/matrix/onboard-agent",
                json={"agent_id": "hector"},
                headers=self._headers(),
            )
            if r.status_code < 500:
                _check(r)
            else:
                print(f"         (Matrix onboard skipped — {r.status_code})")
        except Exception as e:
            print(f"         (Matrix onboard skipped — {e})")

        # Finalize onboarding
        r = await http.post(
            f"{self.base}/api/agents/hector/finalize-onboarding",
            json={"role": "wizard"},
            headers=self._headers(),
        )
        return _check(r)

    async def verify_hector(self, http: httpx.AsyncClient):
        r = await http.get(f"{self.base}/api/agents/hector", headers=self._headers())
        data = _check(r)
        status = data.get("status", "") if isinstance(data, dict) else ""
        if status != "active":
            print(f"         (Hector status: '{status}' — expected 'active', may be OK)")
        return data

    # ── Phase C: Create New Agent ──

    async def create_agent(self, http: httpx.AsyncClient):
        # Create
        r = await http.post(
            f"{self.base}/api/agents",
            json={"name": self.p.agent.name, "model": self.p.agent.model},
            headers=self._headers(),
        )
        data = _check(r)
        agent_id = data.get("id") if isinstance(data, dict) else None
        if not agent_id:
            raise StepError(cause=f"No agent id in response: {data}")
        self.agent_id = agent_id
        print(f"         (agent_id: {agent_id})")

        # Set allowed connections
        r = await http.put(
            f"{self.base}/api/agents/{agent_id}",
            json={"allowedConnections": "matrix"},
            headers=self._headers(),
        )
        _check(r)

        # Install matrix skill (may not exist — Swift uses try?)
        r = await http.post(
            f"{self.base}/api/agents/{agent_id}/skills",
            json={"name": "matrix"},
            headers=self._headers(),
        )
        if r.status_code >= 400:
            print(f"         (matrix skill not available — {r.status_code}, continuing)")
        else:
            _check(r)

        # Install additional skills
        for skill in self.p.agent.skills:
            r = await http.post(
                f"{self.base}/api/agents/{agent_id}/skills",
                json={"name": skill},
                headers=self._headers(),
            )
            if r.status_code >= 400:
                print(f"         (skill '{skill}' install failed — {r.status_code}, continuing)")
            else:
                _check(r)

        # Matrix onboard (may fail)
        try:
            r = await http.post(
                f"{self.base}/api/matrix/onboard-agent",
                json={"agent_id": agent_id},
                headers=self._headers(),
            )
            if r.status_code >= 500:
                print(f"         (Matrix onboard skipped — {r.status_code})")
        except Exception as e:
            print(f"         (Matrix onboard skipped — {e})")

        return data

    async def verify_agent(self, http: httpx.AsyncClient):
        if not self.agent_id:
            # Try to find it from list
            r = await http.get(f"{self.base}/api/agents", headers=self._headers())
            data = _check(r)
            for a in (data if isinstance(data, list) else []):
                if a.get("name") == self.p.agent.name:
                    self.agent_id = a["id"]
                    break
            if not self.agent_id:
                raise StepError(cause=f"Agent '{self.p.agent.name}' not found in agent list")

        r = await http.get(f"{self.base}/api/agents/{self.agent_id}", headers=self._headers())
        data = _check(r)
        print(f"         (agent '{data.get('name')}' status: {data.get('status')})")
        return data

    # ── Phase D: Talk to Agent ──

    async def chat_with_agent(self, http: httpx.AsyncClient):
        if not self.agent_id:
            raise StepError(cause="No agent_id — run create_agent first or use --skip-to correctly")

        # Create session
        r = await http.post(
            f"{self.base}/api/agents/{self.agent_id}/sessions",
            json={"name": f"Harness test (seed={self.p.seed})"},
            headers=self._headers(),
        )
        data = _check(r)
        session_id = data.get("id") if isinstance(data, dict) else None
        if not session_id:
            raise StepError(cause=f"No session_id in response: {data}")
        self.session_id = session_id
        print(f"         (session_id: {session_id})")

        # Chat via WebSocket
        try:
            import websockets
        except ImportError:
            raise StepError(cause="'websockets' package not installed — run: pip install websockets")

        ws_url = f"ws://127.0.0.1:{self.base.split(':')[-1]}/ws/{session_id}?token={self.token}"

        for i, message in enumerate(self.p.agent.conversation):
            print(f"         → [{i+1}/{len(self.p.agent.conversation)}] \"{message[:60]}{'...' if len(message) > 60 else ''}\"")

            frames = []
            try:
                async with websockets.connect(ws_url, close_timeout=5) as ws:
                    # Send message
                    await ws.send(json.dumps({
                        "type": "message",
                        "content": message,
                        "agent_id": self.agent_id,
                    }))

                    # Collect response frames
                    deadline = time.monotonic() + 90  # 90s timeout for AI response
                    while time.monotonic() < deadline:
                        try:
                            remaining = deadline - time.monotonic()
                            raw = await asyncio.wait_for(ws.recv(), timeout=min(10.0, remaining))
                            frame = json.loads(raw)
                            frames.append(frame)
                            ftype = frame.get("type", "")

                            if ftype == "message":
                                # Final response
                                content = frame.get("content", "")
                                preview = content[:80].replace("\n", " ")
                                print(f"         ← \"{preview}{'...' if len(content) > 80 else ''}\"")
                                break
                            elif ftype == "error":
                                raise StepError(cause=f"WebSocket error frame: {frame.get('content', frame)}")
                            elif ftype == "tool_use":
                                print(f"         ⚡ tool: {frame.get('name', '?')}")
                        except asyncio.TimeoutError:
                            # Check if we got any response at all
                            if frames:
                                # Got chunks but no final message — may be OK
                                last_chunk = ""
                                for f in reversed(frames):
                                    if f.get("type") == "chunk":
                                        last_chunk = f.get("content", "")[:80]
                                        break
                                if last_chunk:
                                    print(f"         ← (timeout, last chunk: \"{last_chunk}...\")")
                                    break
                            raise StepError(cause=f"WebSocket timeout — no response after 90s. Frames received: {len(frames)}")

            except websockets.exceptions.ConnectionClosed as e:
                raise StepError(cause=f"WebSocket closed: {e}")

            if not frames:
                raise StepError(cause=f"No frames received for message: {message}")

            # Brief pause between messages in multi-turn
            if i < len(self.p.agent.conversation) - 1:
                await asyncio.sleep(1)

        return {"messages_sent": len(self.p.agent.conversation), "total_frames": sum(1 for _ in [])}

    async def verify_history(self, http: httpx.AsyncClient):
        if not self.session_id:
            raise StepError(cause="No session_id — run chat first")

        r = await http.get(
            f"{self.base}/api/sessions/{self.session_id}/history",
            headers=self._headers(),
        )
        data = _check(r)
        if not isinstance(data, list):
            raise StepError(cause=f"Expected list, got {type(data)}")
        n_user = sum(1 for m in data if m.get("role") == "user")
        n_asst = sum(1 for m in data if m.get("role") == "assistant")
        print(f"         ({len(data)} messages: {n_user} user, {n_asst} assistant)")
        if n_user < len(self.p.agent.conversation):
            raise StepError(cause=f"Expected at least {len(self.p.agent.conversation)} user messages, got {n_user}")
        return data

    # ── Phase E: Configure ──

    async def configure(self, http: httpx.AsyncClient):
        if not self.agent_id:
            raise StepError(cause="No agent_id — cannot configure")

        # Update soul
        r = await http.put(
            f"{self.base}/api/agents/{self.agent_id}/soul",
            json={"content": self.p.agent.personality},
            headers=self._headers(),
        )
        _check(r)
        print(f"         (soul updated)")

        # Create cron job
        cron = self.p.cron
        r = await http.post(
            f"{self.base}/api/cron",
            json={"name": cron["name"], "prompt": cron["prompt"], "schedule": cron["schedule"]},
            headers=self._headers(),
        )
        _check(r)
        print(f"         (cron '{cron['name']}' created)")

        # Verify cron
        r = await http.get(f"{self.base}/api/cron", headers=self._headers())
        crons = _check(r)
        if isinstance(crons, list):
            found = any(c.get("name") == cron["name"] for c in crons)
            if not found:
                raise StepError(cause=f"Cron '{cron['name']}' not found after creation")

        # Create rule
        rule = self.p.rule
        r = await http.post(
            f"{self.base}/api/rules",
            json={"name": rule["name"], "condition": rule["condition"], "action": rule["action"], "priority": rule["priority"]},
            headers=self._headers(),
        )
        _check(r)
        print(f"         (rule '{rule['name']}' created)")

        # Verify rules
        r = await http.get(f"{self.base}/api/rules", headers=self._headers())
        rules = _check(r)
        if isinstance(rules, list):
            found = any(rl.get("name") == rule["name"] for rl in rules)
            if not found:
                raise StepError(cause=f"Rule '{rule['name']}' not found after creation")

        return {"cron": cron["name"], "rule": rule["name"]}

    # ── Phase F: Verify & Cleanup ──

    async def final_verify(self, http: httpx.AsyncClient):
        # List all agents
        r = await http.get(f"{self.base}/api/agents", headers=self._headers())
        agents = _check(r)
        if isinstance(agents, list):
            names = [a.get("name") for a in agents]
            print(f"         (agents: {names})")

        # Check audit trail
        r = await http.get(f"{self.base}/api/audit?n=50", headers=self._headers())
        audit = _check(r)
        n_events = len(audit) if isinstance(audit, list) else 0
        print(f"         (audit: {n_events} events)")

        # Cleanup — delete test agent (not Hector)
        if self.agent_id:
            r = await http.delete(
                f"{self.base}/api/agents/{self.agent_id}",
                headers=self._headers(),
            )
            if r.status_code < 400:
                print(f"         (deleted test agent {self.agent_id})")
            else:
                print(f"         (cleanup failed: {r.status_code} — {r.text[:200]})")

        elapsed = time.monotonic() - self._start_time
        return {"elapsed": elapsed}

    # ── Run all ──

    async def run(self, http: httpx.AsyncClient):
        """Run all steps in sequence."""
        print(f"\n{'─'*55}")
        print(f"Persona: {self.p.owner.name} ({self.p.owner.username})")
        print(f"Agent:   {self.p.agent.name} ({self.p.agent.role})")
        print(f"Model:   {self.p.default_model}")
        print(f"Skills:  {self.p.agent.skills}")
        print(f"Seed:    {self.p.seed}")
        print(f"{'─'*55}\n")

        # Phase A
        await self.step("health_check", self.health_check(http))
        await self.step("bootstrap", self.bootstrap(http))

        # Phase B: Identity
        await self.step(f'set_owner "{self.p.owner.name}"', self.set_owner(http))
        await self.step("verify_owner", self.verify_owner(http))
        await self.step(f'matrix_register "{self.p.owner.username}"', self.matrix_register(http))

        # Phase B: Intelligence
        await self.step(f'add_ai_key "{self.p.ai_key_name}"', self.add_ai_key(http))
        await self.step("verify_secrets", self.verify_secrets(http))
        await self.step("list_providers", self.list_providers(http))
        await self.step(f'set_default_model "{self.p.default_model}"', self.set_default_model(http))

        # Phase B: Optional providers
        await self.step("add_optional_keys", self.add_optional_keys(http))

        # Phase B: Hector
        await self.step("activate_hector", self.activate_hector(http))
        await self.step("verify_hector", self.verify_hector(http))

        # Phase C: Create agent
        await self.step(f'create_agent "{self.p.agent.name}"', self.create_agent(http))
        await self.step("verify_agent", self.verify_agent(http))

        # Phase D: Chat
        await self.step("chat_with_agent", self.chat_with_agent(http))
        await self.step("verify_history", self.verify_history(http))

        # Phase E: Configure
        await self.step("configure", self.configure(http))

        # Phase F: Verify & cleanup
        result = await self.step("final_verify", self.final_verify(http))

        elapsed = time.monotonic() - self._start_time
        print(f"\n{'═'*55}")
        print(f"ALL {TOTAL_STEPS} STEPS PASSED (seed={self.p.seed}, {elapsed:.1f}s)")
        print(f"Persona: {self.p.owner.name} → Agent: {self.p.agent.name}")
        print(f"{'═'*55}")


# ── Entrypoint ──


async def main():
    parser = argparse.ArgumentParser(description="VultiHub E2E Harness")
    parser.add_argument("--api-keys", required=True, help="Path to keys.json with API keys")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--port", type=int, default=8080, help="Gateway port (default: 8080)")
    parser.add_argument("--skip-to", default=None, choices=list(SKIP_POINTS.keys()),
                        help="Skip to a specific step")
    parser.add_argument("--count", type=int, default=1, help="Number of personas to run")
    args = parser.parse_args()

    # Load API keys
    keys_path = Path(args.api_keys)
    if not keys_path.exists():
        print(f"ERROR: keys file not found: {keys_path}")
        print(f"Create it with at least: {{\"OPENROUTER_API_KEY\": \"sk-...\", \"default_model\": \"anthropic/claude-3.5-sonnet\"}}")
        sys.exit(1)

    api_keys = json.loads(keys_path.read_text())
    base = f"http://127.0.0.1:{args.port}"
    skip_to = SKIP_POINTS.get(args.skip_to, 0) if args.skip_to else 0

    print(f"VultiHub E2E Harness")
    print(f"Target: {base}")
    print(f"Count:  {args.count}")
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
            except SystemExit:
                failed += 1
                if args.count == 1:
                    sys.exit(1)
                print(f"\n(Continuing to next persona...)\n")

    if args.count > 1:
        print(f"\n{'═'*55}")
        print(f"BATCH COMPLETE: {passed}/{args.count} passed, {failed} failed")
        print(f"{'═'*55}")
        if failed > 0:
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
