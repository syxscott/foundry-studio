"""Tool registry for foundry-studio.

Tools are protein-design-specific utilities that the LLM agent can call
during a planning conversation.  Each tool has a JSON Schema (OpenAI tool
format) and an async handler function.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

__all__ = ["ToolEntry", "ToolRegistry"]


@dataclass(slots=True)
class ToolEntry:
    """One registered tool."""

    name: str
    schema: dict  # OpenAI tool schema
    handler: Callable[..., Coroutine[Any, Any, Any]]
    check_fn: Callable[[], bool] | None = None
    description: str = ""


class ToolRegistry:
    """Central registry for built-in and extension tools."""

    _tools: dict[str, ToolEntry] = {}
    _check_cache: dict[str, tuple[bool, float]] = {}
    _CACHE_TTL: float = 30.0  # seconds

    @classmethod
    def register(
        cls,
        name: str,
        schema: dict,
        handler: Callable[..., Coroutine[Any, Any, Any]],
        check_fn: Callable[[], bool] | None = None,
        description: str = "",
    ) -> None:
        cls._tools[name] = ToolEntry(
            name=name,
            schema=schema,
            handler=handler,
            check_fn=check_fn,
            description=description,
        )

    @classmethod
    def list_tools(cls) -> list[ToolEntry]:
        return list(cls._tools.values())

    @classmethod
    def get_tool(cls, name: str) -> ToolEntry | None:
        return cls._tools.get(name)

    @classmethod
    def get_schemas(cls) -> list[dict]:
        """Return all tool schemas in OpenAI tool format, filtered by runtime availability."""
        schemas: list[dict] = []
        for tool in cls._tools.values():
            available, _ = cls._check_availability(tool.name)
            if not available:
                continue
            schemas.append(tool.schema)
        return schemas

    @classmethod
    def get_all_schemas(cls) -> list[dict]:
        """Return all tool schemas regardless of runtime availability (for discovery)."""
        return [t.schema for t in cls._tools.values()]

    @classmethod
    def get_checks(cls) -> dict[str, bool]:
        """Return runtime availability for all tools."""
        return {name: cls._check_availability(name)[0] for name in cls._tools}

    @classmethod
    def _check_availability(cls, name: str) -> tuple[bool, float]:
        """Return (available, cached_at)."""
        tool = cls._tools.get(name)
        if not tool:
            return False, 0.0
        if not tool.check_fn:
            return True, float("inf")

        now = asyncio.get_event_loop().time()
        cached_ok, cached_at = cls._check_cache.get(name, (False, 0.0))
        if now - cached_at < cls._CACHE_TTL:
            return cached_ok, cached_at

        try:
            available = tool.check_fn()
            cls._check_cache[name] = (available, now)
            return available, now
        except Exception:
            cls._check_cache[name] = (False, now)
            return False, now

    @classmethod
    async def execute_tool(
        cls, name: str, arguments: dict
    ) -> dict[str, Any]:
        """Execute a tool by name with the given arguments. Returns a result dict."""
        tool = cls._tools.get(name)
        if not tool:
            return {"ok": False, "error": f"unknown tool: {name}"}

        available, _ = cls._check_availability(name)
        if not available:
            return {"ok": False, "error": f"tool '{name}' is not available right now"}

        try:
            result = await tool.handler(**arguments)
            return {"ok": True, "result": result}
        except TypeError as exc:
            # Missing or extra arguments
            return {"ok": False, "error": f"invalid arguments for '{name}': {exc}"}
        except Exception as exc:
            return {"ok": False, "error": f"tool '{name}' failed: {exc}"}
