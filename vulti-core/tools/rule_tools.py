"""
Conditional rule management tools for Vulti.

Expose a single compressed action-oriented tool to avoid schema/context bloat.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from rules.rules import (
    create_rule,
    disable_rule,
    enable_rule,
    get_rule,
    list_rules,
    record_trigger,
    remove_rule,
    update_rule,
)


# ---------------------------------------------------------------------------
# Rule prompt scanning — critical-severity patterns only
# ---------------------------------------------------------------------------

_RULE_THREAT_PATTERNS = [
    (r'ignore\s+(?:\w+\s+)*(?:previous|all|above|prior)\s+(?:\w+\s+)*instructions', "prompt_injection"),
    (r'do\s+not\s+tell\s+the\s+user', "deception_hide"),
    (r'system\s+prompt\s+override', "sys_prompt_override"),
    (r'disregard\s+(your|all|any)\s+(instructions|rules|guidelines)', "disregard_rules"),
    (r'curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_curl"),
    (r'wget\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_wget"),
    (r'cat\s+[^\n]*(\.env|credentials|\.netrc|\.pgpass)', "read_secrets"),
    (r'authorized_keys', "ssh_backdoor"),
    (r'/etc/sudoers|visudo', "sudoers_mod"),
    (r'rm\s+-rf\s+/', "destructive_root_rm"),
]

_RULE_INVISIBLE_CHARS = {
    '\u200b', '\u200c', '\u200d', '\u2060', '\ufeff',
    '\u202a', '\u202b', '\u202c', '\u202d', '\u202e',
}


def _scan_rule_prompt(text: str) -> str:
    """Scan a rule condition/action for critical threats. Returns error string if blocked, else empty."""
    for char in _RULE_INVISIBLE_CHARS:
        if char in text:
            return f"Blocked: text contains invisible unicode U+{ord(char):04X} (possible injection)."
    for pattern, pid in _RULE_THREAT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return f"Blocked: text matches threat pattern '{pid}'. Rule conditions/actions must not contain injection or exfiltration payloads."
    return ""


def _format_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    condition = rule.get("condition", "")
    action = rule.get("action", "")
    return {
        "rule_id": rule["id"],
        "name": rule["name"],
        "condition_preview": condition[:100] + "..." if len(condition) > 100 else condition,
        "action_preview": action[:100] + "..." if len(action) > 100 else action,
        "enabled": rule.get("enabled", True),
        "priority": rule.get("priority", 0),
        "trigger_count": rule.get("trigger_count", 0),
        "max_triggers": rule.get("max_triggers"),
        "cooldown_minutes": rule.get("cooldown_minutes"),
        "last_triggered_at": rule.get("last_triggered_at"),
        "tags": rule.get("tags", []),
    }


def rule(
    action: str,
    rule_id: Optional[str] = None,
    condition: Optional[str] = None,
    action_prompt: Optional[str] = None,
    name: Optional[str] = None,
    priority: Optional[int] = None,
    max_triggers: Optional[int] = None,
    cooldown_minutes: Optional[int] = None,
    tags: Optional[List[str]] = None,
    include_disabled: bool = False,
    task_id: str = None,
) -> str:
    """Unified rule management tool."""
    del task_id  # unused but kept for handler signature compatibility

    try:
        normalized = (action or "").strip().lower()

        if normalized == "create":
            if not condition:
                return json.dumps({"success": False, "error": "condition is required for create"}, indent=2)
            if not action_prompt:
                return json.dumps({"success": False, "error": "action_prompt is required for create"}, indent=2)

            # Scan both condition and action for threats
            scan_error = _scan_rule_prompt(condition)
            if scan_error:
                return json.dumps({"success": False, "error": f"Condition: {scan_error}"}, indent=2)
            scan_error = _scan_rule_prompt(action_prompt)
            if scan_error:
                return json.dumps({"success": False, "error": f"Action: {scan_error}"}, indent=2)

            new_rule = create_rule(
                condition=condition,
                action=action_prompt,
                name=name,
                priority=priority if priority is not None else 0,
                max_triggers=max_triggers,
                cooldown_minutes=cooldown_minutes,
                tags=tags,
            )
            return json.dumps(
                {
                    "success": True,
                    "rule_id": new_rule["id"],
                    "name": new_rule["name"],
                    "rule": _format_rule(new_rule),
                    "message": f"Rule '{new_rule['name']}' created.",
                },
                indent=2,
            )

        if normalized == "list":
            rules = [_format_rule(r) for r in list_rules(include_disabled=include_disabled)]
            return json.dumps({"success": True, "count": len(rules), "rules": rules}, indent=2)

        if normalized == "record":
            if not rule_id:
                return json.dumps({"success": False, "error": "rule_id is required for record"}, indent=2)
            updated = record_trigger(rule_id)
            if not updated:
                return json.dumps({"success": False, "error": f"Rule '{rule_id}' not found."}, indent=2)
            try:
                from orchestrator.audit import emit as audit_emit
                audit_emit("rule_trigger", details={
                    "rule_id": rule_id,
                    "rule_name": updated.get("name"),
                    "trigger_count": updated.get("trigger_count", 0),
                })
            except Exception:
                pass
            return json.dumps(
                {
                    "success": True,
                    "rule_id": rule_id,
                    "trigger_count": updated.get("trigger_count", 0),
                    "enabled": updated.get("enabled", True),
                    "message": f"Trigger recorded for rule '{updated['name']}'."
                    + (" Rule auto-disabled (max triggers reached)." if not updated.get("enabled", True) else ""),
                },
                indent=2,
            )

        if not rule_id:
            return json.dumps({"success": False, "error": f"rule_id is required for action '{normalized}'"}, indent=2)

        existing = get_rule(rule_id)
        if not existing:
            return json.dumps(
                {"success": False, "error": f"Rule with ID '{rule_id}' not found. Use rule(action='list') to inspect rules."},
                indent=2,
            )

        if normalized == "get":
            return json.dumps(
                {
                    "success": True,
                    "rule": {
                        **_format_rule(existing),
                        "condition": existing.get("condition", ""),
                        "action": existing.get("action", ""),
                        "created_at": existing.get("created_at"),
                        "agent": existing.get("agent", "default"),
                    },
                },
                indent=2,
            )

        if normalized == "remove":
            removed = remove_rule(rule_id)
            if not removed:
                return json.dumps({"success": False, "error": f"Failed to remove rule '{rule_id}'"}, indent=2)
            return json.dumps(
                {
                    "success": True,
                    "message": f"Rule '{existing['name']}' removed.",
                    "removed_rule": {"id": rule_id, "name": existing["name"]},
                },
                indent=2,
            )

        if normalized == "enable":
            updated = enable_rule(rule_id)
            return json.dumps({"success": True, "rule": _format_rule(updated)}, indent=2)

        if normalized == "disable":
            updated = disable_rule(rule_id)
            return json.dumps({"success": True, "rule": _format_rule(updated)}, indent=2)

        if normalized == "update":
            updates: Dict[str, Any] = {}
            if condition is not None:
                scan_error = _scan_rule_prompt(condition)
                if scan_error:
                    return json.dumps({"success": False, "error": f"Condition: {scan_error}"}, indent=2)
                updates["condition"] = condition
            if action_prompt is not None:
                scan_error = _scan_rule_prompt(action_prompt)
                if scan_error:
                    return json.dumps({"success": False, "error": f"Action: {scan_error}"}, indent=2)
                updates["action"] = action_prompt
            if name is not None:
                updates["name"] = name
            if priority is not None:
                updates["priority"] = priority
            if max_triggers is not None:
                updates["max_triggers"] = max_triggers
            if cooldown_minutes is not None:
                updates["cooldown_minutes"] = cooldown_minutes
            if tags is not None:
                updates["tags"] = tags
            if not updates:
                return json.dumps({"success": False, "error": "No updates provided."}, indent=2)
            updated = update_rule(rule_id, updates)
            return json.dumps({"success": True, "rule": _format_rule(updated)}, indent=2)

        return json.dumps({"success": False, "error": f"Unknown rule action '{action}'"}, indent=2)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


RULE_SCHEMA = {
    "name": "rule",
    "description": """Manage conditional automation rules that trigger on matching messages.

Use action='create' to define a new rule with a condition and action.
Use action='list' to see all rules.
Use action='get', 'update', 'enable', 'disable', 'remove' to manage an existing rule.
Use action='record' to log that a rule was triggered (call this after executing a rule's action).

Rules are evaluated against every incoming message. When a rule's condition matches,
execute the rule's action using your available tools, then call rule(action='record', rule_id='...')
to track the trigger. The agent decides whether a condition matches based on semantic understanding.

Example: rule(action='create', condition='message is a purchase receipt', action_prompt='Save to Google Drive and log the amount')""",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "One of: create, list, get, update, enable, disable, remove, record"
            },
            "rule_id": {
                "type": "string",
                "description": "Required for get/update/enable/disable/remove/record"
            },
            "condition": {
                "type": "string",
                "description": "For create/update: natural language condition describing when this rule should trigger"
            },
            "action_prompt": {
                "type": "string",
                "description": "For create/update: natural language instruction for what to do when triggered"
            },
            "name": {
                "type": "string",
                "description": "Optional human-friendly name"
            },
            "priority": {
                "type": "integer",
                "description": "Optional priority (lower = higher priority, default 0)"
            },
            "max_triggers": {
                "type": "integer",
                "description": "Optional max trigger count before auto-disable. Omit for unlimited."
            },
            "cooldown_minutes": {
                "type": "integer",
                "description": "Optional minimum minutes between triggers"
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tags for organization"
            },
            "include_disabled": {
                "type": "boolean",
                "description": "For list: include disabled rules"
            }
        },
        "required": ["action"]
    }
}


def check_rule_requirements() -> bool:
    """
    Check if rule tools can be used.

    Available in interactive CLI mode and gateway/messaging platforms.
    """
    return bool(
        os.getenv("VULTI_INTERACTIVE")
        or os.getenv("VULTI_GATEWAY_SESSION")
        or os.getenv("VULTI_EXEC_ASK")
    )


def get_rule_tool_definitions():
    """Return tool definitions for rule management."""
    return [RULE_SCHEMA]


# --- Registry ---
from tools.registry import registry

registry.register(
    name="rule",
    toolset="rule",
    schema=RULE_SCHEMA,
    handler=lambda args, **kw: rule(
        action=args.get("action", ""),
        rule_id=args.get("rule_id"),
        condition=args.get("condition"),
        action_prompt=args.get("action_prompt"),
        name=args.get("name"),
        priority=args.get("priority"),
        max_triggers=args.get("max_triggers"),
        cooldown_minutes=args.get("cooldown_minutes"),
        tags=args.get("tags"),
        include_disabled=args.get("include_disabled", False),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_rule_requirements,
    emoji="📋",
)
