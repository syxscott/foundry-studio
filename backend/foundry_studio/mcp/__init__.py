"""MCP stdio server for foundry-studio.

Exposes foundry-studio tools via the Model Context Protocol over stdin/stdout.
Clients connect via stdio transport and call tools via JSON-RPC 2.0 messages.
"""

from __future__ import annotations

from foundry_studio.mcp import handlers
from foundry_studio.mcp import server
from foundry_studio.mcp import tools
from foundry_studio.mcp import transport

__all__ = ["handlers", "server", "tools", "transport"]
