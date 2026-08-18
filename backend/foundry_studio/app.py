"""FastAPI application factory for foundry-studio."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from foundry_studio import __version__
from foundry_studio.api import routes_agent, routes_files, routes_jobs, routes_meta
from foundry_studio.api.errors import register_exception_handlers
from foundry_studio.config import Settings, get_settings
from foundry_studio.db import StudioDB
from foundry_studio.joblifecycle import JobOrchestrator
from foundry_studio.session import SessionStore

# Import tools package to trigger ToolRegistry registration at startup.
from foundry_studio import tools  # noqa: F401

logger = logging.getLogger("foundry_studio.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle: start JobOrchestrator + init session store on startup; stop on shutdown."""
    # Startup: manager is already started in create_app()
    session_store: SessionStore | None = getattr(app.state, "session_store", None)
    if session_store is not None:
        session_store.init()
        logger.info("Session store initialized.")
    yield
    # Shutdown: gracefully stop the JobOrchestrator
    manager = getattr(app.state, "manager", None)
    if manager is not None:
        logger.info("Shutting down JobOrchestrator...")
        manager.stop()
        logger.info("JobOrchestrator stopped.")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application.  ``settings`` is injectable for tests."""
    settings = settings or get_settings()
    data_dir = settings.resolved_data_dir()
    (data_dir / "jobs").mkdir(parents=True, exist_ok=True)
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)

    db = StudioDB(data_dir / "studio.db")
    manager = JobOrchestrator(settings=settings, db=db)
    manager.start()

    app = FastAPI(
        title="foundry-studio",
        description="Agent-first control surface for RosettaCommons Foundry protein design on HPC",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = db
    app.state.manager = manager

    # Session store for multi-turn conversations
    session_store = SessionStore(data_dir / "sessions.db")
    app.state.session_store = session_store

    register_exception_handlers(app)

    # CORS: explicit allow-list driven by ``cors_allowed_origins``.
    # When the list is empty (the default) we still allow the loopback
    # Vite dev server so local development works without extra config.
    # Production deployments should set ``cors_allowed_origins`` to the
    # exact origin(s) they serve from.
    if settings.cors_allowed_origins:
        cors_origins = list(settings.cors_allowed_origins)
    else:
        cors_origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            f"http://127.0.0.1:{settings.port}",
            f"http://localhost:{settings.port}",
        ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_prefix = "/api"
    app.include_router(routes_meta.router, prefix=api_prefix, tags=["meta"])
    app.include_router(routes_jobs.router, prefix=api_prefix + "/jobs", tags=["jobs"])
    app.include_router(routes_files.router, prefix=api_prefix + "/jobs", tags=["files"])
    app.include_router(routes_agent.router, prefix=api_prefix + "/agent", tags=["agent"])

    # Mount built frontend if present.
    frontend_dist = settings.resolved_frontend_dist()
    if frontend_dist is not None:
        app.mount(
            "/",
            StaticFiles(directory=str(frontend_dist), html=True),
            name="frontend",
        )
    else:
        @app.get("/", include_in_schema=False)
        async def root() -> dict[str, Any]:
            return {
                "service": "foundry-studio",
                "version": __version__,
                "message": "API is running. Frontend build not found — run the "
                "frontend dev server (vite) or build it with `npm run build`.",
                "docs": "/docs",
                "api": "/api/health",
            }

    return app


def run_server(settings: Settings | None = None) -> None:
    """Run uvicorn programmatically (used by the CLI)."""
    import uvicorn

    settings = settings or get_settings()
    uvicorn.run(
        "foundry_studio.main:app",
        host=settings.effective_bind_host,
        port=settings.port,
        reload=False,
        log_level="info",
    )
