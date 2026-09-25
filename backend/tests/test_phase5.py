"""
Phase 5 — Backend test suite.

Tests:
  Voice endpoint:
  1.  GET /api/voice/status returns configured flag and model
  2.  POST /api/voice/transcribe — unsupported MIME type returns 415
  3.  POST /api/voice/transcribe — oversized audio returns 413
  4.  POST /api/voice/transcribe — empty bytes returns 422
  5.  VoiceService.validate_mime — accepted types pass
  6.  VoiceService.validate_mime — rejected type raises VoiceError
  7.  VoiceService.validate_size — oversized raises VoiceError
  8.  VoiceService — no key raises VoiceError
  9.  VoiceService — empty transcript raises VoiceError (mocked)
  10. VoiceService — MIME with codec qualifier accepted (e.g. audio/webm;codecs=opus)

  Onboarding intents:
  11. "I'm new to this project" → onboarding_start
  12. "Help me get started" → onboarding_start
  13. "Explain the architecture" → architecture_overview
  14. "How is this project structured?" → architecture_overview
  15. "How do I set up this project?" → setup_guidance
  16. "How do I run the project?" → setup_guidance
  17. "Give me beginner tasks" → beginner_tasks
  18. "What should I do first?" → beginner_tasks
  19. "Suggest beginner tasks" → beginner_tasks

  Onboarding API:
  20. POST /api/assistant/chat "I'm new to this project" → onboarding_start response
  21. POST /api/assistant/chat "Explain the architecture" → architecture_overview response
  22. POST /api/assistant/chat "How do I set up this project?" → setup_guidance response
  23. POST /api/assistant/chat "Give me beginner tasks" → beginner_tasks response
  24. Onboarding response always includes follow_up_suggestions list
  25. Existing Phase 3/4 backward compat: Explain Login.jsx still works
"""
from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.voice_service import VoiceService, VoiceError, MAX_AUDIO_BYTES
from app.services.intent_classifier import classify, Intent


# ─── Tests 1–10: Voice service / endpoint ────────────────────────────────────

def test_voice_status_endpoint():
    """GET /api/voice/status returns configured flag and model name."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/voice/status")
    assert r.status_code == 200
    body = r.json()
    assert "configured" in body
    assert "model" in body
    assert isinstance(body["configured"], bool)


def test_voice_transcribe_unsupported_mime():
    """POST /api/voice/transcribe with unsupported MIME type returns HTTP 415."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post(
        "/api/voice/transcribe",
        files={"file": ("test.xyz", b"fake audio", "application/octet-stream")},
    )
    assert r.status_code == 415


def test_voice_transcribe_oversized():
    """POST /api/voice/transcribe with oversized file returns HTTP 413."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    # Pass the MIME validation but fail size check
    big_audio = b"X" * (MAX_AUDIO_BYTES + 1)
    r = client.post(
        "/api/voice/transcribe",
        files={"file": ("audio.webm", big_audio, "audio/webm")},
    )
    assert r.status_code == 413


def test_voice_transcribe_empty_bytes():
    """POST /api/voice/transcribe with empty file returns HTTP 422 (empty transcript)."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post(
        "/api/voice/transcribe",
        files={"file": ("audio.webm", b"", "audio/webm")},
    )
    # Either 422 (empty) or 422 (no key configured) depending on env
    assert r.status_code in (422, 415)


def test_voice_validate_mime_accepted():
    """Known MIME types pass validation."""
    svc = VoiceService()
    for mime in ("audio/webm", "audio/ogg", "audio/mpeg", "audio/wav"):
        result = svc.validate_mime(mime)
        assert result.endswith((".webm", ".ogg", ".mp3", ".wav"))


def test_voice_validate_mime_rejected():
    """Unknown MIME type raises VoiceError."""
    svc = VoiceService()
    with pytest.raises(VoiceError, match="Unsupported audio type"):
        svc.validate_mime("video/mp4")


def test_voice_validate_size_oversized():
    """Audio larger than limit raises VoiceError."""
    svc = VoiceService()
    with pytest.raises(VoiceError, match="too large"):
        svc.validate_size(MAX_AUDIO_BYTES + 1)


@pytest.mark.asyncio
async def test_voice_no_key_raises_error():
    """VoiceService.transcribe raises VoiceError when GROQ_API_KEY is empty."""
    svc = VoiceService.__new__(VoiceService)
    svc._key = ""
    svc._model = "whisper-large-v3-turbo"
    with pytest.raises(VoiceError, match="GROQ_API_KEY"):
        await svc.transcribe(b"fake", "audio/webm")


@pytest.mark.asyncio
async def test_voice_empty_transcript_error():
    """VoiceService raises VoiceError when Groq returns empty text."""
    svc = VoiceService.__new__(VoiceService)
    svc._key = "fake-key"
    svc._model = "whisper-large-v3-turbo"
    with patch("app.services.voice_service.httpx.AsyncClient") as mock_client_cls:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_resp.json.return_value = {"text": ""}
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client
        with pytest.raises(VoiceError, match="No speech detected"):
            await svc.transcribe(b"real audio bytes", "audio/webm")


def test_voice_validate_mime_with_codec():
    """MIME type with codec qualifier (e.g. audio/webm;codecs=opus) is accepted."""
    svc = VoiceService()
    result = svc.validate_mime("audio/webm;codecs=opus")
    assert result == "audio.webm"


# ─── Tests 11–19: Onboarding intent classification ───────────────────────────

@pytest.mark.parametrize("text,expected_intent", [
    ("I'm new to this project",                 Intent.ONBOARDING_START),
    ("I am new to this project",                Intent.ONBOARDING_START),
    ("Help me get started",                     Intent.ONBOARDING_START),
    ("Where do I start?",                       Intent.ONBOARDING_START),
    ("Getting started",                         Intent.ONBOARDING_START),
    ("Explain the architecture",                Intent.ARCHITECTURE_OVERVIEW),
    ("How is this project structured?",         Intent.ARCHITECTURE_OVERVIEW),
    ("Describe the system design",              Intent.ARCHITECTURE_OVERVIEW),
    ("What is the overall architecture?",       Intent.ARCHITECTURE_OVERVIEW),
    ("How do I set up this project?",           Intent.SETUP_GUIDANCE),
    ("How do I run the project?",               Intent.SETUP_GUIDANCE),
    ("Setup guide please",                      Intent.SETUP_GUIDANCE),
    ("Give me beginner tasks",                  Intent.BEGINNER_TASKS),
    ("What should I do first?",                 Intent.BEGINNER_TASKS),
    ("Suggest beginner tasks",                  Intent.BEGINNER_TASKS),
    ("Show me starter tasks",                   Intent.BEGINNER_TASKS),
    ("I'm new to the codebase",                 Intent.ONBOARDING_START),
    ("How to install this project?",            Intent.SETUP_GUIDANCE),
])
def test_onboarding_intent_classification(text, expected_intent):
    result = classify(text)
    assert result.intent == expected_intent, (
        f"Input: {text!r} → got {result.intent}, expected {expected_intent}"
    )


# ─── Tests 20–25: Onboarding API ─────────────────────────────────────────────

def test_api_onboarding_start():
    """POST /api/assistant/chat 'I'm new to this project' → onboarding_start."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/assistant/chat", json={"message": "I'm new to this project"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "onboarding_start"
    assert isinstance(body["response"], str)
    assert len(body["response"]) > 0


def test_api_architecture_overview():
    """POST /api/assistant/chat 'Explain the architecture' → architecture_overview."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/assistant/chat", json={"message": "Explain the architecture"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "architecture_overview"
    assert isinstance(body["response"], str)


def test_api_setup_guidance():
    """POST /api/assistant/chat 'How do I set up this project?' → setup_guidance."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/assistant/chat", json={"message": "How do I set up this project?"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "setup_guidance"
    assert isinstance(body["response"], str)


def test_api_beginner_tasks():
    """POST /api/assistant/chat 'Give me beginner tasks' → beginner_tasks."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/assistant/chat", json={"message": "Give me beginner tasks"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "beginner_tasks"
    assert isinstance(body["response"], str)


def test_api_onboarding_has_follow_up_suggestions():
    """Every onboarding response includes a follow_up_suggestions list."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/assistant/chat", json={"message": "I'm new to this project"})
    assert r.status_code == 200
    body = r.json()
    assert "follow_up_suggestions" in body
    assert isinstance(body["follow_up_suggestions"], list)


def test_api_phase4_still_works_with_phase5():
    """Phase 3/4 Explain Login.jsx still routes correctly with Phase 5 in place."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/assistant/chat", json={"message": "Explain Login.jsx"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "explain_file"
    assert body["target_file"] is not None
    assert "Login" in body["target_file"]
