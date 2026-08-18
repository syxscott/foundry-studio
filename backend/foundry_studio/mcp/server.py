"""MCP stdio server entry point for foundry-studio.

Listens on stdin for JSON-RPC 2.0 requests and writes responses to stdout.
Implements the Model Context Protocol §Protocol conventions:
  - initialize  → returns server capabilities
  - tools/list  → returns registered tool schemas
  - tools/call  → dispatches to the appropriate handler
  - notifications (id=null) → acknowledged, no response sent

Usage (standalone):
    python -m foundry_studio.mcp.server

Or via the foundry-mcp entry point defined in pyproject.toml.
The FOUNDRY_STUDIO_API_URL environment variable controls which server to talk to
(defaults to http://localhost:8000).
"""

from __future__ import annotations

import asyncio
import json
import sys

from foundry_studio.mcp.handlers import handle_request
from foundry_studio.mcp.tools import PROTOCOL_VERSION, SERVER_INFO, TOOLS
from foundry_studio.mcp.transport import StdioTransport

__all__ = ["main"]


async def _handle_jsonrpc(request: dict) -> None:
    """Process one JSON-RPC request and send the response over stdio."""
    if request.get("method") == "initialize":
        # The client initilializes first; we respond with our capabilities.
        response = {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
                # MCP 2025-06-18 requires we echo back the client's options.
                "instructions": (
                    "foundry-studio MCP server — protein-design job management. "
                    "Submit RFD3/RF3/ProteinMPNN design jobs, query job status and logs, "
                    "and download results.  Set FOUNDRY_STUDIO_API_URL to point at the "
                    "foundry-studio web API (default http://localhost:8000)."
                ),
            },
        }
        transport.send_response(response)
        return

    if request.get("method") == "tools/list":
        response = {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {"tools": TOOLS},
        }
        transport.send_response(response)
        return

    if request.get("method") == "tools/call":
        params = request.get("params") or {}
        tool_name = params.get("name")
        tool_args = params.get("arguments") or {}

        if not tool_name:
            transport.send_response({
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32602, "message": "Missing required parameter: name"},
            })
            return

        # Map MCP tool name → the key used in handlers.METHODS
        _HANDLER_MAP = {
            "list_models": "list_models",
            "list_jobs": "list_jobs",
            "get_job_status": "get_job_status",
            "get_job_logs": "get_job_logs",
            "submit_design": "submit_design",
            "download_results": "download_results",
            "cancel_job": "cancel_job",
        }
        handler_key = _HANDLER_MAP.get(tool_name)

        # Build the MCP success response shape: content[{type, text}]
        req_id = request.get("id")

        if handler_key is None:
            transport.send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            })
            return

        # Delegate to the async handler
        inner = await handle_request({
            "jsonrpc": "2.0",
            "id": None,  # inner calls don't need their own id
            "method": handler_key,
            "params": tool_args,
        })

        if inner is None:
            # Notification — nothing to send
            return

        if "error" in inner:
            # Map handler error to MCP error form
            transport.send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32000,
                    "message": inner["error"].get("message", str(inner["error"])),
                },
            })
            return

        # Success — wrap the result in MCP content block
        result_data = inner.get("result", {})
        # Flatten result to readable text for the text content block
        text = _format_result(tool_name, result_data)
        transport.send_response({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": text}],
                "isError": False,
            },
        })
        return

    # Any other method — method not found
    transport.send_response({
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "error": {"code": -32601, "message": f"Method not found: {request.get('method')}"},
    })


def _format_result(tool_name: str, result: dict) -> str:
    """Human-readable one-line summary of a tool result for the text content block."""
    if tool_name == "list_models":
        models = result.get("models", [])
        if not models:
            return "No models available."
        lines = [f"{m['name']}: {m['description']}" for m in models]
        return "\n".join(lines)

    if tool_name == "list_jobs":
        jobs = result.get("jobs", [])
        if not jobs:
            return "No jobs found."
        lines = [f"[{j['job_id']}] {j['status']} — {j.get('description', '')}" for j in jobs]
        return "\n".join(lines)

    if tool_name == "get_job_status":
        return json.dumps(result, indent=2, ensure_ascii=False)

    if tool_name == "get_job_logs":
        logs = result.get("logs", "(no logs)")
        return logs if isinstance(logs, str) else json.dumps(logs)

    if tool_name == "submit_design":
        return (f"Job submitted: job_id={result.get('job_id')}, "
                f"status={result.get('status')}")

    if tool_name == "download_results":
        if not result.get("ok", True):
            return f"Error: {result.get('error')}"
        return f"Download URL: {result.get('url')}"

    if tool_name == "cancel_job":
        return json.dumps(result, indent=2, ensure_ascii=False)

    # Fallback
    return json.dumps(result, indent=2, ensure_ascii=False)


# Singleton transport shared across the event loop.
transport: StdioTransport | None = None


def main() -> None:
    global transport

    transport = StdioTransport()

    def sync_dispatch(request: dict) -> None:
        """Sync wrapper — schedule the async handler on the running loop."""
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already inside an async context, create a new task.
            # For the stdio loop there should be no outer loop, but some
            # platforms may initialize one automatically.
            asyncio.ensure_future(_handle_jsonrpc(request))
        else:
            loop.run_until_complete(_handle_jsonrpc(request))

    try:
        transport.read_loop(sync_dispatch)
    except KeyboardInterrupt:
        transport.close()


if __name__ == "__main__":
    main()
