"""
FastAPI application entry point.

Run (development):
    uvicorn backend.main:app --reload --port 8000

The app serves:
    /api/*          — JSON REST + WebSocket endpoints
    /health         — liveness probe
    /               — React frontend static files (once frontend/dist/ exists)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# PyInstaller compatibility: add extracted directory to sys.path
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    sys.path.insert(0, sys._MEIPASS)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.jobs import router as jobs_router
from backend.core import config

# ──────────────────────────────────────────────────────────────────────────────
# App
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ESS Comprestimator UI",
    description=(
        "Web interface for the IBM ESS / GPFS compression estimator tool. "
        "Accepts job parameters, runs the comprestimator binary asynchronously, "
        "and streams results back to the browser."
    ),
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ──────────────────────────────────────────────────────────────────────────────
# CORS — only allow the Vite dev server when DEV_CORS=true.
# In production (packaged Electron app) the renderer is served by the same
# FastAPI process, so it is same-origin and no CORS headers are needed.
# ──────────────────────────────────────────────────────────────────────────────

_DEV_CORS = os.environ.get("DEV_CORS", "").lower() in ("1", "true")
_cors_origins = (
    ["http://localhost:5173", "http://127.0.0.1:5173"]
    if _DEV_CORS
    else []
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# ──────────────────────────────────────────────────────────────────────────────
# Routers
# ──────────────────────────────────────────────────────────────────────────────

app.include_router(jobs_router)

# ──────────────────────────────────────────────────────────────────────────────
# Health endpoint
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
async def health() -> JSONResponse:
    binary_ok = os.path.isfile(config.COMPRESTIMATOR_PATH)
    return JSONResponse(
        content={
            "status": "ok",
            "binary_found": binary_ok,
            "mock_mode": config.MOCK_BINARY,
            "max_concurrent_jobs": config.MAX_CONCURRENT_JOBS,
        }
    )

# ──────────────────────────────────────────────────────────────────────────────
# Static files — serve the React build when it exists
# ──────────────────────────────────────────────────────────────────────────────

_FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    # Serve static assets (JS, CSS, images) under /assets
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")

    # Catch-all: serve index.html for all non-API routes so React Router works
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        index = _FRONTEND_DIST / "index.html"
        return FileResponse(str(index))
