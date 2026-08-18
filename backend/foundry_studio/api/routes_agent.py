"""Agent API: natural-language planning + one-shot job submission.

Two audiences share these endpoints:
- *In-app chat agent*: ``POST /chat`` streams tokens in real time (Server-Sent
  Events) and ends with a transparent JobSpec draft the user confirms in the UI.
- *External LLM agents*: ``POST /run`` creates and submits a job in a single call
  (the Control API surface), and ``GET /capabilities`` exposes the model catalog
  + the configured LLM provider(s) so an external agent can discover what is
  runnable.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from foundry_studio import __version__
from foundry_studio.agent.planner import Planner
from foundry_studio.agent.tool_agent import ToolAgent
from foundry_studio.api.deps import get_db, get_manager, get_settings
from foundry_studio.api.errors import ApiError
from foundry_studio.config import Settings
from foundry_studio.db import StudioDB
from foundry_studio.engines import models as model_catalog
from foundry_studio.joblifecycle import JobOrchestrator
from foundry_studio.llm.registry import build_registry
from foundry_studio.schemas import JobRead
from foundry_studio.tools import ToolRegistry

router = APIRouter()


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class ChatRequest(BaseModel):
    message: str
    lang: str = "en"
    api_key: str | None = None  # frontend-provided key; overrides env var
    base_url: str | None = None  # frontend-provided base URL; overrides env var
    model: str | None = None  # frontend-provided model; overrides env var
    api_format: str | None = None  # "openai_chat" (default) or "anthropic"
    tools: list[dict] | None = None  # OpenAI tool schemas; None = text-only planning


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
    api_key: str | None = None
    base_url: str | None = None  # user-provided LLM base URL
    llm_model: str | None = None  # user-provided LLM model name
    api_format: str | None = None  # "openai_chat" (default) or "anthropic"


# --------------------------------------------------------------------------- #
# SSE helpers
# --------------------------------------------------------------------------- #
def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _chat_sse(planner: Planner, text: str) -> AsyncIterator[str]:
    """Translate Planner stream events into an SSE byte stream.

    Handles ``token``, ``plan``, and ``error`` events from the text-only Planner.
    """
    try:
        async for ev in planner.plan_stream(text):
            kind = ev.get("type")
            if kind == "token":
                yield _sse("token", {"text": ev.get("text", "")})
            elif kind == "plan":
                yield _sse("plan", ev.get("plan", {}))
            elif kind == "error":
                yield _sse(
                    "error",
                    {
                        "message": ev.get("message", "error"),
                        "i18nErrorKey": "error.agent_planner_stream",
                        "errorArgs": {},
                    },
                )
    except Exception as exc:  # noqa: BLE001
        yield _sse(
            "error",
            {
                "message": "Agent streaming failed",
                "i18nErrorKey": "error.agent_planner_stream",
                "errorArgs": {"detail": repr(str(exc)[:200])},
            },
        )
        return
    yield _sse("done", {})


async def _tool_agent_sse(agent: ToolAgent, text: str) -> AsyncIterator[str]:
    """Translate ToolAgent stream events into an SSE byte stream.

    Handles ``token``, ``tool-call``, ``tool-result``, ``plan``, and ``error``
    events from the tool-capable agent.
    """
    try:
        async for ev in agent.run(text):
            kind = ev.get("type")
            if kind == "token":
                yield _sse("token", {"text": ev.get("text", "")})
            elif kind == "tool-call":
                yield _sse("tool-call", {
                    "toolCallId": ev.get("toolCallId", ""),
                    "toolName": ev.get("toolName", ""),
                    "arguments": ev.get("arguments", {}),
                })
            elif kind == "tool-result":
                yield _sse("tool-result", {
                    "toolCallId": ev.get("toolCallId", ""),
                    "ok": ev.get("ok", False),
                    "result": ev.get("result"),
                    "error": ev.get("error"),
                })
            elif kind == "plan":
                yield _sse("plan", ev.get("plan", {}))
            elif kind == "error":
                yield _sse(
                    "error",
                    {
                        "message": ev.get("message", "error"),
                        "i18nErrorKey": "error.agent_planner_stream",
                        "errorArgs": {},
                    },
                )
    except Exception as exc:  # noqa: BLE001
        yield _sse(
            "error",
            {
                "message": "Agent streaming failed",
                "i18nErrorKey": "error.agent_planner_stream",
                "errorArgs": {"detail": repr(str(exc)[:200])},
            },
        )
        return
    yield _sse("done", {})


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.get("/capabilities")
def capabilities(
    settings: Settings = Depends(get_settings),
    manager: JobOrchestrator = Depends(get_manager),
) -> dict[str, Any]:
    """What an external agent can run: model catalog + active backend + LLM providers."""
    return {
        "version": __version__,
        "backend": manager.backend_info(),
        "providers": build_registry(settings).summaries(),
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
        "tools": ToolRegistry.get_all_schemas(),
        "tool_checks": ToolRegistry.get_checks(),
    }


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Stream an NL instruction as tokens, ending with a JobSpec draft (SSE).

    When ``payload.tools`` is provided, the ToolAgent handles tool-calling
    during the conversation.  Otherwise falls back to the text-only Planner.
    """
    if payload.tools:
        agent = ToolAgent(
            settings=settings,
            tools=payload.tools,
            api_key=payload.api_key,
            base_url=payload.base_url,
            model=payload.model,
            api_format=payload.api_format,
        )
        return StreamingResponse(
            _tool_agent_sse(agent, payload.message),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    planner = Planner(
        settings=settings,
        api_key=payload.api_key,
        base_url=payload.base_url,
        model=payload.model,
        api_format=payload.api_format,
    )
    return StreamingResponse(
        _chat_sse(planner, payload.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/run", response_model=JobRead, status_code=201)
async def run(
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
        planner = Planner(settings=settings, api_key=payload.api_key, base_url=payload.base_url, model=payload.llm_model, api_format=payload.api_format)
        try:
            plan = await planner.resolve(payload.message)
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
