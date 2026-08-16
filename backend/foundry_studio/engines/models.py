"""Model registry: static metadata + parameter schemas for each supported model.

The ``param_schema`` entries are JSON-Schema-like dicts consumed by the
frontend to render dynamic task forms.  They are curated subsets of the full
Hydra/engine parameter space (the full space is not exposed; advanced users
can paste raw JSON via the "advanced" editor instead).
"""

from __future__ import annotations

from typing import Any

MODELS: dict[str, dict[str, Any]] = {
    "rfd3": {
        "id": "rfd3",
        "name": "RFdiffusion3 (RFD3)",
        "description": (
            "All-atom generative protein design. De-novo backbones, motif "
            "scaffolding, binder design, symmetry and more under complex "
            "constraints."
        ),
        "capabilities": [
            "de novo design",
            "motif scaffolding",
            "binder / interaction design",
            "symmetry",
            "contig specification",
        ],
        "requires_checkpoint": True,
        "accepted_extensions": ["cif", "pdb", "json", "yaml", "yml"],
        "param_schema": {
            "type": "object",
            "properties": {
                "contigs": {
                    "type": "string",
                    "title": "Contigs",
                    "default": "A1-100",
                    "description": (
                        "Chain/segment specification, e.g. 'A1-100' for a single "
                        "100-residue chain, or 'A1-50/B1-50' for a two-chain design."
                    ),
                },
                "n_batches": {
                    "type": "integer",
                    "title": "Number of designs (batches)",
                    "minimum": 1,
                    "maximum": 64,
                    "default": 1,
                    "description": "Number of independent designs to generate.",
                },
                "hotspots": {
                    "type": "string",
                    "title": "Hotspots (optional)",
                    "default": "",
                    "description": (
                        "Residues to design around, e.g. 'A1,A5,A10'. Leave empty "
                        "to disable."
                    ),
                },
                "diffusion_steps": {
                    "type": "integer",
                    "title": "Diffusion steps",
                    "minimum": 1,
                    "maximum": 500,
                    "default": 50,
                    "description": "Number of denoising steps.",
                },
                "sampler": {
                    "type": "string",
                    "title": "Sampler",
                    "enum": ["default", "reflow", "analytic", "ddpm", "ddim"],
                    "default": "default",
                    "description": "Diffusion sampling strategy.",
                },
                "symmetry": {
                    "type": "string",
                    "title": "Symmetry (optional)",
                    "default": "",
                    "description": (
                        "Symmetry group id, e.g. 'C3', 'D2' or 'tetrahedral'. "
                        "Leave empty for asymmetric."
                    ),
                },
                "scaffold_dir": {
                    "type": "string",
                    "title": "Scaffold dir (optional)",
                    "default": "",
                    "description": (
                        "Path to a directory of CIF scaffolds (server-side). "
                        "Prefer uploading files via the form."
                    ),
                },
                "seed": {
                    "type": ["integer", "null"],
                    "title": "Seed",
                    "default": None,
                    "description": "Random seed for reproducibility (null = random).",
                },
            },
        },
        "param_defaults": {
            "contigs": "A1-100",
            "n_batches": 1,
            "diffusion_steps": 50,
            "sampler": "default",
        },
    },
    "rfd3na": {
        "id": "rfd3na",
        "name": "RFdiffusion3NA (RFD3NA)",
        "description": (
            "Extension of RFdiffusion3 for mixed protein / nucleic-acid design "
            "under complex constraints."
        ),
        "capabilities": ["de novo design", "nucleic acid design", "symmetry"],
        "requires_checkpoint": True,
        "accepted_extensions": ["cif", "pdb", "json", "yaml", "yml"],
        "param_schema": {
            "type": "object",
            "properties": {
                "contigs": {
                    "type": "string",
                    "title": "Contigs",
                    "default": "A1-80/D1-20",
                    "description": (
                        "Chain specification including nucleic-acid segments, "
                        "e.g. 'A1-80/D1-20' designs a protein chain A and DNA chain D."
                    ),
                },
                "n_batches": {
                    "type": "integer",
                    "title": "Number of designs (batches)",
                    "minimum": 1,
                    "maximum": 64,
                    "default": 1,
                },
                "diffusion_steps": {
                    "type": "integer",
                    "title": "Diffusion steps",
                    "minimum": 1,
                    "maximum": 500,
                    "default": 50,
                },
                "sampler": {
                    "type": "string",
                    "title": "Sampler",
                    "enum": ["default", "reflow", "analytic", "ddpm", "ddim"],
                    "default": "default",
                },
                "seed": {"type": ["integer", "null"], "title": "Seed", "default": None},
            },
        },
        "param_defaults": {
            "contigs": "A1-80/D1-20",
            "n_batches": 1,
            "diffusion_steps": 50,
        },
    },
    "rf3": {
        "id": "rf3",
        "name": "RosettaFold3 (RF3)",
        "description": (
            "Structure prediction neural network. Predicts all-atom structures "
            "from sequences or templates, closing the gap to closed-source AF3."
        ),
        "capabilities": ["structure prediction", "complex prediction", "pLDDT"],
        "requires_checkpoint": True,
        "accepted_extensions": ["fasta", "fa", "cif", "pdb", "json"],
        "param_schema": {
            "type": "object",
            "properties": {
                "n_recycles": {
                    "type": "integer",
                    "title": "Recycles",
                    "minimum": 0,
                    "maximum": 20,
                    "default": 10,
                    "description": "Number of structure prediction recycles.",
                },
                "num_steps": {
                    "type": "integer",
                    "title": "Diffusion steps",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 50,
                },
                "dump_trajectories": {
                    "type": "boolean",
                    "title": "Dump trajectories",
                    "default": False,
                },
                "annotate_b_factor_with_plddt": {
                    "type": "boolean",
                    "title": "Annotate pLDDT in B-factor",
                    "default": False,
                },
                "seed": {"type": ["integer", "null"], "title": "Seed", "default": None},
            },
        },
        "param_defaults": {"n_recycles": 10, "num_steps": 50},
    },
    "mpnn": {
        "id": "mpnn",
        "name": "ProteinMPNN / LigandMPNN",
        "description": (
            "Inverse folding: designs amino-acid sequences that fold into a "
            "given backbone structure, under user-defined constraints."
        ),
        "capabilities": ["sequence design", "fixed residues", "ligand-aware design"],
        "requires_checkpoint": True,
        "accepted_extensions": ["cif", "pdb"],
        "param_schema": {
            "type": "object",
            "properties": {
                "model_type": {
                    "type": "string",
                    "title": "Model variant",
                    "enum": ["protein_mpnn", "ligand_mpnn"],
                    "default": "protein_mpnn",
                },
                "number_of_batches": {
                    "type": "integer",
                    "title": "Number of sequences",
                    "minimum": 1,
                    "maximum": 64,
                    "default": 8,
                    "description": "Number of sequences to sample per input structure.",
                },
                "temperature": {
                    "type": "number",
                    "title": "Temperature",
                    "minimum": 0.01,
                    "maximum": 10.0,
                    "default": 0.1,
                    "description": "Sampling temperature (lower = more deterministic).",
                },
                "batch_size": {
                    "type": "integer",
                    "title": "Batch size",
                    "minimum": 1,
                    "maximum": 256,
                    "default": 1,
                },
                "seed": {"type": ["integer", "null"], "title": "Seed", "default": None},
            },
        },
        "param_defaults": {
            "model_type": "protein_mpnn",
            "number_of_batches": 8,
            "temperature": 0.1,
            "batch_size": 1,
        },
    },
}

ORDER = ["rfd3", "rfd3na", "rf3", "mpnn"]


def get_model(model_id: str) -> dict[str, Any] | None:
    return MODELS.get(model_id)


def all_models() -> list[dict[str, Any]]:
    return [MODELS[m] for m in ORDER if m in MODELS]
