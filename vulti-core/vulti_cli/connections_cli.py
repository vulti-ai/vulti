"""CLI commands for managing the global connection registry.

Handles ``/connections`` (or ``/conn``) slash commands in the interactive CLI
and the ``vulti connections`` subcommand group from the shell.
"""

import os
import sys
from pathlib import Path
from typing import Optional

from vulti_cli.config import get_vulti_home, get_connections_path
from vulti_cli.connection_registry import ConnectionEntry, ConnectionRegistry
from vulti_cli.agent_registry import AgentRegistry
from orchestrator.permissions import (
    add_allowed_connection,
    get_allowed_connections,
    remove_allowed_connection,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _registry() -> ConnectionRegistry:
    return ConnectionRegistry(get_vulti_home())


def _agent_registry() -> AgentRegistry:
    return AgentRegistry(get_vulti_home())


def _print_info(msg: str) -> None:
    print(f"  \033[36m{msg}\033[0m")


def _print_success(msg: str) -> None:
    print(f"  \033[32m{msg}\033[0m")


def _print_warning(msg: str) -> None:
    print(f"  \033[33m{msg}\033[0m")


def _print_error(msg: str) -> None:
    print(f"  \033[31m{msg}\033[0m")


def _redact(value: str) -> str:
    """Redact a credential value for display."""
    if len(value) <= 8:
        return "****"
    return value[:4] + "..." + value[-4:]


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_list() -> None:
    """List all defined connections with agent usage info."""
    reg = _registry()
    connections = reg.list_all()

    if not connections:
        _print_info("No connections defined yet.")
        _print_info(f"Add one with: /connections add <name>")
        _print_info(f"Or import from .env: /connections import-env")
        return

    agent_reg = _agent_registry()
    agents = agent_reg.list_agents()

    print()
    for conn in connections:
        status = "\033[32m[enabled]\033[0m" if conn.enabled else "\033[33m[disabled]\033[0m"
        tags_str = ", ".join(conn.tags) if conn.tags else ""
        tag_part = f" ({tags_str})" if tags_str else ""

        # Which agents have this connection allowed?
        users = [a.id for a in agents if conn.name in get_allowed_connections(a.id)]
        users_str = ", ".join(users) if users else "none"

        print(f"  {conn.name} [{conn.type}]{tag_part} {status}")
        print(f"    {conn.description}")
        print(f"    Agents: {users_str}")
        print()


def cmd_add(name: str) -> None:
    """Add a new connection interactively."""
    reg = _registry()

    if reg.get(name):
        _print_error(f"Connection '{name}' already exists. Use /connections remove first.")
        return

    print(f"\n  Adding connection: {name}")
    print()

    # Type
    conn_type = input("  Type (mcp/api_key/oauth/custom) [api_key]: ").strip() or "api_key"
    if conn_type not in ("mcp", "api_key", "oauth", "custom"):
        _print_error(f"Unknown type: {conn_type}")
        return

    description = input("  Description: ").strip()
    tags_input = input("  Tags (comma-separated): ").strip()
    tags = [t.strip() for t in tags_input.split(",") if t.strip()] if tags_input else []

    # Credentials
    credentials = {}
    print("  Credentials (enter ENV_VAR=value pairs, empty line to finish):")
    while True:
        pair = input("    > ").strip()
        if not pair:
            break
        if "=" not in pair:
            _print_warning("Format: ENV_VAR=value")
            continue
        key, _, value = pair.partition("=")
        credentials[key.strip()] = value.strip()

    # MCP-specific config
    mcp = {}
    if conn_type == "mcp":
        command = input("  MCP command (e.g., npx): ").strip()
        args_input = input("  MCP args (space-separated): ").strip()
        mcp_args = args_input.split() if args_input else []
        mcp = {"command": command, "args": mcp_args}
        timeout = input("  Timeout [120]: ").strip()
        if timeout:
            mcp["timeout"] = int(timeout)

    # Toolsets
    provides_toolsets = []
    if conn_type != "mcp":
        ts_input = input("  Provides toolsets (comma-separated, optional): ").strip()
        provides_toolsets = [t.strip() for t in ts_input.split(",") if t.strip()] if ts_input else []

    entry = ConnectionEntry(
        name=name,
        type=conn_type,
        description=description,
        tags=tags,
        credentials=credentials,
        mcp=mcp,
        provides_toolsets=provides_toolsets,
    )
    reg.add(name, entry)
    _print_success(f"Connection '{name}' added.")

    # Offer to allow for an agent
    agent_reg = _agent_registry()
    agents = agent_reg.list_agents()
    if agents:
        agent_names = ", ".join(a.id for a in agents)
        allow_input = input(f"  Allow for agent? ({agent_names}) [skip]: ").strip()
        if allow_input and allow_input != "skip":
            cmd_allow(allow_input, name)


def cmd_remove(name: str) -> None:
    """Remove a connection."""
    reg = _registry()

    if not reg.get(name):
        _print_error(f"Connection '{name}' not found.")
        return

    # Warn if agents reference it
    agent_reg = _agent_registry()
    users = [a.id for a in agent_reg.list_agents() if name in get_allowed_connections(a.id)]
    if users:
        _print_warning(f"Warning: used by agents: {', '.join(users)}")
        confirm = input("  Remove anyway? [y/N]: ").strip().lower()
        if confirm != "y":
            _print_info("Cancelled.")
            return
        # Clean up allow lists
        for agent_id in users:
            remove_allowed_connection(agent_id, name)

    reg.remove(name)
    _print_success(f"Connection '{name}' removed.")


def cmd_show(name: str) -> None:
    """Show connection details with redacted credentials."""
    reg = _registry()
    conn = reg.get(name)
    if not conn:
        _print_error(f"Connection '{name}' not found.")
        return

    print(f"\n  Name: {conn.name}")
    print(f"  Type: {conn.type}")
    print(f"  Description: {conn.description}")
    print(f"  Tags: {', '.join(conn.tags) if conn.tags else 'none'}")
    print(f"  Enabled: {conn.enabled}")
    if conn.provides_toolsets:
        print(f"  Toolsets: {', '.join(conn.provides_toolsets)}")
    if conn.mcp:
        print(f"  MCP: {conn.mcp}")
    print("  Credentials:")
    for key, value in conn.credentials.items():
        print(f"    {key} = {_redact(value)}")
    print()


def cmd_allow(agent_id: str, conn_name: str) -> None:
    """Grant an agent access to a connection."""
    reg = _registry()
    if not reg.get(conn_name):
        _print_error(f"Connection '{conn_name}' not found.")
        return

    agent_reg = _agent_registry()
    meta = agent_reg.get_agent(agent_id)
    if not meta:
        _print_error(f"Agent '{agent_id}' not found.")
        return

    allowed = get_allowed_connections(agent_id)
    if conn_name in allowed:
        _print_info(f"Agent '{agent_id}' already has access to '{conn_name}'.")
        return

    add_allowed_connection(agent_id, conn_name)
    _print_success(f"Agent '{agent_id}' can now use connection '{conn_name}'.")


def cmd_revoke(agent_id: str, conn_name: str) -> None:
    """Remove an agent's access to a connection."""
    agent_reg = _agent_registry()
    meta = agent_reg.get_agent(agent_id)
    if not meta:
        _print_error(f"Agent '{agent_id}' not found.")
        return

    allowed = get_allowed_connections(agent_id)
    if conn_name not in allowed:
        _print_info(f"Agent '{agent_id}' doesn't have access to '{conn_name}'.")
        return

    remove_allowed_connection(agent_id, conn_name)
    _print_success(f"Revoked '{conn_name}' from agent '{agent_id}'.")


def cmd_audit() -> None:
    """Show a matrix of agents x connections."""
    reg = _registry()
    connections = reg.list_all()
    if not connections:
        _print_info("No connections defined.")
        return

    agent_reg = _agent_registry()
    agents = agent_reg.list_agents()
    if not agents:
        _print_info("No agents registered.")
        return

    conn_names = [c.name for c in connections]

    # Header
    max_agent_len = max(len(a.id) for a in agents)
    header = " " * (max_agent_len + 2)
    for cn in conn_names:
        header += f" {cn[:12]:>12}"
    print(f"\n{header}")
    print("  " + "-" * (len(header) - 2))

    for agent in agents:
        allowed = set(get_allowed_connections(agent.id))
        row = f"  {agent.id:<{max_agent_len}}"
        for cn in conn_names:
            if cn in allowed:
                row += f" {'yes':>12}"
            else:
                row += f" {'-':>12}"
        print(row)
    print()


def cmd_import_env() -> None:
    """Import connections from existing .env and mcp_servers config."""
    from vulti_cli.config import load_config, get_env_path

    reg = _registry()
    existing = reg.load()
    added = 0

    # Import from .env
    env_path = get_env_path()
    if env_path.exists():
        try:
            from dotenv import dotenv_values
            env_vals = dotenv_values(str(env_path))
        except ImportError:
            env_vals = {}
            _print_warning("python-dotenv not installed, reading .env manually")
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env_vals[k.strip()] = v.strip().strip('"').strip("'")

        # Known API key patterns
        _API_KEY_PATTERNS = {
            "FIRECRAWL_API_KEY": ("firecrawl", "Firecrawl web scraping", ["web", "scraping"], ["web"]),
            "FAL_KEY": ("fal", "fal.ai image generation", ["image", "generation"], ["image"]),
            "BROWSERBASE_API_KEY": ("browserbase", "BrowserBase cloud browser", ["browser"], ["browser"]),
            "HONCHO_API_KEY": ("honcho", "Honcho AI user modeling", ["memory", "context"], []),
            "VOICE_TOOLS_OPENAI_KEY": ("openai-voice", "OpenAI TTS/STT", ["audio", "tts", "stt"], ["tts"]),
        }

        for env_key, (conn_name, desc, tags, toolsets) in _API_KEY_PATTERNS.items():
            if env_key in env_vals and env_vals[env_key] and conn_name not in existing:
                entry = ConnectionEntry(
                    name=conn_name,
                    type="api_key",
                    description=desc,
                    tags=tags,
                    credentials={env_key: env_vals[env_key]},
                    provides_toolsets=toolsets,
                )
                reg.add(conn_name, entry)
                existing[conn_name] = entry
                added += 1
                _print_success(f"Imported: {conn_name} (from {env_key})")

    # Import from mcp_servers in config.yaml
    try:
        config = load_config()
        mcp_servers = config.get("mcp_servers", {})
        if isinstance(mcp_servers, dict):
            for name, cfg in mcp_servers.items():
                if name not in existing:
                    creds = cfg.pop("env", {}) if isinstance(cfg.get("env"), dict) else {}
                    entry = ConnectionEntry(
                        name=name,
                        type="mcp",
                        description=f"MCP server: {name}",
                        tags=["mcp"],
                        credentials=creds,
                        mcp={k: v for k, v in cfg.items() if k not in ("enabled",)},
                    )
                    reg.add(name, entry)
                    existing[name] = entry
                    added += 1
                    _print_success(f"Imported MCP: {name}")
    except Exception as e:
        _print_warning(f"Could not read mcp_servers from config: {e}")

    if added == 0:
        _print_info("Nothing new to import.")
    else:
        _print_success(f"\nImported {added} connection(s).")
        _print_info("Use '/connections allow <agent-id> <name>' to grant agent access.")


def cmd_test(name: str) -> None:
    """Test a connection (basic connectivity check)."""
    reg = _registry()
    conn = reg.get(name)
    if not conn:
        _print_error(f"Connection '{name}' not found.")
        return

    if conn.type == "api_key":
        missing = [k for k, v in conn.credentials.items() if not v]
        if missing:
            _print_error(f"Missing credential values: {', '.join(missing)}")
        else:
            _print_success(f"Connection '{name}': all credential keys have values.")

    elif conn.type == "mcp":
        command = conn.mcp.get("command")
        if not command:
            _print_error("No MCP command configured.")
            return
        import shutil as sh
        if sh.which(command):
            _print_success(f"MCP command '{command}' found in PATH.")
        else:
            _print_warning(f"MCP command '{command}' not found in PATH.")
    else:
        _print_info(f"No automated test for type '{conn.type}'. Credentials present: {bool(conn.credentials)}")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def handle_connections_command(args_str: str) -> None:
    """Dispatch /connections subcommands.

    Called from ``cli.py`` ``process_command()`` with everything after
    ``/connections`` as a single string.
    """
    parts = args_str.strip().split()
    subcmd = parts[0] if parts else "list"
    rest = parts[1:]

    if subcmd == "list":
        cmd_list()
    elif subcmd == "add":
        if not rest:
            _print_error("Usage: /connections add <name>")
            return
        cmd_add(rest[0])
    elif subcmd == "remove":
        if not rest:
            _print_error("Usage: /connections remove <name>")
            return
        cmd_remove(rest[0])
    elif subcmd == "show":
        if not rest:
            _print_error("Usage: /connections show <name>")
            return
        cmd_show(rest[0])
    elif subcmd == "allow":
        if len(rest) < 2:
            _print_error("Usage: /connections allow <agent-id> <connection-name>")
            return
        cmd_allow(rest[0], rest[1])
    elif subcmd == "revoke":
        if len(rest) < 2:
            _print_error("Usage: /connections revoke <agent-id> <connection-name>")
            return
        cmd_revoke(rest[0], rest[1])
    elif subcmd == "audit":
        cmd_audit()
    elif subcmd in ("import-env", "import_env"):
        cmd_import_env()
    elif subcmd == "test":
        if not rest:
            _print_error("Usage: /connections test <name>")
            return
        cmd_test(rest[0])
    else:
        _print_error(f"Unknown subcommand: {subcmd}")
        _print_info("Available: list, add, remove, show, allow, revoke, audit, import-env, test")
