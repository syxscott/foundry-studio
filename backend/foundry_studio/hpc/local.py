"""Local backend: runs jobs as subprocesses on this machine (mock HPC).

This is the default backend and requires no cluster.  It behaves like a single
node scheduler: ``submit`` dispatches a runner subprocess, ``status`` reports the
process state, ``cancel`` terminates it, and outputs are already on local disk so
``fetch_outputs`` is a no-op copy of what the runner produced.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from foundry_studio.db import StudioDB
from foundry_studio.hpc.base import (
    STATUS_CANCELED,
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    Backend,
    RemoteHandle,
)
from foundry_studio.hpc.job_spec import JobSpec
from foundry_studio.utils import sanitize_job_id


class LocalBackend(Backend):
    name = "local"

    def __init__(self, *, settings: Any, db: StudioDB):
        self.settings = settings
        self.db = db

    def submit(self, spec: JobSpec, local_job_dir: Path) -> RemoteHandle:
        local_job_dir = Path(local_job_dir)
        local_job_dir.mkdir(parents=True, exist_ok=True)
        # Persist the spec so the runner + UI can show exactly what was submitted.
        (local_job_dir / "job_spec.json").write_text(
            __import__("json").dumps(spec.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        cmd = [
            sys.executable,
            "-m",
            "foundry_studio.hpc._local_runner",
            spec.job_id or "",
            str(self.settings.resolved_data_dir()),
        ]
        log_file = self.settings.resolved_data_dir() / "logs" / f"{sanitize_job_id(spec.job_id or '')}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            log_fh = open(log_file, "a", encoding="utf-8")
            proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
            )
        finally:
            log_fh.close()
        return RemoteHandle(
            backend=self.name,
            remote_id=str(proc.pid),
            meta={"pid": proc.pid, "proc": proc, "started": time.time(), "job_id": spec.job_id},
        )

    def status(self, handle: RemoteHandle) -> tuple[str, int | None]:
        proc = handle.meta.get("proc")
        if proc is None:
            # Lost track of the process (e.g. after a restart) — trust the DB.
            job = self.db.get_job(handle.meta.get("job_id") or "")
            if job is None:
                return STATUS_FAILED, None
            return job["status"], job.get("progress")
        rc = proc.poll()
        if rc is None:
            # Still running; report DB progress if available.
            job = self.db.get_job(handle.meta.get("job_id") or "")
            return STATUS_RUNNING, (job or {}).get("progress")
        if rc == 0:
            return STATUS_SUCCEEDED, 100
        # Non-zero: read the DB terminal status (runner sets failed/canceled).
        job = self.db.get_job(handle.meta.get("job_id") or "")
        if job is not None and job["status"] in (STATUS_FAILED, STATUS_CANCELED, STATUS_SUCCEEDED):
            return job["status"], job.get("progress")
        return STATUS_FAILED, None

    def cancel(self, handle: RemoteHandle) -> None:
        proc = handle.meta.get("proc")
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        job_id = handle.meta.get("job_id")
        if job_id:
            job = self.db.get_job(job_id)
            if job is not None and job["status"] not in (
                STATUS_SUCCEEDED,
                STATUS_FAILED,
                STATUS_CANCELED,
            ):
                self.db.update_job(job_id, status=STATUS_CANCELED)

    def fetch_outputs(self, handle: RemoteHandle, dest_dir: Path) -> list[Path]:
        # Outputs are already written locally by the runner; ensure dest exists.
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        job_id = handle.meta.get("job_id")
        if job_id:
            safe_job_id = sanitize_job_id(job_id)
            src = self.settings.resolved_data_dir() / "jobs" / safe_job_id
            # Additional check: ensure src is within data_dir
            try:
                src.resolve().relative_to(self.settings.resolved_data_dir().resolve())
            except ValueError:
                raise ValueError(f"Path traversal attempt in job_id: {job_id!r}")
        else:
            src = self.settings.resolved_data_dir() / "jobs" / ""
        out: list[Path] = []
        if src.is_dir():
            for p in sorted(src.rglob("*")):
                if p.is_file():
                    out.append(p)
        return out

    def logs(self, handle: RemoteHandle) -> str:
        from foundry_studio.engines.base import tail_text

        log_path = self.settings.resolved_data_dir() / "logs" / f"{handle.meta.get('job_id')}.log"
        return tail_text(log_path)
