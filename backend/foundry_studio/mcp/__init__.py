"""MCP stdio server for foundry-studio.

Exposes foundry-studio tools via the Model Context Protocol over stdin/stdout.
Clients connect via stdio transport and call tools via JSON-RPC 2.0 messages.
"""

from __future__ import annotations

from foundry_studio.mcp import handlers, server, tools, transport

__all__ = ["handlers", "server", "tools", "transport"]
