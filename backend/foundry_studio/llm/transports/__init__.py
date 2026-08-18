"""Transport registry — auto-discovers and registers all known transports."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

_TRANSPORTS: dict[str, type] = {}


def _discover_transports() -> None:
    """Import all modules under this package to trigger register() calls."""
    package_path = Path(__file__).parent
    for _module_info in pkgutil.iter_modules([str(package_path)]):
        if _module_info.name in ("_", "base"):
            continue
        importlib.import_module(f"foundry_studio.llm.transports.{_module_info.name}")


def register_transport(api_mode: str, cls: type) -> None:
    _TRANSPORTS[api_mode] = cls


def get_transport(api_mode: str) -> type | None:
    return _TRANSPORTS.get(api_mode)


def _ensure_discovered() -> None:
    if not _TRANSPORTS:
        _discover_transports()


# Auto-discover transports on first import
_ensure_discovered()

from foundry_studio.llm.transports.base import ProviderTransport

__all__ = [
    "ProviderTransport",
    "get_transport",
    "register_transport",
]
