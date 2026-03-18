"""
Vulti cron subsystem — wraps upstream hermes-agent cron with multi-agent scoping.

Provides vulti_run_job() which wraps the upstream run_job() with AgentContext
scoping, and vulti_tick() which replaces the upstream tick() to use per-agent
context for each job.
"""

from orchestrator.cron.scheduler import vulti_run_job, vulti_tick  # noqa: F401

# Re-export upstream job CRUD for convenience
from cron.jobs import (  # noqa: F401
    create_job,
    get_due_jobs,
    get_job,
    list_jobs,
    mark_job_run,
    remove_job,
    save_job_output,
    update_job,
    pause_job,
    resume_job,
    trigger_job,
)
