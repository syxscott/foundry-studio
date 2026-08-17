"""Pydantic schemas for the foundry-studio API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ModelId = Literal["rfd3", "rfd3na", "rf3", "mpnn"]

JOB_STATUSES = ("queued", "running", "succeeded", "failed", "canceled")

ENGINE_MODES = ("auto", "real", "simulation")


class ModelInfo(BaseModel):
    """Static description of one supported model."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    name_key: str = ""
    description: str
    description_key: str = ""
    # Human-readable capability list, e.g. ["de-novo design", "motif scaffolding"]
    capabilities: list[str] = Field(default_factory=list)
    # Parallel i18n keys for each capability entry.
    capability_keys: list[str] = Field(default_factory=list)
    # Parameter schema used by the frontend to render the task form.
    param_schema: dict[str, Any] = Field(default_factory=dict)
    # Optional per-parameter defaults exposed to the UI.
    param_defaults: dict[str, Any] = Field(default_factory=dict)
    # Accepted upload extensions for this model, e.g. ["cif", "pdb", "fasta"].
    accepted_extensions: list[str] = Field(default_factory=list)
    # Whether a checkpoint is required for the real engine.
    requires_checkpoint: bool = True
    # Available engine kinds on this host.
    available_engines: list[str] = Field(default_factory=list)
    # Current effective engine for this model ("real" or "simulation").
    effective_engine: str | None = None
    # Checkpoint installation state ("installed" | "missing" | "unknown").
    checkpoint_state: str = "unknown"


class CheckpointInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    filename: str
    description: str
    installed: bool
    path: str | None = None
    size_bytes: int | None = None
    url: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    engine_mode: str
    simulation_fallback: bool
    gpu_available: bool
    foundry_available: bool
    data_dir: str
    backend: dict[str, Any] = Field(default_factory=dict)
    workers: list[dict[str, Any]] = Field(default_factory=list)
    llm: dict[str, Any] | None = None
    message: str | None = None


class JobCreate(BaseModel):
    model: str
    name: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    # Uploaded file descriptors: [{"role": "structure", "filename": "x.cif"}, ...]
    input_files: list[dict[str, str]] = Field(default_factory=list)
    engine_mode: str = "auto"


class JobRead(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    model: str
    name: str
    status: str
    params: dict[str, Any] = Field(default_factory=dict)
    input_files: list[dict[str, str]] = Field(default_factory=list)
    engine_mode: str
    progress: int | None = None
    error_code: str | None = None
    error_detail: str | None = None
    cancel_requested: bool = False
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    # HPC / remote execution tracking — useful for external agents to correlate a
    # local job with the scheduler job it spawned (e.g. a SLURM job id).
    remote_job_id: str | None = None
    backend: str | None = None
    scheduler: str | None = None
    # The exact JobSpec handed to the backend (for transparency / re-submission).
    job_spec: dict[str, Any] | None = None
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    logs_url: str | None = None


class JobList(BaseModel):
    items: list[JobRead]
    total: int


class UploadResponse(BaseModel):
    uploaded: list[dict[str, str]] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)


class CancelResponse(BaseModel):
    job_id: str
    canceled: bool
    status: str


class ActionResponse(BaseModel):
    ok: bool
    detail: str = ""


class ErrorResponse(BaseModel):
    message_key: str
    params: dict[str, str] = Field(default_factory=dict)
    message: str
    detail: str | None = None


class LlmSettingsResponse(BaseModel):
    """Current LLM provider configuration (safe, non-sensitive fields only)."""

    provider: str
    base_url: str
    model: str
    api_key_env: str
    key_present: bool
    configured: bool
    timeout: float
    retry: int
