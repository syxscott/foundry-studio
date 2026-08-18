"""File routes: upload inputs to a job, download outputs.

Upload flow (frontend): create job (draft) -> upload files to
``POST /api/jobs/{id}/files`` -> submit job.  Files are stored in the job
directory ``data/jobs/{job_id}/`` and referenced in the job's
``input_files`` descriptor list.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from threading import Thread
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from foundry_studio.api.deps import get_db, get_settings
from foundry_studio.api.errors import ApiError
from foundry_studio.config import Settings
from foundry_studio.db import StudioDB
from foundry_studio.engines import models as model_catalog

router = APIRouter()

MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB

# Allowed extensions by category (validated against the model catalog too).
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_filename(filename: str) -> str:
    name = Path(filename).name
    if not name or name in (".", ".."):
        raise ApiError(
            "error.invalid_file_type",
            params={"filename": filename, "allowed": "see model"},
        )
    if not _SAFE_NAME.match(name):
        # Strip path separators / control chars defensively.
        name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name


def _resolve_job_file(job_dir: Path, rel_path: str) -> Path:
    """Resolve a (possibly nested) relative path inside ``job_dir`` safely.

    Output listings use ``rglob`` relative paths that may contain subdirectories
    (e.g. ``traj/model_0.cif``), so downloads must keep the nested structure
    while still refusing any path traversal.
    """
    parts = [
        p
        for p in rel_path.replace("\\", "/").split("/")
        if p not in ("", ".", "..")
    ]
    if not parts:
        raise ApiError(
            "error.file_not_found", status_code=404, params={"path": rel_path}
        )
    candidate = job_dir.resolve()
    for part in parts:
        candidate = candidate / _validate_filename(part)
    candidate = candidate.resolve()
    if not candidate.is_relative_to(job_dir.resolve()):
        raise ApiError(
            "error.file_not_found", status_code=404, params={"path": rel_path}
        )
    return candidate


@router.post("/{job_id}/files", response_model=dict)
async def upload_files(
    job_id: str,
    files: list[UploadFile] = File(...),
    role: str = Form("input"),
    settings: Settings = Depends(get_settings),
    db: StudioDB = Depends(get_db),
) -> dict:
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

    model_info = model_catalog.get_model(job["model"])
    allowed = set(model_info.get("accepted_extensions", [])) if model_info else set()

    job_dir = settings.resolved_data_dir() / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    uploaded: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    for f in files:
        filename = _validate_filename(f.filename or "upload.bin")
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if allowed and ext not in allowed:
            errors.append(
                {
                    "filename": filename,
                    "error": "invalid_file_type",
                    "detail": f"allowed: {', '.join(sorted(allowed))}",
                }
            )
            continue

        dest = job_dir / filename
        total = 0
        try:
            with open(dest, "wb") as fh:
                while chunk := await f.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES:
                        raise ApiError(
                            "error.upload_failed",
                            status_code=413,
                            params={"detail": f"file exceeds {MAX_UPLOAD_BYTES // (1024**3)} GiB limit"},
                        )
                    fh.write(chunk)
        except ApiError:
            dest.unlink(missing_ok=True)
            raise
        except Exception as exc:  # noqa: BLE001
            dest.unlink(missing_ok=True)
            errors.append(
                {
                    "filename": filename,
                    "error": "upload_failed",
                    "detail": str(exc),
                }
            )
            continue

        uploaded.append(
            {
                "role": role,
                "filename": filename,
                "name": Path(filename).stem,
            }
        )

    if uploaded:
        existing = _json_loads(job.get("input_files_json") or "[]")
        existing = [e for e in existing if e.get("filename") not in {u["filename"] for u in uploaded}]
        db.set_input_files(job_id, existing + uploaded)

    return {"job_id": job_id, "uploaded": uploaded, "errors": errors}


def _json_loads(text: str) -> list:
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


@router.get("/{job_id}/files/{filename:path}")
def download_file(
    job_id: str,
    filename: str,
    settings: Settings = Depends(get_settings),
    db: StudioDB = Depends(get_db),
) -> FileResponse:
    job = db.get_job(job_id)
    if job is None:
        raise ApiError(
            "error.job_not_found", status_code=404, params={"job_id": job_id}
        )
    job_dir = settings.resolved_data_dir() / "jobs" / job_id
    path = _resolve_job_file(job_dir, filename)
    if not path.is_file():
        raise ApiError(
            "error.file_not_found",
            status_code=404,
            params={"path": filename},
        )
    media_type = _media_type(path.name)
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.get("/{job_id}/download-zip")
def download_job_zip(
    job_id: str,
    settings: Settings = Depends(get_settings),
    db: StudioDB = Depends(get_db),
) -> FileResponse:
    """Zip all job outputs into a single archive for download."""
    import zipfile

    job = db.get_job(job_id)
    if job is None:
        raise ApiError(
            "error.job_not_found", status_code=404, params={"job_id": job_id}
        )
    outputs_dir = job.get("outputs_dir")
    if not outputs_dir or not Path(outputs_dir).is_dir():
        raise ApiError(
            "error.file_not_found",
            status_code=404,
            params={"path": f"outputs of {job_id}"},
        )
    out_root = Path(outputs_dir)
    files = [p for p in out_root.rglob("*") if p.is_file()]
    if not files:
        raise ApiError(
            "error.file_not_found",
            status_code=404,
            params={"path": f"outputs of {job_id}"},
        )

    tmp_dir = settings.resolved_data_dir() / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    zip_path = tmp_dir / f"{job_id}_outputs.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, arcname=p.relative_to(out_root).as_posix())

    # Schedule cleanup in a background thread after a delay (gives time for download to complete)
    t = Thread(target=_cleanup_zip_delayed, args=(zip_path, 300), daemon=True)
    t.start()

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{job_id}_outputs.zip",
    )


def _cleanup_zip_delayed(zip_path: Path, delay: float = 300.0) -> None:
    """Delete the temporary zip file after a delay."""
    time.sleep(delay)
    if zip_path.exists():
        try:
            os.unlink(zip_path)
        except OSError:
            pass


def _media_type(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".cif") or lower.endswith(".mmcif"):
        return "chemical/x-cif"
    if lower.endswith(".gz"):
        return "application/gzip"
    if lower.endswith(".pdb"):
        return "chemical/x-pdb"
    if lower.endswith((".fa", ".fasta", ".fas")):
        return "text/plain"
    if lower.endswith(".json"):
        return "application/json"
    if lower.endswith(".zip"):
        return "application/zip"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".svg"):
        return "image/svg+xml"
    if lower.endswith(".log") or lower.endswith(".txt"):
        return "text/plain"
    return "application/octet-stream"
