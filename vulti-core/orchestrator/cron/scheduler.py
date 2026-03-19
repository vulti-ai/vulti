"""
Vulti cron scheduler — wraps upstream hermes-agent cron with multi-agent scoping.

The upstream cron.scheduler.run_job() creates a bare AIAgent with no agent
identity. This module wraps it to:
  1. Resolve which agent owns the cron job
  2. Scope execution within AgentContext so tools see the correct agent
  3. Use AgentFactory for per-agent config resolution

The upstream tick() is wrapped similarly via vulti_tick().
"""

import logging
import os
from typing import Optional

from orchestrator.agent_context import AgentContext
from orchestrator.agent_registry import get_default_agent_id
from orchestrator.audit import emit as audit_emit

logger = logging.getLogger(__name__)


def vulti_run_job(job: dict) -> tuple:
    """Execute a cron job within the correct agent context.

    Wraps the upstream cron.scheduler.run_job() by:
    1. Determining which agent owns this job
    2. Setting AgentContext.scope() so all downstream code (tools, prompt
       builder, memory) sees the correct agent identity
    3. Delegating to the upstream run_job()

    Returns:
        Tuple of (success, full_output_doc, final_response, error_message)
    """
    from cron.scheduler import run_job as upstream_run_job

    # Resolve agent identity for this job
    agent_id = job.get("agent") or get_default_agent_id()

    audit_emit("cron_execute", agent_id=agent_id, details={
        "job_id": job.get("id"),
        "job_name": job.get("name"),
        "prompt_preview": (job.get("prompt") or "")[:200],
    })

    with AgentContext.scope(agent_id, hop_count=0):
        return upstream_run_job(job)


def vulti_tick(verbose: bool = True) -> int:
    """Check and run all due jobs with per-agent context scoping.

    Replaces upstream cron.scheduler.tick() to scope each job
    within the correct AgentContext.
    """
    import fcntl
    from pathlib import Path
    from cron.jobs import get_due_jobs, mark_job_run, save_job_output

    # Use upstream's lock mechanism
    try:
        from hermes_time import now as _now
    except ImportError:
        from vulti_time import now as _now

    vulti_home = Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))
    lock_dir = vulti_home / "cron"
    lock_file = lock_dir / ".tick.lock"
    lock_dir.mkdir(parents=True, exist_ok=True)

    lock_fd = None
    try:
        lock_fd = open(lock_file, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, IOError):
        logger.debug("Tick skipped — another instance holds the lock")
        if lock_fd is not None:
            lock_fd.close()
        return 0

    try:
        due_jobs = get_due_jobs()

        if verbose and not due_jobs:
            logger.info("%s - No jobs due", _now().strftime("%H:%M:%S"))
            return 0

        if verbose:
            logger.info("%s - %s job(s) due", _now().strftime("%H:%M:%S"), len(due_jobs))

        executed = 0
        for job in due_jobs:
            try:
                # Run each job within its agent's context
                success, output, final_response, error = vulti_run_job(job)

                output_file = save_job_output(job["id"], output)
                if verbose:
                    logger.info("Output saved to: %s", output_file)

                # Deliver results
                deliver_content = (
                    final_response if success
                    else f"⚠️ Cron job '{job.get('name', job['id'])}' failed:\n{error}"
                )
                if deliver_content:
                    try:
                        from cron.scheduler import _deliver_result
                        _deliver_result(job, deliver_content)
                    except Exception as de:
                        logger.error("Delivery failed for job %s: %s", job["id"], de)

                mark_job_run(job["id"], success, error)
                executed += 1

            except Exception as e:
                logger.error("Error processing job %s: %s", job["id"], e)
                mark_job_run(job["id"], False, str(e))

        return executed
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
