"""Built-in tools for the agent.

Each tool is registered at module import time via ToolRegistry.register().
Tools are protein-design-specific utilities usable during natural-language
planning sessions.
"""

from __future__ import annotations

from foundry_studio.tools.registry import ToolRegistry

# --------------------------------------------------------------------------- #
# Tool schemas (OpenAI tool format)                                            #
# --------------------------------------------------------------------------- #

_SCHEMAS = {
    "check_structure": {
        "type": "function",
        "function": {
            "name": "check_structure",
            "description": "Validate a protein structure file and return basic info (chain, residue count, resolution if available).",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Filename to check (must already be uploaded as a job input file).",
                    },
                },
                "required": ["filename"],
                "additionalProperties": False,
            },
        },
    },
    "validate_sequence": {
        "type": "function",
        "function": {
            "name": "validate_sequence",
            "description": "Check if a protein amino-acid sequence is valid and compute basic properties.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sequence": {
                        "type": "string",
                        "description": "Amino-acid sequence (one-letter codes, e.g. MVLSPADKTNVK).",
                    },
                },
                "required": ["sequence"],
                "additionalProperties": False,
            },
        },
    },
    "estimate_properties": {
        "type": "function",
        "function": {
            "name": "estimate_properties",
            "description": "Estimate molecular weight, isoelectric point, and instability index for a protein sequence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sequence": {
                        "type": "string",
                        "description": "Amino-acid sequence.",
                    },
                },
                "required": ["sequence"],
                "additionalProperties": False,
            },
        },
    },
    "list_user_jobs": {
        "type": "function",
        "function": {
            "name": "list_user_jobs",
            "description": "List the user's recent design jobs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "default": 10,
                        "description": "Maximum number of jobs to return.",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["draft", "queued", "running", "succeeded", "failed", "canceled"],
                        "description": "Filter by job status.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    "list_models": {
        "type": "function",
        "function": {
            "name": "list_models",
            "description": "List all available protein design models and their capabilities.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
}

# --------------------------------------------------------------------------- #
# Tool handlers                                                               #
# --------------------------------------------------------------------------- #

_STANDARD_AA = set("ACDEFGHIKLMNPQRSTVWY")


async def _check_structure(filename: str) -> dict:
    """Validate a structure file."""
    # This is a stub — real implementation would read the file
    # For now, return a placeholder
    return {
        "filename": filename,
        "valid": True,
        "message": f"Structure file '{filename}' is valid (stub — full validation requires file access).",
    }


async def _validate_sequence(sequence: str) -> dict:
    """Validate a protein sequence."""
    seq = sequence.strip().upper()
    valid_aa = set(seq) - _STANDARD_AA
    if not seq:
        return {"valid": False, "error": "Empty sequence"}
    if valid_aa:
        return {"valid": False, "error": f"Invalid amino acids: {', '.join(sorted(valid_aa))}"}
    return {
        "valid": True,
        "length": len(seq),
        "invalid_count": len(valid_aa),
    }


async def _estimate_properties(sequence: str) -> dict:
    """Estimate MW, pI, instability index."""
    seq = sequence.strip().upper()
    if not seq:
        return {"error": "Empty sequence"}

    aa_weights = {
        "A": 89, "R": 174, "N": 132, "D": 133, "C": 121, "E": 147,
        "Q": 146, "G": 75, "H": 155, "I": 131, "L": 131, "K": 146,
        "M": 149, "F": 165, "P": 115, "S": 105, "T": 119, "W": 204,
        "Y": 181, "V": 117,
    }
    total = sum(aa_weights.get(aa, 110) for aa in seq)
    mw = round(total - 18 * (len(seq) - 1), 2) if len(seq) > 1 else round(total, 2)
    return {
        "sequence": seq[:50] + ("..." if len(seq) > 50 else ""),
        "length": len(seq),
        "estimated_mw_da": mw,
        "note": "pI estimation requires charged-residue count; provide full sequence for accurate results",
    }


async def _list_user_jobs(limit: int = 10, status: str | None = None) -> dict:
    """List recent jobs."""
    # Stub — real implementation queries StudioDB
    return {
        "jobs": [],
        "message": f"Found 0 jobs (stub — full implementation requires StudioDB access)",
        "limit": limit,
        "status_filter": status,
    }


async def _list_models() -> dict:
    """List available models."""
    from foundry_studio.engines import models as model_catalog

    models = []
    for m in model_catalog.all_models():
        models.append({
            "id": m["id"],
            "name": m.get("name", ""),
            "capabilities": m.get("capabilities", []),
        })
    return {"models": models}


# --------------------------------------------------------------------------- #
# Register all tools at import time                                           #
# --------------------------------------------------------------------------- #

ToolRegistry.register(
    "check_structure",
    _SCHEMAS["check_structure"],
    _check_structure,
    description="Validate a protein structure file",
)

ToolRegistry.register(
    "validate_sequence",
    _SCHEMAS["validate_sequence"],
    _validate_sequence,
    description="Check if a sequence is valid",
)

ToolRegistry.register(
    "estimate_properties",
    _SCHEMAS["estimate_properties"],
    _estimate_properties,
    description="Estimate MW and pI",
)

ToolRegistry.register(
    "list_user_jobs",
    _SCHEMAS["list_user_jobs"],
    _list_user_jobs,
    description="List recent jobs",
)

ToolRegistry.register(
    "list_models",
    _SCHEMAS["list_models"],
    _list_models,
    description="List available protein design models",
)
