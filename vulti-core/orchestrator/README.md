# Vulti Orchestrator

Multi-agent orchestration layer over [hermes-agent](https://github.com/NousResearch/hermes-agent).

## Architecture

```
┌─────────────────────────────────────────────┐
│  VultiHub (Svelte/Tauri UI)                 │
│  REST API + WebSocket                       │
└────────────────┬────────────────────────────┘
                 │
┌────────────────▼────────────────────────────┐
│  orchestrator/                              │
│  ┌──────────┐ ┌──────────┐ ┌─────────────┐ │
│  │ Agent    │ │ Rules    │ │ Agent Bus   │ │
│  │ Registry │ │ Engine   │ │ (inter-agent│ │
│  │ + Factory│ │          │ │  messaging) │ │
│  └──────────┘ └──────────┘ └─────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌─────────────┐ │
│  │ Gateway  │ │ Cron     │ │ Prompt      │ │
│  │ Router   │ │ Scheduler│ │ Hooks       │ │
│  └──────────┘ └──────────┘ └─────────────┘ │
└────────────────┬────────────────────────────┘
                 │ wraps (no modifications)
┌────────────────▼────────────────────────────┐
│  hermes-agent                               │
│  AIAgent, ToolRegistry, GatewayRunner,      │
│  Platform Adapters, Skills, Memory, etc.    │
└─────────────────────────────────────────────┘
```

## The Thin Bridge Pattern

Hermes-agent is a single-agent runtime. The orchestrator adds multi-agent support
**without modifying hermes-agent files**. The contract between the two layers is
a single environment variable:

```
VULTI_AGENT_ID — set by AgentContext.scope(), read by hermes files
```

### How it works

1. **Hermes files** read `os.getenv("VULTI_AGENT_ID")` to resolve per-agent
   paths (SOUL.md, memories, cron jobs, rules). This is the only modification
   to hermes code — a ~10 line diff from upstream.

2. **The orchestrator** wraps hermes entry points and sets the env var:
   - `VultiGatewayRunner` wraps `GatewayRunner`, adds agent routing, sets
     `VULTI_AGENT_ID` before delegating to the upstream message handler
   - `vulti_tick()` wraps cron's `tick()`, scoping each job to its agent
   - `orchestrator.init()` monkey-patches `_build_system_prompt` to inject
     rules and agent identity, and patches `send_message` for inter-agent targets

3. **AgentContext** is the thread-safe mechanism that sets/restores `VULTI_AGENT_ID`:
   ```python
   with AgentContext.scope("my-agent", hop_count=0):
       # All code here sees VULTI_AGENT_ID=my-agent
       agent.run_conversation(message)
   # Env var restored to previous value
   ```

## Usage

```python
import orchestrator

# Initialize once at startup — patches send_message and prompt builder
orchestrator.init()

# Use VultiGatewayRunner instead of GatewayRunner
from orchestrator.gateway.runner import VultiGatewayRunner
runner = VultiGatewayRunner()
await runner.run()

# Or use vulti_tick for cron with per-agent scoping
from orchestrator.cron import vulti_tick
vulti_tick()
```

## Package Structure

```
orchestrator/
├── __init__.py              # init() — patches and wires everything
├── agent_context.py         # Thread-safe VULTI_AGENT_ID scoping
├── agent_factory.py         # Creates AIAgent with per-agent config
├── agent_registry.py        # Multi-agent CRUD (re-exports vulti_cli)
├── agent_bus.py             # Inter-agent messaging via AgentFactory
├── rules/                   # Rules engine (re-exports rules.rules)
├── cron/
│   ├── __init__.py          # Re-exports + vulti_run_job, vulti_tick
│   └── scheduler.py         # Wraps upstream cron with AgentContext
├── tools/
│   ├── rule_tools.py        # Rule management tool registration
│   ├── cronjob_tools.py     # Cron tool registration
│   └── send_message_ext.py  # Monkey-patch for agent: targets
├── gateway/
│   ├── routing.py           # @mention + routing table → agent_id
│   └── runner.py            # VultiGatewayRunner (wraps GatewayRunner)
└── hooks/
    └── prompt_hook.py       # Per-agent SOUL, rules, identity injection
```

## Compatibility Shims

Upstream hermes-agent uses `hermes_constants`, `hermes_time`, `hermes_state`.
Our fork uses `vulti_constants`, `vulti_time`, `vulti_state`. Three shim files
bridge the gap:

```
hermes_constants.py → from vulti_constants import *
hermes_time.py      → from vulti_time import *
hermes_state.py     → from vulti_state import *
```

## What Lives Where

| Module | Owner | Description |
|--------|-------|-------------|
| `orchestrator/` | Vulti | Multi-agent lifecycle, routing, hooks |
| `vulti_cli/` | Vulti | CLI commands, setup, agent registry |
| `rules/` | Vulti | Conditional rule engine |
| `vulti_constants.py` | Vulti | Shared constants |
| `vulti_time.py` | Vulti | Timezone-aware clock |
| `vulti_state.py` | Vulti | SQLite session store |
| `run_agent.py` | Hermes (local copy) | AIAgent core — env var reads only |
| `agent/` | Hermes (local copy) | Prompt builder, model metadata — env var reads only |
| `tools/` | Hermes (local copy) | Tool implementations — env var reads only |
| `gateway/` | Hermes (local copy) | Platform adapters, session mgmt — env var reads only |
| `cron/` | Hermes (local copy) | Cron storage + scheduler — env var reads only |

## Rebasing from Upstream

The hermes files have a ~10 line diff from upstream (env var reads for
`VULTI_AGENT_ID`). When upstream releases a new version:

1. Fetch upstream changes
2. Rebase — conflicts will be minimal (env var reads are self-contained)
3. Run tests: `pytest tests/`
4. Bump the hermes-agent pin in `pyproject.toml`
