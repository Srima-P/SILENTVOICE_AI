"""
Voice API routes — Phase 5.

Endpoints:
  POST /api/voice/transcribe  → Accept audio upload, call Groq Whisper, return transcript
  GET  /api/voice/status      → Whether voice (Groq) is configured
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from app.config import settings
from app.services.voice_service import VoiceService, VoiceError, MAX_AUDIO_BYTES

router = APIRouter()
logger = logging.getLogger("silentvoice.api.voice")


class TranscribeResponse(BaseModel):
    """Response from POST /api/voice/transcribe"""
    text: str
    duration_hint: Optional[str] = None   # human-readable (e.g. "short clip")


class VoiceStatusResponse(BaseModel):
    configured: bool
    model: str
    max_audio_mb: float


# ── GET /api/voice/status ─────────────────────────────────────────────────────

@router.get("/status", response_model=VoiceStatusResponse, summary="Check voice configuration")
async def voice_status() -> VoiceStatusResponse:
    """Returns whether the Groq key is set for voice (same key as chat)."""
    configured = bool(settings.groq_api_key and settings.groq_api_key.strip())
    return VoiceStatusResponse(
        configured=configured,
        model="whisper-large-v3-turbo",
        max_audio_mb=round(MAX_AUDIO_BYTES / (1024 * 1024), 1),
    )


# ── POST /api/voice/transcribe ────────────────────────────────────────────────

@router.post(
    "/transcribe",
    response_model=TranscribeResponse,
    summary="Transcribe an audio file using Groq Whisper",
)
async def transcribe(
    file: UploadFile = File(..., description="Audio file to transcribe"),
    language: Optional[str] = Query(
        None,
        description="Optional ISO-639-1 language code (e.g. 'en'). Leave blank for auto-detect.",
    ),
) -> TranscribeResponse:
    """
    Accepts an audio upload, validates it, and returns the Whisper transcript.

    Security:
      - GROQ_API_KEY is read from server environment only.
      - Audio bytes are discarded after the response.
      - File size and MIME type are validated before any API call.
    """
    logger.info(
        "Transcription request: filename=%r content_type=%r",
        file.filename,
        file.content_type,
    )

    content_type = file.content_type or "application/octet-stream"
    svc = VoiceService()

    # Validate MIME type before reading large payload
    try:
        svc.validate_mime(content_type)
    except VoiceError as exc:
        logger.warning("MIME validation failed: %s", exc)
        raise HTTPException(status_code=415, detail=str(exc))

    # Read audio bytes
    try:
        audio_bytes = await file.read()
    except Exception as exc:
        logger.exception("Failed to read uploaded audio")
        raise HTTPException(status_code=400, detail=f"Failed to read audio: {exc}")
    finally:
        await file.close()

    # Validate size after reading
    try:
        svc.validate_size(len(audio_bytes))
    except VoiceError as exc:
        logger.warning("Size validation failed: %s", exc)
        raise HTTPException(status_code=413, detail=str(exc))

    # Transcribe
    try:
        text = await svc.transcribe(audio_bytes, content_type, language=language)
    except VoiceError as exc:
        logger.warning("Transcription failed: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected transcription error")
        raise HTTPException(status_code=500, detail="Transcription failed. Please try again.")

    size_kb = len(audio_bytes) / 1024
    hint = "short clip" if size_kb < 200 else ("medium clip" if size_kb < 1000 else "long clip")

    return TranscribeResponse(text=text, duration_hint=hint)
