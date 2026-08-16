"""Job routes: create (draft), submit, list, detail, cancel, delete, logs."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from foundry_studio.api.deps import get_db, get_manager, get_settings
from foundry_studio.api.errors import ApiError
from foundry_studio.config import Settings
from foundry_studio.db import StudioDB
from foundry_studio.engines import models as model_catalog
from foundry_studio.engines.base import tail_text
from foundry_studio.engines.registry import (
    engine_modes_for,
    resolve_engine,
)
from foundry_studio.schemas import (
    CancelResponse,
    JobCreate,
    JobList,
    JobRead,
    JOB_STATUSES,
)
from foundry_studio.workers.manager import WorkerManager

router = APIRouter()


def _job_to_read(
    job: dict[str, Any],
    *,
    data_dir: Path,
    include_outputs: bool = True,
    locale: str = "en",
) -> JobRead:
    try:
        params = json.loads(job.get("params_json") or "{}")
    except json.JSONDecodeError:
        params = {}
    try:
        input_files = json.loads(job.get("input_files_json") or "[]")
    except json.JSONDecodeError:
        input_files = []

    outputs: list[dict[str, Any]] = []
    outputs_dir = job.get("outputs_dir")
    if include_outputs and outputs_dir and Path(outputs_dir).is_dir():
        for path in sorted(Path(outputs_dir).rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(Path(outputs_dir)).as_posix()
            outputs.append(
                {
                    "name": rel,
                    "kind": _kind_for(rel),
                    "url": f"/api/jobs/{job['id']}/files/{rel}",
                    "size_bytes": path.stat().st_size,
                }
            )

    logs_url = (
        f"/api/jobs/{job['id']}/logs" if job.get("log_path") else None
    )
    return JobRead(
        id=job["id"],
        model=job["model"],
        name=job.get("name") or "",
        status=job["status"],
        params=params,
        input_files=input_files,
        engine_mode=job.get("engine_mode") or "auto",
        progress=job.get("progress"),
        error_code=job.get("error_code"),
        error_detail=job.get("error_detail"),
        cancel_requested=bool(job.get("cancel_requested")),
        created_at=job["created_at"],
        started_at=job.get("started_at"),
        finished_at=job.get("finished_at"),
        outputs=outputs,
        logs_url=logs_url,
    )


def _kind_for(rel: str) -> str:
    lower = rel.lower()
    if lower.endswith((".cif", ".cif.gz", ".mmcif")):
        return "cif"
    if lower.endswith((".pdb", ".pdb.gz")):
        return "pdb"
    if lower.endswith((".fa", ".fasta", ".fas")):
        return "fasta"
    if lower.endswith(".json"):
        return "json"
    if lower.endswith(".log"):
        return "log"
    if lower.endswith(".txt"):
        return "txt"
    if lower.endswith(".zip"):
        return "zip"
    if lower.endswith((".png", ".jpg", ".jpeg", ".svg")):
        return "image"
    return "file"


def _validate_model(model: str) -> None:
    if model_catalog.get_model(model) is None:
        raise ApiError(
            "error.model_not_found", status_code=404, params={"model": model}
        )


@router.post("", response_model=JobRead, status_code=201)
def create_job(
    payload: JobCreate,
    request: Request,
    settings: Settings = Depends(get_settings),
    db: StudioDB = Depends(get_db),
) -> JobRead:
    _validate_model(payload.model)

    if payload.engine_mode not in ("auto", "real", "simulation"):
        raise ApiError(
            "error.invalid_params",
            params={"detail": f"engine_mode must be one of auto/real/simulation, got {payload.engine_mode}"},
        )

    # Normalize input file descriptors.
    input_files = []
    for f in payload.input_files:
        input_files.append(
            {
                "role": str(f.get("role") or "input"),
                "filename": str(f.get("filename") or ""),
                "name": str(f.get("name") or Path(f.get("filename") or "").stem),
            }
        )
    input_files = [f for f in input_files if f["filename"]]

    job = db.create_job(
        model=payload.model,
        name=payload.name or f"{payload.model} job",
        params=payload.params,
        input_files=input_files,
        engine_mode=payload.engine_mode,
    )
    assert job is not None
    return _job_to_read(job, data_dir=settings.resolved_data_dir())


@router.get("", response_model=JobList)
def list_jobs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
    settings: Settings = Depends(get_settings),
    db: StudioDB = Depends(get_db),
) -> JobList:
    if status is not None and status not in JOB_STATUSES:
        raise ApiError(
            "error.invalid_params",
            params={"detail": f"unknown status '{status}'"},
        )
    if status is None:
        rows = db.list_jobs(limit=limit, offset=offset)
        total = len(rows)
    else:
        with db.tx() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM jobs WHERE status = ?", (status,)
            ).fetchone()
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            ).fetchall()
        rows = [dict(r) for r in rows]
        total = int(row["n"]) if row else 0
    return JobList(
        items=[
            _job_to_read(r, data_dir=settings.resolved_data_dir())
            for r in rows
        ],
        total=total,
    )


@router.get("/{job_id}", response_model=JobRead)
def get_job(
    job_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    db: StudioDB = Depends(get_db),
) -> JobRead:
    job = db.get_job(job_id)
    if job is None:
        raise ApiError(
            "error.job_not_found", status_code=404, params={"job_id": job_id}
        )
    locale = request.query_params.get("lang", "en")
    return _job_to_read(job, data_dir=settings.resolved_data_dir(), locale=locale)


@router.post("/{job_id}/submit", response_model=JobRead)
def submit_job(
    job_id: str,
    settings: Settings = Depends(get_settings),
    db: StudioDB = Depends(get_db),
    manager: WorkerManager = Depends(get_manager),
) -> JobRead:
    job = db.get_job(job_id)
    if job is None:
        raise ApiError(
            "error.job_not_found", status_code=404, params={"job_id": job_id}
        )
    if job["status"] not in ("draft", "queued"):
        raise ApiError(
            "error.job_already_finished",
            status_code=409,
            params={"job_id": job_id},
        )

    # Validate that the model has a usable engine before queueing.
    try:
        _, effective, is_sim = resolve_engine(
            job["model"],
            engine_mode=settings.engine_mode,
            allow_simulation=settings.allow_simulation_fallback,
            db=db,
            workdir=settings.resolved_data_dir() / "jobs",
            log_path=settings.resolved_data_dir() / "logs" / f"{job_id}.log",
        )
    except RuntimeError as exc:
        raise ApiError(
            "error.engine_unavailable",
            status_code=503,
            params={"model": job["model"], "detail": str(exc)},
        ) from exc

    updated = db.submit_job(job_id)
    assert updated is not None

    # Ensure a worker is alive for this model so the job starts promptly.
    if settings.worker_autostart:
        manager.ensure_worker(job["model"])
    return _job_to_read(updated, data_dir=settings.resolved_data_dir())


@router.post("/{job_id}/cancel", response_model=CancelResponse)
def cancel_job(
    job_id: str,
    db: StudioDB = Depends(get_db),
) -> CancelResponse:
    job = db.get_job(job_id)
    if job is None:
        raise ApiError(
            "error.job_not_found", status_code=404, params={"job_id": job_id}
        )
    if job["status"] in ("succeeded", "failed", "canceled"):
        raise ApiError(
            "error.cancel_failed",
            status_code=409,
            params={"job_id": job_id},
        )
    updated = db.request_cancel(job_id)
    assert updated is not None
    # If still queued, cancel is immediate.
    if updated["status"] == "queued":
        db.update_job(job_id, status="canceled")
        updated = db.get_job(job_id)
    assert updated is not None
    return CancelResponse(
        job_id=job_id, canceled=True, status=updated["status"]
    )


@router.delete("/{job_id}", response_model=dict)
def delete_job(
    job_id: str,
    settings: Settings = Depends(get_settings),
    db: StudioDB = Depends(get_db),
) -> dict:
    job = db.get_job(job_id)
    if job is None:
        raise ApiError(
            "error.job_not_found", status_code=404, params={"job_id": job_id}
        )
    if job["status"] == "running":
        raise ApiError(
            "error.job_already_finished",
            status_code=409,
            params={"job_id": job_id},
            detail="cannot delete a running job; cancel it first",
        )
    db.delete_job(job_id)
    # Best-effort cleanup of job artifacts.
    job_dir = settings.resolved_data_dir() / "jobs" / job_id
    if job_dir.is_dir():
        import shutil

        shutil.rmtree(job_dir, ignore_errors=True)
    return {"ok": True, "job_id": job_id}


@router.get("/{job_id}/logs")
async def job_logs(
    job_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    db: StudioDB = Depends(get_db),
):
    """Return the job log file (polling-friendly)."""
    job = db.get_job(job_id)
    if job is None:
        raise ApiError(
            "error.job_not_found", status_code=404, params={"job_id": job_id}
        )
    log_path = job.get("log_path")
    if not log_path or not Path(log_path).is_file():
        return {"job_id": job_id, "logs": ""}
    return {"job_id": job_id, "logs": tail_text(Path(log_path), max_chars=200000)}


@router.get("/{job_id}/logs/stream")
async def job_logs_stream(
    job_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    db: StudioDB = Depends(get_db),
):
    """Server-Sent Events stream of the job log file tail."""
    job = db.get_job(job_id)
    if job is None:
        raise ApiError(
            "error.job_not_found", status_code=404, params={"job_id": job_id}
        )
    log_path = job.get("log_path")
    if not log_path:
        log_path = str(
            settings.resolved_data_dir() / "logs" / f"{job_id}.log"
        )

    async def event_stream():
        last_size = 0
        terminal = {"succeeded", "failed", "canceled"}
        while True:
            try:
                p = Path(log_path)
                if p.is_file():
                    size = p.stat().st_size
                    if size > last_size:
                        with open(p, "r", encoding="utf-8", errors="replace") as fh:
                            fh.seek(last_size)
                            chunk = fh.read()
                        if chunk:
                            yield f"data: {json.dumps({'logs': chunk}, ensure_ascii=False)}\n\n"
                            last_size = size
                current = db.get_job(job_id)
                if current and current["status"] in terminal:
                    # Final flush.
                    if p.is_file() and p.stat().st_size > last_size:
                        with open(p, "r", encoding="utf-8", errors="replace") as fh:
                            fh.seek(last_size)
                            chunk = fh.read()
                        if chunk:
                            yield f"data: {json.dumps({'logs': chunk}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'status': current['status']}, ensure_ascii=False)}\n\n"
                    break
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
