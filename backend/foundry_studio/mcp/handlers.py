"""JSON-RPC request handlers for the foundry-studio MCP server.

Each handler takes a dict of method parameters and returns a result dict
(or raises a JSON-RPC error).  The actual I/O with the FastAPI backend
is done via httpx so this process remains independent of the web server.
"""

from __future__ import annotations

import os
import httpx
from typing import Any

__all__ = [
    "METHODS",
    "handle_request",
]

_BASE_URL = os.environ.get("FOUNDRY_STUDIO_API_URL", "http://localhost:8000")
_TIMEOUT = 30.0


def _api_path(path: str) -> str:
    return f"{_BASE_URL}/api{path}"


async def _get(path: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(_api_path(path))
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]


async def _post(path: str, json: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.post(_api_path(path), json=json)
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]


# -------------------------------------------------------------------------- #
# Individual tool handlers                                                    #
# -------------------------------------------------------------------------- #


async def handle_list_models(_params: dict[str, Any]) -> dict[str, Any]:
    """Return the list of available protein-design models."""
    models = await _get("/models")
    # Normalize to a flat list of name + description
    return {
        "models": [
            {
                "name": m.get("name", ""),
                "description": m.get("description", ""),
                "kind": m.get("kind", ""),
            }
            for m in models
        ]
    }


async def handle_list_jobs(params: dict[str, Any]) -> dict[str, Any]:
    """Return recent jobs, optionally filtered by status."""
    status = params.get("status", "")
    limit = int(params.get("limit", 20))
    path = "/jobs"
    if status:
        path = f"/jobs?status={status}"
    data = await _get(path)
    items = data.get("items", []) if isinstance(data, dict) else data
    return {
        "jobs": [
            {
                "job_id": j.get("job_id", ""),
                "status": j.get("status", ""),
                "created_at": j.get("created_at", ""),
                "kind": j.get("kind", ""),
                "description": j.get("description", ""),
            }
            for j in items[:limit]
        ]
    }


async def handle_get_job_status(params: dict[str, Any]) -> dict[str, Any]:
    """Return full status details for one job."""
    job_id = params["job_id"]
    return await _get(f"/jobs/{job_id}")


async def handle_get_job_logs(params: dict[str, Any]) -> dict[str, Any]:
    """Return the latest log lines for a job."""
    job_id = params["job_id"]
    data = await _get(f"/jobs/{job_id}/logs")
    return {"logs": data.get("logs", "")}


async def handle_submit_design(params: dict[str, Any]) -> dict[str, Any]:
    """Submit a new protein-design job."""
    payload = {
        "target": params["target"],
        "input_type": params.get("input_type", "pdb_path"),
        "kind": params.get("method", "rfdiffusion"),
        "num_sequences": params.get("num_sequences", 5),
        "temperature": params.get("temperature", 0.1),
        "lang": params.get("lang", "en"),
    }
    # Step 1: create job
    job = await _post("/jobs", payload)
    # Step 2: submit it
    job = await _post(f"/jobs/{job['job_id']}/submit", {})
    return {"job_id": job.get("job_id"), "status": job.get("status")}


async def handle_download_results(params: dict[str, Any]) -> dict[str, Any]:
    """Return the download URL for a completed job's results."""
    job_id = params["job_id"]
    # Verify the job is completed first
    job = await _get(f"/jobs/{job_id}")
    if job.get("status") != "completed":
        return {"ok": False, "error": f"job {job_id} is not completed (status: {job.get('status')})"}
    download_url = f"{_BASE_URL}/api/jobs/{job_id}/download-zip"
    return {"url": download_url}


async def handle_cancel_job(params: dict[str, Any]) -> dict[str, Any]:
    """Request cancellation of a job."""
    job_id = params["job_id"]
    return await _post(f"/jobs/{job_id}/cancel", {})


# -------------------------------------------------------------------------- #
# Dispatch table                                                             #
# -------------------------------------------------------------------------- #

METHODS: dict[str, tuple[list[str], Any]] = {
    # method_name: (required_param_names, handler_async_fn)
    "list_models": ([], handle_list_models),
    "list_jobs": ([], handle_list_jobs),
    "get_job_status": (["job_id"], handle_get_job_status),
    "get_job_logs": (["job_id"], handle_get_job_logs),
    "submit_design": (["target"], handle_submit_design),
    "download_results": (["job_id"], handle_download_results),
    "cancel_job": (["job_id"], handle_cancel_job),
}


async def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    """Process one JSON-RPC request and return a response dict, or None for notifications."""
    method = request.get("method", "")
    if method not in METHODS:
        # Per JSON-RPC 2.0, method not found returns -32601
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    required, handler = METHODS[method]
    params = request.get("params") or {}

    # Validate required parameters
    missing = [p for p in required if p not in params]
    if missing:
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {
                "code": -32602,
                "message": f"Missing required parameter(s): {', '.join(missing)}",
            },
        }

    try:
        result = await handler(params)
        req_id = request.get("id")
        # Notifications (id is None) don't get a response
        if req_id is None:
            return None
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    except httpx.HTTPStatusError as exc:
        req_id = request.get("id")
        if req_id is None:
            return None
        try:
            err_body = exc.response.json()
        except Exception:
            err_body = {"message": exc.response.text}
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32000,
                "message": f"Backend API error ({exc.response.status_code}): {err_body.get('message', exc.response.text[:100])}",
            },
        }
    except Exception as exc:
        req_id = request.get("id")
        if req_id is None:
            return None
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32000, "message": f"Internal error: {exc}"},
        }
