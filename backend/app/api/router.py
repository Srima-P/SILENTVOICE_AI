"""
Central API router — mounts all versioned sub-routers.
Future phases add their routers here without touching main.py.
"""
from fastapi import APIRouter

from app.api.routes import health
from app.api.routes import project
from app.api.routes import assistant

api_router = APIRouter()

# Phase 1 routes
api_router.include_router(health.router, tags=["health"])

# Phase 2 routes
api_router.include_router(project.router, prefix="/project", tags=["project"])

# Phase 3 routes
api_router.include_router(assistant.router, prefix="/assistant", tags=["assistant"])

# ── Future routes (Phase 4+) ──────────────────────────────────────────────────
# from app.api.routes import voice, diff
# api_router.include_router(voice.router, prefix="/voice", tags=["voice"])
# api_router.include_router(diff.router,  prefix="/diff",  tags=["diff"])
