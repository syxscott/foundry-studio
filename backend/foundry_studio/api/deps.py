"""FastAPI application dependencies (db, settings, worker manager)."""

from __future__ import annotations

from fastapi import Request

from foundry_studio.db import StudioDB
from foundry_studio.workers.manager import WorkerManager


def get_db(request: Request) -> StudioDB:
    return request.app.state.db


def get_settings(request: Request):
    return request.app.state.settings


def get_manager(request: Request) -> WorkerManager:
    return request.app.state.manager
