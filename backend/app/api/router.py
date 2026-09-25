"""
Central API router — mounts all versioned sub-routers.
Future phases add their routers here without touching main.py.
"""
from fastapi import APIRouter

from app.api.routes import health
from app.api.routes import project
from app.api.routes import assistant
from app.api.routes import voice     # Phase 5

api_router = APIRouter()

# Phase 1 routes
api_router.include_router(health.router, tags=["health"])

# Phase 2 routes
api_router.include_router(project.router, prefix="/project", tags=["project"])

# Phase 3 routes
api_router.include_router(assistant.router, prefix="/assistant", tags=["assistant"])

# Phase 5 routes
api_router.include_router(voice.router, prefix="/voice", tags=["voice"])
