"""Simulation engine.

This engine produces *structurally valid* placeholder outputs (real CIF / FASTA
files) so the entire web flow — upload, queue, worker, results, 3D viewer —
can be exercised on machines without Foundry weights or a GPU.

It is NEVER presented as a real prediction: every job run through this engine
is tagged ``engine_mode="simulation"`` and the UI shows a persistent warning
banner.  When the real Foundry package and checkpoints are present, the
registry routes to the real engines instead.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

from foundry_studio.engines.base import BaseEngine, EngineResult, OutputFile

_CIF_TEMPLATE = """data_{name}
#
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_seq_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.occupancy
_atom_site.B_iso_or_equiv
ATOM {idx} C CA ALA A {res} {x:.3f} {y:.3f} {z:.3f} 1.00 20.00
"""


def _simulated_coords(res_index: int, n_res: int) -> tuple[float, float, float]:
    """Deterministic pseudo-helix coordinates so the 3D viewer shows a shape."""
    phi = res_index * 0.45
    radius = 4.0 * (1.0 + 0.2 * math.sin(res_index / 7.0))
    z = (res_index - n_res / 2) * 1.5
    return radius * math.cos(phi), radius * math.sin(phi), z


def write_simulated_cif(path: Path, n_res: int, tag: str) -> None:
    lines: list[str] = []
    for i in range(1, n_res + 1):
        x, y, z = _simulated_coords(i, n_res)
        lines.append(
            f"ATOM {i:4d}  C  CA ALA A {i:3d} {x:7.3f} {y:7.3f} {z:7.3f} 1.00 20.00"
        )
    content = f"data_{tag}\n#\nloop_\n_atom_site.group_PDB\n_atom_site.id\n_atom_site.type_symbol\n_atom_site.label_atom_id\n_atom_site.label_comp_id\n_atom_site.label_asym_id\n_atom_site.label_seq_id\n_atom_site.Cartn_x\n_atom_site.Cartn_y\n_atom_site.Cartn_z\n_atom_site.occupancy\n_atom_site.B_iso_or_equiv\n" + "\n".join(
        lines
    )
    path.write_text(content, encoding="utf-8")


def write_simulated_fasta(path: Path, n_res: int, tag: str) -> None:
    alphabet = "ACDEFGHIKLMNPQRSTVWY"
    seq = "".join(alphabet[i % len(alphabet)] for i in range(n_res))
    path.write_text(f">{tag} simulated_sequence\n{seq}\n", encoding="utf-8")


def write_metadata(path: Path, meta: dict[str, Any]) -> None:
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


class SimulationEngine(BaseEngine):
    """Placeholder engine producing valid but simulated outputs."""

    model_id: str = ""

    def __init__(self, *, db, workdir, log_path):
        super().__init__(db=db, workdir=workdir, log_path=log_path)
        self._start = time.monotonic()

    def _initialize(self) -> None:
        # Nothing heavy to load.
        self._start = time.monotonic()

    def _run(self, job: dict[str, Any]) -> EngineResult:
        params = json.loads(job.get("params_json") or "{}")
        out_dir = self.ensure_job_dir(job)

        # Simulate a short "computation" so progress and logs are realistic.
        progress_steps = 10
        for i in range(progress_steps):
            time.sleep(0.15)
            self.db.update_job(
                job["id"],
                progress=min(95, int((i + 1) / progress_steps * 95)),
            )

        model = job.get("model", "rfd3")
        n_res = _guess_residues(params, model)
        tag = f"{model}_sim_{job['id'][:8]}"

        outputs: list[OutputFile] = []

        if model in ("rfd3", "rfd3na"):
            cif = out_dir / f"{tag}.cif"
            write_simulated_cif(cif, n_res, tag)
            outputs.append(
                OutputFile(name=cif.name, path=cif, kind="cif", description="Structure (simulated)")
            )
            meta = {
                "simulated": True,
                "model": model,
                "contigs": params.get("contigs", ""),
                "n_batches": params.get("n_batches", 1),
                "diffusion_steps": params.get("diffusion_steps", 50),
                "note": "Simulation output - not a real prediction",
            }
            meta_path = out_dir / f"{tag}.json"
            write_metadata(meta_path, meta)
            outputs.append(
                OutputFile(name=meta_path.name, path=meta_path, kind="json", description="Metadata")
            )

        elif model == "rf3":
            cif = out_dir / f"{tag}.cif"
            write_simulated_cif(cif, n_res, tag)
            outputs.append(
                OutputFile(name=cif.name, path=cif, kind="cif", description="Predicted structure (simulated)")
            )
            meta = {
                "simulated": True,
                "model": model,
                "n_recycles": params.get("n_recycles", 10),
                "plddt_mean": round(0.6 + 0.1 * math.sin(n_res / 13.0), 3),
            }
            meta_path = out_dir / f"{tag}.json"
            write_metadata(meta_path, meta)
            outputs.append(
                OutputFile(name=meta_path.name, path=meta_path, kind="json", description="Metadata")
            )

        elif model == "mpnn":
            fasta = out_dir / f"{tag}.fasta"
            write_simulated_fasta(fasta, n_res, tag)
            outputs.append(
                OutputFile(name=fasta.name, path=fasta, kind="fasta", description="Designed sequences (simulated)")
            )
            cif = out_dir / f"{tag}_designed.cif"
            write_simulated_cif(cif, n_res, tag)
            outputs.append(
                OutputFile(name=cif.name, path=cif, kind="cif", description="Designed structure (simulated)")
            )
            meta = {
                "simulated": True,
                "model": model,
                "model_type": params.get("model_type", "protein_mpnn"),
                "temperature": params.get("temperature", 0.1),
                "number_of_batches": params.get("number_of_batches", 8),
            }
            meta_path = out_dir / f"{tag}.json"
            write_metadata(meta_path, meta)
            outputs.append(
                OutputFile(name=meta_path.name, path=meta_path, kind="json", description="Metadata")
            )

        self.db.update_job(job["id"], progress=100)
        return EngineResult(outputs=outputs, summary={"simulated": True, "model": model})

    @staticmethod
    def is_available() -> tuple[bool, str]:
        return True, "simulation engine is always available"


def _guess_residues(params: dict[str, Any], model: str) -> int:
    """Infer a plausible length from parameters for the simulated output."""
    contigs = str(params.get("contigs") or "")
    n_res = 0
    for part in contigs.split("/"):
        seg = part.strip()
        if "-" in seg:
            try:
                start, end = seg.split("-")[0][-2:], seg.split("-")[1]
                # Strip chain letters.
                digits = "".join(ch for ch in start if ch.isdigit())
                end_digits = "".join(ch for ch in end if ch.isdigit())
                n_res += max(1, (int(end_digits or 1) - int(digits or 1) + 1))
            except Exception:  # noqa: BLE001
                n_res += 40
        elif part:
            n_res += 40
    if n_res == 0:
        n_res = {"rfd3": 100, "rfd3na": 100, "rf3": 150, "mpnn": 100}.get(model, 100)
    return min(max(int(n_res), 20), 800)
