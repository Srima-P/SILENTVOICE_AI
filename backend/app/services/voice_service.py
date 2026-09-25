"""
VoiceService — Phase 5 speech-to-text integration.

Uses Groq's Whisper API (whisper-large-v3-turbo) to transcribe audio.

Responsibilities:
  • Accept audio bytes + MIME type
  • Validate file size and MIME type
  • Send audio securely to Groq Whisper
  • Return plain-text transcript
  • Handle all API/network errors without exposing keys or traces

Security:
  • API key read from settings only (never from request)
  • No audio permanently stored — bytes discarded after response
  • All errors surfaced as VoiceError (safe strings only)
"""
from __future__ import annotations

import io
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger("silentvoice.voice")

# Groq Whisper endpoint (OpenAI-compatible)
GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

# Hard limits
MAX_AUDIO_BYTES = 25 * 1024 * 1024   # 25 MB — Groq's documented limit
_TIMEOUT = 60.0

# Accepted MIME types → file extension the API expects
_ALLOWED_MIME: dict[str, str] = {
    "audio/webm":  "audio.webm",
    "audio/ogg":   "audio.ogg",
    "audio/mpeg":  "audio.mp3",
    "audio/mp4":   "audio.mp4",
    "audio/wav":   "audio.wav",
    "audio/x-wav": "audio.wav",
    "audio/flac":  "audio.flac",
    "audio/x-m4a": "audio.m4a",
    # Browsers often report these during MediaRecorder output
    "audio/webm;codecs=opus": "audio.webm",
    "audio/ogg;codecs=opus":  "audio.ogg",
}


class VoiceError(Exception):
    """Raised when transcription fails for a known, reportable reason."""


class VoiceService:
    """
    Transcribes audio using Groq Whisper.

    Usage:
        svc = VoiceService()
        transcript = await svc.transcribe(audio_bytes, "audio/webm")
    """

    def __init__(self) -> None:
        self._key: str = settings.groq_api_key
        self._model: str = "whisper-large-v3-turbo"

    def is_configured(self) -> bool:
        return bool(self._key and self._key.strip())

    @staticmethod
    def validate_mime(content_type: str) -> str:
        """
        Return the canonical filename extension for the given MIME type,
        or raise VoiceError if unsupported.

        The content_type may include codec qualifiers (e.g. 'audio/webm;codecs=opus').
        """
        # normalise: strip params, lowercase
        base = content_type.split(";")[0].strip().lower()
        full = content_type.strip().lower()

        # Try full string first (e.g. 'audio/webm;codecs=opus'), then base
        filename = _ALLOWED_MIME.get(full) or _ALLOWED_MIME.get(base)
        if not filename:
            supported = ", ".join(sorted({k.split(";")[0] for k in _ALLOWED_MIME}))
            raise VoiceError(
                f"Unsupported audio type '{base}'. "
                f"Supported: {supported}"
            )
        return filename

    @staticmethod
    def validate_size(size_bytes: int) -> None:
        """Raise VoiceError if audio exceeds the hard limit."""
        if size_bytes > MAX_AUDIO_BYTES:
            mb = size_bytes / (1024 * 1024)
            limit_mb = MAX_AUDIO_BYTES / (1024 * 1024)
            raise VoiceError(
                f"Audio file is too large ({mb:.1f} MB). "
                f"Maximum allowed is {limit_mb:.0f} MB."
            )

    async def transcribe(
        self,
        audio_bytes: bytes,
        content_type: str,
        language: Optional[str] = None,
    ) -> str:
        """
        Transcribe audio bytes using Groq Whisper.

        Args:
            audio_bytes:   Raw audio data.
            content_type:  MIME type reported by the client.
            language:      Optional ISO-639-1 language hint (e.g. 'en').

        Returns:
            The transcribed text string.

        Raises:
            VoiceError: On validation failure, API error, or empty transcript.
        """
        if not self.is_configured():
            raise VoiceError(
                "GROQ_API_KEY is not set. Add your key to .env to enable voice features."
            )

        # Validate before touching the network
        filename = self.validate_mime(content_type)
        self.validate_size(len(audio_bytes))

        if len(audio_bytes) == 0:
            raise VoiceError("Empty audio received — nothing to transcribe.")

        headers = {
            "Authorization": f"Bearer {self._key}",
        }

        # Build multipart form — Groq expects the file as 'file' field
        files = {"file": (filename, io.BytesIO(audio_bytes), content_type)}
        data = {"model": self._model}
        if language:
            data["language"] = language

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    GROQ_WHISPER_URL,
                    headers=headers,
                    files=files,
                    data=data,
                )
        except httpx.TimeoutException:
            raise VoiceError("Transcription request timed out. Please try again.")
        except httpx.RequestError as exc:
            raise VoiceError(f"Network error contacting Groq: {exc}") from exc

        if response.status_code == 401:
            raise VoiceError("Invalid GROQ_API_KEY. Check your .env file.")
        if response.status_code == 429:
            raise VoiceError("Groq rate limit reached. Please wait a moment and try again.")
        if response.status_code == 413:
            raise VoiceError("Audio file was too large for the Groq API.")
        if response.status_code >= 500:
            raise VoiceError(f"Groq service error (HTTP {response.status_code}). Try again shortly.")
        if not response.is_success:
            try:
                detail = response.json().get("error", {}).get("message", response.text[:200])
            except Exception:
                detail = response.text[:200]
            raise VoiceError(f"Groq API error (HTTP {response.status_code}): {detail}")

        try:
            text = response.json().get("text", "").strip()
            print("TRANSCRIPT:", text)
        except Exception as exc:
            raise VoiceError(f"Unexpected response format from Groq: {exc}") from exc

        if not text:
            raise VoiceError(
                "No speech detected in the audio. "
                "Please speak clearly and try again."
            )

        logger.info("Transcription complete: %d chars", len(text))
        return text
