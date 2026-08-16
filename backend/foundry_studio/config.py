"""Application configuration for foundry-studio.

All settings can be overridden with environment variables prefixed by
``FOUNDRY_STUDIO_`` (for example ``FOUNDRY_STUDIO_DATA_DIR=...``).
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATA_DIR = Path.home() / ".foundry-studio"


def _env_file_path() -> str:
    """Env file path: honour an explicit FOUNDRY_STUDIO_ENV_FILE override,
    otherwise fall back to the local ``.env`` (if present)."""
    explicit = os.environ.get("FOUNDRY_STUDIO_ENV_FILE")
    if explicit:
        return explicit
    local = Path.cwd() / ".env"
    return str(local) if local.is_file() else ""


class Settings(BaseSettings):
    """Runtime settings. Values are read from env vars with the
    ``FOUNDRY_STUDIO_`` prefix, or from a ``.env`` file."""

    model_config = SettingsConfigDict(
        env_prefix="FOUNDRY_STUDIO_",
        env_file=_env_file_path(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Server -----------------------------------------------------------------
    host: str = "127.0.0.1"
    port: int = 8765

    # --- Storage -----------------------------------------------------------------
    # Root directory that holds the job database, uploaded inputs, outputs and logs.
    data_dir: Path = DEFAULT_DATA_DIR

    # --- Engine behaviour ----------------------------------------------------------
    # auto: use the real Foundry engines when the packages + checkpoints are
    #       available, otherwise fall back to the labelled simulation engine.
    # real: force real engines (fail the job if the package is missing).
    # simulation: force the labelled simulation engine for every model.
    engine_mode: str = "auto"

    # When engine_mode=auto, simulation fallback is allowed only if this is true.
    allow_simulation_fallback: bool = True

    # --- Checkpoint management ------------------------------------------------------
    # Colon-separated extra checkpoint directories appended to the Foundry search
    # path (same semantics as FOUNDRY_CHECKPOINT_DIRS).
    checkpoint_dirs: str = ""

    # --- Worker ----------------------------------------------------------------------
    # Seconds a worker waits between database polls when idle.
    worker_poll_interval: float = 2.0

    # Automatically (re)spawn model workers while the API server is running.
    worker_autostart: bool = True

    # --- Security --------------------------------------------------------------------
    # Bind the API only to loopback by default. Set to "0.0.0.0" for LAN access.
    # A reverse proxy (TLS + auth) is strongly recommended before exposing publicly.
    allow_remote_access: bool = False

    # --- Frontend ----------------------------------------------------------------------
    # Path to the built frontend (frontend/dist). If the directory does not exist,
    # the API serves only the JSON endpoints and a hint is returned at "/".
    frontend_dist: Path | None = None

    def resolved_data_dir(self) -> Path:
        return self.data_dir.expanduser().resolve()

    def resolved_frontend_dist(self) -> Path | None:
        if self.frontend_dist is None:
            return None
        resolved = self.frontend_dist.expanduser().resolve()
        return resolved if resolved.is_dir() else None

    @property
    def effective_bind_host(self) -> str:
        if self.allow_remote_access:
            return "0.0.0.0"
        return "127.0.0.1"


def get_settings() -> Settings:
    """Return a process-wide settings instance (cached)."""
    return Settings()
