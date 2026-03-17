---
sidebar_position: 20
---

# Plugins

Vulti has a plugin system for adding custom tools, hooks, and integrations without modifying core code.

**→ [Build a Vulti Plugin](/docs/guides/build-a-vulti-plugin)** — step-by-step guide with a complete working example.

## Quick overview

Drop a directory into `~/.vulti/plugins/` with a `plugin.yaml` and Python code:

```
~/.vulti/plugins/my-plugin/
├── plugin.yaml      # manifest
├── __init__.py      # register() — wires schemas to handlers
├── schemas.py       # tool schemas (what the LLM sees)
└── tools.py         # tool handlers (what runs when called)
```

Start Vulti — your tools appear alongside built-in tools. The model can call them immediately.

## What plugins can do

| Capability | How |
|-----------|-----|
| Add tools | `ctx.register_tool(name, schema, handler)` |
| Add hooks | `ctx.register_hook("post_tool_call", callback)` |
| Ship data files | `Path(__file__).parent / "data" / "file.yaml"` |
| Bundle skills | Copy `skill.md` to `~/.vulti/skills/` at load time |
| Gate on env vars | `requires_env: [API_KEY]` in plugin.yaml |
| Distribute via pip | `[project.entry-points."vulti_agent.plugins"]` |

## Plugin discovery

| Source | Path | Use case |
|--------|------|----------|
| User | `~/.vulti/plugins/` | Personal plugins |
| Project | `.vulti/plugins/` | Project-specific plugins |
| pip | `vulti_agent.plugins` entry_points | Distributed packages |

## Available hooks

| Hook | Fires when |
|------|-----------|
| `pre_tool_call` | Before any tool executes |
| `post_tool_call` | After any tool returns |
| `pre_llm_call` | Before LLM API request |
| `post_llm_call` | After LLM API response |
| `on_session_start` | Session begins |
| `on_session_end` | Session ends |

## Managing plugins

```
/plugins              # list loaded plugins in a session
vulti config set display.show_cost true  # show cost in status bar
```

See the **[full guide](/docs/guides/build-a-vulti-plugin)** for handler contracts, schema format, hook behavior, error handling, and common mistakes.
