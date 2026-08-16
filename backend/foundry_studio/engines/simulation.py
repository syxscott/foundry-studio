"""Simulation engine.

This engine produces *structurally plausible* placeholder outputs (real CIF / FASTA
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
import random
import time
from pathlib import Path
from typing import Any

from foundry_studio.engines.base import BaseEngine, EngineResult, OutputFile

# --------------------------------------------------------------------------- #
# Physical constants (Å)
# --------------------------------------------------------------------------- #
_CA_CA_BOND = 3.80          # Cα–Cα virtual bond
_N_CA_BOND = 1.46           # N–Cα bond (peptide plane half)
_CA_C_BOND = 1.53           # Cα–C bond (peptide plane half)
_BOND_TOLERANCE = 0.05      # allowed deviation from reference bond length

# Alpha-helix parameters (ideal)
_ALPHA_PHI = math.radians(-57.0)
_ALPHA_PSI = math.radians(-47.0)
_ALPHA_TWIST = 3.6          # residues per turn

# Extended/beta-strand parameters
_BETA_PHI = math.radians(-135.0)
_BETA_PSI = math.radians(135.0)
_BETA_TWIST = 2.0           # residues per turn

# 3_10-helix
_HELIX310_PHI = math.radians(-49.0)
_HELIX310_PSI = math.radians(-26.0)
_HELIX310_TWIST = 3.0

# --------------------------------------------------------------------------- #
# Amino-acid side-chain geometries (Å from Cα)
# Cβ direction is ~tetrahedral: roughly +120° from CA->N in the plane
# perpendicular to the backbone.
# --------------------------------------------------------------------------- #
_SIDECHAINS: dict[str, tuple[str, float, float, float]] = {
    # (one-letter, name, Cβ_x_offset, Cβ_y_offset, Cβ_z_offset from CA)
    "A": ("ALA",  1.50,  0.00,  0.00),
    "C": ("CYS",  1.50,  0.80,  0.60),
    "D": ("ASP",  1.40,  0.90, -0.40),
    "E": ("GLU",  1.50,  0.90, -0.40),
    "F": ("PHE",  1.50,  1.10,  0.30),
    "G": ("GLY",  0.00,  0.00,  0.00),   # no Cβ
    "H": ("HIS",  1.45,  0.90,  0.30),
    "I": ("ILE",  1.50,  0.60,  0.80),
    "K": ("LYS",  1.50,  0.85,  0.40),
    "L": ("LEU",  1.50,  0.60,  0.80),
    "M": ("MET",  1.50,  0.85,  0.40),
    "N": ("ASN",  1.40,  0.85, -0.30),
    "P": ("PRO",  1.40,  0.00,  1.20),   # ring: Cδ pushes forward
    "Q": ("GLN",  1.50,  0.85, -0.30),
    "R": ("ARG",  1.50,  0.85,  0.40),
    "S": ("SER",  1.45,  0.70, -0.55),
    "T": ("THR",  1.45,  0.60,  0.80),
    "V": ("VAL",  1.50,  0.60,  0.80),
    "W": ("TRP",  1.50,  1.15,  0.30),
    "Y": ("TYR",  1.50,  1.10,  0.30),
}
_ALPHABET = list(_SIDECHAINS.keys())


# --------------------------------------------------------------------------- #
# 3-D geometry helpers
# --------------------------------------------------------------------------- #

def _rot_mat(axis: tuple[float, float, float], angle: float):
    """Rodrigues rotation matrix around a unit axis."""
    ux, uy, uz = axis
    c = math.cos(angle)
    s = math.sin(angle)
    oc = 1 - c
    return [
        [oc * ux * ux + c,      oc * ux * uy - uz * s, oc * ux * uz + uy * s],
        [oc * uy * ux + uz * s, oc * uy * uy + c,      oc * uy * uz - ux * s],
        [oc * uz * ux - uy * s, oc * uz * uy + ux * s, oc * uz * uz + c],
    ]


def _matmul_vec(m, v):
    return [m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2]]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def _normalize(v):
    norm = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if norm < 1e-9:
        return [0.0, 0.0, 1.0]
    return [v[0] / norm, v[1] / norm, v[2] / norm]


def _build_frame(n_ca_prev: list[float], ca_curr: list[float]) -> tuple[list[float], list[float], list[float]]:
    """Build (n, ca, c) orthonormal frame from two consecutive Cα atoms."""
    # Backbone direction: from prev_CA to curr_CA
    bond_vec = _normalize([ca_curr[i] - n_ca_prev[i] for i in range(3)])

    # Choose n direction perpendicular to bond (use global z as seed)
    up = _normalize(_cross(bond_vec, [0.0, 0.0, 1.0]))
    n_vec = _normalize(_cross(up, bond_vec))

    # C is in the peptide plane, roughly opposite direction
    # In ideal helix: CA->C is at ~+109° from CA->N, in the plane
    c_vec = _normalize(_cross(bond_vec, n_vec))
    return n_vec, bond_vec, c_vec


def _simulate_alpha_helix(n_res: int, seq: str, start_idx: int = 1,
                          center=(0.0, 0.0, 0.0)) -> list[tuple[int, str, str, list[float], list[float]]]:
    """Generate coordinates for an alpha-helix of n_res residues.

    Returns list of (resnum, one-letter, 3-letter, ca_coord, cb_coord_or_None).
    """
    atoms = []
    phi = _ALPHA_PHI
    ca_prev = [center[0] - _CA_CA_BOND, center[1], center[2]]

    # First N (place roughly before first CA)
    n_prev = [ca_prev[0] - _N_CA_BOND, center[1], center[2]]

    # Build initial frame
    bond_vec = _normalize([_CA_CA_BOND, 0.0, 0.0])
    n_vec = [0.0, 0.0, 1.0]
    c_vec = _normalize(_cross(bond_vec, n_vec))

    rng = random.Random(42 + start_idx)

    for i in range(n_res):
        letter = seq[i] if i < len(seq) else rng.choice(_ALPHABET)
        resname = _SIDECHAINS[letter][0]
        resnum = start_idx + i

        # Place N and CA
        rot_axis = _normalize(n_vec)
        bond_dir = _matmul_vec(_rot_mat(rot_axis, phi), bond_vec)

        n_curr = [n_prev[j] + bond_dir[j] * _N_CA_BOND for j in range(3)]
        ca_curr = [n_curr[j] + bond_dir[j] * _N_CA_BOND for j in range(3)]

        # Apply small helix curvature: twist per residue
        twist_angle = 2 * math.pi / _ALPHA_TWIST
        helix_axis = _normalize(_cross(bond_vec, n_vec))
        rot_m = _rot_mat(helix_axis, twist_angle * (i + 1))
        ca_curr = _matmul_vec(rot_m, [ca_curr[j] - center[j] for j in range(3)])
        ca_curr = [ca_curr[j] + center[j] for j in range(3)]
        n_curr = _matmul_vec(rot_m, [n_curr[j] - center[j] for j in range(3)])
        n_curr = [n_curr[j] + center[j] for j in range(3)]

        # Side chain Cβ
        sc_offset = _SIDECHAINS[letter]
        cb_coord = None
        if letter != "G":
            cb_rel = [sc_offset[1], sc_offset[2], sc_offset[3]]
            cb_coord = [ca_curr[j] + cb_rel[j] for j in range(3)]

        atoms.append((resnum, letter, resname, ca_curr, cb_coord))

        # Update for next residue
        n_prev = n_curr
        bond_vec = _normalize([ca_curr[j] - n_curr[j] for j in range(3)])
        n_vec, bond_vec, c_vec = _build_frame(ca_curr, [ca_curr[j] + bond_vec[j] * 0.01 for j in range(3)])

    return atoms


def _simulate_beta_strand(n_res: int, seq: str, start_idx: int = 1,
                           center=(0.0, 0.0, 0.0)) -> list[tuple[int, str, str, list[float], list[float]]]:
    """Generate coordinates for a beta-strand (extended conformation)."""
    atoms = []
    rng = random.Random(137 + start_idx)

    for i in range(n_res):
        letter = seq[i] if i < len(seq) else rng.choice(_ALPHABET)
        resname = _SIDECHAINS[letter][0]
        resnum = start_idx + i

        # Extended chain: roughly along x-axis with slight wave
        x = i * _CA_CA_BOND * 0.87  # ~cos(60°) for extended
        y = 0.5 * math.sin(i * 0.8)  # slight pleating
        z = i * 0.15  # slight rise
        ca = [center[0] + x, center[1] + y, center[2] + z]

        sc_offset = _SIDECHAINS[letter]
        cb_coord = None
        if letter != "G":
            cb = [ca[0] + sc_offset[1], ca[1] + sc_offset[2], ca[2] + sc_offset[3]]
            cb_coord = cb

        atoms.append((resnum, letter, resname, ca, cb_coord))

    return atoms


def _generate_sequence(n_res: int, seed: int = 0) -> str:
    """Generate a realistic-ish amino-acid sequence."""
    rng = random.Random(seed)
    # Bias toward common amino acids
    common = "AAGVVLISSKKMMMNNPPQRRTTDEEHHFFYYCCWW"
    return "".join(rng.choice(common) for _ in range(n_res))


def _build_sse_blocks(n_res: int, seed: int) -> list[tuple[str, int]]:
    """Divide n_res into secondary-structure blocks.

    Returns list of (sstype, length): helix/turn/strand segments.
    """
    rng = random.Random(seed + 1000)
    blocks = []
    remaining = n_res
    sstypes = [
        ("alpha", 7, 18),   # min, max helix length
        ("beta", 5, 15),    # min, max strand length
        ("310", 3, 9),      # 3_10 helix
        ("loop", 2, 6),     # random coil / turns
    ]
    while remaining > 0:
        sstype, lo, hi = rng.choice(sstypes)
        length = rng.randint(lo, hi)
        length = min(length, remaining)
        blocks.append((sstype, length))
        remaining -= length
    return blocks


def _simulate_protein(n_res: int, model: str, seed: int) -> list[tuple[int, str, str, list[float], list[float]]]:
    """Simulate a plausible protein fragment with secondary structure diversity.

    For RFdiffusion models: bias toward longer helix-rich designs.
    For MPNN: bias toward diverse sequences.
    """
    seq = _generate_sequence(n_res, seed=seed)

    blocks = _build_sse_blocks(n_res, seed=seed)
    atoms: list[tuple[int, str, str, list[float], list[float]]] = []

    if model in ("rfd3", "rfd3na"):
        # RFdiffusion tends to produce helix-dominant designs
        # Make a central helix flanked by loops
        if n_res >= 80:
            n_term = max(n_res // 5, 3)
            helix_len = n_res - 2 * n_term
            c_term = n_res - n_term - helix_len
            blocks = [("loop", n_term), ("alpha", helix_len), ("loop", c_term)]
        else:
            blocks = [("alpha", n_res)]

    elif model == "rf3":
        # RosettaFold3: more diverse, often mixed alpha/beta
        if n_res >= 60:
            n_term = max(n_res // 6, 3)
            beta1 = max(n_res // 5, 4)
            helix = n_res - n_term - beta1 - max(n_res // 6, 3)
            c_term = n_res - n_term - beta1 - helix
            blocks = [("loop", n_term), ("beta", beta1), ("alpha", max(helix, 5)), ("loop", max(c_term, 3))]
        else:
            blocks = [("alpha", max(n_res // 2, 3)), ("loop", max(n_res - n_res // 2, 2)), ("beta", max(n_res // 3, 3))]

    elif model == "mpnn":
        # MPNN designs often have diverse composition
        blocks = _build_sse_blocks(n_res, seed=seed)

    center = [0.0, 0.0, 0.0]
    resnum = 1

    for sstype, length in blocks:
        if sstype == "alpha":
            seg_atoms = _simulate_alpha_helix(length, seq=seq[resnum - 1:resnum - 1 + length],
                                              start_idx=resnum, center=center)
        elif sstype == "beta":
            seg_atoms = _simulate_beta_strand(length, seq=seq[resnum - 1:resnum - 1 + length],
                                               start_idx=resnum, center=center)
        elif sstype == "310":
            # 3_10 helix: tighter, shorter
            seg_atoms = _simulate_alpha_helix(length, seq=seq[resnum - 1:resnum - 1 + length],
                                              start_idx=resnum, center=center)
        else:
            # Loop: simple extended with noise
            seg_atoms = _simulate_beta_strand(length, seq=seq[resnum - 1:resnum - 1 + length],
                                               start_idx=resnum, center=center)

        # Offset subsequent blocks slightly
        if seg_atoms:
            last_ca = seg_atoms[-1][3]
            center = [last_ca[0] + 3.0, last_ca[1], last_ca[2]]

        atoms.extend(seg_atoms)
        resnum += length

    return atoms


def write_simulated_cif(path: Path, n_res: int, model: str, tag: str, seed: int) -> None:
    """Write a structurally plausible CIF with secondary structure diversity."""
    atoms = _simulate_protein(n_res, model, seed=seed)

    lines = [
        f"data_{tag}",
        "#",
        "loop_",
        "_atom_site.group_PDB",
        "_atom_site.id",
        "_atom_site.type_symbol",
        "_atom_site.label_atom_id",
        "_atom_site.label_comp_id",
        "_atom_site.label_asym_id",
        "_atom_site.label_seq_id",
        "_atom_site.Cartn_x",
        "_atom_site.Cartn_y",
        "_atom_site.Cartn_z",
        "_atom_site.occupancy",
        "_atom_site.B_iso_or_equiv",
    ]

    atom_id = 1
    for resnum, letter, resname, ca, cb in atoms:
        x, y, z = ca
        lines.append(
            f"ATOM {atom_id:5d}  N  N   {resname:3s} A {resnum:4d} {x:8.3f} {y:8.3f} {z:8.3f}  1.00  20.00"
        )
        atom_id += 1
        lines.append(
            f"ATOM {atom_id:5d}  C  CA  {resname:3s} A {resnum:4d} {x:8.3f} {y:8.3f} {z:8.3f}  1.00  20.00"
        )
        atom_id += 1
        lines.append(
            f"ATOM {atom_id:5d}  C  C   {resname:3s} A {resnum:4d} {x:8.3f} {y:8.3f} {z:8.3f}  1.00  25.00"
        )
        atom_id += 1
        lines.append(
            f"ATOM {atom_id:5d}  O  O   {resname:3s} A {resnum:4d} {x:8.3f} {y:8.3f} {z:8.3f}  1.00  30.00"
        )
        atom_id += 1
        if cb is not None:
            cx, cy, cz = cb
            lines.append(
                f"ATOM {atom_id:5d}  C  CB  {resname:3s} A {resnum:4d} {cx:8.3f} {cy:8.3f} {cz:8.3f}  1.00  25.00"
            )
            atom_id += 1

    content = "\n".join(lines) + "\n"
    path.write_text(content, encoding="utf-8")


def write_simulated_fasta(path: Path, n_res: int, tag: str, seed: int) -> None:
    seq = _generate_sequence(n_res, seed=seed)
    path.write_text(f">{tag} simulated_designed_sequence\n{seq}\n", encoding="utf-8")


def write_metadata(path: Path, meta: dict[str, Any]) -> None:
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


class SimulationEngine(BaseEngine):
    """Placeholder engine producing structurally plausible but simulated outputs."""

    model_id: str = ""

    def __init__(self, *, db, workdir, log_path):
        super().__init__(db=db, workdir=workdir, log_path=log_path)
        self._start = time.monotonic()

    def _initialize(self) -> None:
        self._start = time.monotonic()

    def _run(self, job: dict[str, Any]) -> EngineResult:
        params = json.loads(job.get("params_json") or "{}")
        out_dir = self.ensure_job_dir(job)

        # Simulate realistic computation progress
        progress_steps = 10
        for i in range(progress_steps):
            time.sleep(0.15)
            self.db.update_job(
                job["id"],
                progress=min(95, int((i + 1) / progress_steps * 95)),
            )

        model = job.get("model", "rfd3")
        n_res = _guess_residues(params, model)
        job_id = job["id"]
        tag = f"{model}_sim_{job_id[:8]}"
        seed = hash(job_id) & 0x7FFFFFFF

        outputs: list[OutputFile] = []

        if model in ("rfd3", "rfd3na"):
            cif = out_dir / f"{tag}.cif"
            write_simulated_cif(cif, n_res, model, tag, seed=seed)
            outputs.append(
                OutputFile(name=cif.name, path=cif, kind="cif", description="Structure (simulated)")
            )
            meta = {
                "simulated": True,
                "model": model,
                "contigs": params.get("contigs", ""),
                "n_batches": params.get("n_batches", 1),
                "diffusion_steps": params.get("diffusion_steps", 50),
                "note": "Simulation output — not a real prediction. Real inference requires rc-foundry[all] + GPU.",
            }
            meta_path = out_dir / f"{tag}.json"
            write_metadata(meta_path, meta)
            outputs.append(
                OutputFile(name=meta_path.name, path=meta_path, kind="json", description="Metadata")
            )

        elif model == "rf3":
            cif = out_dir / f"{tag}.cif"
            write_simulated_cif(cif, n_res, model, tag, seed=seed)
            outputs.append(
                OutputFile(name=cif.name, path=cif, kind="cif", description="Predicted structure (simulated)")
            )
            meta = {
                "simulated": True,
                "model": model,
                "n_recycles": params.get("n_recycles", 10),
                "plddt_mean": round(0.6 + 0.1 * math.sin(n_res / 13.0), 3),
                "note": "Simulation output — not a real prediction. Real inference requires rc-foundry[all] + GPU.",
            }
            meta_path = out_dir / f"{tag}.json"
            write_metadata(meta_path, meta)
            outputs.append(
                OutputFile(name=meta_path.name, path=meta_path, kind="json", description="Metadata")
            )

        elif model == "mpnn":
            fasta = out_dir / f"{tag}.fasta"
            write_simulated_fasta(fasta, n_res, tag, seed=seed)
            outputs.append(
                OutputFile(name=fasta.name, path=fasta, kind="fasta", description="Designed sequences (simulated)")
            )
            cif = out_dir / f"{tag}_designed.cif"
            write_simulated_cif(cif, n_res, model, tag + "_designed", seed=seed + 1)
            outputs.append(
                OutputFile(name=cif.name, path=cif, kind="cif", description="Designed structure (simulated)")
            )
            meta = {
                "simulated": True,
                "model": model,
                "model_type": params.get("model_type", "protein_mpnn"),
                "temperature": params.get("temperature", 0.1),
                "number_of_batches": params.get("number_of_batches", 8),
                "note": "Simulation output — not a real prediction. Real inference requires rc-foundry[all] + GPU.",
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
    """Infer a plausible length from parameters for the simulated output.

    RFD3 / RFD3NA contig syntax is richer than ``A1-100/B1-50``:
    segments can carry chain letters anywhere (``H1-50/A23-200``),
    a length prefix (``40-60``), a zero-length gap (``/0``), or a
    percentage token (``10-30/A1-100:0.5``).  We only need a sensible
    number for a *labelled simulation* — so we extract every integer
    range we can find, ignore tokens that don't match, and fall back
    to a model-specific default when nothing parses.
    """
    import re

    contigs = str(params.get("contigs") or "")
    n_res = 0
    range_re = re.compile(r"(\d+)\s*-\s*(\d+)")
    for m in range_re.finditer(contigs):
        try:
            a, b = int(m.group(1)), int(m.group(2))
        except ValueError:
            continue
        lo, hi = sorted((a, b))
        if hi <= 0:
            continue
        n_res += min(max(hi - lo + 1, 1), 400)
    if n_res == 0:
        single = re.search(r"\b(\d{2,4})\b", contigs)
        if single:
            try:
                n_res = int(single.group(1))
            except ValueError:
                pass
    if n_res == 0:
        n_res = {"rfd3": 100, "rfd3na": 100, "rf3": 150, "mpnn": 100}.get(
            model, 100
        )
    return min(max(int(n_res), 20), 800)
