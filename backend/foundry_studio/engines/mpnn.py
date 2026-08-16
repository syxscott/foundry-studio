"""Real ProteinMPNN / LigandMPNN engine.

Wraps ``mpnn.inference_engines.mpnn.MPNNInferenceEngine``.  Uploaded CIF/PDB
files become ``structure_path`` entries; sampling parameters map to the
per-input defaults used by the upstream CLI.
"""

from __future__ import annotations

import json
from typing import Any

from foundry_studio.engines.base import BaseEngine, EngineResult
from foundry_studio.engines.checkpoints import model_checkpoint_state

# Variant -> checkpoint registry name.
_VARIANT_CHECKPOINT = {
    "protein_mpnn": "proteinmpnn",
    "ligand_mpnn": "ligandmpnn",
}


class MPNNEngine(BaseEngine):
    model_id = "mpnn"

    def __init__(self, *, db, workdir, log_path):
        super().__init__(db=db, workdir=workdir, log_path=log_path)
        self._params: dict[str, Any] = {}
        self._initialized_model_type: str | None = None

    def run(self, job: dict[str, Any]) -> EngineResult:
        self._params = json.loads(job.get("params_json") or "{}")
        # protein_mpnn vs ligand_mpnn load different checkpoints; force a
        # re-initialization so one worker can serve both variants without
        # carrying stale weights into the next job.
        model_type = str(self._params.get("model_type") or "protein_mpnn")
        if (
            self._initialized_model_type is not None
            and self._initialized_model_type != model_type
        ):
            self._engine = None  # type: ignore[assignment]
            self.initialized = False
            self._initialized_model_type = None
        return super().run(job)

    def _initialize(self) -> None:
        from mpnn.inference_engines.mpnn import (
            MPNNInferenceEngine,  # type: ignore[import-not-found]
        )

        model_type = str(self._params.get("model_type") or "protein_mpnn")
        ckpt_name = _VARIANT_CHECKPOINT.get(model_type, "proteinmpnn")
        ckpt_state = model_checkpoint_state(ckpt_name)
        checkpoint_path = ckpt_state["path"] or None

        self._engine = MPNNInferenceEngine(
            model_type=model_type,
            checkpoint_path=checkpoint_path,
            is_legacy_weights=False,
            out_directory=None,
            write_fasta=True,
            write_structures=True,
            device=None,  # auto-detect CUDA/XPU/MPS/CPU
        )
        self._initialized_model_type = model_type

    def _run(self, job: dict[str, Any]) -> EngineResult:
        params = json.loads(job.get("params_json") or "{}")
        job_dir = self.ensure_job_dir(job)

        input_dicts = self._build_input_dicts(params, job_dir, job)
        if not input_dicts:
            raise ValueError("MPNN requires at least one input structure (CIF/PDB)")

        self._engine.run(input_dicts=input_dicts, atom_arrays=None)

        outputs = self.collect_outputs(job_dir)
        if not outputs:
            raise RuntimeError("MPNN completed but produced no output files")
        return EngineResult(outputs=outputs, summary={"model": "mpnn"})

    def _build_input_dicts(
        self, params: dict[str, Any], job_dir: Any, job: dict[str, Any]
    ) -> list[dict[str, Any]]:
        structures = self.job_input_files(
            job, roles={"structure", "input"}
        )
        if not structures:
            return []

        temperature = float(params.get("temperature", 0.1))
        number_of_batches = int(params.get("number_of_batches", 8))
        batch_size = int(params.get("batch_size", 1))
        seed = params.get("seed")

        input_dicts: list[dict[str, Any]] = []
        for f in structures:
            path = job_dir / f["filename"]
            if not path.is_file():
                continue
            entry: dict[str, Any] = {
                "structure_path": str(path),
                "name": f.get("name") or path.stem,
                "batch_size": batch_size,
                "number_of_batches": number_of_batches,
                "temperature": temperature,
            }
            if seed is not None:
                entry["seed"] = int(seed)
            input_dicts.append(entry)
        return input_dicts

    @staticmethod
    def is_available() -> tuple[bool, str]:
        try:
            import mpnn  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            return False, f"rc-foundry (mpnn) not installed: {exc}"
        for name in ("proteinmpnn", "ligandmpnn"):
            state = model_checkpoint_state(name)
            if state["installed"]:
                return True, "ready"
        return False, "ProteinMPNN/LigandMPNN checkpoint is not installed"
