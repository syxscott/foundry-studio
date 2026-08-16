"""Model registry: static metadata + parameter schemas for each supported model.

The ``param_schema`` entries are JSON-Schema-like dicts consumed by the
frontend to render dynamic task forms.  They are curated subsets of the full
Hydra/engine parameter space (the full space is not exposed; advanced users
can paste raw JSON via the "advanced" editor instead).

Every user-facing string ships with a stable i18n key (``*_key`` fields).
The frontend renders ``t(key, {defaultValue: <english>})`` so the UI is
localized in zh/en/ja/ru while gracefully falling back to English when a
translation is missing.
"""

from __future__ import annotations

from typing import Any

MODELS: dict[str, dict[str, Any]] = {
    "rfd3": {
        "id": "rfd3",
        "name": "RFdiffusion3 (RFD3)",
        "name_key": "models.rfd3.name",
        "description": (
            "All-atom generative protein design. De-novo backbones, motif "
            "scaffolding, binder design, symmetry and more under complex "
            "constraints."
        ),
        "description_key": "models.rfd3.description",
        "capabilities": [
            "de novo design",
            "motif scaffolding",
            "binder / interaction design",
            "symmetry",
            "contig specification",
        ],
        "capability_keys": [
            "models.rfd3.cap.design",
            "models.rfd3.cap.scaffold",
            "models.rfd3.cap.binder",
            "models.rfd3.cap.symmetry",
            "models.rfd3.cap.contigs",
        ],
        "requires_checkpoint": True,
        "accepted_extensions": ["cif", "pdb", "json", "yaml", "yml"],
        "param_schema": {
            "type": "object",
            "properties": {
                "contigs": {
                    "type": "string",
                    "title": "Contigs",
                    "title_key": "models.rfd3.param.contigs.title",
                    "default": "A1-100",
                    "description": (
                        "Chain/segment specification, e.g. 'A1-100' for a single "
                        "100-residue chain, or 'A1-50/B1-50' for a two-chain design."
                    ),
                    "description_key": "models.rfd3.param.contigs.desc",
                },
                "n_batches": {
                    "type": "integer",
                    "title": "Number of designs (batches)",
                    "title_key": "models.rfd3.param.n_batches.title",
                    "minimum": 1,
                    "maximum": 64,
                    "default": 1,
                    "description": "Number of independent designs to generate.",
                    "description_key": "models.rfd3.param.n_batches.desc",
                },
                "hotspots": {
                    "type": "string",
                    "title": "Hotspots (optional)",
                    "title_key": "models.rfd3.param.hotspots.title",
                    "default": "",
                    "description": (
                        "Residues to design around, e.g. 'A1,A5,A10'. Leave empty "
                        "to disable."
                    ),
                    "description_key": "models.rfd3.param.hotspots.desc",
                },
                "diffusion_steps": {
                    "type": "integer",
                    "title": "Diffusion steps",
                    "title_key": "models.rfd3.param.diffusion_steps.title",
                    "minimum": 1,
                    "maximum": 500,
                    "default": 50,
                    "description": "Number of denoising steps.",
                    "description_key": "models.rfd3.param.diffusion_steps.desc",
                },
                "sampler": {
                    "type": "string",
                    "title": "Sampler",
                    "title_key": "models.rfd3.param.sampler.title",
                    "enum": ["default", "reflow", "analytic", "ddpm", "ddim"],
                    "default": "default",
                    "description": "Diffusion sampling strategy.",
                    "description_key": "models.rfd3.param.sampler.desc",
                },
                "symmetry": {
                    "type": "string",
                    "title": "Symmetry (optional)",
                    "title_key": "models.rfd3.param.symmetry.title",
                    "default": "",
                    "description": (
                        "Symmetry group id, e.g. 'C3', 'D2' or 'tetrahedral'. "
                        "Leave empty for asymmetric."
                    ),
                    "description_key": "models.rfd3.param.symmetry.desc",
                },
                "scaffold_dir": {
                    "type": "string",
                    "title": "Scaffold dir (optional)",
                    "title_key": "models.rfd3.param.scaffold_dir.title",
                    "default": "",
                    "description": (
                        "Path to a directory of CIF scaffolds (server-side). "
                        "Prefer uploading files via the form."
                    ),
                    "description_key": "models.rfd3.param.scaffold_dir.desc",
                },
                "seed": {
                    "type": ["integer", "null"],
                    "title": "Seed",
                    "title_key": "models.rfd3.param.seed.title",
                    "default": None,
                    "description": "Random seed for reproducibility (null = random).",
                    "description_key": "models.rfd3.param.seed.desc",
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
        "name_key": "models.rfd3na.name",
        "description": (
            "Extension of RFdiffusion3 for mixed protein / nucleic-acid design "
            "under complex constraints."
        ),
        "description_key": "models.rfd3na.description",
        "capabilities": [
            "de novo design",
            "nucleic acid design",
            "symmetry",
        ],
        "capability_keys": [
            "models.rfd3na.cap.design",
            "models.rfd3na.cap.nucleic",
            "models.rfd3na.cap.symmetry",
        ],
        "requires_checkpoint": True,
        "accepted_extensions": ["cif", "pdb", "json", "yaml", "yml"],
        "param_schema": {
            "type": "object",
            "properties": {
                "contigs": {
                    "type": "string",
                    "title": "Contigs",
                    "title_key": "models.rfd3na.param.contigs.title",
                    "default": "A1-80/D1-20",
                    "description": (
                        "Chain specification including nucleic-acid segments, "
                        "e.g. 'A1-80/D1-20' designs a protein chain A and DNA chain D."
                    ),
                    "description_key": "models.rfd3na.param.contigs.desc",
                },
                "n_batches": {
                    "type": "integer",
                    "title": "Number of designs (batches)",
                    "title_key": "models.rfd3na.param.n_batches.title",
                    "minimum": 1,
                    "maximum": 64,
                    "default": 1,
                    "description_key": "models.rfd3na.param.n_batches.desc",
                    "description": "Number of independent designs to generate.",
                },
                "diffusion_steps": {
                    "type": "integer",
                    "title": "Diffusion steps",
                    "title_key": "models.rfd3na.param.diffusion_steps.title",
                    "minimum": 1,
                    "maximum": 500,
                    "default": 50,
                    "description_key": "models.rfd3na.param.diffusion_steps.desc",
                    "description": "Number of denoising steps.",
                },
                "sampler": {
                    "type": "string",
                    "title": "Sampler",
                    "title_key": "models.rfd3na.param.sampler.title",
                    "enum": ["default", "reflow", "analytic", "ddpm", "ddim"],
                    "default": "default",
                    "description_key": "models.rfd3na.param.sampler.desc",
                    "description": "Diffusion sampling strategy.",
                },
                "seed": {
                    "type": ["integer", "null"],
                    "title": "Seed",
                    "title_key": "models.rfd3na.param.seed.title",
                    "default": None,
                    "description_key": "models.rfd3na.param.seed.desc",
                    "description": "Random seed for reproducibility (null = random).",
                },
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
        "name_key": "models.rf3.name",
        "description": (
            "Structure prediction neural network. Predicts all-atom structures "
            "from sequences or templates, closing the gap to closed-source AF3."
        ),
        "description_key": "models.rf3.description",
        "capabilities": [
            "structure prediction",
            "complex prediction",
            "pLDDT",
        ],
        "capability_keys": [
            "models.rf3.cap.prediction",
            "models.rf3.cap.complex",
            "models.rf3.cap.plddt",
        ],
        "requires_checkpoint": True,
        "accepted_extensions": ["fasta", "fa", "cif", "pdb", "json"],
        "param_schema": {
            "type": "object",
            "properties": {
                "n_recycles": {
                    "type": "integer",
                    "title": "Recycles",
                    "title_key": "models.rf3.param.n_recycles.title",
                    "minimum": 0,
                    "maximum": 20,
                    "default": 10,
                    "description": "Number of structure prediction recycles.",
                    "description_key": "models.rf3.param.n_recycles.desc",
                },
                "num_steps": {
                    "type": "integer",
                    "title": "Diffusion steps",
                    "title_key": "models.rf3.param.num_steps.title",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 50,
                    "description_key": "models.rf3.param.num_steps.desc",
                    "description": "Number of diffusion steps for refinement.",
                },
                "dump_trajectories": {
                    "type": "boolean",
                    "title": "Dump trajectories",
                    "title_key": "models.rf3.param.dump_trajectories.title",
                    "default": False,
                    "description_key": "models.rf3.param.dump_trajectories.desc",
                    "description": "Save diffusion trajectories in the output.",
                },
                "annotate_b_factor_with_plddt": {
                    "type": "boolean",
                    "title": "Annotate pLDDT in B-factor",
                    "title_key": "models.rf3.param.annotate_plddt.title",
                    "default": False,
                    "description_key": "models.rf3.param.annotate_plddt.desc",
                    "description": "Write per-residue pLDDT into the B-factor column.",
                },
                "seed": {
                    "type": ["integer", "null"],
                    "title": "Seed",
                    "title_key": "models.rf3.param.seed.title",
                    "default": None,
                    "description_key": "models.rf3.param.seed.desc",
                    "description": "Random seed for reproducibility (null = random).",
                },
            },
        },
        "param_defaults": {"n_recycles": 10, "num_steps": 50},
    },
    "mpnn": {
        "id": "mpnn",
        "name": "ProteinMPNN / LigandMPNN",
        "name_key": "models.mpnn.name",
        "description": (
            "Inverse folding: designs amino-acid sequences that fold into a "
            "given backbone structure, under user-defined constraints."
        ),
        "description_key": "models.mpnn.description",
        "capabilities": [
            "sequence design",
            "fixed residues",
            "ligand-aware design",
        ],
        "capability_keys": [
            "models.mpnn.cap.seq_design",
            "models.mpnn.cap.fixed_res",
            "models.mpnn.cap.ligand",
        ],
        "requires_checkpoint": True,
        "accepted_extensions": ["cif", "pdb"],
        "param_schema": {
            "type": "object",
            "properties": {
                "model_type": {
                    "type": "string",
                    "title": "Model variant",
                    "title_key": "models.mpnn.param.model_type.title",
                    "enum": ["protein_mpnn", "ligand_mpnn"],
                    "default": "protein_mpnn",
                    "description_key": "models.mpnn.param.model_type.desc",
                    "description": "Choose the ProteinMPNN or LigandMPNN weights.",
                },
                "number_of_batches": {
                    "type": "integer",
                    "title": "Number of sequences",
                    "title_key": "models.mpnn.param.number_of_batches.title",
                    "minimum": 1,
                    "maximum": 64,
                    "default": 8,
                    "description": "Number of sequences to sample per input structure.",
                    "description_key": "models.mpnn.param.number_of_batches.desc",
                },
                "temperature": {
                    "type": "number",
                    "title": "Temperature",
                    "title_key": "models.mpnn.param.temperature.title",
                    "minimum": 0.01,
                    "maximum": 10.0,
                    "default": 0.1,
                    "description": "Sampling temperature (lower = more deterministic).",
                    "description_key": "models.mpnn.param.temperature.desc",
                },
                "batch_size": {
                    "type": "integer",
                    "title": "Batch size",
                    "title_key": "models.mpnn.param.batch_size.title",
                    "minimum": 1,
                    "maximum": 256,
                    "default": 1,
                    "description_key": "models.mpnn.param.batch_size.desc",
                    "description": "Structures processed per forward pass.",
                },
                "seed": {
                    "type": ["integer", "null"],
                    "title": "Seed",
                    "title_key": "models.mpnn.param.seed.title",
                    "default": None,
                    "description_key": "models.mpnn.param.seed.desc",
                    "description": "Random seed for reproducibility (null = random).",
                },
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
