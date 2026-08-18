"""FastAPI application dependencies (db, settings, worker manager, session store)."""

from __future__ import annotations

from fastapi import Request

from foundry_studio.db import StudioDB
from foundry_studio.joblifecycle import JobOrchestrator
from foundry_studio.session import SessionStore


def get_db(request: Request) -> StudioDB:
    return request.app.state.db


def get_settings(request: Request):
    return request.app.state.settings


def get_manager(request: Request) -> JobOrchestrator:
    return request.app.state.manager


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.session_store
