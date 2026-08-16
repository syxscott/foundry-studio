"""Real RFdiffusion3 (RFD3) engine.

Wraps ``rfd3.engine.RFD3InferenceEngine``.  The heavy imports are performed
lazily inside ``_initialize`` so that the API server and the simulation path
never pay the torch/atomworks import cost.

Job parameters map to a design-spec JSON file (see
``rfd3.inference.input_parsing.DesignInputSpecification``); uploaded CIF/PDB
files are referenced through ``input`` so they act as scaffolds/motifs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from foundry_studio.engines.base import BaseEngine, EngineResult
from foundry_studio.engines.checkpoints import model_checkpoint_state


def _build_design_json(
    params: dict[str, Any], job_dir: Path, input_files: list[dict[str, Any]]
) -> Path:
    """Write the design specification JSON consumed by RFD3."""
    spec: dict[str, Any] = {}

    contigs = str(params.get("contigs") or "").strip()
    if contigs:
        spec["contig"] = contigs

    hotspots = str(params.get("hotspots") or "").strip()
    if hotspots:
        spec["select_hotspots"] = hotspots

    symmetry = str(params.get("symmetry") or "").strip()
    if symmetry:
        spec["symmetry"] = {"id": symmetry}

    length = str(params.get("length") or "").strip()
    if length:
        spec["length"] = length

    # Reference uploaded scaffold/motif files as design inputs.
    cif_like = [
        f["filename"]
        for f in input_files
        if f.get("role") in ("scaffold", "motif", "input")
    ]
    if cif_like:
        spec["input"] = str(job_dir / cif_like[0])

    extra = params.get("extra")
    if isinstance(extra, dict):
        spec["extra"] = extra

    design_key = params.get("_design_key", "design_1")
    payload = {design_key: spec}
    json_path = job_dir / "design_spec.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return json_path


class RFD3Engine(BaseEngine):
    model_id = "rfd3"

    def _initialize(self) -> None:
        from rfd3.engine import (  # type: ignore[import-not-found]
            RFD3InferenceConfig,
            RFD3InferenceEngine,
        )

        ckpt_state = model_checkpoint_state("rfd3")
        ckpt = ckpt_state["path"] or "rfd3"
        cfg = RFD3InferenceConfig(
            ckpt_path=ckpt,
            diffusion_batch_size=1,
            skip_existing=False,
        )
        self._engine = RFD3InferenceEngine(**cfg)
        self._engine.initialize()
        self._engine_cfg = cfg

    def _run(self, job: dict[str, Any]) -> EngineResult:
        params = json.loads(job.get("params_json") or "{}")
        job_dir = self.ensure_job_dir(job)
        input_files = self.job_input_files(job)
        json_path = _build_design_json(params, job_dir, input_files)

        n_batches = int(params.get("n_batches") or 1)
        sampler = str(params.get("sampler") or "default")
        steps = int(params.get("diffusion_steps") or 50)
        seed = params.get("seed")

        # Configure the sampler on the engine (validated values from the UI).
        self._engine.inference_sampler_overrides.update(
            {"sampler": sampler, "steps": steps}
        )
        if seed is not None:
            self._engine.seed = int(seed)

        self._engine.run(
            inputs=str(json_path),
            n_batches=n_batches,
            out_dir=str(job_dir),
        )

        outputs = self.collect_outputs(job_dir)
        if not outputs:
            raise RuntimeError("RFD3 completed but produced no output files")
        return EngineResult(outputs=outputs, summary={"model": "rfd3"})

    @staticmethod
    def is_available() -> tuple[bool, str]:
        try:
            import rfd3  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            return False, f"rc-foundry (rfd3) not installed: {exc}"
        state = model_checkpoint_state("rfd3")
        if not state["installed"]:
            return False, "RFD3 checkpoint is not installed"
        return True, "ready"
