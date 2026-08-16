"""Shared engine runner: executes one job and updates the DB to terminal state.

This module exists to give both the in-process orchestrator
(``foundry_studio.hpc._local_runner``) and the test suite a single,
importable entry point. The historical ``foundry_studio.workers.worker``
process model is gone — the orchestrator always runs jobs via the
``LocalBackend`` subprocess in :mod:`foundry_studio.hpc._local_runner`,
which itself calls :func:`run_one` for the actual engine invocation.
"""

from __future__ import annotations

import logging
from pathlib import Path

from foundry_studio.config import Settings
from foundry_studio.db import StudioDB

logger = logging.getLogger("foundry_studio.runner")


def _write_log(log_path: Path, text: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(text if text.endswith("\n") else text + "\n")


def run_one(
    *,
    db: StudioDB,
    settings: Settings,
    model: str,
    engine,
    job: dict,
    data_dir: Path,
) -> None:
    """Execute one job, updating the DB to terminal state.

    Mirrors the engine-call shape of the production ``_local_runner``
    subprocess: writes a log path, honours a pre-start cancel, runs the
    engine, and on success records outputs + ``status='succeeded'``.
    """
    job_id = job["id"]
    workdir = data_dir / "jobs"
    log_path = data_dir / "logs" / f"{job_id}.log"
    db.update_job(job_id, log_path=str(log_path))

    _write_log(
        log_path,
        f"[runner] model={model} job={job_id} engine={job.get('engine_mode')}",
    )

    # Cancellation check before starting.
    current = db.get_job(job_id)
    if current and current.get("cancel_requested"):
        db.update_job(job_id, status="canceled")
        _write_log(log_path, "[runner] canceled before start")
        return

    try:
        result = engine.run(job)
        outputs_dir = str(workdir / job_id)
        db.update_job(
            job_id,
            status="succeeded",
            progress=100,
            outputs_dir=outputs_dir,
        )
        _write_log(
            log_path,
            f"[runner] done, {len(result.outputs or [])} outputs",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Job %s failed", job_id)
        db.update_job(
            job_id,
            status="failed",
            error_code="error.engine_failed",
            error_detail=f"{type(exc).__name__}: {exc}",
        )
        _write_log(log_path, f"[runner] FAILED: {type(exc).__name__}: {exc}")


# Kept as a back-compat alias for the old ``foundry_studio.workers.worker``
# import path that some test suites and external scripts still use.
_run_one = run_one
