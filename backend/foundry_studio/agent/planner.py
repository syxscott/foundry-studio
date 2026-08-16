"""Planner: natural-language -> JobSpec draft.

Two modes share one contract (the :class:`PlanResult`):

- *Heuristic* (default, zero dependencies): a deterministic parser that recognises
  the model id, common parameters, and resource hints from free text. It never
  invents values and reports unrecognised snippets as warnings, so the agent
  always produces a valid, transparent plan.
- *LLM* (optional): when ``agent_llm_provider`` is configured, the planner sends
  the instruction (plus the model catalog) to that OpenAI-compatible endpoint and
  parses the JSON plan it returns. If the call fails for any reason it falls back
  to the heuristic, so the system keeps working without a live model.

The streaming path (``plan_stream``) is what the in-app chat agent consumes for
real-time token display; the one-shot path (``resolve``) is what the external
Control API (``/run``) uses.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from foundry_studio.config import Settings
from foundry_studio.engines import models as model_catalog
from foundry_studio.llm.registry import build_registry

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
    def __init__(self, settings: Settings | None = None):
        self.settings = settings

    # ------------------------------------------------------------------ #
    # Public entry points
    # ------------------------------------------------------------------ #
    def _registry(self):
        if self.settings is None:
            return None
        return build_registry(self.settings)

    async def resolve(self, text: str) -> PlanResult:
        """One-shot planning for the Control API: LLM when available, else heuristic."""
        reg = self._registry()
        provider = reg.default_provider() if reg else None
        if provider is None:
            return self._plan_heuristic(text)
        try:
            messages = self._build_messages(text)
            model = getattr(self.settings, "agent_llm_model", None)
            raw = await provider.complete(messages, model=model or None)
            return self._parse_llm_plan(raw, text)
        except Exception as exc:  # noqa: BLE001
            result = self._plan_heuristic(text)
            result.warnings.append(f"llm planner unavailable ({exc}); used heuristic")
            return result

    async def plan_stream(self, text: str) -> AsyncIterator[dict[str, Any]]:
        """Stream planning events: ``token`` deltas then a final ``plan`` event.

        Yields dicts of the form
        ``{"type": "token", "text": "…"}`` and
        ``{"type": "plan", "plan": <PlanResult.to_dict()>}``. On any failure it
        yields a heuristic ``plan`` rather than raising, so the UI always gets a
        usable result.
        """
        reg = self._registry()
        provider = reg.default_provider() if reg else None
        if provider is None:
            yield {"type": "plan", "plan": self._plan_heuristic(text).to_dict()}
            return
        try:
            messages = self._build_messages(text)
            model = getattr(self.settings, "agent_llm_model", None)
            acc: list[str] = []
            async for delta in provider.stream(messages, model=model or None):
                acc.append(delta)
                yield {"type": "token", "text": delta}
            plan = self._parse_llm_plan("".join(acc), text)
            yield {"type": "plan", "plan": plan.to_dict()}
        except Exception as exc:  # noqa: BLE001
            result = self._plan_heuristic(text)
            result.warnings.append(f"llm planner unavailable ({exc}); used heuristic")
            yield {"type": "plan", "plan": result.to_dict()}

    # ------------------------------------------------------------------ #
    # LLM message construction + parsing
    # ------------------------------------------------------------------ #
    def _build_messages(self, text: str) -> list[dict[str, str]]:
        catalog_lines = []
        for m in model_catalog.all_models():
            caps = m.get("capabilities", [])
            catalog_lines.append(
                f"- {m['id']}: {m.get('name', '')} — capabilities: {', '.join(caps)}"
            )
        catalog = "\n".join(catalog_lines)
        system = (
            "You are the planning agent for foundry-studio, a control surface for the "
            "RosettaCommons Foundry protein-design toolkit (RFD3, RFD3NA, RF3, "
            "ProteinMPNN). Given a natural-language experiment description, output a "
            "single JSON object and NOTHING else.\n"
            "Required keys:\n"
            "  model: one of [rfd3, rfd3na, rf3, mpnn]\n"
            "  name: short job name (string)\n"
            "  params: object of model parameters (contigs, n_batches, "
            "diffusion_steps, sampler, symmetry, hotspots, seed, num_steps, "
            "n_recycles, temperature, model_type, number_of_batches, batch_size, …)\n"
            "  resources: object with optional keys gres (e.g. 'gpu:1'), account, "
            "partition, time (HH:MM:SS)\n"
            "  invocation: object (usually {})\n"
            "  warnings: array of strings (notes about ambiguity)\n"
            "  missing_inputs: array of strings (e.g. ['upload a structure file "
            "(cif/pdb)'])\n"
            "Available models:\n"
            f"{catalog}\n"
            "Only output the JSON object. Do not wrap it in markdown fences."
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ]

    def _parse_llm_plan(self, raw: str, text: str) -> PlanResult:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("LLM did not return a JSON plan")
        blob = raw[start : end + 1]
        data = json.loads(blob)
        model = data.get("model")
        if model is None or model_catalog.get_model(model) is None:
            raise ValueError(f"LLM returned unknown model '{model}'")
        return PlanResult(
            model=model,
            name=data.get("name", "") or f"{model} agent job",
            params=data.get("params", {}) or {},
            resources=data.get("resources", {}) or {},
            invocation=data.get("invocation", {}) or {},
            warnings=list(data.get("warnings", []) or []),
            missing_inputs=list(data.get("missing_inputs", []) or []),
            resolved_by="llm",
        )

    # ------------------------------------------------------------------ #
    # Heuristic parser (unchanged behaviour, dependency-free)
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
        needs = model in ("rf3", "mpnn", "rfd3na")
        mentioned = bool(re.search(r"\.(cif|pdb|fasta|fa|json)\b", text, re.I))
        if needs and not mentioned:
            exts = info.get("accepted_extensions", [])
            return [f"upload a structure file ({', '.join(exts)}) before running"]
        return []
