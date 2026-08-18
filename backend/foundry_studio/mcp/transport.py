"""Stdio transport for MCP JSON-RPC 2.0.

Reads JSON-RPC requests from stdin (one JSON object per line, per the MCP spec)
and writes responses to stdout using the same line-delimited JSON format.

UTF-8 is assumed for both directions.  Blank lines are ignored.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

__all__ = ["StdioTransport"]


class StdioTransport:
    """Reads requests from stdin, writes responses to stdout, line-delimited JSON."""

    def __init__(self) -> None:
        self._closed = False

    def close(self) -> None:
        self._closed = True

    def send_response(self, response: dict[str, Any]) -> None:
        """Write one JSON-RPC response to stdout."""
        if self._closed:
            return
        line = json.dumps(response, ensure_ascii=False)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    def read_requests(
        self, handler: Callable[[dict[str, Any]], None]
    ) -> None:
        """Read stdin line-by-line, parse each JSON-RPC request, and dispatch to handler.

        Blocks until stdin is closed.  Each line that is empty or not valid JSON
        is silently skipped (consistent with the MCP spec behaviour for probes).
        """
        for raw_line in sys.stdin:
            line = raw_line.rstrip("\r\n")
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                # Malformed JSON — silently ignore per MCP spec §Transport
                continue
            if not isinstance(request, dict):
                continue
            # Per the spec, a JSON-RPC request MUST have "jsonrpc": "2.0" and a method.
            if request.get("jsonrpc") != "2.0" or "method" not in request:
                continue
            handler(request)

    def read_loop(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Synonym for read_requests for clarity in server.py."""
        self.read_requests(handler)
