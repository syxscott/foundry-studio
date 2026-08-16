"""Real RFdiffusion3NA (RFD3NA) engine.

Same input conventions as RFD3; the difference is the underlying model
package (``rfd3na.engine.RFD3NAInferenceEngine``).
"""

from __future__ import annotations

import json
from typing import Any

from foundry_studio.engines.base import BaseEngine, EngineResult
from foundry_studio.engines.checkpoints import model_checkpoint_state
from foundry_studio.engines.rfd3 import _build_design_json


class RFD3NAEngine(BaseEngine):
    model_id = "rfd3na"

    def _initialize(self) -> None:
        from rfd3na.engine import (  # type: ignore[import-not-found]
            RFD3NAInferenceConfig,
            RFD3NAInferenceEngine,
        )

        ckpt_state = model_checkpoint_state("rfd3na")
        ckpt = ckpt_state["path"] or "rfd3na"
        cfg = RFD3NAInferenceConfig(ckpt_path=ckpt, diffusion_batch_size=1)
        self._engine = RFD3NAInferenceEngine(**cfg)
        self._engine.initialize()

    def _run(self, job: dict[str, Any]) -> EngineResult:
        params = json.loads(job.get("params_json") or "{}")
        job_dir = self.ensure_job_dir(job)
        input_files = self.job_input_files(job)
        json_path = _build_design_json(params, job_dir, input_files)

        n_batches = int(params.get("n_batches") or 1)
        sampler = str(params.get("sampler") or "default")
        steps = int(params.get("diffusion_steps") or 50)
        seed = params.get("seed")

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
            raise RuntimeError("RFD3NA completed but produced no output files")
        return EngineResult(outputs=outputs, summary={"model": "rfd3na"})

    @staticmethod
    def is_available() -> tuple[bool, str]:
        try:
            import rfd3na  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            return False, f"rc-foundry (rfd3na) not installed: {exc}"
        state = model_checkpoint_state("rfd3na")
        if not state["installed"]:
            return False, "RFD3NA checkpoint is not installed"
        return True, "ready"
