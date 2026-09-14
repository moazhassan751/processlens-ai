"""
ProcessLens — Main Entry Point
================================
Thin compatibility shim that re-exports the app from the new modular backend.
This ensures `uvicorn backend.main:app --port 8000` continues to work unchanged.

The actual application logic is in:
  - backend/app.py        — FastAPI app factory
  - backend/config.py     — Centralized configuration
  - backend/routers/      — API route handlers
  - backend/services/     — Business logic & data access
  - backend/models/       — Pydantic schemas
"""

from backend.app import app  # noqa: F401

__all__ = ["app"]
