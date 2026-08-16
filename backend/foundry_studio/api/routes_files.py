"""File routes: upload inputs to a job, download outputs.

Upload flow (frontend): create job (draft) -> upload files to
``POST /api/jobs/{id}/files`` -> submit job.  Files are stored in the job
directory ``data/jobs/{job_id}/`` and referenced in the job's
``input_files`` descriptor list.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

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
        try:
            with open(dest, "wb") as fh:
                while chunk := await f.read(1024 * 1024):
                    fh.write(chunk)
        except Exception as exc:  # noqa: BLE001
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
        existing = json_loads(job.get("input_files_json") or "[]")
        existing = [e for e in existing if e.get("filename") not in {u["filename"] for u in uploaded}]
        db.set_input_files(job_id, existing + uploaded)

    return {"job_id": job_id, "uploaded": uploaded, "errors": errors}


def json_loads(text: str):
    import json

    try:
        return json.loads(text)
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
    safe_name = _validate_filename(filename)
    job_dir = settings.resolved_data_dir() / "jobs" / job_id
    path = (job_dir / safe_name).resolve()
    # Path traversal guard: must stay inside the job directory.
    if not path.is_relative_to(job_dir.resolve()):
        raise ApiError(
            "error.file_not_found",
            status_code=404,
            params={"path": filename},
        )
    if not path.is_file():
        raise ApiError(
            "error.file_not_found",
            status_code=404,
            params={"path": filename},
        )
    media_type = _media_type(path.name)
    return FileResponse(path, media_type=media_type, filename=path.name)


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
