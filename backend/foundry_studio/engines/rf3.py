"""Real RosettaFold3 (RF3) engine.

Wraps ``rf3.inference_engines.rf3.RF3InferenceEngine``.  Inputs are FASTA /
CIF / PDB file paths uploaded with the job (or server-side paths).
"""

from __future__ import annotations

import json
from typing import Any

from foundry_studio.engines.base import BaseEngine, EngineResult
from foundry_studio.engines.checkpoints import model_checkpoint_state


class RF3Engine(BaseEngine):
    model_id = "rf3"

    def __init__(self, *, db, workdir, log_path):
        super().__init__(db=db, workdir=workdir, log_path=log_path)
        # Stashed before initialize() so n_recycles/num_steps can be applied.
        self._params: dict[str, Any] = {}

    def _initialize(self) -> None:
        from rf3.inference_engines.rf3 import RF3InferenceEngine  # type: ignore[import-not-found]

        ckpt_state = model_checkpoint_state("rf3")
        ckpt = ckpt_state["path"] or "rf3"
        self._engine = RF3InferenceEngine(
            ckpt_path=ckpt,
            n_recycles=int(self._params.get("n_recycles", 10)),
            num_steps=int(self._params.get("num_steps", 50)),
        )
        self._engine.initialize()

    def run(self, job: dict[str, Any]) -> EngineResult:
        # RF3 params are needed at init time; stash them before initialize().
        self._params = json.loads(job.get("params_json") or "{}")
        return super().run(job)

    def _run(self, job: dict[str, Any]) -> EngineResult:
        params = json.loads(job.get("params_json") or "{}")
        job_dir = self.ensure_job_dir(job)

        # Inputs: prefer uploaded files, else server-side paths in params.
        input_paths = self._resolve_input_paths(params, job_dir)
        if not input_paths:
            raise ValueError("RF3 requires at least one input (FASTA/CIF/PDB)")

        dump_trajectories = bool(params.get("dump_trajectories", False))
        annotate_plddt = bool(params.get("annotate_b_factor_with_plddt", False))
        seed = params.get("seed")
        if seed is not None:
            self._engine.seed = int(seed)

        self._engine.run(
            inputs=input_paths,
            out_dir=str(job_dir),
            dump_predictions=True,
            dump_trajectories=dump_trajectories,
            annotate_b_factor_with_plddt=annotate_plddt,
        )

        outputs = self.collect_outputs(job_dir)
        if not outputs:
            raise RuntimeError("RF3 completed but produced no output files")
        return EngineResult(outputs=outputs, summary={"model": "rf3"})

    def _resolve_input_paths(
        self, params: dict[str, Any], job_dir: Any
    ) -> list[str]:
        paths: list[str] = []
        input_files = params.get("_input_files", [])
        for f in input_files:
            if f.get("role") in ("structure", "input", "sequence", "fasta"):
                candidate = job_dir / f["filename"]
                if candidate.is_file():
                    paths.append(str(candidate))
        for raw in (params.get("input_paths") or []):
            if isinstance(raw, str) and raw.strip():
                paths.append(raw)
        return paths

    @staticmethod
    def is_available() -> tuple[bool, str]:
        try:
            import rf3  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            return False, f"rc-foundry (rf3) not installed: {exc}"
        state = model_checkpoint_state("rf3")
        if not state["installed"]:
            return False, "RF3 checkpoint is not installed"
        return True, "ready"
