"""Meta routes: health, model catalog, checkpoints, i18n messages."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query

from foundry_studio import __version__
from foundry_studio.api.deps import get_db, get_manager, get_settings
from foundry_studio.api.errors import ApiError
from foundry_studio.config import Settings
from foundry_studio.db import StudioDB
from foundry_studio.engines import checkpoints as ckpt
from foundry_studio.engines import models as model_catalog
from foundry_studio.engines.registry import (
    engine_modes_for,
    real_engine_available,
)
from foundry_studio.i18n import MESSAGES
from foundry_studio.schemas import CheckpointInfo, HealthResponse, ModelInfo
from foundry_studio.workers.manager import WorkerManager

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(
    settings: Settings = Depends(get_settings),
    db: StudioDB = Depends(get_db),
    manager: WorkerManager = Depends(get_manager),
) -> HealthResponse:
    foundry_ok = _foundry_importable()
    gpu_ok = _gpu_available()
    return HealthResponse(
        status="ok",
        version=__version__,
        engine_mode=settings.engine_mode,
        simulation_fallback=settings.allow_simulation_fallback,
        gpu_available=gpu_ok,
        foundry_available=foundry_ok,
        data_dir=str(settings.resolved_data_dir()),
        workers=manager.worker_status(),
        message=None,
    )


@router.get("/models", response_model=list[ModelInfo])
def list_models(
    settings: Settings = Depends(get_settings),
) -> list[ModelInfo]:
    out: list[ModelInfo] = []
    for info in model_catalog.all_models():
        model_id = info["id"]
        ckpt_state = ckpt.model_checkpoint_state(model_id, settings.checkpoint_dirs)
        real_ok, reason = real_engine_available(model_id)
        # Determine effective engine for the current settings.
        effective: str | None = None
        if settings.engine_mode == "simulation":
            effective = "simulation"
        elif settings.engine_mode == "real":
            effective = "real" if real_ok else None
        else:  # auto
            effective = "real" if real_ok else ("simulation" if settings.allow_simulation_fallback else None)

        checkpoint_state = (
            "installed" if ckpt_state["installed"] else "missing"
        )
        out.append(
            ModelInfo(
                id=model_id,
                name=info["name"],
                name_key=info.get("name_key", ""),
                description=info["description"],
                description_key=info.get("description_key", ""),
                capabilities=info.get("capabilities", []),
                capability_keys=info.get("capability_keys", []),
                param_schema=info.get("param_schema", {}),
                param_defaults=info.get("param_defaults", {}),
                accepted_extensions=info.get("accepted_extensions", []),
                requires_checkpoint=info.get("requires_checkpoint", True),
                available_engines=engine_modes_for(model_id),
                effective_engine=effective,
                checkpoint_state=checkpoint_state,
                **(
                    {"real_engine_reason": reason} if not real_ok else {}
                ),
            )
        )
    return out


@router.get("/checkpoints", response_model=list[CheckpointInfo])
def list_checkpoints(
    settings: Settings = Depends(get_settings),
) -> list[CheckpointInfo]:
    entries = ckpt.list_checkpoints(settings.checkpoint_dirs)
    return [CheckpointInfo(**e) for e in entries]


@router.post("/checkpoints/install", response_model=CheckpointInfo)
def install_checkpoint(
    name: str = Query(..., description="Checkpoint registry name"),
    settings: Settings = Depends(get_settings),
) -> CheckpointInfo:
    try:
        result = ckpt.install_checkpoint(name, extra_dirs=settings.checkpoint_dirs)
    except KeyError as exc:
        raise ApiError(
            "error.model_not_found", status_code=404, params={"model": name}
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise ApiError(
            "error.checkpoint_install_failed",
            status_code=500,
            params={"name": name, "detail": str(exc)},
        ) from exc
    return CheckpointInfo(
        name=result["name"],
        filename=Path(result["path"]).name,
        description=_description_for(result["name"]),
        installed=True,
        path=result["path"],
        size_bytes=result["size_bytes"],
        url=_url_for(result["name"]),
    )


@router.post("/checkpoints/clean", response_model=dict)
def clean_checkpoints(
    settings: Settings = Depends(get_settings),
) -> dict:
    result = ckpt.cleanup_checkpoints(settings.checkpoint_dirs, dry_run=False)
    return result


@router.get("/i18n", response_model=dict)
def i18n_messages() -> dict:
    """Full backend message catalog for the active locale (frontend cache)."""
    return MESSAGES


def _foundry_importable() -> bool:
    try:
        import foundry  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def _gpu_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001
        return False


def _description_for(name: str) -> str:
    for entry in ckpt.list_checkpoints():
        if entry["name"] == name:
            return entry["description"]
    return name


def _url_for(name: str) -> str | None:
    registry = ckpt._merged_registry()  # noqa: SLF001
    info = registry.get(name)
    return info.get("url") if info else None
