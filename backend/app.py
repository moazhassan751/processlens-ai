"""
ProcessLens — FastAPI Application Factory
============================================
Creates the app, adds middleware, includes all routers, and runs startup tasks.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("processlens")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # Startup
    from backend.services.supabase_client import init_supabase
    from backend.services.storage import ensure_storage
    init_supabase()
    ensure_storage()
    logger.info("Backend ready.")
    yield
    # Shutdown
    logger.info("Shutting down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="ProcessLens API",
        version="3.0.0",
        description="Process Mining, Predictive Analytics & AI-Powered Recommendations",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include all routers
    from backend.routers import data, pipeline, upload, history, process_map, snapshot, projects, explain, conformance, simulation, connectors

    app.include_router(data.router)
    app.include_router(pipeline.router)
    app.include_router(upload.router)
    app.include_router(history.router)
    app.include_router(process_map.router)
    app.include_router(snapshot.router)
    app.include_router(projects.router)
    app.include_router(explain.router)
    app.include_router(conformance.router)
    app.include_router(simulation.router)
    app.include_router(connectors.router)

    return app


# Module-level app instance for uvicorn
app = create_app()
