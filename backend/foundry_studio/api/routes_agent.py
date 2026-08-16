"""Agent API: natural-language planning + one-shot job submission.

Two audiences share these endpoints:
- *In-app chat agent*: ``POST /chat`` turns a free-text instruction into a
  transparent JobSpec draft the user confirms in the UI.
- *External LLM agents*: ``POST /run`` creates and submits a job in a single call
  (the Control API surface), and ``GET /capabilities`` exposes the model catalog
  + active backend so an external agent can discover what is runnable.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from foundry_studio import __version__
from foundry_studio.agent.planner import Planner
from foundry_studio.api.deps import get_db, get_manager, get_settings
from foundry_studio.api.errors import ApiError
from foundry_studio.config import Settings
from foundry_studio.db import StudioDB
from foundry_studio.engines import models as model_catalog
from foundry_studio.joblifecycle import JobOrchestrator
from foundry_studio.schemas import JobRead

router = APIRouter()


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class ChatRequest(BaseModel):
    message: str
    lang: str = "en"


class RunRequest(BaseModel):
    model: str | None = None
    message: str | None = None
    name: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    input_files: list[dict[str, str]] = Field(default_factory=list)
    resources: dict[str, Any] = Field(default_factory=dict)
    invocation: dict[str, Any] = Field(default_factory=dict)
    engine_mode: str = "auto"
    lang: str = "en"


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.get("/capabilities")
def capabilities(
    settings: Settings = Depends(get_settings),
    manager: JobOrchestrator = Depends(get_manager),
) -> dict[str, Any]:
    """What an external agent can run: model catalog + active backend."""
    return {
        "version": __version__,
        "backend": manager.backend_info(),
        "models": [
            {
                "id": m["id"],
                "name": m.get("name"),
                "capabilities": m.get("capabilities", []),
                "accepted_extensions": m.get("accepted_extensions", []),
                "param_schema": m.get("param_schema", {}),
            }
            for m in model_catalog.all_models()
        ],
    }


@router.post("/chat")
def chat(
    payload: ChatRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Turn a natural-language instruction into a JobSpec draft (for confirmation)."""
    planner = Planner(
        llm_url=settings.agent_llm_url,
        llm_model=settings.agent_llm_model,
        llm_token=settings.agent_llm_token,
    )
    try:
        plan = planner.plan(payload.message)
    except ValueError as exc:
        raise ApiError(
            "error.agent_cannot_parse",
            status_code=422,
            params={"detail": str(exc)},
        ) from exc
    return plan.to_dict()


@router.post("/run", response_model=JobRead, status_code=201)
def run(
    payload: RunRequest,
    settings: Settings = Depends(get_settings),
    db: StudioDB = Depends(get_db),
    manager: JobOrchestrator = Depends(get_manager),
) -> JobRead:
    """Agent-first one-shot: create + submit a job from a plan or instruction."""
    model = payload.model
    params = dict(payload.params)
    resources = dict(payload.resources)
    invocation = dict(payload.invocation)

    # If only free text was given, let the planner resolve model + params.
    if model is None and payload.message:
        planner = Planner(
            llm_url=settings.agent_llm_url,
            llm_model=settings.agent_llm_model,
            llm_token=settings.agent_llm_token,
        )
        try:
            plan = planner.plan(payload.message)
        except ValueError as exc:
            raise ApiError(
                "error.agent_cannot_parse",
                status_code=422,
                params={"detail": str(exc)},
            ) from exc
        model = plan.model
        params = {**plan.params, **params}
        resources = {**plan.resources, **resources}
        invocation = {**plan.invocation, **invocation}

    if model is None or model_catalog.get_model(model) is None:
        raise ApiError(
            "error.model_not_found",
            status_code=404,
            params={"model": str(model)},
        )

    # Normalize input file descriptors.
    input_files = []
    for f in payload.input_files:
        input_files.append(
            {
                "role": str(f.get("role") or "input"),
                "filename": str(f.get("filename") or ""),
                "name": str(f.get("name") or (f.get("filename") or "").rsplit(".", 1)[0]),
            }
        )
    input_files = [f for f in input_files if f["filename"]]

    job = db.create_job(
        model=model,
        name=payload.name or f"{model} agent job",
        params=params,
        input_files=input_files,
        engine_mode=payload.engine_mode,
    )
    assert job is not None

    # Persist agent-tuned environment overrides (resources/invocation) so the
    # orchestrator applies them when building the JobSpec.
    overrides = {k: v for k, v in {"resources": resources, "invocation": invocation}.items() if v}
    if overrides:
        db.set_spec_overrides(job["id"], overrides)

    updated = manager.submit(job["id"])
    if updated is None:
        raise ApiError("error.job_not_found", status_code=404, params={"job_id": job["id"]})
    # Reuse the jobs serializer for a consistent response.
    from foundry_studio.api.routes_jobs import _job_to_read

    return _job_to_read(updated, data_dir=settings.resolved_data_dir())
