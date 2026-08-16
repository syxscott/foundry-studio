"""Local job runner (the "mock HPC" backend).

Invoked as a subprocess per job by :class:`LocalBackend`::

    python -m foundry_studio.hpc._local_runner <job_id> <data_dir>

It resolves the appropriate engine (real when available, otherwise the labelled
simulation engine) and runs it exactly like the old in-process worker did — the
outputs land in ``data/jobs/<job_id>/`` and the DB is updated to a terminal
state.  This is a *real* local execution, not a stub: it reuses the exact same
engine code path the production system would, so the full upload → queue →
result → 3D viewer flow is exercisable without any cluster.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from foundry_studio.config import get_settings
from foundry_studio.db import StudioDB
from foundry_studio.engines.registry import resolve_engine
from foundry_studio.engines.runner import run_one

logger = logging.getLogger("foundry_studio.local_runner")


def run_job(job_id: str, data_dir: Path, *, allow_simulation: bool = True) -> int:
    data_dir = Path(data_dir)
    db = StudioDB(data_dir / "studio.db")
    workdir = data_dir / "jobs"
    workdir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / "logs" / f"{job_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    job = db.get_job(job_id)
    if job is None:
        logger.error("job %s not found", job_id)
        return 2

    # Mark the job as running BEFORE the heavy work so the UI doesn't show
    # a stale "queued" status for the entire duration of the run.
    db.update_job(job_id, log_path=str(log_path), status="running")
    if job.get("cancel_requested"):
        db.update_job(job_id, status="canceled")
        return 0

    # Engine resolution is local to the runner subprocess so a missing /
    # un-importable real engine only kills the job, not the API server.
    try:
        engine, _effective_mode, _is_sim = resolve_engine(
            job["model"],
            engine_mode=job.get("engine_mode") or "auto",
            allow_simulation=allow_simulation,
            db=db,
            workdir=workdir,
            log_path=log_path,
        )
        engine.initialize()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Cannot run job %s", job_id)
        db.update_job(
            job_id,
            status="failed",
            error_code="error.engine_unavailable",
            error_detail=f"{type(exc).__name__}: {exc}",
        )
        return 1

    # Delegate the actual engine invocation to the shared runner so the
    # in-process test path and the subprocess production path stay
    # byte-for-byte identical.
    run_one(
        db=db,
        settings=get_settings(),
        model=job["model"],
        engine=engine,
        job=job,
        data_dir=data_dir,
    )
    # Mirror the old behaviour: tail the run state from the DB instead of
    # trying to interpret the engine result here.
    final = db.get_job(job_id)
    return 0 if final and final.get("status") == "succeeded" else 1


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print("usage: python -m foundry_studio.hpc._local_runner <job_id> <data_dir>")
        return 2
    job_id, data_dir = argv[0], argv[1]
    settings = get_settings()
    return run_job(job_id, Path(data_dir), allow_simulation=settings.allow_simulation_fallback)


if __name__ == "__main__":
    sys.exit(main())
