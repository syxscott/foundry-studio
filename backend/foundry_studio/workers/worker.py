"""Worker entrypoint: a long-lived process that executes jobs for one model.

Each worker owns a single model engine instance (weights loaded once) and
polls the SQLite queue for queued jobs.  It heartbeats into the ``workers``
table so the API server can detect and report dead workers.

Run directly with::

    python -m foundry_studio.workers.worker --model rfd3
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

from foundry_studio.config import Settings, get_settings
from foundry_studio.db import StudioDB
from foundry_studio.engines.registry import resolve_engine

logger = logging.getLogger("foundry_studio.worker")

_STOP = False


def _handle_stop(signum, frame):  # noqa: ARG001
    global _STOP
    _STOP = True


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _write_job_log(log_path: Path, text: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(text if text.endswith("\n") else text + "\n")


def _run_one(
    *,
    db: StudioDB,
    settings: Settings,
    model: str,
    engine,
    job: dict,
    data_dir: Path,
) -> None:
    """Execute one job, updating the DB to terminal state."""
    job_id = job["id"]
    workdir = data_dir / "jobs"
    log_path = data_dir / "logs" / f"{job_id}.log"
    db.update_job(job_id, log_path=str(log_path))

    _write_job_log(
        log_path,
        f"[worker] model={model} job={job_id} engine={job.get('engine_mode')}",
    )
    # Cancellation check before starting.
    current = db.get_job(job_id)
    if current and current.get("cancel_requested"):
        db.update_job(job_id, status="canceled")
        _write_job_log(log_path, "[worker] canceled before start")
        return

    try:
        engine_run = getattr(engine, "run")
        result = engine_run(job)
        outputs_dir = str(workdir / job_id)
        db.update_job(
            job_id,
            status="succeeded",
            progress=100,
            outputs_dir=outputs_dir,
        )
        _write_job_log(log_path, f"[worker] done, {len(result.outputs)} outputs")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Job %s failed", job_id)
        db.update_job(
            job_id,
            status="failed",
            error_code="error.engine_failed",
            error_detail=f"{type(exc).__name__}: {exc}",
        )
        _write_job_log(log_path, f"[worker] FAILED: {type(exc).__name__}: {exc}")


def run_worker(model: str, settings: Settings | None = None) -> int:
    """Worker main loop. Returns process exit code."""
    settings = settings or get_settings()
    data_dir = settings.resolved_data_dir()
    (data_dir / "jobs").mkdir(parents=True, exist_ok=True)
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)

    db = StudioDB(data_dir / "studio.db")
    workdir = data_dir / "jobs"
    log_path = data_dir / "logs" / f"worker_{model}.log"

    # Claim any stale running jobs for this model left by a dead worker.
    stale = db.requeue_stale_running()
    if stale:
        logger.info("Requeued %d stale running job(s)", stale)

    # Resolve engine once.  If unavailable and no simulation fallback is
    # allowed, the worker exits with an error (the manager reports it).
    try:
        engine, effective_mode, is_sim = resolve_engine(
            model,
            engine_mode=settings.engine_mode,
            allow_simulation=settings.allow_simulation_fallback,
            db=db,
            workdir=workdir,
            log_path=log_path,
        )
        engine.initialize()
    except Exception as exc:  # noqa: BLE001
        logger.error("Cannot start worker for %s: %s", model, exc)
        db.mark_worker_stopped(model, last_error=str(exc))
        return 1

    db.upsert_worker(model, pid=os.getpid(), status="running")
    logger.info(
        "Worker %s ready (engine=%s, simulation=%s)", model, effective_mode, is_sim
    )
    _write_job_log(
        log_path,
        f"[worker] started model={model} engine={effective_mode} sim={is_sim}",
    )

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    last_heartbeat = 0.0
    while not _STOP:
        job = db.claim_next_job(model)
        if job is not None:
            _run_one(
                db=db,
                settings=settings,
                model=model,
                engine=engine,
                job=job,
                data_dir=data_dir,
            )
            last_heartbeat = 0.0
            continue
        now = time.monotonic()
        if now - last_heartbeat >= max(settings.worker_poll_interval, 0.5):
            db.heartbeat(model, os.getpid())
            last_heartbeat = now
        time.sleep(min(settings.worker_poll_interval, 2.0))

    db.mark_worker_stopped(model)
    logger.info("Worker %s stopped", model)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="foundry-studio worker")
    parser.add_argument("--model", required=True, choices=["rfd3", "rfd3na", "rf3", "mpnn"])
    parser.add_argument("--config", default=None, help="Path to a .env file")
    args = parser.parse_args(argv)

    _configure_logging()
    if args.config:
        os.environ["FOUNDRY_STUDIO_ENV_FILE"] = args.config
    return run_worker(args.model)


if __name__ == "__main__":
    sys.exit(main())
