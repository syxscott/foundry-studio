"""Worker manager: spawns and supervises model worker processes.

Runs inside the API server process.  On startup it marks stale ``running``
jobs as queued again, then spawns one worker subprocess per supported model
(``worker_autostart``).  It periodically checks each worker's heartbeat and
reports stopped workers through the ``workers`` table.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from foundry_studio.config import Settings
from foundry_studio.db import StudioDB

logger = logging.getLogger("foundry_studio.manager")

HEARTBEAT_STALE_SECONDS = 60


class WorkerManager:
    def __init__(self, settings: Settings, db: StudioDB):
        self.settings = settings
        self.db = db
        self.processes: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        """Requeue stale jobs and spawn workers (if enabled)."""
        try:
            requeued = self.db.requeue_stale_running()
            if requeued:
                logger.info("Requeued %d stale running job(s)", requeued)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to requeue stale jobs")

        if self.settings.worker_autostart:
            for model in ("rfd3", "rfd3na", "rf3", "mpnn"):
                self.ensure_worker(model)

        self._thread = threading.Thread(
            target=self._monitor_loop, name="worker-manager", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            for proc in list(self.processes.values()):
                try:
                    proc.terminate()
                except Exception:  # noqa: BLE001
                    pass
            self.processes.clear()

    # ------------------------------------------------------------------ #
    def ensure_worker(self, model: str) -> bool:
        """Spawn a worker for ``model`` if none is running. Returns spawned."""
        with self._lock:
            existing = self.processes.get(model)
            if existing is not None and existing.poll() is None:
                return False

            env = os.environ.copy()
            env.setdefault("PYTHONUNBUFFERED", "1")
            cmd = [
                sys.executable,
                "-m",
                "foundry_studio.workers.worker",
                "--model",
                model,
            ]
            log_file = (
                self.settings.resolved_data_dir()
                / "logs"
                / f"manager_{model}.log"
            )
            log_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                fh = open(log_file, "a", encoding="utf-8")
                proc = subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=fh,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(Path.cwd()),
                )
            except OSError:
                logger.exception("Failed to spawn worker for %s", model)
                return False

            self.processes[model] = proc
            logger.info("Spawned worker for %s (pid=%s)", model, proc.pid)
            return True

    def worker_status(self) -> list[dict[str, Any]]:
        """Current status of each model worker for the health endpoint."""
        rows: list[dict[str, Any]] = []
        for model, proc in sorted(self.processes.items()):
            alive = proc.poll() is None
            rows.append(
                {
                    "model": model,
                    "pid": proc.pid,
                    "alive": alive,
                    "exit_code": None if alive else proc.returncode,
                }
            )
        return rows

    # ------------------------------------------------------------------ #
    def _monitor_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._monitor_once()
            except Exception:  # noqa: BLE001
                logger.exception("Worker monitor error")
            self._stop.wait(15)

    def _monitor_once(self) -> None:
        for model in ("rfd3", "rfd3na", "rf3", "mpnn"):
            with self._lock:
                proc = self.processes.get(model)
            if proc is None:
                # Only autospawn if jobs are waiting.
                if self._has_queued_jobs(model):
                    self.ensure_worker(model)
                continue
            if proc.poll() is not None:
                # Dead worker: mark it and respawn if jobs remain.
                self.db.mark_worker_stopped(model)
                with self._lock:
                    self.processes.pop(model, None)
                if self.settings.worker_autostart and self._has_queued_jobs(model):
                    logger.warning("Worker %s died; respawning", model)
                    self.ensure_worker(model)

    def _has_queued_jobs(self, model: str) -> bool:
        try:
            with self.db.tx() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM jobs WHERE model = ? AND status = 'queued'",
                    (model,),
                ).fetchone()
            return bool(row and row["n"] > 0)
        except Exception:  # noqa: BLE001
            return False
