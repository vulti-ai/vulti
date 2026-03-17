"""
Rule subcommand for vulti CLI.

Handles standalone rule management commands like list, create, edit,
enable/disable/remove.
"""

import json
import sys
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from vulti_cli.colors import Colors, color


def _rule_api(**kwargs):
    from tools.rule_tools import rule as rule_tool

    return json.loads(rule_tool(**kwargs))


def rule_list(show_all: bool = False):
    """List all rules."""
    from rules.rules import list_rules

    rules = list_rules(include_disabled=show_all)

    if not rules:
        print(color("No rules configured.", Colors.DIM))
        print(color("Create one with 'vulti rule create ...' or the /rule command in chat.", Colors.DIM))
        return

    print()
    print(color("┌─────────────────────────────────────────────────────────────────────────┐", Colors.CYAN))
    print(color("│                         Conditional Rules                               │", Colors.CYAN))
    print(color("└─────────────────────────────────────────────────────────────────────────┘", Colors.CYAN))
    print()

    for r in rules:
        rule_id = r.get("id", "?")[:8]
        name = r.get("name", "(unnamed)")
        condition = r.get("condition", "")
        action = r.get("action", "")
        priority = r.get("priority", 0)
        trigger_count = r.get("trigger_count", 0)
        max_triggers = r.get("max_triggers")
        cooldown = r.get("cooldown_minutes")
        tags = r.get("tags", [])

        if r.get("enabled", True):
            status = color("[active]", Colors.GREEN)
        else:
            status = color("[disabled]", Colors.RED)

        triggers_str = str(trigger_count)
        if max_triggers is not None:
            triggers_str = f"{trigger_count}/{max_triggers}"

        print(f"  {color(rule_id, Colors.YELLOW)} {status}  p={priority}")
        print(f"    Name:       {name}")
        print(f"    IF:         {condition[:80]}{'...' if len(condition) > 80 else ''}")
        print(f"    THEN:       {action[:80]}{'...' if len(action) > 80 else ''}")
        print(f"    Triggers:   {triggers_str}")
        if cooldown:
            print(f"    Cooldown:   {cooldown}m")
        if tags:
            print(f"    Tags:       {', '.join(tags)}")
        print()


def rule_create(args):
    result = _rule_api(
        action="create",
        condition=args.condition,
        action_prompt=args.action,
        name=getattr(args, "name", None),
        priority=getattr(args, "priority", None),
        max_triggers=getattr(args, "max_triggers", None),
        cooldown_minutes=getattr(args, "cooldown", None),
        tags=getattr(args, "tags", None),
    )
    if not result.get("success"):
        print(color(f"Failed to create rule: {result.get('error', 'unknown error')}", Colors.RED))
        return 1
    print(color(f"Created rule: {result['rule_id']}", Colors.GREEN))
    print(f"  Name: {result['name']}")
    return 0


def rule_edit(args):
    from rules.rules import get_rule

    r = get_rule(args.rule_id)
    if not r:
        print(color(f"Rule not found: {args.rule_id}", Colors.RED))
        return 1

    kwargs = {"action": "update", "rule_id": args.rule_id}
    if getattr(args, "condition", None) is not None:
        kwargs["condition"] = args.condition
    if getattr(args, "action_prompt", None) is not None:
        kwargs["action_prompt"] = args.action_prompt
    if getattr(args, "name", None) is not None:
        kwargs["name"] = args.name
    if getattr(args, "priority", None) is not None:
        kwargs["priority"] = args.priority
    if getattr(args, "max_triggers", None) is not None:
        kwargs["max_triggers"] = args.max_triggers
    if getattr(args, "cooldown", None) is not None:
        kwargs["cooldown_minutes"] = args.cooldown
    if getattr(args, "tags", None) is not None:
        kwargs["tags"] = args.tags
    if getattr(args, "clear_tags", False):
        kwargs["tags"] = []

    result = _rule_api(**kwargs)
    if not result.get("success"):
        print(color(f"Failed to update rule: {result.get('error', 'unknown error')}", Colors.RED))
        return 1

    updated = result["rule"]
    print(color(f"Updated rule: {updated['rule_id']}", Colors.GREEN))
    print(f"  Name: {updated['name']}")
    return 0


def _rule_action(action: str, rule_id: str, success_verb: str) -> int:
    result = _rule_api(action=action, rule_id=rule_id)
    if not result.get("success"):
        print(color(f"Failed to {action} rule: {result.get('error', 'unknown error')}", Colors.RED))
        return 1
    r = result.get("rule") or result.get("removed_rule") or {}
    print(color(f"{success_verb} rule: {r.get('name', rule_id)} ({rule_id})", Colors.GREEN))
    return 0


def rule_command(args):
    """Handle rule subcommands."""
    subcmd = getattr(args, 'rule_command', None)

    if subcmd is None or subcmd == "list":
        show_all = getattr(args, 'all', False)
        rule_list(show_all)
        return 0

    if subcmd in {"create", "add"}:
        return rule_create(args)

    if subcmd == "edit":
        return rule_edit(args)

    if subcmd == "enable":
        return _rule_action("enable", args.rule_id, "Enabled")

    if subcmd == "disable":
        return _rule_action("disable", args.rule_id, "Disabled")

    if subcmd in {"remove", "rm", "delete"}:
        return _rule_action("remove", args.rule_id, "Removed")

    print(f"Unknown rule command: {subcmd}")
    print("Usage: vulti rule [list|create|edit|enable|disable|remove]")
    sys.exit(1)
