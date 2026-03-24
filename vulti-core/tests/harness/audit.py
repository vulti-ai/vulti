#!/usr/bin/env python3
"""VultiHub Audit — snapshot the entire system state for review.

Dumps every agent, every file, every config, every endpoint response
to scratchpad.md so Claude can critically review quality.

Usage:
    python tests/harness/audit.py --api-keys tests/harness/keys.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8080"
SCRATCHPAD = Path(__file__).parent / "scratchpad.md"


class Auditor:
    def __init__(self, base: str, token: str = ""):
        self.base = base
        self.token = token
        self.lines: list[str] = []

    def _h(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def log(self, text: str):
        print(text)
        self.lines.append(text)

    def section(self, title: str):
        self.log(f"\n## {title}\n")

    def dump_json(self, label: str, data, indent: int = 2):
        """Pretty-print JSON data with a label."""
        if isinstance(data, (dict, list)):
            formatted = json.dumps(data, indent=indent, default=str)
            # Truncate very long dumps
            if len(formatted) > 3000:
                formatted = formatted[:3000] + "\n... (truncated)"
            self.log(f"**{label}**:\n```json\n{formatted}\n```")
        else:
            self.log(f"**{label}**: `{data}`")

    async def get(self, http: httpx.AsyncClient, path: str) -> dict | list | str | None:
        try:
            r = await http.get(f"{self.base}{path}", headers=self._h())
            if r.status_code >= 400:
                self.log(f"  `{path}` → {r.status_code}: {r.text[:200]}")
                return None
            return r.json()
        except Exception as e:
            self.log(f"  `{path}` → ERROR: {e}")
            return None

    async def run(self):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log(f"# VultiHub System Audit — {ts}\n")

        async with httpx.AsyncClient(timeout=15) as http:
            # Bootstrap
            data = await self.get(http, "/api/bootstrap")
            if data and isinstance(data, dict):
                self.token = data.get("token", "")
            else:
                self.log("FATAL: Cannot bootstrap")
                return

            # ── Status ──
            self.section("System Status")
            data = await self.get(http, "/api/status")
            self.dump_json("Gateway", data)

            # ── Owner ──
            self.section("Owner Profile")
            data = await self.get(http, "/api/owner")
            self.dump_json("Owner", data)

            # ── Providers ──
            self.section("Providers")
            data = await self.get(http, "/api/providers")
            if isinstance(data, list):
                for p in data:
                    auth = "✓" if p.get("authenticated") else "✗"
                    models = p.get("models", [])
                    self.log(f"- **{p.get('name')}** [{auth}] — {len(models)} models")

            # ── Secrets ──
            self.section("Secrets")
            data = await self.get(http, "/api/secrets")
            if isinstance(data, list):
                for s in data:
                    is_set = "SET" if s.get("is_set") else "empty"
                    self.log(f"- `{s.get('key')}`: {is_set} ({s.get('category', '?')})")

            # ── Agents (deep dive each one) ──
            self.section("Agents")
            agents = await self.get(http, "/api/agents")
            if not isinstance(agents, list):
                self.log("No agents found")
                return

            for agent in agents:
                aid = agent.get("id", "?")
                name = agent.get("name", "?")
                self.log(f"\n### Agent: {name} (`{aid}`)")
                self.log(f"- **Status**: {agent.get('status')}")
                self.log(f"- **Role**: `{agent.get('role', '(none)')}`")
                self.log(f"- **Description**: {agent.get('description', '(none)')}")
                self.log(f"- **Created**: {agent.get('created_at', '?')}")
                self.log(f"- **Platforms**: {agent.get('platforms', [])}")
                self.log(f"- **Allowed connections**: {agent.get('allowed_connections', [])}")

                # Soul
                soul = await self.get(http, f"/api/agents/{aid}/soul")
                soul_text = soul.get("content", "") if isinstance(soul, dict) else ""
                if soul_text:
                    # Show first 500 chars
                    preview = soul_text[:500].replace("\n", "\n> ")
                    self.log(f"- **SOUL.md** ({len(soul_text)} chars):\n> {preview}{'...' if len(soul_text) > 500 else ''}")
                else:
                    self.log(f"- **SOUL.md**: EMPTY ✗")

                # Config
                config = await self.get(http, f"/api/agents/{aid}/config")
                if isinstance(config, dict):
                    model = config.get("model", "(not set)")
                    self.log(f"- **Model (config)**: `{model}`")

                # Memories
                memories = await self.get(http, f"/api/agents/{aid}/memories")
                if isinstance(memories, dict):
                    mem = memories.get("memory", "")
                    user = memories.get("user", "")
                    self.log(f"- **Memory**: {len(mem)} chars")
                    self.log(f"- **User profile**: {len(user)} chars")
                    if user:
                        preview = user[:300].replace("\n", "\n>   ")
                        self.log(f">   {preview}")

                # Skills
                skills = await self.get(http, f"/api/agents/{aid}/skills")
                if isinstance(skills, list):
                    names = [s.get("name") for s in skills]
                    self.log(f"- **Skills**: {names if names else '(none)'}")

                # Cron
                crons = await self.get(http, f"/api/agents/{aid}/cron")
                if isinstance(crons, list) and crons:
                    self.log(f"- **Cron jobs** ({len(crons)}):")
                    for c in crons:
                        self.log(f"  - `{c.get('name')}`: {c.get('schedule')} — \"{c.get('prompt', '')[:80]}\"")
                else:
                    self.log(f"- **Cron jobs**: (none)")

                # Rules
                rules = await self.get(http, f"/api/agents/{aid}/rules")
                if isinstance(rules, list) and rules:
                    self.log(f"- **Rules** ({len(rules)}):")
                    for r in rules:
                        self.log(f"  - `{r.get('name')}`: {r.get('condition', '')[:60]} → {r.get('action', '')[:60]}")
                else:
                    self.log(f"- **Rules**: (none)")

                # Avatar
                avatar = await self.get(http, f"/api/agents/{aid}/avatar")
                if isinstance(avatar, dict):
                    has = bool(avatar.get("avatar"))
                    fmt = avatar.get("format", "?")
                    self.log(f"- **Avatar**: {'yes' if has else 'no'} (format: {fmt})")

                # Wallet
                wallet = await self.get(http, f"/api/agents/{aid}/wallet")
                if isinstance(wallet, dict) and wallet:
                    self.log(f"- **Wallet**: {list(wallet.keys())}")
                else:
                    self.log(f"- **Wallet**: (empty)")

                # Sessions
                sessions = await self.get(http, f"/api/agents/{aid}/sessions")
                if isinstance(sessions, list):
                    self.log(f"- **Sessions**: {len(sessions)}")
                    for s in sessions[:3]:
                        self.log(f"  - `{s.get('id')}`: {s.get('name', '(untitled)')}")
                    if len(sessions) > 3:
                        self.log(f"  - ... and {len(sessions) - 3} more")

                # Pane widgets
                pane = await self.get(http, f"/api/agents/{aid}/pane")
                if isinstance(pane, dict):
                    tabs = pane.get("tabs", {})
                    home = tabs.get("home", [])
                    self.log(f"- **Pane widgets**: {len(home)} home widgets")

                # Files
                files = await self.get(http, f"/api/agents/{aid}/files")
                if isinstance(files, list) and files:
                    self.log(f"- **Files** ({len(files)}):")
                    for f in files[:5]:
                        self.log(f"  - {f.get('name')} ({f.get('category')}, {f.get('size')} bytes)")

            # ── Connections ──
            self.section("Connections")
            conns = await self.get(http, "/api/connections")
            if isinstance(conns, list):
                for c in conns:
                    enabled = "✓" if c.get("enabled", True) else "✗"
                    self.log(f"- **{c.get('name')}** [{enabled}] type={c.get('type', '?')} — {c.get('description', '')[:80]}")

            # ── Relationships ──
            self.section("Relationships")
            rels = await self.get(http, "/api/relationships")
            if isinstance(rels, list) and rels:
                for r in rels:
                    self.log(f"- {r.get('from_agent_id')} → {r.get('to_agent_id')} ({r.get('type', '?')})")
            else:
                self.log("(none)")

            # ── Analytics ──
            self.section("Analytics")
            analytics = await self.get(http, "/api/analytics?days=30")
            if isinstance(analytics, dict):
                ov = analytics.get("overview", {})
                self.log(f"- Sessions: {ov.get('total_sessions', 0)}")
                self.log(f"- Messages: {ov.get('total_messages', 0)}")
                self.log(f"- Tokens: {ov.get('total_tokens', 0)}")
                self.log(f"- Cost: ${ov.get('estimated_cost', 0):.4f}")
                self.log(f"- Models used: {[m.get('model') for m in analytics.get('models', [])]}")

            # ── Audit log (last 20) ──
            self.section("Recent Audit Events (last 20)")
            events = await self.get(http, "/api/audit?n=20")
            if isinstance(events, list):
                for e in events:
                    self.log(f"- `{e.get('ts', '?')}` **{e.get('event', '?')}** agent={e.get('agent_id', '?')}")

            # ── Integrations ──
            self.section("Integrations")
            integ = await self.get(http, "/api/integrations")
            if isinstance(integ, list):
                for i in integ:
                    self.log(f"- **{i.get('name', i.get('id', '?'))}**: {i.get('status', '?')}")

            # ── Inbox ──
            self.section("Inbox")
            inbox = await self.get(http, "/api/inbox")
            n = len(inbox) if isinstance(inbox, list) else 0
            self.log(f"{n} items")

            # ── Permissions ──
            self.section("Pending Permissions")
            perms = await self.get(http, "/api/permissions")
            n = len(perms) if isinstance(perms, list) else 0
            self.log(f"{n} pending")

        # Write to scratchpad
        with open(SCRATCHPAD, "w") as f:
            f.write("\n".join(self.lines) + "\n")
        print(f"\n{'═'*50}")
        print(f"Audit written to: {SCRATCHPAD}")
        print(f"{'═'*50}")


if __name__ == "__main__":
    asyncio.run(Auditor(BASE).run())
