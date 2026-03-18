"""
Conditional rule storage and management.

Rules are stored in ~/.vulti/rules/rules.json
Each rule defines a condition/action pair that the agent evaluates on every message.
"""

import json
import logging
import tempfile
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


def _get_default_agent_id() -> str:
    """Lazy import to avoid circular dependencies."""
    try:
        from orchestrator.agent_registry import get_default_agent_id
        return get_default_agent_id()
    except Exception:
        return "default"


def _current_agent_id() -> str:
    """Return the active agent ID from AgentContext, env var, or registry default."""
    try:
        from orchestrator.agent_context import AgentContext
        aid = AgentContext.current_agent_id()
        if aid != "default":
            return aid
    except Exception:
        pass
    return os.getenv("VULTI_AGENT_ID") or _get_default_agent_id()


from vulti_time import now as _vulti_now

# =============================================================================
# Configuration
# =============================================================================

VULTI_DIR = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))
RULES_DIR = VULTI_DIR / "rules"
RULES_FILE = RULES_DIR / "rules.json"


def _secure_dir(path: Path):
    """Set directory to owner-only access (0700). No-op on Windows."""
    try:
        os.chmod(path, 0o700)
    except (OSError, NotImplementedError):
        pass


def _secure_file(path: Path):
    """Set file to owner-only read/write (0600). No-op on Windows."""
    try:
        if path.exists():
            os.chmod(path, 0o600)
    except (OSError, NotImplementedError):
        pass


def ensure_dirs():
    """Ensure rules directories exist with secure permissions."""
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    _secure_dir(RULES_DIR)


# =============================================================================
# Rule CRUD Operations
# =============================================================================

def load_rules() -> List[Dict[str, Any]]:
    """Load all rules from storage."""
    ensure_dirs()
    if not RULES_FILE.exists():
        return []

    try:
        with open(RULES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("rules", [])
    except (json.JSONDecodeError, IOError):
        return []


def save_rules(rules: List[Dict[str, Any]]):
    """Save all rules to storage."""
    ensure_dirs()
    fd, tmp_path = tempfile.mkstemp(dir=str(RULES_FILE.parent), suffix='.tmp', prefix='.rules_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump({"rules": rules, "updated_at": _vulti_now().isoformat()}, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, RULES_FILE)
        _secure_file(RULES_FILE)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def create_rule(
    condition: str,
    action: str,
    name: Optional[str] = None,
    priority: int = 0,
    max_triggers: Optional[int] = None,
    cooldown_minutes: Optional[int] = None,
    tags: Optional[List[str]] = None,
    agent: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new conditional rule.

    Args:
        condition: Natural language condition for when this rule triggers
        action: Natural language instruction for what to do when triggered
        name: Optional friendly name
        priority: Execution priority (lower = higher priority, default 0)
        max_triggers: Optional max trigger count before auto-disable (None = unlimited)
        cooldown_minutes: Optional minimum minutes between triggers (None = no cooldown)
        tags: Optional list of tags for organization
        agent: Agent ID that owns this rule

    Returns:
        The created rule dict
    """
    rule_id = uuid.uuid4().hex[:12]
    now = _vulti_now().isoformat()

    rule = {
        "id": rule_id,
        "name": name or condition[:50].strip(),
        "condition": condition,
        "action": action,
        "enabled": True,
        "priority": priority,
        "created_at": now,
        "last_triggered_at": None,
        "trigger_count": 0,
        "max_triggers": max_triggers,
        "cooldown_minutes": cooldown_minutes,
        "tags": tags or [],
        "agent": agent or _current_agent_id(),
    }

    rules = load_rules()
    rules.append(rule)
    save_rules(rules)

    return rule


def get_rule(rule_id: str) -> Optional[Dict[str, Any]]:
    """Get a rule by ID."""
    rules = load_rules()
    for rule in rules:
        if rule["id"] == rule_id:
            return rule
    return None


def list_rules(include_disabled: bool = False) -> List[Dict[str, Any]]:
    """List all rules, optionally including disabled ones."""
    rules = load_rules()
    if not include_disabled:
        rules = [r for r in rules if r.get("enabled", True)]
    return rules


def update_rule(rule_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update a rule by ID."""
    rules = load_rules()
    for i, rule in enumerate(rules):
        if rule["id"] != rule_id:
            continue

        updated = {**rule, **updates}
        rules[i] = updated
        save_rules(rules)
        return rules[i]
    return None


def enable_rule(rule_id: str) -> Optional[Dict[str, Any]]:
    """Enable a disabled rule."""
    return update_rule(rule_id, {"enabled": True})


def disable_rule(rule_id: str) -> Optional[Dict[str, Any]]:
    """Disable a rule without deleting it."""
    return update_rule(rule_id, {"enabled": False})


def remove_rule(rule_id: str) -> bool:
    """Remove a rule by ID."""
    rules = load_rules()
    original_len = len(rules)
    rules = [r for r in rules if r["id"] != rule_id]
    if len(rules) < original_len:
        save_rules(rules)
        return True
    return False


def record_trigger(rule_id: str) -> Optional[Dict[str, Any]]:
    """
    Record that a rule was triggered.

    Updates last_triggered_at, increments trigger_count,
    and auto-disables if max_triggers is reached.
    """
    rules = load_rules()
    for i, rule in enumerate(rules):
        if rule["id"] == rule_id:
            now = _vulti_now().isoformat()
            rule["last_triggered_at"] = now
            rule["trigger_count"] = rule.get("trigger_count", 0) + 1

            # Auto-disable if max_triggers reached
            max_t = rule.get("max_triggers")
            if max_t is not None and rule["trigger_count"] >= max_t:
                rule["enabled"] = False

            rules[i] = rule
            save_rules(rules)
            return rule
    return None


def get_active_rules(agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get all active rules for an agent, respecting cooldowns.

    Rules within their cooldown window are excluded.
    Returns rules sorted by priority (lowest first).
    """
    now = _vulti_now()
    effective_agent = agent_id or _current_agent_id()
    rules = load_rules()
    active = []

    for rule in rules:
        if not rule.get("enabled", True):
            continue

        # Filter by agent
        if rule.get("agent", "default") != effective_agent:
            continue

        # Check cooldown
        cooldown = rule.get("cooldown_minutes")
        last_triggered = rule.get("last_triggered_at")
        if cooldown and last_triggered:
            try:
                last_dt = datetime.fromisoformat(last_triggered)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=now.tzinfo)
                if (now - last_dt).total_seconds() < cooldown * 60:
                    continue  # Still in cooldown
            except (ValueError, TypeError):
                pass  # Invalid timestamp, skip cooldown check

        active.append(rule)

    # Sort by priority (lower = higher priority)
    active.sort(key=lambda r: r.get("priority", 0))
    return active
