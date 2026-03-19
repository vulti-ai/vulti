"""
Modify Pane Tool — dynamically update Hub UI widgets.

Allows agents to add, remove, update, and replace widgets in the
right-side content pane of the Vulti Hub. Widgets are scoped per-agent
per-tab and persist across sessions.

Storage: ``~/.vulti/agents/{agent_id}/pane_widgets.json``
"""

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_VULTI_HOME = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))

VALID_TABS = {"profile", "connections", "skills", "actions", "wallet", "analytics"}
VALID_WIDGET_TYPES = {
    "markdown", "kv", "table", "image",
    "status", "stat_grid", "bar_chart", "progress",
    "button", "form", "toggle_list", "action_list", "empty",
}


def _widgets_path(agent_id: str) -> Path:
    return _VULTI_HOME / "agents" / agent_id / "pane_widgets.json"


def _load_widgets(agent_id: str) -> Dict[str, Any]:
    path = _widgets_path(agent_id)
    if not path.exists():
        return {"version": 1, "tabs": {}}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {"version": 1, "tabs": {}}


def _save_widgets(agent_id: str, data: Dict[str, Any]) -> None:
    path = _widgets_path(agent_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _gen_id() -> str:
    return "w_" + uuid.uuid4().hex[:8]


def _ensure_ids(widgets: List[dict]) -> List[dict]:
    for w in widgets:
        if not w.get("id"):
            w["id"] = _gen_id()
    return widgets


def modify_pane(args, **kw) -> str:
    action = (args.get("action") or "").strip().lower()
    # Default to the tab the user is currently viewing in the Hub
    default_tab = os.getenv("VULTI_HUB_CHANNEL", "profile")
    tab = (args.get("tab") or default_tab).strip().lower()
    widgets = args.get("widgets") or []
    widget_id = args.get("widget_id") or ""
    widget_data = args.get("widget_data")

    agent_id = os.getenv("VULTI_AGENT_ID", "default")

    if tab not in VALID_TABS:
        return json.dumps({"success": False, "error": f"Invalid tab '{tab}'. Valid: {', '.join(sorted(VALID_TABS))}"})

    # Validate widget types
    for w in widgets:
        wtype = w.get("type", "")
        if wtype not in VALID_WIDGET_TYPES:
            return json.dumps({"success": False, "error": f"Unknown widget type '{wtype}'. Valid: {', '.join(sorted(VALID_WIDGET_TYPES))}"})

    try:
        if action == "set":
            if not widgets:
                return json.dumps({"success": False, "error": "widgets array required for 'set'"})
            widgets = _ensure_ids(widgets)
            data = _load_widgets(agent_id)
            data["tabs"][tab] = widgets
            _save_widgets(agent_id, data)
            return json.dumps({
                "success": True,
                "message": f"Set {len(widgets)} widget(s) on '{tab}' tab.",
                "pane_update": {"tab": tab, "widgets": widgets},
            })

        elif action == "add":
            if not widgets:
                return json.dumps({"success": False, "error": "widgets array required for 'add'"})
            widgets = _ensure_ids(widgets)
            data = _load_widgets(agent_id)
            existing = data["tabs"].get(tab, [])
            existing.extend(widgets)
            data["tabs"][tab] = existing
            _save_widgets(agent_id, data)
            return json.dumps({
                "success": True,
                "message": f"Added {len(widgets)} widget(s) to '{tab}' tab ({len(existing)} total).",
                "pane_update": {"tab": tab, "widgets": existing},
            })

        elif action == "remove":
            if not widget_id:
                return json.dumps({"success": False, "error": "widget_id required for 'remove'"})
            data = _load_widgets(agent_id)
            existing = data["tabs"].get(tab, [])
            before = len(existing)
            existing = [w for w in existing if w.get("id") != widget_id]
            if len(existing) == before:
                return json.dumps({"success": False, "error": f"Widget '{widget_id}' not found on '{tab}' tab."})
            if existing:
                data["tabs"][tab] = existing
            else:
                data["tabs"].pop(tab, None)
            _save_widgets(agent_id, data)
            result_widgets = existing if existing else None
            return json.dumps({
                "success": True,
                "message": f"Removed widget '{widget_id}' from '{tab}' tab.",
                "pane_update": {"tab": tab, "widgets": result_widgets},
            })

        elif action == "update":
            if not widget_id:
                return json.dumps({"success": False, "error": "widget_id required for 'update'"})
            if not widget_data and not widgets:
                return json.dumps({"success": False, "error": "widget_data or widgets[0] required for 'update'"})
            update_with = widget_data if widget_data else (widgets[0] if widgets else {})
            data = _load_widgets(agent_id)
            existing = data["tabs"].get(tab, [])
            found = False
            for w in existing:
                if w.get("id") == widget_id:
                    if update_with.get("title") is not None:
                        w["title"] = update_with["title"]
                    if update_with.get("data") is not None:
                        w["data"] = update_with["data"]
                    if update_with.get("type") is not None:
                        w["type"] = update_with["type"]
                    found = True
                    break
            if not found:
                return json.dumps({"success": False, "error": f"Widget '{widget_id}' not found on '{tab}' tab."})
            data["tabs"][tab] = existing
            _save_widgets(agent_id, data)
            return json.dumps({
                "success": True,
                "message": f"Updated widget '{widget_id}' on '{tab}' tab.",
                "pane_update": {"tab": tab, "widgets": existing},
            })

        elif action == "list":
            data = _load_widgets(agent_id)
            if tab:
                tab_widgets = data["tabs"].get(tab, [])
                return json.dumps({
                    "success": True,
                    "tab": tab,
                    "widgets": tab_widgets,
                    "count": len(tab_widgets),
                    "is_default": len(tab_widgets) == 0,
                })
            else:
                return json.dumps({
                    "success": True,
                    "tabs": {t: len(ws) for t, ws in data["tabs"].items()},
                })

        elif action == "clear":
            data = _load_widgets(agent_id)
            if tab:
                data["tabs"].pop(tab, None)
            else:
                data["tabs"] = {}
            _save_widgets(agent_id, data)
            return json.dumps({
                "success": True,
                "message": f"Cleared widgets on '{tab}' tab. Default view restored." if tab else "Cleared all custom widgets.",
                "pane_update": {"tab": tab, "widgets": None},
            })

        else:
            return json.dumps({"success": False, "error": f"Unknown action '{action}'. Use: set, add, remove, update, list, clear"})

    except Exception as e:
        logger.error("modify_pane error: %s", e)
        return json.dumps({"success": False, "error": str(e)})


MODIFY_PANE_SCHEMA = {
    "name": "modify_pane",
    "description": (
        "Manage widgets in the Hub's right-side content pane for this agent.\n\n"
        "Actions:\n"
        "  set    — Replace all widgets on a tab\n"
        "  add    — Append widget(s) to a tab\n"
        "  remove — Remove a widget by ID\n"
        "  update — Update a widget's data by ID\n"
        "  list   — Show current widgets\n"
        "  clear  — Restore default static view\n\n"
        "Widget types:\n"
        "  markdown    — Rich text (data: {content})\n"
        "  kv          — Key-value pairs (data: {entries: [{key, value, mono?, masked?}]})\n"
        "  table       — Data table (data: {columns: [...], rows: [[...]]})\n"
        "  image       — Image display (data: {src, alt?, width?, height?})\n"
        "  status      — Colored indicator (data: {label, variant: success|warning|error|info, detail?})\n"
        "  stat_grid   — Metric cards grid (data: {columns?: 2|3|4, stats: [{label, value, unit?}]})\n"
        "  bar_chart   — Bar chart (data: {orientation?: h|v, items: [{label, value, max?}]})\n"
        "  progress    — Progress bar (data: {label?, percent?: 0-100, variant?, indeterminate?})\n"
        "  button      — Action button (data: {label, message, variant?: primary|secondary|danger})\n"
        "  form        — Input form (data: {fields: [{name, label, type, placeholder?}], submit_label, message_template})\n"
        "  toggle_list — Toggleable items (data: {items: [{id, label, description?, enabled, tags?}], on_toggle_message})\n"
        "  action_list — Items with buttons (data: {items: [{id, title, subtitle?, status?, actions: [{label, message, variant?}]}]})\n"
        "  empty       — Empty state (data: {icon?: clock|bolt|book|search, heading, subtext?, button?: {label, message}})\n\n"
        "Tabs: profile, connections, skills, actions, wallet, analytics\n"
        "Widgets replace the default tab view when set. Use clear to restore defaults."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "One of: set, add, remove, update, list, clear",
            },
            "tab": {
                "type": "string",
                "description": "Target tab. Defaults to the tab the user is currently viewing. Options: profile, connections, skills, actions, wallet, analytics",
            },
            "widgets": {
                "type": "array",
                "description": "For set/add: widget definitions. For update: single widget with updated fields.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Widget ID (auto-generated if omitted)"},
                        "type": {"type": "string", "description": "Widget type"},
                        "title": {"type": "string", "description": "Optional heading"},
                        "data": {"type": "object", "description": "Type-specific payload"},
                    },
                    "required": ["type", "data"],
                },
            },
            "widget_id": {
                "type": "string",
                "description": "For remove/update: target widget ID",
            },
            "widget_data": {
                "type": "object",
                "description": "For update: new data payload for the widget",
            },
        },
        "required": ["action"],
    },
}


def _check_modify_pane():
    return bool(
        os.getenv("VULTI_INTERACTIVE")
        or os.getenv("VULTI_GATEWAY_SESSION")
        or os.getenv("VULTI_SESSION_PLATFORM")
        or os.getenv("VULTI_AGENT_ID")
    )


from tools.registry import registry

registry.register(
    name="modify_pane",
    toolset="ui",
    schema=MODIFY_PANE_SCHEMA,
    handler=modify_pane,
    check_fn=_check_modify_pane,
    emoji="🎨",
)
