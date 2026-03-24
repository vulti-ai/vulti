"""
Cron job storage and management.

Jobs are stored in ~/.vulti/cron/jobs.json
Output is saved to ~/.vulti/cron/output/{job_id}/{timestamp}.md
"""

import json
import logging
import tempfile
import os
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


def _current_agent_id() -> str:
    """Return the active agent ID from AgentContext or env var.

    Raises ValueError if no agent context is available — cron jobs
    must always have an explicit agent assignment.
    """
    try:
        from orchestrator.agent_context import AgentContext
        ctx_id = AgentContext.current_agent_id()
        if ctx_id:
            return ctx_id
    except ImportError:
        pass
    agent_id = os.getenv("VULTI_AGENT_ID")
    if agent_id:
        return agent_id
    raise ValueError("No agent context — cron job must specify an agent")


from vulti_time import now as _vulti_now

try:
    from croniter import croniter
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False

# =============================================================================
# Configuration
# =============================================================================

VULTI_DIR = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))
CRON_DIR = VULTI_DIR / "cron"
JOBS_FILE = CRON_DIR / "jobs.json"  # Legacy global path (unused for new writes)
OUTPUT_DIR = CRON_DIR / "output"


def _agent_jobs_file(agent_id: str) -> Path:
    """Return the per-agent jobs file path."""
    return VULTI_DIR / "agents" / agent_id / "cron" / "jobs.json"


def _agent_output_dir(agent_id: str) -> Path:
    """Return the per-agent cron output directory."""
    return VULTI_DIR / "agents" / agent_id / "cron" / "output"


def _normalize_skill_list(skill: Optional[str] = None, skills: Optional[Any] = None) -> List[str]:
    """Normalize legacy/single-skill and multi-skill inputs into a unique ordered list."""
    if skills is None:
        raw_items = [skill] if skill else []
    elif isinstance(skills, str):
        raw_items = [skills]
    else:
        raw_items = list(skills)

    normalized: List[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _apply_skill_fields(job: Dict[str, Any]) -> Dict[str, Any]:
    """Return a job dict with canonical `skills` and legacy `skill` fields aligned."""
    normalized = dict(job)
    skills = _normalize_skill_list(normalized.get("skill"), normalized.get("skills"))
    normalized["skills"] = skills
    normalized["skill"] = skills[0] if skills else None
    return normalized


def _secure_dir(path: Path):
    """Set directory to owner-only access (0700). No-op on Windows."""
    try:
        os.chmod(path, 0o700)
    except (OSError, NotImplementedError):
        pass  # Windows or other platforms where chmod is not supported


def _secure_file(path: Path):
    """Set file to owner-only read/write (0600). No-op on Windows."""
    try:
        if path.exists():
            os.chmod(path, 0o600)
    except (OSError, NotImplementedError):
        pass


def ensure_dirs():
    """Ensure cron directories exist with secure permissions."""
    CRON_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _secure_dir(CRON_DIR)
    _secure_dir(OUTPUT_DIR)


# =============================================================================
# Schedule Parsing
# =============================================================================

def parse_duration(s: str) -> int:
    """
    Parse duration string into minutes.
    
    Examples:
        "30m" → 30
        "2h" → 120
        "1d" → 1440
    """
    s = s.strip().lower()
    match = re.match(r'^(\d+)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)$', s)
    if not match:
        raise ValueError(f"Invalid duration: '{s}'. Use format like '30m', '2h', or '1d'")
    
    value = int(match.group(1))
    unit = match.group(2)[0]  # First char: m, h, or d
    
    multipliers = {'m': 1, 'h': 60, 'd': 1440}
    return value * multipliers[unit]


def parse_schedule(schedule: str) -> Dict[str, Any]:
    """
    Parse schedule string into structured format.
    
    Returns dict with:
        - kind: "once" | "interval" | "cron"
        - For "once": "run_at" (ISO timestamp)
        - For "interval": "minutes" (int)
        - For "cron": "expr" (cron expression)
    
    Examples:
        "30m"              → once in 30 minutes
        "2h"               → once in 2 hours
        "every 30m"        → recurring every 30 minutes
        "every 2h"         → recurring every 2 hours
        "0 9 * * *"        → cron expression
        "2026-02-03T14:00" → once at timestamp
    """
    schedule = schedule.strip()
    original = schedule
    schedule_lower = schedule.lower()
    
    # "every X" pattern → recurring interval
    if schedule_lower.startswith("every "):
        duration_str = schedule[6:].strip()
        minutes = parse_duration(duration_str)
        return {
            "kind": "interval",
            "minutes": minutes,
            "display": f"every {minutes}m"
        }
    
    # Check for cron expression (5 or 6 space-separated fields)
    # Cron fields: minute hour day month weekday [year]
    parts = schedule.split()
    if len(parts) >= 5 and all(
        re.match(r'^[\d\*\-,/]+$', p) for p in parts[:5]
    ):
        if not HAS_CRONITER:
            raise ValueError("Cron expressions require 'croniter' package. Install with: pip install croniter")
        # Validate cron expression
        try:
            croniter(schedule)
        except Exception as e:
            raise ValueError(f"Invalid cron expression '{schedule}': {e}")
        return {
            "kind": "cron",
            "expr": schedule,
            "display": schedule
        }
    
    # ISO timestamp (contains T or looks like date)
    if 'T' in schedule or re.match(r'^\d{4}-\d{2}-\d{2}', schedule):
        try:
            # Parse and validate
            dt = datetime.fromisoformat(schedule.replace('Z', '+00:00'))
            return {
                "kind": "once",
                "run_at": dt.isoformat(),
                "display": f"once at {dt.strftime('%Y-%m-%d %H:%M')}"
            }
        except ValueError as e:
            raise ValueError(f"Invalid timestamp '{schedule}': {e}")
    
    # Duration like "30m", "2h", "1d" → one-shot from now
    try:
        minutes = parse_duration(schedule)
        run_at = _vulti_now() + timedelta(minutes=minutes)
        return {
            "kind": "once",
            "run_at": run_at.isoformat(),
            "display": f"once in {original}"
        }
    except ValueError:
        pass
    
    raise ValueError(
        f"Invalid schedule '{original}'. Use:\n"
        f"  - Duration: '30m', '2h', '1d' (one-shot)\n"
        f"  - Interval: 'every 30m', 'every 2h' (recurring)\n"
        f"  - Cron: '0 9 * * *' (cron expression)\n"
        f"  - Timestamp: '2026-02-03T14:00:00' (one-shot at time)"
    )


def _ensure_aware(dt: datetime) -> datetime:
    """Return a timezone-aware datetime in Vulti configured timezone.

    Backward compatibility:
    - Older stored timestamps may be naive.
    - Naive values are interpreted as *system-local wall time* (the timezone
      `datetime.now()` used when they were created), then converted to the
      configured Vulti timezone.

    This preserves relative ordering for legacy naive timestamps across
    timezone changes and avoids false not-due results.
    """
    target_tz = _vulti_now().tzinfo
    if dt.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo
        return dt.replace(tzinfo=local_tz).astimezone(target_tz)
    return dt.astimezone(target_tz)


def compute_next_run(schedule: Dict[str, Any], last_run_at: Optional[str] = None) -> Optional[str]:
    """
    Compute the next run time for a schedule.

    Returns ISO timestamp string, or None if no more runs.
    """
    now = _vulti_now()

    if schedule["kind"] == "once":
        run_at = _ensure_aware(datetime.fromisoformat(schedule["run_at"]))
        # If in the future, return it; if in the past, no more runs
        return schedule["run_at"] if run_at > now else None

    elif schedule["kind"] == "interval":
        minutes = schedule["minutes"]
        if last_run_at:
            # Next run is last_run + interval
            last = _ensure_aware(datetime.fromisoformat(last_run_at))
            next_run = last + timedelta(minutes=minutes)
        else:
            # First run is now + interval
            next_run = now + timedelta(minutes=minutes)
        return next_run.isoformat()

    elif schedule["kind"] == "cron":
        if not HAS_CRONITER:
            return None
        cron = croniter(schedule["expr"], now)
        next_run = cron.get_next(datetime)
        return next_run.isoformat()

    return None


# =============================================================================
# Job CRUD Operations
# =============================================================================

def load_jobs(agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load jobs for a specific agent from per-agent storage.

    If *agent_id* is ``None`` the current agent (from env / registry) is used.
    """
    agent_id = agent_id or _current_agent_id()
    jobs_file = _agent_jobs_file(agent_id)
    if not jobs_file.exists():
        # Migration: check legacy global file for this agent's jobs
        if JOBS_FILE.exists():
            return _migrate_agent_jobs(agent_id)
        return []

    try:
        with open(jobs_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("jobs", [])
    except (json.JSONDecodeError, IOError):
        return []


def load_all_jobs() -> List[Dict[str, Any]]:
    """Load jobs from ALL agents.  Used by the scheduler to find due jobs."""
    agents_dir = VULTI_DIR / "agents"
    all_jobs: List[Dict[str, Any]] = []
    if not agents_dir.is_dir():
        return all_jobs
    for agent_dir in agents_dir.iterdir():
        if not agent_dir.is_dir():
            continue
        jobs_file = agent_dir / "cron" / "jobs.json"
        if not jobs_file.exists():
            continue
        try:
            with open(jobs_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for j in data.get("jobs", []):
                    j.setdefault("agent", agent_dir.name)
                    all_jobs.append(j)
        except (json.JSONDecodeError, IOError):
            continue

    # Also check legacy global file for any un-migrated jobs
    if JOBS_FILE.exists():
        try:
            with open(JOBS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                migrated_ids = {j["id"] for j in all_jobs}
                for j in data.get("jobs", []):
                    if j["id"] not in migrated_ids:
                        all_jobs.append(j)
        except (json.JSONDecodeError, IOError):
            pass

    return all_jobs


def save_jobs(jobs: List[Dict[str, Any]], agent_id: Optional[str] = None):
    """Save jobs to per-agent storage.

    If *agent_id* is ``None`` the current agent (from env / registry) is used.
    """
    agent_id = agent_id or _current_agent_id()
    jobs_file = _agent_jobs_file(agent_id)
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    _secure_dir(jobs_file.parent)

    fd, tmp_path = tempfile.mkstemp(dir=str(jobs_file.parent), suffix='.tmp', prefix='.jobs_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump({"jobs": jobs, "updated_at": _vulti_now().isoformat()}, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, jobs_file)
        _secure_file(jobs_file)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _migrate_agent_jobs(agent_id: str) -> List[Dict[str, Any]]:
    """One-time migration: pull jobs for *agent_id* out of the legacy global file
    and write them into per-agent storage.  Returns the migrated jobs list."""
    try:
        with open(JOBS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

    all_jobs = data.get("jobs", [])
    agent_jobs = [j for j in all_jobs if j.get("agent") == agent_id]
    if not agent_jobs:
        return []

    # Write to per-agent path
    save_jobs(agent_jobs, agent_id=agent_id)

    # Remove from legacy global file
    remaining = [j for j in all_jobs if j.get("agent") != agent_id]
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(JOBS_FILE.parent), suffix='.tmp', prefix='.jobs_')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump({"jobs": remaining, "updated_at": _vulti_now().isoformat()}, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, JOBS_FILE)
        _secure_file(JOBS_FILE)
    except (OSError, IOError):
        pass  # Migration cleanup is best-effort

    return agent_jobs


def create_job(
    prompt: str,
    schedule: str,
    name: Optional[str] = None,
    repeat: Optional[int] = None,
    deliver: Optional[str] = None,
    origin: Optional[Dict[str, Any]] = None,
    skill: Optional[str] = None,
    skills: Optional[List[str]] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    agent: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new cron job.

    Args:
        prompt: The prompt to run (must be self-contained, or a task instruction when skill is set)
        schedule: Schedule string (see parse_schedule)
        name: Optional friendly name
        repeat: How many times to run (None = forever, 1 = once)
        deliver: Where to deliver output ("origin", "local", "telegram", etc.)
        origin: Source info where job was created (for "origin" delivery)
        skill: Optional legacy single skill name to load before running the prompt
        skills: Optional ordered list of skills to load before running the prompt
        model: Optional per-job model override
        provider: Optional per-job provider override
        base_url: Optional per-job base URL override

    Returns:
        The created job dict
    """
    parsed_schedule = parse_schedule(schedule)

    # Auto-set repeat=1 for one-shot schedules if not specified
    if parsed_schedule["kind"] == "once" and repeat is None:
        repeat = 1

    # Resolve agent early so delivery can reference the agent's home channel
    _effective_agent = agent or _current_agent_id()

    # Default delivery: prefer agent's Matrix home channel over web/app origin.
    # The web/hub origin (platform="app") can't receive deliveries, so when
    # deliver is "origin" with an app origin, or deliver is None, resolve to
    # the agent's Matrix DM if they have one configured.
    _origin_is_app = origin and origin.get("platform") == "app"
    if deliver is None or (deliver == "origin" and _origin_is_app):
        if origin and not _origin_is_app:
            deliver = "origin"
        else:
            try:
                from vulti_cli.agent_registry import AgentRegistry
                _agent_meta = AgentRegistry().get_agent(_effective_agent)
                _matrix_hc = (_agent_meta.home_channels or {}).get("matrix", {}) if _agent_meta else {}
                if _matrix_hc.get("chat_id"):
                    deliver = f"matrix:{_matrix_hc['chat_id']}"
                else:
                    deliver = "local"
            except Exception:
                deliver = "local"

    job_id = uuid.uuid4().hex[:12]
    now = _vulti_now().isoformat()

    normalized_skills = _normalize_skill_list(skill, skills)
    normalized_model = str(model).strip() if isinstance(model, str) else None
    normalized_provider = str(provider).strip() if isinstance(provider, str) else None
    normalized_base_url = str(base_url).strip().rstrip("/") if isinstance(base_url, str) else None
    normalized_model = normalized_model or None
    normalized_provider = normalized_provider or None
    normalized_base_url = normalized_base_url or None

    label_source = (prompt or (normalized_skills[0] if normalized_skills else None)) or "cron job"
    job = {
        "id": job_id,
        "name": name or label_source[:50].strip(),
        "prompt": prompt,
        "skills": normalized_skills,
        "skill": normalized_skills[0] if normalized_skills else None,
        "model": normalized_model,
        "provider": normalized_provider,
        "base_url": normalized_base_url,
        "schedule": parsed_schedule,
        "schedule_display": parsed_schedule.get("display", schedule),
        "repeat": {
            "times": repeat,  # None = forever
            "completed": 0
        },
        "enabled": True,
        "state": "scheduled",
        "paused_at": None,
        "paused_reason": None,
        "created_at": now,
        "next_run_at": compute_next_run(parsed_schedule),
        "last_run_at": None,
        "last_status": None,
        "last_error": None,
        # Delivery configuration
        "deliver": deliver,
        "origin": origin,  # Tracks where job was created for "origin" delivery
        # Agent scope -- which agent owns this cron job
        "agent": agent or _current_agent_id(),
    }

    # Save to the target agent's cron directory, not the caller's
    target_agent = job["agent"]
    target_jobs = [j for j in load_jobs() if j.get("agent") == target_agent]
    target_jobs.append(job)
    save_jobs(target_jobs, agent_id=target_agent)

    return job


def _find_job_agent(job_id: str) -> Optional[str]:
    """Find which agent owns a job by scanning all agents.  Used by scheduler
    functions that operate outside a specific agent context."""
    agents_dir = VULTI_DIR / "agents"
    if not agents_dir.is_dir():
        return None
    for agent_dir in agents_dir.iterdir():
        if not agent_dir.is_dir():
            continue
        jobs_file = agent_dir / "cron" / "jobs.json"
        if not jobs_file.exists():
            continue
        try:
            with open(jobs_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for j in data.get("jobs", []):
                    if j.get("id") == job_id:
                        return agent_dir.name
        except (json.JSONDecodeError, IOError):
            continue
    return None


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get a job by ID.  Searches the current agent first, then all agents."""
    # Try current agent first
    jobs = load_jobs()
    for job in jobs:
        if job["id"] == job_id:
            return _apply_skill_fields(job)
    # Fallback: search all agents (needed by scheduler / cross-agent calls)
    for job in load_all_jobs():
        if job["id"] == job_id:
            return _apply_skill_fields(job)
    return None


def list_jobs(include_disabled: bool = False) -> List[Dict[str, Any]]:
    """List jobs for the current agent, optionally including disabled ones."""
    jobs = [_apply_skill_fields(j) for j in load_jobs()]
    if not include_disabled:
        jobs = [j for j in jobs if j.get("enabled", True)]
    return jobs


def update_job(job_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update a job by ID, refreshing derived schedule fields when needed."""
    # Find which agent owns this job
    agent_id = _find_job_agent(job_id) or _current_agent_id()
    jobs = load_jobs(agent_id)
    for i, job in enumerate(jobs):
        if job["id"] != job_id:
            continue

        updated = _apply_skill_fields({**job, **updates})
        schedule_changed = "schedule" in updates

        if "skills" in updates or "skill" in updates:
            normalized_skills = _normalize_skill_list(updated.get("skill"), updated.get("skills"))
            updated["skills"] = normalized_skills
            updated["skill"] = normalized_skills[0] if normalized_skills else None

        if schedule_changed:
            updated_schedule = updated["schedule"]
            updated["schedule_display"] = updates.get(
                "schedule_display",
                updated_schedule.get("display", updated.get("schedule_display")),
            )
            if updated.get("state") != "paused":
                updated["next_run_at"] = compute_next_run(updated_schedule)

        if updated.get("enabled", True) and updated.get("state") != "paused" and not updated.get("next_run_at"):
            updated["next_run_at"] = compute_next_run(updated["schedule"])

        jobs[i] = updated
        save_jobs(jobs, agent_id)
        return _apply_skill_fields(jobs[i])
    return None


def pause_job(job_id: str, reason: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Pause a job without deleting it."""
    return update_job(
        job_id,
        {
            "enabled": False,
            "state": "paused",
            "paused_at": _vulti_now().isoformat(),
            "paused_reason": reason,
        },
    )


def resume_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Resume a paused job and compute the next future run from now."""
    job = get_job(job_id)
    if not job:
        return None

    next_run_at = compute_next_run(job["schedule"])
    return update_job(
        job_id,
        {
            "enabled": True,
            "state": "scheduled",
            "paused_at": None,
            "paused_reason": None,
            "next_run_at": next_run_at,
        },
    )


def trigger_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Schedule a job to run on the next scheduler tick."""
    job = get_job(job_id)
    if not job:
        return None
    return update_job(
        job_id,
        {
            "enabled": True,
            "state": "scheduled",
            "paused_at": None,
            "paused_reason": None,
            "next_run_at": _vulti_now().isoformat(),
        },
    )


def remove_job(job_id: str) -> bool:
    """Remove a job by ID."""
    agent_id = _find_job_agent(job_id) or _current_agent_id()
    jobs = load_jobs(agent_id)
    original_len = len(jobs)
    jobs = [j for j in jobs if j["id"] != job_id]
    if len(jobs) < original_len:
        save_jobs(jobs, agent_id)
        return True
    return False


def mark_job_run(job_id: str, success: bool, error: Optional[str] = None):
    """
    Mark a job as having been run.

    Updates last_run_at, last_status, increments completed count,
    computes next_run_at, and auto-deletes if repeat limit reached.
    """
    agent_id = _find_job_agent(job_id)
    if not agent_id:
        return
    jobs = load_jobs(agent_id)
    for i, job in enumerate(jobs):
        if job["id"] == job_id:
            now = _vulti_now().isoformat()
            job["last_run_at"] = now
            job["last_status"] = "ok" if success else "error"
            job["last_error"] = error if not success else None

            # Increment completed count
            if job.get("repeat"):
                job["repeat"]["completed"] = job["repeat"].get("completed", 0) + 1

                # Check if we've hit the repeat limit
                times = job["repeat"].get("times")
                completed = job["repeat"]["completed"]
                if times is not None and completed >= times:
                    # Remove the job (limit reached)
                    jobs.pop(i)
                    save_jobs(jobs, agent_id)
                    return

            # Compute next run
            job["next_run_at"] = compute_next_run(job["schedule"], now)

            # If no next run (one-shot completed), disable
            if job["next_run_at"] is None:
                job["enabled"] = False
                job["state"] = "completed"
            elif job.get("state") != "paused":
                job["state"] = "scheduled"

            save_jobs(jobs, agent_id)
            return


def get_due_jobs() -> List[Dict[str, Any]]:
    """Get all jobs across all agents that are due to run now.

    For recurring jobs (cron/interval), if the scheduled time is stale
    (more than one period in the past, e.g. because the gateway was down),
    the job is fast-forwarded to the next future run instead of firing
    immediately.  This prevents a burst of missed jobs on gateway restart.
    """
    now = _vulti_now()
    all_jobs = [_apply_skill_fields(j) for j in load_all_jobs()]
    due = []
    # Track which agents need saves for fast-forward updates
    dirty_agents: dict[str, bool] = {}

    for job in all_jobs:
        if not job.get("enabled", True):
            continue

        next_run = job.get("next_run_at")
        if not next_run:
            continue

        next_run_dt = _ensure_aware(datetime.fromisoformat(next_run))
        if next_run_dt <= now:
            schedule = job.get("schedule", {})
            kind = schedule.get("kind")

            # For recurring jobs, check if the scheduled time is stale
            # (gateway was down and missed the window). Fast-forward to
            # the next future occurrence instead of firing a stale run.
            if kind in ("cron", "interval") and (now - next_run_dt).total_seconds() > 120:
                new_next = compute_next_run(schedule, now.isoformat())
                if new_next:
                    logger.info(
                        "Job '%s' missed its scheduled time (%s). "
                        "Fast-forwarding to next run: %s",
                        job.get("name", job["id"]),
                        next_run,
                        new_next,
                    )
                    job["next_run_at"] = new_next
                    agent = job.get("agent") or _current_agent_id()
                    dirty_agents[agent] = True
                    continue  # Skip this run

            due.append(job)

    # Persist fast-forward updates per-agent
    for agent in dirty_agents:
        agent_jobs = [j for j in all_jobs if (j.get("agent") or _current_agent_id()) == agent]
        save_jobs(agent_jobs, agent)

    return due


def save_job_output(job_id: str, output: str):
    """Save job output to the owning agent's output directory."""
    agent_id = _find_job_agent(job_id) or _current_agent_id()
    job_output_dir = _agent_output_dir(agent_id) / job_id
    job_output_dir.mkdir(parents=True, exist_ok=True)
    _secure_dir(job_output_dir)
    
    timestamp = _vulti_now().strftime("%Y-%m-%d_%H-%M-%S")
    output_file = job_output_dir / f"{timestamp}.md"
    
    fd, tmp_path = tempfile.mkstemp(dir=str(job_output_dir), suffix='.tmp', prefix='.output_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(output)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, output_file)
        _secure_file(output_file)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    
    return output_file
