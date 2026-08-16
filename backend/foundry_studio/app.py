"""FastAPI application factory for foundry-studio."""

from __future__ import annotations

import logging
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

logger = logging.getLogger("foundry_studio.api")


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
    )
    app.state.settings = settings
    app.state.db = db
    app.state.manager = manager

    register_exception_handlers(app)

    # CORS: allow the Vite dev server during development.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
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
