"""Engine registry: maps a model id + settings to a concrete engine class.

Resolution logic (``engine_mode`` setting + per-model availability):

- ``simulation`` : always the labelled SimulationEngine.
- ``real``      : the real engine; jobs fail with ``error.engine_unavailable``
                  when the model package / checkpoint is missing.
- ``auto``      : real engine if available, else SimulationEngine (only when
                  ``allow_simulation_fallback`` is enabled).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from foundry_studio.db import StudioDB
from foundry_studio.engines.base import BaseEngine
from foundry_studio.engines.mpnn import MPNNEngine
from foundry_studio.engines.rfd3 import RFD3Engine
from foundry_studio.engines.rfd3na import RFD3NAEngine
from foundry_studio.engines.rf3 import RF3Engine
from foundry_studio.engines.simulation import SimulationEngine

_REAL_ENGINES: dict[str, type[BaseEngine]] = {
    "rfd3": RFD3Engine,
    "rfd3na": RFD3NAEngine,
    "rf3": RF3Engine,
    "mpnn": MPNNEngine,
}

SIMULATION_WARNING = (
    "Simulation mode: results are produced by the built-in simulation engine "
    "for UI/flow validation only, not real predictions."
)


def real_engine_available(model_id: str) -> tuple[bool, str]:
    """Whether the real engine for ``model_id`` can run on this host."""
    cls = _REAL_ENGINES.get(model_id)
    if cls is None:
        return False, f"no engine registered for model '{model_id}'"
    try:
        return cls.is_available()
    except Exception as exc:  # noqa: BLE001
        return False, f"availability check failed: {exc}"


def resolve_engine(
    model_id: str,
    *,
    engine_mode: str,
    allow_simulation: bool = True,
    db: StudioDB,
    workdir: Path,
    log_path: Path,
) -> tuple[BaseEngine, str, bool]:
    """Return (engine, effective_mode, is_simulation).

    Raises RuntimeError when the requested engine cannot be satisfied.
    """
    real_cls = _REAL_ENGINES.get(model_id)
    if engine_mode == "simulation":
        return (
            SimulationEngine(db=db, workdir=workdir, log_path=log_path),
            "simulation",
            True,
        )

    real_ok, reason = (False, "no engine")
    if real_cls is not None:
        real_ok, reason = real_cls.is_available()

    if engine_mode == "real":
        if not real_ok:
            raise RuntimeError(reason or "real engine unavailable")
        return real_cls(db=db, workdir=workdir, log_path=log_path), "real", False

    # auto
    if real_ok:
        return real_cls(db=db, workdir=workdir, log_path=log_path), "real", False
    if allow_simulation:
        return (
            SimulationEngine(db=db, workdir=workdir, log_path=log_path),
            "simulation",
            True,
        )
    raise RuntimeError(reason or "real engine unavailable")


def engine_modes_for(model_id: str) -> list[str]:
    """Available engine kinds for a model on this host (for the UI badge)."""
    ok, _ = real_engine_available(model_id)
    modes = ["simulation"]
    if ok:
        modes.insert(0, "real")
    return modes
