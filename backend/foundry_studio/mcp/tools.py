"""MCP tool definitions for foundry-studio.

Each tool has an inputSchema in the format MCP expects (JSON Schema, draft-07).
These schemas are used both for discovery (tools/list) and for validation
(tools/call).  The actual handlers live in handlers.py.
"""

from __future__ import annotations

# MCP protocol version this server implements.
PROTOCOL_VERSION = "2025-06-18"

SERVER_INFO = {"name": "foundry-studio", "version": "0.1.0"}


def _str_schema(desc: str, *, default: str | None = None) -> dict:
    props = {"type": "string", "description": desc}
    if default is not None:
        props["default"] = default
    return props


# -------------------------------------------------------------------------- #
# Tool schemas                                                                #
# -------------------------------------------------------------------------- //

TOOLS: list[dict] = [
    {
        "name": "list_models",
        "description": "List all protein-design models available on this server "
        "(e.g. RFD3, RF3, ProteinMPNN, ESMFold).",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "list_jobs",
        "description": "List the most recent protein-design jobs submitted through this server. "
        "Returns job id, status, created time, and key parameters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": _str_schema(
                    "Filter by job status (e.g. pending, running, completed, failed).",
                    default="",
                ),
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of jobs to return.",
                    "default": 20,
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_job_status",
        "description": "Get the current status of a specific job by its job ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": _str_schema("The unique job identifier."),
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_job_logs",
        "description": "Fetch the latest stderr/stdout log lines from a running or finished job.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": _str_schema("The unique job identifier."),
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "submit_design",
        "description": "Submit a new protein-design job (RFD3 sequence design). "
        "Provide a target structure PDB path or FASTA sequence, design method, "
        "and number of sequences to generate.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": _str_schema(
                    "Target input: either a path to a PDB/CIF file, a FASTA sequence, "
                    "or a PDB code (e.g. 6QRZ)."
                ),
                "input_type": _str_schema(
                    "Type of the target field: 'pdb_path', 'fasta', or 'pdb_code'.",
                    default="pdb_path",
                ),
                "method": _str_schema(
                    "Design method: 'rfdiffusion' (default), 'rf3', or 'proteinmpnn'.",
                    default="rfdiffusion",
                ),
                "num_sequences": {
                    "type": "integer",
                    "description": "Number of sequences to design.",
                    "default": 5,
                },
                "temperature": {
                    "type": "number",
                    "description": "Sampling temperature for ProteinMPNN (0.1–1.0).",
                    "default": 0.1,
                },
                "lang": _str_schema(
                    "Language for job description and logs: 'en', 'zh', 'ja', or 'ru'.",
                    default="en",
                ),
            },
            "required": ["target"],
            "additionalProperties": False,
        },
    },
    {
        "name": "download_results",
        "description": "Return a pre-signed URL (or local path) to download the result "
        "ZIP for a completed job.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": _str_schema("The unique job identifier."),
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "cancel_job",
        "description": "Request cancellation of a running or pending job.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": _str_schema("The unique job identifier."),
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
]
