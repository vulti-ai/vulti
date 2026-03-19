"""System prompt assembly -- identity, platform hints, skills index, context files.

All functions are stateless. AIAgent._build_system_prompt() calls these to
assemble pieces, then combines them with memory and ephemeral prompts.
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context file scanning — detect prompt injection in AGENTS.md, .cursorrules,
# SOUL.md before they get injected into the system prompt.
# ---------------------------------------------------------------------------

_CONTEXT_THREAT_PATTERNS = [
    (r'ignore\s+(previous|all|above|prior)\s+instructions', "prompt_injection"),
    (r'do\s+not\s+tell\s+the\s+user', "deception_hide"),
    (r'system\s+prompt\s+override', "sys_prompt_override"),
    (r'disregard\s+(your|all|any)\s+(instructions|rules|guidelines)', "disregard_rules"),
    (r'act\s+as\s+(if|though)\s+you\s+(have\s+no|don\'t\s+have)\s+(restrictions|limits|rules)', "bypass_restrictions"),
    (r'<!--[^>]*(?:ignore|override|system|secret|hidden)[^>]*-->', "html_comment_injection"),
    (r'<\s*div\s+style\s*=\s*["\'].*display\s*:\s*none', "hidden_div"),
    (r'translate\s+.*\s+into\s+.*\s+and\s+(execute|run|eval)', "translate_execute"),
    (r'curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_curl"),
    (r'cat\s+[^\n]*(\.env|credentials|\.netrc|\.pgpass)', "read_secrets"),
]

_CONTEXT_INVISIBLE_CHARS = {
    '\u200b', '\u200c', '\u200d', '\u2060', '\ufeff',
    '\u202a', '\u202b', '\u202c', '\u202d', '\u202e',
}


def _scan_context_content(content: str, filename: str) -> str:
    """Scan context file content for injection. Returns sanitized content."""
    findings = []

    # Check invisible unicode
    for char in _CONTEXT_INVISIBLE_CHARS:
        if char in content:
            findings.append(f"invisible unicode U+{ord(char):04X}")

    # Check threat patterns
    for pattern, pid in _CONTEXT_THREAT_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            findings.append(pid)

    if findings:
        logger.warning("Context file %s blocked: %s", filename, ", ".join(findings))
        return f"[BLOCKED: {filename} contained potential prompt injection ({', '.join(findings)}). Content not loaded.]"

    return content

# =========================================================================
# Constants
# =========================================================================

DEFAULT_AGENT_IDENTITY = (
    "You are Vulti, an intelligent AI assistant created by Nous Research. "
    "You are helpful, knowledgeable, and direct. You assist users with a wide "
    "range of tasks including answering questions, writing and editing code, "
    "analyzing information, creative work, and executing actions via your tools. "
    "You communicate clearly, admit uncertainty when appropriate, and prioritize "
    "being genuinely useful over being verbose unless otherwise directed below. "
    "Be targeted and efficient in your exploration and investigations."
)

MEMORY_GUIDANCE = (
    "You have persistent memory across sessions. Save durable facts using the memory "
    "tool: user preferences, environment details, tool quirks, and stable conventions. "
    "Memory is injected into every turn, so keep it compact and focused on facts that "
    "will still matter later.\n"
    "Prioritize what reduces future user steering — the most valuable memory is one "
    "that prevents the user from having to correct or remind you again. "
    "User preferences and recurring corrections matter more than procedural task details.\n"
    "Do NOT save task progress, session outcomes, completed-work logs, or temporary TODO "
    "state to memory; use session_search to recall those from past transcripts. "
    "If you've discovered a new way to do something, solved a problem that could be "
    "necessary later, save it as a skill with the skill tool.\n"
    "At the natural end of a substantive conversation (5+ exchanges, or after corrections "
    "or significant learnings), load the 'reflect' skill and run a reflection pass. "
    "This consolidates what you learned into three layers: soul (USER.md — who the user is "
    "at a deep level), memories (MEMORY.md — specific learnings and corrections), and "
    "understanding (your own behavioral calibration). You can also offer: "
    "'Want me to reflect on this session before we close?'"
)

SESSION_SEARCH_GUIDANCE = (
    "When the user references something from a past conversation or you suspect "
    "relevant cross-session context exists, use session_search to recall it before "
    "asking them to repeat themselves."
)

SKILLS_GUIDANCE = (
    "After completing a complex task (5+ tool calls), fixing a tricky error, "
    "or discovering a non-trivial workflow, save the approach as a "
    "skill with skill_manage so you can reuse it next time.\n"
    "When using a skill and finding it outdated, incomplete, or wrong, "
    "patch it immediately with skill_manage(action='patch') — don't wait to be asked. "
    "Skills that aren't maintained become liabilities."
)

PLATFORM_HINTS = {
    "whatsapp": (
        "You are on a text messaging communication platform, WhatsApp. "
        "Please do not use markdown as it does not render. "
        "You can send media files natively: to deliver a file to the user, "
        "include MEDIA:/absolute/path/to/file in your response. The file "
        "will be sent as a native WhatsApp attachment — images (.jpg, .png, "
        ".webp) appear as photos, videos (.mp4, .mov) play inline, and other "
        "files arrive as downloadable documents. You can also include image "
        "URLs in markdown format ![alt](url) and they will be sent as photos."
    ),
    "telegram": (
        "You are on a text messaging communication platform, Telegram. "
        "Please do not use markdown as it does not render. "
        "You can send media files natively: to deliver a file to the user, "
        "include MEDIA:/absolute/path/to/file in your response. Images "
        "(.png, .jpg, .webp) appear as photos, audio (.ogg) sends as voice "
        "bubbles, and videos (.mp4) play inline. You can also include image "
        "URLs in markdown format ![alt](url) and they will be sent as native photos."
    ),
    "discord": (
        "You are in a Discord server or group chat communicating with your user. "
        "You can send media files natively: include MEDIA:/absolute/path/to/file "
        "in your response. Images (.png, .jpg, .webp) are sent as photo "
        "attachments, audio as file attachments. You can also include image URLs "
        "in markdown format ![alt](url) and they will be sent as attachments."
    ),
    "slack": (
        "You are in a Slack workspace communicating with your user. "
        "You can send media files natively: include MEDIA:/absolute/path/to/file "
        "in your response. Images (.png, .jpg, .webp) are uploaded as photo "
        "attachments, audio as file attachments. You can also include image URLs "
        "in markdown format ![alt](url) and they will be uploaded as attachments."
    ),
    "signal": (
        "You are on a text messaging communication platform, Signal. "
        "Please do not use markdown as it does not render. "
        "You can send media files natively: to deliver a file to the user, "
        "include MEDIA:/absolute/path/to/file in your response. Images "
        "(.png, .jpg, .webp) appear as photos, audio as attachments, and other "
        "files arrive as downloadable documents. You can also include image "
        "URLs in markdown format ![alt](url) and they will be sent as photos."
    ),
    "email": (
        "You are communicating via email. Write clear, well-structured responses "
        "suitable for email. Use plain text formatting (no markdown). "
        "Keep responses concise but complete. You can send file attachments — "
        "include MEDIA:/absolute/path/to/file in your response. The subject line "
        "is preserved for threading. Do not include greetings or sign-offs unless "
        "contextually appropriate."
    ),
    "matrix": (
        "You are communicating via Matrix, a federated messaging protocol. "
        "Markdown is fully supported. You can send media files natively: "
        "include MEDIA:/absolute/path/to/file in your response. The file "
        "will be uploaded and sent as a native Matrix attachment. You can "
        "also include image URLs in markdown format ![alt](url) and they "
        "will be sent as image attachments."
    ),
    "cron": (
        "You are running as a scheduled cron job. Your final response is automatically "
        "delivered to the job's configured destination, so do not use send_message to "
        "send to that same target again. If you want the user to receive something in "
        "the scheduled destination, put it directly in your final response. Use "
        "send_message only for additional or different targets."
    ),
    "cli": (
        "You are a CLI AI Agent. Try not to use markdown but simple text "
        "renderable inside a terminal."
    ),
}

CONTEXT_FILE_MAX_CHARS = 20_000
CONTEXT_TRUNCATE_HEAD_RATIO = 0.7
CONTEXT_TRUNCATE_TAIL_RATIO = 0.2


# =========================================================================
# Skills index
# =========================================================================

def _parse_skill_file(skill_file: Path) -> tuple[bool, dict, str]:
    """Read a SKILL.md once and return platform compatibility, frontmatter, and description.

    Returns (is_compatible, frontmatter, description). On any error, returns
    (True, {}, "") to err on the side of showing the skill.
    """
    try:
        from tools.skills_tool import _parse_frontmatter, skill_matches_platform

        raw = skill_file.read_text(encoding="utf-8")[:2000]
        frontmatter, _ = _parse_frontmatter(raw)

        if not skill_matches_platform(frontmatter):
            return False, {}, ""

        desc = ""
        raw_desc = frontmatter.get("description", "")
        if raw_desc:
            desc = str(raw_desc).strip().strip("'\"")
            if len(desc) > 60:
                desc = desc[:57] + "..."

        return True, frontmatter, desc
    except Exception as e:
        logger.debug("Failed to parse skill file %s: %s", skill_file, e)
        return True, {}, ""


def _read_skill_conditions(skill_file: Path) -> dict:
    """Extract conditional activation fields from SKILL.md frontmatter."""
    try:
        from tools.skills_tool import _parse_frontmatter
        raw = skill_file.read_text(encoding="utf-8")[:2000]
        frontmatter, _ = _parse_frontmatter(raw)
        vulti = frontmatter.get("metadata", {}).get("vulti", {})
        return {
            "fallback_for_toolsets": vulti.get("fallback_for_toolsets", []),
            "requires_toolsets": vulti.get("requires_toolsets", []),
            "fallback_for_tools": vulti.get("fallback_for_tools", []),
            "requires_tools": vulti.get("requires_tools", []),
        }
    except Exception as e:
        logger.debug("Failed to read skill conditions from %s: %s", skill_file, e)
        return {}


def _skill_should_show(
    conditions: dict,
    available_tools: "set[str] | None",
    available_toolsets: "set[str] | None",
) -> bool:
    """Return False if the skill's conditional activation rules exclude it."""
    if available_tools is None and available_toolsets is None:
        return True  # No filtering info — show everything (backward compat)

    at = available_tools or set()
    ats = available_toolsets or set()

    # fallback_for: hide when the primary tool/toolset IS available
    for ts in conditions.get("fallback_for_toolsets", []):
        if ts in ats:
            return False
    for t in conditions.get("fallback_for_tools", []):
        if t in at:
            return False

    # requires: hide when a required tool/toolset is NOT available
    for ts in conditions.get("requires_toolsets", []):
        if ts not in ats:
            return False
    for t in conditions.get("requires_tools", []):
        if t not in at:
            return False

    return True


def build_skills_system_prompt(
    available_tools: "set[str] | None" = None,
    available_toolsets: "set[str] | None" = None,
) -> str:
    """Build a compact skill index for the system prompt.

    Scans ~/.vulti/skills/ for SKILL.md files grouped by category.
    Includes per-skill descriptions from frontmatter so the model can
    match skills by meaning, not just name.
    Filters out skills incompatible with the current OS platform.
    """
    vulti_home = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))
    skills_dir = vulti_home / "skills"

    if not skills_dir.exists():
        return ""

    # Collect skills with descriptions, grouped by category.
    # Each entry: (skill_name, description)
    # Supports sub-categories: skills/mlops/training/axolotl/SKILL.md
    # -> category "mlops/training", skill "axolotl"
    skills_by_category: dict[str, list[tuple[str, str]]] = {}
    for skill_file in skills_dir.rglob("SKILL.md"):
        is_compatible, _, desc = _parse_skill_file(skill_file)
        if not is_compatible:
            continue
        # Skip skills whose conditional activation rules exclude them
        conditions = _read_skill_conditions(skill_file)
        if not _skill_should_show(conditions, available_tools, available_toolsets):
            continue
        rel_path = skill_file.relative_to(skills_dir)
        parts = rel_path.parts
        if len(parts) >= 2:
            # Category is everything between skills_dir and the skill folder
            # e.g. parts = ("mlops", "training", "axolotl", "SKILL.md")
            #   → category = "mlops/training", skill_name = "axolotl"
            # e.g. parts = ("github", "github-auth", "SKILL.md")
            #   → category = "github", skill_name = "github-auth"
            skill_name = parts[-2]
            category = "/".join(parts[:-2]) if len(parts) > 2 else parts[0]
        else:
            category = "general"
            skill_name = skill_file.parent.name
        skills_by_category.setdefault(category, []).append((skill_name, desc))

    if not skills_by_category:
        return ""

    # Read category-level descriptions from DESCRIPTION.md
    # Checks both the exact category path and parent directories
    category_descriptions = {}
    for category in skills_by_category:
        cat_path = Path(category)
        desc_file = skills_dir / cat_path / "DESCRIPTION.md"
        if desc_file.exists():
            try:
                content = desc_file.read_text(encoding="utf-8")
                match = re.search(r"^---\s*\n.*?description:\s*(.+?)\s*\n.*?^---", content, re.MULTILINE | re.DOTALL)
                if match:
                    category_descriptions[category] = match.group(1).strip()
            except Exception as e:
                logger.debug("Could not read skill description %s: %s", desc_file, e)

    index_lines = []
    for category in sorted(skills_by_category.keys()):
        cat_desc = category_descriptions.get(category, "")
        if cat_desc:
            index_lines.append(f"  {category}: {cat_desc}")
        else:
            index_lines.append(f"  {category}:")
        # Deduplicate and sort skills within each category
        seen = set()
        for name, desc in sorted(skills_by_category[category], key=lambda x: x[0]):
            if name in seen:
                continue
            seen.add(name)
            if desc:
                index_lines.append(f"    - {name}: {desc}")
            else:
                index_lines.append(f"    - {name}")

    return (
        "## Skills (mandatory)\n"
        "Before replying, scan the skills below. If one clearly matches your task, "
        "load it with skill_view(name) and follow its instructions. "
        "If a skill has issues, fix it with skill_manage(action='patch').\n"
        "After difficult/iterative tasks, offer to save as a skill. "
        "If a skill you loaded was missing steps, had wrong commands, or needed "
        "pitfalls you discovered, update it before finishing.\n"
        "\n"
        "<available_skills>\n"
        + "\n".join(index_lines) + "\n"
        "</available_skills>\n"
        "\n"
        "If none match, proceed normally without loading a skill."
    )


# =========================================================================
# Context files (SOUL.md, AGENTS.md, .cursorrules)
# =========================================================================

def _truncate_content(content: str, filename: str, max_chars: int = CONTEXT_FILE_MAX_CHARS) -> str:
    """Head/tail truncation with a marker in the middle."""
    if len(content) <= max_chars:
        return content
    head_chars = int(max_chars * CONTEXT_TRUNCATE_HEAD_RATIO)
    tail_chars = int(max_chars * CONTEXT_TRUNCATE_TAIL_RATIO)
    head = content[:head_chars]
    tail = content[-tail_chars:]
    marker = f"\n\n[...truncated {filename}: kept {head_chars}+{tail_chars} of {len(content)} chars. Use file tools to read the full file.]\n\n"
    return head + marker + tail


def build_context_files_prompt(cwd: Optional[str] = None, agent_id: Optional[str] = None) -> str:
    """Discover and load context files for the system prompt.

    Discovery: AGENTS.md (recursive), .cursorrules / .cursor/rules/*.mdc,
    and SOUL.md from VULTI_HOME (or per-agent directory). Each capped at 20,000 chars.
    """
    if cwd is None:
        cwd = os.getcwd()

    cwd_path = Path(cwd).resolve()
    sections = []

    # AGENTS.md (hierarchical, recursive)
    top_level_agents = None
    for name in ["AGENTS.md", "agents.md"]:
        candidate = cwd_path / name
        if candidate.exists():
            top_level_agents = candidate
            break

    if top_level_agents:
        agents_files = []
        for root, dirs, files in os.walk(cwd_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', '__pycache__', 'venv', '.venv')]
            for f in files:
                if f.lower() == "agents.md":
                    agents_files.append(Path(root) / f)
        agents_files.sort(key=lambda p: len(p.parts))

        total_agents_content = ""
        for agents_path in agents_files:
            try:
                content = agents_path.read_text(encoding="utf-8").strip()
                if content:
                    rel_path = agents_path.relative_to(cwd_path)
                    content = _scan_context_content(content, str(rel_path))
                    total_agents_content += f"## {rel_path}\n\n{content}\n\n"
            except Exception as e:
                logger.debug("Could not read %s: %s", agents_path, e)

        if total_agents_content:
            total_agents_content = _truncate_content(total_agents_content, "AGENTS.md")
            sections.append(total_agents_content)

    # .cursorrules
    cursorrules_content = ""
    cursorrules_file = cwd_path / ".cursorrules"
    if cursorrules_file.exists():
        try:
            content = cursorrules_file.read_text(encoding="utf-8").strip()
            if content:
                content = _scan_context_content(content, ".cursorrules")
                cursorrules_content += f"## .cursorrules\n\n{content}\n\n"
        except Exception as e:
            logger.debug("Could not read .cursorrules: %s", e)

    cursor_rules_dir = cwd_path / ".cursor" / "rules"
    if cursor_rules_dir.exists() and cursor_rules_dir.is_dir():
        mdc_files = sorted(cursor_rules_dir.glob("*.mdc"))
        for mdc_file in mdc_files:
            try:
                content = mdc_file.read_text(encoding="utf-8").strip()
                if content:
                    content = _scan_context_content(content, f".cursor/rules/{mdc_file.name}")
                    cursorrules_content += f"## .cursor/rules/{mdc_file.name}\n\n{content}\n\n"
            except Exception as e:
                logger.debug("Could not read %s: %s", mdc_file, e)

    if cursorrules_content:
        cursorrules_content = _truncate_content(cursorrules_content, ".cursorrules")
        sections.append(cursorrules_content)

    # SOUL.md: check per-agent directory first, then VULTI_HOME
    try:
        from vulti_cli.config import ensure_vulti_home
        ensure_vulti_home()
    except Exception as e:
        logger.debug("Could not ensure VULTI_HOME before loading SOUL.md: %s", e)

    _vulti_home = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))
    _agent_id = agent_id or os.getenv("VULTI_AGENT_ID")
    soul_path = None
    if _agent_id:
        _agent_soul = _vulti_home / "agents" / _agent_id / "SOUL.md"
        if _agent_soul.exists():
            soul_path = _agent_soul
    if soul_path is None and not _agent_id:
        # Only fall back to global SOUL.md when there's no specific agent
        soul_path = _vulti_home / "SOUL.md"
    if soul_path is not None and soul_path.exists():
        try:
            content = soul_path.read_text(encoding="utf-8").strip()
            if content:
                content = _scan_context_content(content, "SOUL.md")
                content = _truncate_content(content, "SOUL.md")
                sections.append(content)
        except Exception as e:
            logger.debug("Could not read SOUL.md from %s: %s", soul_path, e)

    if not sections:
        return ""
    return "# Project Context\n\nThe following project context files have been loaded and should be followed:\n\n" + "\n".join(sections)


# ---------------------------------------------------------------------------
# Rules prompt injection
# ---------------------------------------------------------------------------

MAX_RULES_IN_PROMPT = 20
MAX_RULE_TEXT_CHARS = 200
MAX_RULES_SECTION_CHARS = 3000


def build_rules_prompt(agent_id: Optional[str] = None) -> str:
    """Build the active rules block for injection into the system prompt.

    Loads enabled rules for the given agent (respecting cooldowns),
    sorts by priority, and renders a compact instruction block.
    Returns empty string if no active rules.
    """
    try:
        from rules.rules import get_active_rules
    except ImportError:
        return ""

    rules = get_active_rules(agent_id)
    if not rules:
        return ""

    total = len(rules)
    shown = rules[:MAX_RULES_IN_PROMPT]

    def _trunc(text: str) -> str:
        text = text.strip().replace("\n", " ")
        if len(text) > MAX_RULE_TEXT_CHARS:
            return text[:MAX_RULE_TEXT_CHARS - 3] + "..."
        return text

    lines = []
    for r in shown:
        name = r.get("name", "unnamed")
        rid = r["id"]
        cond = _trunc(r.get("condition", ""))
        act = _trunc(r.get("action", ""))
        lines.append(f'  [p={r.get("priority", 0)}] {name} (id:{rid}): IF "{cond}" THEN "{act}"')

    rules_block = "\n".join(lines)

    overflow_note = ""
    if total > MAX_RULES_IN_PROMPT:
        overflow_note = f"\n  ({total - MAX_RULES_IN_PROMPT} more rules not shown — consider consolidating or removing unused rules)"

    section = (
        "## Active Rules\n\n"
        "You have conditional rules. For EVERY incoming message, silently evaluate whether\n"
        "any rule's condition matches. If a rule matches, execute its action using your\n"
        "tools BEFORE composing your normal response. Multiple rules can match the same message.\n"
        "Execute them in priority order (lowest number first). After executing a rule's action,\n"
        "call rule(action='record', rule_id='...') to log the trigger.\n"
        "Do not mention rule evaluation to the user unless the rule's action produces a visible result.\n"
        "If no rules match, proceed normally without mentioning rules.\n\n"
        "<rules>\n"
        f"{rules_block}{overflow_note}\n"
        "</rules>"
    )

    # Final size guard
    if len(section) > MAX_RULES_SECTION_CHARS:
        # Drop lowest-priority rules until we fit
        while len(shown) > 1 and len(section) > MAX_RULES_SECTION_CHARS:
            shown = shown[:-1]
            lines = lines[:-1]
            rules_block = "\n".join(lines)
            dropped = total - len(shown)
            overflow_note = f"\n  ({dropped} more rules not shown — consider consolidating or removing unused rules)"
            section = (
                "## Active Rules\n\n"
                "You have conditional rules. For EVERY incoming message, silently evaluate whether\n"
                "any rule's condition matches. If a rule matches, execute its action using your\n"
                "tools BEFORE composing your normal response. Multiple rules can match the same message.\n"
                "Execute them in priority order (lowest number first). After executing a rule's action,\n"
                "call rule(action='record', rule_id='...') to log the trigger.\n"
                "Do not mention rule evaluation to the user unless the rule's action produces a visible result.\n"
                "If no rules match, proceed normally without mentioning rules.\n\n"
                "<rules>\n"
                f"{rules_block}{overflow_note}\n"
                "</rules>"
            )

    return section


# ---------------------------------------------------------------------------
# Connection discovery prompt
# ---------------------------------------------------------------------------

def build_connections_discovery_prompt(agent_id: Optional[str] = None) -> str:
    """Return a prompt section listing connections the agent doesn't yet have access to.

    This enables the "I noticed you have X, want me to use it?" flow.
    Returns empty string if no connections exist or all are already allowed.
    """
    if not agent_id:
        return ""

    try:
        from vulti_cli.config import get_vulti_home
        from vulti_cli.connection_registry import ConnectionRegistry

        registry = ConnectionRegistry(get_vulti_home())
        if not registry.exists():
            return ""

        visible = registry.get_visible_for_agent(agent_id)
        if not visible:
            return ""

        unused = [c for c in visible if not c["allowed"] and c.get("enabled", True)]
        if not unused:
            return ""

        lines = ["## Available Connections (not yet enabled for you)\n"]
        for conn in unused:
            tags_str = ", ".join(conn.get("tags", []))
            tag_part = f" ({tags_str})" if tags_str else ""
            lines.append(f"- **{conn['name']}**{tag_part}: {conn.get('description', '')}")
        lines.append(
            "\nIf any of these would help with the current task, suggest the user run:\n"
            "`vulti connections allow <agent-id> <connection-name>`"
        )
        return "\n".join(lines)
    except Exception as e:
        logger.debug("Connection discovery prompt failed: %s", e)
        return ""
