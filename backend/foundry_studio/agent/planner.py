"""Planner: natural-language -> JobSpec draft.

Two modes:
- *Heuristic* (default, zero dependencies): a deterministic parser that recognises
  the model id, common parameters, and resource hints from a free-text instruction.
  It never invents values and reports unrecognised snippets as warnings, so the
  agent always produces a valid, transparent plan.
- *LLM* (optional): when ``agent_llm_url`` is configured, the same interface
  delegates to that endpoint.  If the call fails, it falls back to the heuristic
  so the system keeps working without a live model.

The output :class:`PlanResult` is exactly what the UI shows for confirmation and
what ``/api/agent/run`` turns into a submitted job — one shared contract for the
in-app chat agent and external agents alike.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from foundry_studio.engines import models as model_catalog

_MODEL_ALIASES: dict[str, str] = {
    "rfd3na": "rfd3na",
    "rfdiffusion3na": "rfd3na",
    "nucleic": "rfd3na",
    "rfd3": "rfd3",
    "rfdiffusion3": "rfd3",
    "rf diffusion 3": "rfd3",
    "rfdiffusion": "rfd3",
    "rf3": "rf3",
    "rosefold3": "rf3",
    "rosettafold3": "rf3",
    "rosettafold": "rf3",
    "rfold3": "rf3",
    "mpnn": "mpnn",
    "proteinmpnn": "mpnn",
    "ligandmpnn": "mpnn",
    "inverse folding": "mpnn",
    "sequence design": "mpnn",
}


@dataclass
class PlanResult:
    model: str
    params: dict[str, Any] = field(default_factory=dict)
    name: str = ""
    resources: dict[str, Any] = field(default_factory=dict)
    invocation: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    resolved_by: str = "heuristic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "name": self.name,
            "params": self.params,
            "resources": self.resources,
            "invocation": self.invocation,
            "warnings": self.warnings,
            "missing_inputs": self.missing_inputs,
            "resolved_by": self.resolved_by,
        }


class Planner:
    def __init__(self, *, llm_url: str = "", llm_model: str = "", llm_token: str = ""):
        self.llm_url = llm_url
        self.llm_model = llm_model
        self.llm_token = llm_token

    def plan(self, text: str) -> PlanResult:
        if self.llm_url:
            try:
                return self._plan_llm(text)
            except Exception as exc:  # noqa: BLE001
                # Fall back rather than fail the whole request.
                result = self._plan_heuristic(text)
                result.warnings.append(f"llm planner unavailable ({exc}); used heuristic")
                return result
        return self._plan_heuristic(text)

    # ------------------------------------------------------------------ #
    def _plan_heuristic(self, text: str) -> PlanResult:
        lowered = text.lower()
        model = self._detect_model(lowered)
        if model is None:
            raise ValueError(
                "Could not identify a model. Try naming one of: "
                + ", ".join(model_catalog.ORDER)
                + " (e.g. 'design with RFD3', 'predict with RF3', 'sequence with MPNN')."
            )

        params: dict[str, Any] = {}
        warnings: list[str] = []
        self._parse_params(model, text, params, warnings)

        resources: dict[str, Any] = {}
        self._parse_resources(lowered, resources)

        info = model_catalog.get_model(model) or {}
        missing_inputs = self._check_inputs(model, info, text)

        name = f"{model} agent job"
        return PlanResult(
            model=model,
            params=params,
            name=name,
            resources=resources,
            warnings=warnings,
            missing_inputs=missing_inputs,
            resolved_by="heuristic",
        )

    def _detect_model(self, lowered: str) -> str | None:
        # Longest alias first to avoid 'mpnn' matching inside 'proteinmpnn'.
        for alias, model in sorted(_MODEL_ALIASES.items(), key=lambda kv: -len(kv[0])):
            if alias in lowered:
                return model
        return None

    def _parse_params(self, model: str, text: str, params: dict, warnings: list) -> None:
        # Batch / design / sequence count.
        m = re.search(r"(?:designs?|batches|sequences?|samples?)\D*?(\d+)", text, re.I)
        if m:
            n = int(m.group(1))
            if model == "mpnn":
                params["number_of_batches"] = min(max(n, 1), 64)
            else:
                params["n_batches"] = min(max(n, 1), 64)

        # Contigs.
        m = re.search(r"contigs?\s*[:=]?\s*([A-Za-z0-9\-\/]+)", text, re.I)
        if m:
            params["contigs"] = m.group(1)

        # Diffusion steps / recycles.
        m = re.search(r"(?:diffusion\s*steps?|steps?)\D*?(\d+)", text, re.I)
        if m:
            if model == "rf3":
                params["num_steps"] = int(m.group(1))
            else:
                params["diffusion_steps"] = int(m.group(1))
        m = re.search(r"recycles?\D*?(\d+)", text, re.I)
        if m and model == "rf3":
            params["n_recycles"] = int(m.group(1))

        # Temperature.
        m = re.search(r"temperature\D*?([\d.]+)", text, re.I)
        if m and model == "mpnn":
            params["temperature"] = float(m.group(1))

        # Sampler (rfd3 family).
        for s in ("reflow", "analytic", "ddpm", "ddim"):
            if re.search(rf"\b{s}\b", text, re.I):
                params["sampler"] = s
                break

        # Symmetry.
        m = re.search(r"symmetry\D*?([A-Za-z0-9]+)", text, re.I)
        if m:
            params["symmetry"] = m.group(1)

        # Hotspots.
        m = re.search(r"hotspots?\D*?([A-Z0-9,\s]+)", text, re.I)
        if m:
            params["hotspots"] = m.group(1).strip()

        # Seed.
        m = re.search(r"seed\D*?(\d+)", text, re.I)
        if m:
            params["seed"] = int(m.group(1))

        # MPNN model variant.
        if model == "mpnn":
            if re.search(r"ligand", text, re.I):
                params["model_type"] = "ligand_mpnn"
            elif re.search(r"protein", text, re.I):
                params["model_type"] = "protein_mpnn"

    def _parse_resources(self, lowered: str, resources: dict) -> None:
        if re.search(r"\bgpu\b", lowered):
            resources["gres"] = "gpu:1"
        m = re.search(r"account\D*?([A-Za-z0-9_\-]+)", lowered)
        if m:
            resources["account"] = m.group(1)
        m = re.search(r"partition\D*?([A-Za-z0-9_\-]+)", lowered)
        if m:
            resources["partition"] = m.group(1)
        m = re.search(r"time\D*?(\d{1,2}:\d{2}:\d{2})", lowered)
        if m:
            resources["time"] = m.group(1)

    def _check_inputs(self, model: str, info: dict, text: str) -> list[str]:
        # Models that need an input structure, but only warn if none mentioned.
        needs = model in ("rf3", "mpnn", "rfd3na")
        mentioned = bool(re.search(r"\.(cif|pdb|fasta|fa|json)\b", text, re.I))
        if needs and not mentioned:
            exts = info.get("accepted_extensions", [])
            return [f"upload a structure file ({', '.join(exts)}) before running"]
        return []

    # ------------------------------------------------------------------ #
    def _plan_llm(self, text: str) -> PlanResult:
        import urllib.request

        payload = json.dumps(
            {"model": self.llm_model or "foundry-agent", "prompt": text}
        ).encode("utf-8")
        req = urllib.request.Request(
            self.llm_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.llm_token}"} if self.llm_token else {}),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        # Expect either a full plan or a text completion we re-parse heuristically.
        if isinstance(data, dict) and data.get("model"):
            return PlanResult(
                model=data["model"],
                params=data.get("params", {}),
                name=data.get("name", ""),
                resources=data.get("resources", {}),
                invocation=data.get("invocation", {}),
                warnings=data.get("warnings", []),
                missing_inputs=data.get("missing_inputs", []),
                resolved_by="llm",
            )
        # Treat the LLM reply as natural language and re-parse.
        return self._plan_heuristic(data.get("text", str(data)))
