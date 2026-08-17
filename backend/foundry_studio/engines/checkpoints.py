"""Checkpoint management for foundry-studio.

The registry mirrors the upstream Foundry checkpoint catalog so the UI can
list / install / verify weights without importing rc-foundry.  When the real
Foundry package is installed, its ``REGISTERED_CHECKPOINTS`` take precedence
(we merge any entries that are not already known here).
"""

from __future__ import annotations

import hashlib
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CHECKPOINT_DIR = Path.home() / ".foundry" / "checkpoints"

# Mirrored from src/foundry/inference_engines/checkpoint_registry.py
REGISTERED: dict[str, dict[str, str]] = {
    "rfd3na": {
        "filename": "rfd3na_1190.ckpt",
        "url": "https://files.ipd.uw.edu/pub/rfdiffusion3na/rfd3na-1190.ckpt",
        "description": "RFdiffusion3NA checkpoint",
    },
    "rfd3": {
        "filename": "rfd3_latest.ckpt",
        "url": "https://files.ipd.uw.edu/pub/rfd3/rfd3_foundry_2025_12_01_remapped.ckpt",
        "description": "RFdiffusion3 checkpoint",
    },
    "rf3": {
        "filename": "rf3_foundry_01_24_latest_remapped.ckpt",
        "url": "https://files.ipd.uw.edu/pub/rf3/rf3_foundry_01_24_latest_remapped.ckpt",
        "description": "latest RF3 checkpoint trained with data until 1/2024 (expect best performance)",
    },
    "proteinmpnn": {
        "filename": "proteinmpnn_v_48_020.pt",
        "url": "https://files.ipd.uw.edu/pub/ligandmpnn/proteinmpnn_v_48_020.pt",
        "description": "ProteinMPNN checkpoint",
    },
    "ligandmpnn": {
        "filename": "ligandmpnn_v_32_010_25.pt",
        "url": "https://files.ipd.uw.edu/pub/ligandmpnn/ligandmpnn_v_32_010_25.pt",
        "description": "LigandMPNN checkpoint",
    },
    "solublempnn": {
        "filename": "solublempnn_v_48_020.pt",
        "url": "https://files.ipd.uw.edu/pub/ligandmpnn/solublempnn_v_48_020.pt",
        "description": "SolubleMPNN checkpoint",
    },
}

# Model id -> checkpoint name used by the real engines.
MODEL_TO_CHECKPOINT = {
    "rfd3": "rfd3",
    "rfd3na": "rfd3na",
    "rf3": "rf3",
    "mpnn": "proteinmpnn",  # default variant; ligand_mpnn maps at job time
}


@dataclass
class CheckpointEntry:
    name: str
    filename: str
    url: str
    description: str


def _foundry_registry() -> dict[str, dict[str, Any]]:
    """Return upstream Foundry's registry if importable, else {}."""
    try:
        from foundry.inference_engines.checkpoint_registry import (  # type: ignore[import-not-found]
            REGISTERED_CHECKPOINTS,
        )

        out: dict[str, dict[str, Any]] = {}
        for name, info in REGISTERED_CHECKPOINTS.items():
            out[name] = {
                "filename": getattr(info, "filename", ""),
                "url": getattr(info, "url", ""),
                "description": getattr(info, "description", ""),
            }
        return out
    except Exception:  # noqa: BLE001 - package not installed
        return {}


def _merged_registry() -> dict[str, dict[str, str]]:
    merged: dict[str, dict[str, str]] = dict(REGISTERED)
    for name, info in _foundry_registry().items():
        merged.setdefault(name, {k: str(v) for k, v in info.items()})
    return merged


def checkpoint_dirs(extra: str = "") -> list[Path]:
    """Search path, mirroring upstream ``get_default_checkpoint_dirs``."""
    paths: list[Path] = []
    for p in [extra, ""]:
        for part in p.split(":") if p else []:
            if part.strip():
                paths.append(Path(part.strip()).expanduser().resolve())
    paths.append(DEFAULT_CHECKPOINT_DIR.expanduser().resolve())
    # Deduplicate preserving order.
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def find_checkpoint_path(entry: CheckpointEntry, extra_dirs: str = "") -> Path | None:
    for d in checkpoint_dirs(extra_dirs):
        candidate = d / entry.filename
        if candidate.is_file():
            return candidate
    return None


def list_checkpoints(extra_dirs: str = "") -> list[dict[str, Any]]:
    registry = _merged_registry()
    entries: list[dict[str, Any]] = []
    for name in sorted(registry):
        info = registry[name]
        entry = CheckpointEntry(name=name, **info)
        path = find_checkpoint_path(entry, extra_dirs)
        size = path.stat().st_size if path else None
        entries.append(
            {
                "name": name,
                "filename": entry.filename,
                "description": entry.description,
                "url": entry.url,
                "installed": path is not None,
                "path": str(path) if path else None,
                "size_bytes": size,
            }
        )
    return entries


def _sha256_of(url: str, dest: Path) -> None:
    """Streaming download; verifies against the upstream published hash if any.

    The upstream registry currently ships hashes as ``None`` for most entries,
    so verification is best-effort: if a hash is known (via the foundry
    package) we enforce it, otherwise we just check the file is non-empty.
    """
    known_hash: str | None = None
    try:
        from foundry.inference_engines.checkpoint_registry import (  # type: ignore[import-not-found]
            REGISTERED_CHECKPOINTS,
        )

        info = REGISTERED_CHECKPOINTS.get(dest.name.replace(".ckpt", "").replace(".pt", ""))
        if info is not None and getattr(info, "sha256", None):
            known_hash = getattr(info, "sha256")
    except Exception:  # noqa: BLE001
        known_hash = None

    req = urllib.request.Request(url, headers={"User-Agent": "foundry-studio/0.1"})
    hasher = hashlib.sha256()
    downloaded = 0
    with urllib.request.urlopen(req, timeout=600) as resp, open(dest, "wb") as fh:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            fh.write(chunk)
            hasher.update(chunk)
            downloaded += len(chunk)

    if downloaded == 0:
        raise RuntimeError("downloaded file is empty")

    if known_hash and hasher.hexdigest() != known_hash:
        dest.unlink(missing_ok=True)
        raise RuntimeError(
            f"SHA256 mismatch: expected {known_hash}, got {hasher.hexdigest()}"
        )


def install_checkpoint(
    name: str,
    checkpoint_dir: Path | None = None,
    extra_dirs: str = "",
    force: bool = False,
    progress_cb=None,
) -> dict[str, Any]:
    """Install a checkpoint. Returns a dict with path/size on success.

    ``progress_cb`` is called with (downloaded_bytes, total_bytes) if known.
    """
    registry = _merged_registry()
    if name not in registry:
        raise KeyError(f"unknown checkpoint '{name}'")

    target_dir = (checkpoint_dir or DEFAULT_CHECKPOINT_DIR).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    entry = CheckpointEntry(name=name, **registry[name])
    dest = target_dir / entry.filename

    if dest.is_file() and not force:
        return {
            "name": name,
            "path": str(dest),
            "size_bytes": dest.stat().st_size,
            "installed": True,
        }

    _download_with_progress(entry.url, dest, progress_cb)
    return {
        "name": name,
        "path": str(dest),
        "size_bytes": dest.stat().st_size,
        "installed": True,
    }


def _download_with_progress(url: str, dest: Path, progress_cb=None) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "foundry-studio/0.1"})
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    start = time.time()
    with urllib.request.urlopen(req, timeout=600) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        with open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                fh.write(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    progress_cb(downloaded, total)
    tmp.replace(dest)


def model_checkpoint_state(
    model_id: str, extra_dirs: str = ""
) -> dict[str, Any]:
    """Return install state for the checkpoint used by ``model_id``."""
    checkpoint_name = MODEL_TO_CHECKPOINT.get(model_id)
    if checkpoint_name is None:
        return {"name": None, "installed": False, "path": None}
    registry = _merged_registry()
    info = registry.get(checkpoint_name)
    if info is None:
        return {"name": checkpoint_name, "installed": False, "path": None}
    entry = CheckpointEntry(name=checkpoint_name, **info)
    path = find_checkpoint_path(entry, extra_dirs)
    return {
        "name": checkpoint_name,
        "installed": path is not None,
        "path": str(path) if path else None,
    }


def cleanup_checkpoints(extra_dirs: str = "", dry_run: bool = False) -> dict[str, Any]:
    """Remove downloaded checkpoints. With dry_run, list what would be removed."""
    deleted: list[dict[str, Any]] = []
    total_bytes = 0
    search_dirs = [str(d) for d in checkpoint_dirs(extra_dirs)]
    install_dir = str(DEFAULT_CHECKPOINT_DIR.expanduser().resolve())
    for entry_info in list_checkpoints(extra_dirs):
        path = Path(entry_info["path"]) if entry_info["path"] else None
        if path is None or not path.is_file():
            continue
        info = path.stat()
        total_bytes += info.st_size
        if dry_run:
            deleted.append({"path": str(path), "size_bytes": info.st_size})
        else:
            path.unlink(missing_ok=True)
            deleted.append({"path": str(path), "size_bytes": info.st_size})
    return {
        "deleted": deleted,
        "total_bytes": total_bytes,
        "dry_run": dry_run,
        "search_dirs": search_dirs,
        "install_dir": install_dir,
    }
