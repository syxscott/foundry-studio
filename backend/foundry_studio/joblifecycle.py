"""Job orchestrator: the new execution core that replaces the local workers.

Where the old design spawned one subprocess-per-model worker that ran engines
in-process, this orchestrator treats execution as *remote job submission*:

1. ``submit`` builds a backend-agnostic :class:`JobSpec` from the job row +
   model catalog + server HPC defaults (an agent or the UI may have overridden
   any field first).
2. It hands the spec to the active :class:`Backend` (``local`` by default, or a
   SLURM/PBS/LSF backend over a configured transport).
3. A background loop polls each submitted job's status, mirrors progress into
   the DB, and on completion fetches outputs back and marks the job terminal.

Because every backend speaks JobSpec, swapping the cluster does not change how
jobs are described or how the UI/agent drives them — that is the "not stuck on
configuration" property the user asked for.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from foundry_studio.config import Settings
from foundry_studio.db import StudioDB
from foundry_studio.engines import models as model_catalog
from foundry_studio.hpc.base import Backend, HPCNotConfigured, RemoteHandle, STATUS_CANCELED, STATUS_FAILED, STATUS_PENDING, STATUS_RUNNING, STATUS_SUCCEEDED
from foundry_studio.hpc.job_spec import JobSpec, build_spec

logger = logging.getLogger("foundry_studio.orchestrator")

_ACTIVE_STATUSES = {"queued", "running"}


class JobOrchestrator:
    def __init__(self, settings: Settings, db: StudioDB):
        self.settings = settings
        self.db = db
        self._handles: dict[str, RemoteHandle] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        # Requeue any jobs left "running" by a dead process.
        try:
            self.db.requeue_stale_running()
        except Exception:  # noqa: BLE001
            logger.exception("requeue stale failed")
        self._resume_submitted()
        self._thread = threading.Thread(
            target=self._loop, name="orchestrator", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------ #
    # Backend selection
    # ------------------------------------------------------------------ #
    def _make_backend(self, kind: str) -> Backend:
        if kind in ("slurm", "pbs", "lsf"):
            transport = self._make_transport(self.settings.hpc_transport)
            if kind == "slurm":
                from foundry_studio.hpc.scheduler.slurm import SlurmBackend

                return SlurmBackend(settings=self.settings, db=self.db, transport=transport)
            if kind == "pbs":
                from foundry_studio.hpc.scheduler.pbs import PbsBackend

                return PbsBackend(settings=self.settings, db=self.db, transport=transport)
            from foundry_studio.hpc.scheduler.lsf import LsfBackend

            return LsfBackend(settings=self.settings, db=self.db, transport=transport)
        # Default: local (mock HPC) — runs engines on this machine.
        from foundry_studio.hpc.local import LocalBackend

        return LocalBackend(settings=self.settings, db=self.db)

    def _make_transport(self, name: str):
        if name == "ssh":
            from foundry_studio.hpc.transport.ssh import SshTransport

            return SshTransport(
                host=self.settings.hpc_remote_host,
                user=self.settings.hpc_remote_user,
                key_path=self.settings.hpc_remote_key,
                remote_workdir=self.settings.hpc_remote_workdir,
                port=self.settings.hpc_remote_port,
            )
        if name == "sharedfs":
            from foundry_studio.hpc.transport.sharedfs import SharedFsTransport

            return SharedFsTransport(remote_workdir=self.settings.hpc_remote_workdir)
        if name == "rest":
            from foundry_studio.hpc.transport.rest import RestTransport

            return RestTransport(
                gateway_url=self.settings.hpc_gateway_url,
                token=self.settings.hpc_gateway_token,
            )
        from foundry_studio.hpc.transport.local import LocalTransport

        return LocalTransport()

    def backend_info(self) -> dict[str, Any]:
        return {
            "active_backend": self.settings.hpc_backend,
            "scheduler": self.settings.hpc_backend if self.settings.hpc_backend != "local" else "local",
            "transport": self.settings.hpc_transport if self.settings.hpc_backend != "local" else "local",
            "configured": self._backend_configured(),
            "agent_enabled": self.settings.agent_enabled,
        }

    def _backend_configured(self) -> bool:
        if self.settings.hpc_backend == "local":
            return True
        try:
            self._make_backend(self.settings.hpc_backend)
            return True
        except HPCNotConfigured:
            return False
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------ #
    # Submission
    # ------------------------------------------------------------------ #
    def submit(self, job_id: str) -> dict[str, Any] | None:
        job = self.db.get_job(job_id)
        if job is None:
            return None
        if job["status"] not in ("draft", "queued"):
            return job

        model_info = model_catalog.get_model(job["model"]) or {}
        try:
            overrides = self._load_overrides(job)
            spec = build_spec(
                job=job,
                model_info=model_info,
                invocation_defaults=self._invocation_defaults(),
                resources_defaults=self._resources_defaults(),
                scheduler=self.settings.hpc_backend,
                overrides=overrides,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("build_spec failed")
            return self.db.update_job(
                job_id,
                status=STATUS_FAILED,
                error_code="error.build_spec_failed",
                error_detail=str(exc),
            )

        backend = self._make_backend(self.settings.hpc_backend)
        local_job_dir = self.settings.resolved_data_dir() / "jobs" / job_id
        try:
            handle = backend.submit(spec, local_job_dir)
        except HPCNotConfigured as exc:
            logger.warning("HPC not configured for job %s: %s", job_id, exc)
            return self.db.update_job(
                job_id,
                status=STATUS_FAILED,
                error_code="error.hpc_not_configured",
                error_detail=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("submit failed")
            return self.db.update_job(
                job_id,
                status=STATUS_FAILED,
                error_code="error.submit_failed",
                error_detail=f"{type(exc).__name__}: {exc}",
            )

        with self._lock:
            self._handles[job_id] = handle
        return self.db.update_job(
            job_id,
            status=STATUS_PENDING,
            remote_job_id=handle.remote_id,
            backend=self.settings.hpc_backend,
            scheduler=self.settings.hpc_backend,
            job_spec_json=json.dumps(spec.to_dict(), ensure_ascii=False),
        )

    def cancel(self, job_id: str) -> None:
        with self._lock:
            handle = self._handles.get(job_id)
        if handle is not None:
            try:
                self._make_backend_for_handle(handle).cancel(handle)
            except Exception:  # noqa: BLE001
                logger.exception("cancel failed for %s", job_id)
        self.db.request_cancel(job_id)
        job = self.db.get_job(job_id)
        if job is not None and job["status"] == "queued":
            self.db.update_job(job_id, status=STATUS_CANCELED)

    def _make_backend_for_handle(self, handle: RemoteHandle) -> Backend:
        return self._make_backend(handle.backend)

    # ------------------------------------------------------------------ #
    # Poll loop
    # ------------------------------------------------------------------ #
    def _resume_submitted(self) -> None:
        try:
            with self.db.tx() as conn:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE status IN ('queued','running') "
                    "AND remote_job_id IS NOT NULL"
                ).fetchall()
        except Exception:  # noqa: BLE001
            return
        for row in rows:
            job = dict(row)
            try:
                spec = JobSpec.from_dict(
                    __import__("json").loads(job.get("job_spec_json") or "{}")
                )
            except Exception:  # noqa: BLE001
                continue
            handle = RemoteHandle(
                backend=job.get("backend") or "local",
                remote_id=job["remote_job_id"],
                meta={
                    "remote_wd": f"{self.settings.hpc_remote_workdir.rstrip('/')}/{job['id']}",
                    "spec": spec,
                    "job_id": job["id"],
                },
            )
            with self._lock:
                self._handles[job["id"]] = handle

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._poll_once()
            except Exception:  # noqa: BLE001
                logger.exception("poll error")
            self._stop.wait(self.settings.worker_poll_interval)

    def _poll_once(self) -> None:
        with self._lock:
            handles = dict(self._handles)
        for job_id, handle in handles.items():
            try:
                status, progress = self._make_backend_for_handle(handle).status(handle)
            except Exception as exc:  # noqa: BLE001
                logger.exception("status check failed for %s", job_id)
                continue
            if progress is not None:
                self.db.update_job(job_id, progress=progress)
            if status in (STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELED):
                self._finalize(job_id, handle, status)
                with self._lock:
                    self._handles.pop(job_id, None)

    def _finalize(self, job_id: str, handle: RemoteHandle, status: str) -> None:
        dest = self.settings.resolved_data_dir() / "jobs" / job_id
        try:
            self._make_backend_for_handle(handle).fetch_outputs(handle, dest)
        except Exception:  # noqa: BLE001
            logger.exception("fetch outputs failed for %s", job_id)
        if status == STATUS_SUCCEEDED:
            self.db.update_job(job_id, status=STATUS_SUCCEEDED, progress=100, outputs_dir=str(dest))
        elif status == STATUS_CANCELED:
            self.db.update_job(job_id, status=STATUS_CANCELED)
        else:
            detail = self._make_backend_for_handle(handle).logs(handle)[-2000:]
            self.db.update_job(
                job_id,
                status=STATUS_FAILED,
                error_code="error.remote_failed",
                error_detail=detail or "remote job failed",
            )

    # ------------------------------------------------------------------ #
    # Defaults
    # ------------------------------------------------------------------ #
    def _invocation_defaults(self) -> dict[str, Any]:
        return {
            "kind": self.settings.hpc_invocation_kind,
            "image": self.settings.hpc_container_image,
            "module": self.settings.hpc_module_load,
            "conda_env": self.settings.hpc_conda_env,
        }

    def _resources_defaults(self) -> dict[str, Any]:
        return {
            "partition": self.settings.hpc_partition,
            "account": self.settings.hpc_account,
            "time": self.settings.hpc_time,
            "gres": self.settings.hpc_gres,
            "cpus": self.settings.hpc_cpus,
            "mem": self.settings.hpc_mem,
            "tasks": self.settings.hpc_tasks,
        }

    @staticmethod
    def _load_overrides(job: dict[str, Any]) -> dict[str, Any] | None:
        raw = job.get("spec_overrides_json")
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
