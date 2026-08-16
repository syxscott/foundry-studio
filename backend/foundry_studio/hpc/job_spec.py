"""JobSpec: the single abstract description of "what to run, where, how".

Everything in foundry-studio that executes a model — the local mock backend, a
real SLURM/PBS/LSF submission, or an external agent — speaks in terms of a
``JobSpec``.  The UI and the agent layer only ever produce a JobSpec; the
concrete HPC backend translates it into scheduler scripts and transport calls.
This is what keeps the system "not stuck on configuration": swapping the backend
does not change how jobs are described.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Scheduler families we can generate submission scripts for.
SCHEDULERS = ("slurm", "pbs", "lsf", "local")

# How foundry is invoked on the remote side.
INVOCATION_KINDS = ("container", "module", "conda", "script")


@dataclass
class JobSpec:
    """A backend-agnostic description of one compute job.

    ``invocation`` and ``resources`` are filled from the model catalog + server
    settings, but an agent or the UI may override any field before submission —
    that is the "flexible environment" the user wants.
    """

    model: str
    params: dict[str, Any] = field(default_factory=dict)
    input_files: list[dict[str, str]] = field(default_factory=list)
    # How to launch foundry on the compute side.
    invocation: dict[str, Any] = field(default_factory=dict)
    # Scheduler resource requests (partition/account/gres/time/cpus/mem/...).
    resources: dict[str, Any] = field(default_factory=dict)
    # Glob patterns (relative to the remote workdir) fetched back as outputs.
    output_patterns: list[str] = field(default_factory=list)
    name: str = ""
    job_id: str | None = None
    # Local staging directory that holds uploaded inputs + receives outputs.
    local_job_dir: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "name": self.name,
            "job_id": self.job_id,
            "params": self.params,
            "input_files": self.input_files,
            "invocation": self.invocation,
            "resources": self.resources,
            "output_patterns": self.output_patterns,
            "local_job_dir": self.local_job_dir,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobSpec:
        return cls(
            model=data["model"],
            params=data.get("params", {}),
            input_files=data.get("input_files", []),
            invocation=data.get("invocation", {}),
            resources=data.get("resources", {}),
            output_patterns=data.get("output_patterns", []),
            name=data.get("name", ""),
            job_id=data.get("job_id"),
            local_job_dir=data.get("local_job_dir"),
        )


def default_output_patterns(model: str) -> list[str]:
    """Glob patterns the backend should fetch back for a given model."""
    if model in ("rfd3", "rfd3na"):
        return ["*.cif", "*.json", "*.pdb"]
    if model == "rf3":
        return ["*.cif", "*.json", "*.pdb"]
    if model == "mpnn":
        return ["*.fasta", "*.cif", "*.json"]
    return ["*"]


def build_spec(
    *,
    job: dict[str, Any],
    model_info: dict[str, Any],
    invocation_defaults: dict[str, Any],
    resources_defaults: dict[str, Any],
    scheduler: str,
    overrides: dict[str, Any] | None = None,
) -> JobSpec:
    """Build a JobSpec for a queued job row using catalog + server defaults.

    Any value already present on the job row (set by an agent or the UI) wins
    over the server defaults, which in turn win over the model catalog.  The
    ``overrides`` dict (typically produced by the agent planner) is merged last,
    so the agent can flexibly tune the model environment without touching config.
    """
    import json

    try:
        params = json.loads(job.get("params_json") or "{}")
    except json.JSONDecodeError:
        params = {}
    try:
        input_files = json.loads(job.get("input_files_json") or "[]")
    except json.JSONDecodeError:
        input_files = []

    # Engine mode is only meaningful for the local (mock) backend; it selects
    # real vs simulation engine.  Pass it through the invocation hints.
    engine_mode = job.get("engine_mode") or "auto"

    invocation = dict(invocation_defaults)
    invocation.setdefault("kind", "container")
    invocation["engine_mode"] = engine_mode

    resources = dict(resources_defaults)
    resources.setdefault("partition", "")
    resources.setdefault("account", "")
    resources.setdefault("time", "24:00:00")
    resources.setdefault("gres", "")
    resources.setdefault("cpus", 4)
    resources.setdefault("mem", "16G")
    resources.setdefault("tasks", 1)

    if overrides:
        params = {**params, **(overrides.get("params") or {})}
        invocation.update(overrides.get("invocation") or {})
        resources.update(overrides.get("resources") or {})

    return JobSpec(
        model=job["model"],
        name=job.get("name") or f"{job['model']} job",
        job_id=job["id"],
        params=params,
        input_files=input_files,
        invocation=invocation,
        resources=resources,
        output_patterns=default_output_patterns(job["model"]),
        local_job_dir=str(Path(job.get("outputs_dir") or "").parent / job["id"])
        if job.get("outputs_dir")
        else None,
    )
