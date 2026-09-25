"""
SilentVoice AI — FastAPI application entry-point.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.router import api_router
from app.utils.errors import register_exception_handlers

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("silentvoice")

# ─── Application ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="SilentVoice AI",
    description="Accessibility-first, voice-driven AI development workspace — Phase 1 backend.",
    version="0.1.0",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routes ───────────────────────────────────────────────────────────────────
app.include_router(api_router, prefix="/api")

# ─── Exception Handlers ───────────────────────────────────────────────────────
register_exception_handlers(app)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("SilentVoice AI backend starting — env=%s", settings.app_env)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("SilentVoice AI backend shutting down.")
