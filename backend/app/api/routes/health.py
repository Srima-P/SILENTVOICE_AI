"""Health-check endpoint."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health_check() -> HealthResponse:
    """
    Returns service status.
    Used by the frontend to verify backend connectivity.
    """
    from app.config import settings

    return HealthResponse(
        status="ok",
        service="silentvoice-ai-backend",
        version="0.1.0",
        environment=settings.app_env,
    )
