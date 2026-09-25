"""
Phase 3 — Backend test suite.

Tests:
  1.  Intent: explain_file detected for "Explain Login.jsx"
  2.  Intent: explain_file detected for "What does App.jsx do?"
  3.  Intent: summarize_file detected for "Summarize Dashboard.jsx"
  4.  Intent: explain_dependencies detected for "Explain dependencies of App.jsx"
  5.  Intent: project_overview detected for "Analyze project"
  6.  Intent: project_overview detected for "Give me a project overview"
  7.  Intent: unsupported for unrecognised input
  8.  File resolution: exact filename match
  9.  File resolution: case-insensitive match
  10. File resolution: extension-less match
  11. File resolution: missing file returns not-found
  12. File resolution: ambiguous reference returns candidates
  13. Missing Groq key: GroqService.is_configured() returns False
  14. Missing Groq key: complete() raises GroqError
  15. GET /api/assistant/status returns groq_configured=False when key absent
  16. POST /api/assistant/chat — intent classified without Groq (no key set)
  17. POST /api/assistant/chat — missing file reference handled
  18. POST /api/assistant/chat — path traversal in message rejected safely
  19. POST /api/assistant/chat — project_overview without Groq key
  20. POST /api/assistant/chat — file not found in project
"""
from __future__ import annotations

import sys
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.intent_classifier import classify, Intent, ClassificationResult
from app.services.file_resolver import FileResolver
from app.services.groq_service import GroqService, GroqError


# ─── Demo project tree fixture ────────────────────────────────────────────────

DEMO_TREE = [
    {
        "type": "directory", "name": "src", "path": "src",
        "children": [
            {
                "type": "directory", "name": "components", "path": "src/components",
                "children": [
                    {"type": "file", "name": "Navbar.jsx",    "path": "src/components/Navbar.jsx"},
                    {"type": "file", "name": "Login.jsx",     "path": "src/components/Login.jsx"},
                    {"type": "file", "name": "Dashboard.jsx", "path": "src/components/Dashboard.jsx"},
                ],
            },
            {"type": "file", "name": "App.jsx",  "path": "src/App.jsx"},
            {"type": "file", "name": "main.jsx", "path": "src/main.jsx"},
        ],
    },
    {"type": "file", "name": "package.json", "path": "package.json"},
]


# ─── Tests 1–7: Intent classification ────────────────────────────────────────

@pytest.mark.parametrize("text,expected_intent,expected_file", [
    ("Explain Login.jsx",                       Intent.EXPLAIN_FILE,         "Login.jsx"),
    ("What does App.jsx do?",                   Intent.EXPLAIN_FILE,         "App.jsx"),
    ("explain app.jsx",                         Intent.EXPLAIN_FILE,         "app.jsx"),
    ("Can you explain src/components/Login.jsx?", Intent.EXPLAIN_FILE,       "src/components/Login.jsx"),
    ("Summarize Dashboard.jsx",                 Intent.SUMMARIZE_FILE,       "Dashboard.jsx"),
    ("Give me a brief summary of main.jsx",     Intent.SUMMARIZE_FILE,       "main.jsx"),
    ("Explain dependencies of App.jsx",         Intent.EXPLAIN_DEPENDENCIES, "App.jsx"),
    ("What does App.jsx import?",               Intent.EXPLAIN_DEPENDENCIES, "App.jsx"),
    ("Analyze project",                         Intent.PROJECT_OVERVIEW,     None),
    ("Give me a project overview",              Intent.PROJECT_OVERVIEW,     None),
    ("What is this project?",                   Intent.PROJECT_OVERVIEW,     None),
    ("project summary",                         Intent.PROJECT_OVERVIEW,     None),
])
def test_intent_classification(text, expected_intent, expected_file):
    result = classify(text)
    assert result.intent == expected_intent, f"Input: {text!r} → got {result.intent}, expected {expected_intent}"
    if expected_file is not None:
        assert result.file_reference is not None
        assert expected_file.lower() in result.file_reference.lower()


def test_unsupported_intent():
    result = classify("hello there how are you")
    assert result.intent == Intent.UNSUPPORTED


def test_bare_filename_defaults_to_explain():
    result = classify("Login.jsx")
    assert result.intent == Intent.EXPLAIN_FILE
    assert result.file_reference == "Login.jsx"


# ─── Tests 8–12: File resolution ─────────────────────────────────────────────

def test_file_resolve_exact():
    resolver = FileResolver(DEMO_TREE)
    r = resolver.resolve("Login.jsx")
    assert r.found
    assert r.path == "src/components/Login.jsx"


def test_file_resolve_case_insensitive():
    resolver = FileResolver(DEMO_TREE)
    r = resolver.resolve("login.jsx")
    assert r.found
    assert "Login.jsx" in r.path


def test_file_resolve_extension_less():
    resolver = FileResolver(DEMO_TREE)
    r = resolver.resolve("Dashboard")
    assert r.found
    assert "Dashboard.jsx" in r.path


def test_file_resolve_partial_path():
    resolver = FileResolver(DEMO_TREE)
    r = resolver.resolve("components/Navbar.jsx")
    assert r.found
    assert r.path == "src/components/Navbar.jsx"


def test_file_resolve_not_found():
    resolver = FileResolver(DEMO_TREE)
    r = resolver.resolve("NonExistent.tsx")
    assert not r.found
    assert r.candidates == []
    assert "not found" in r.message.lower() or "no file" in r.message.lower()


def test_file_resolve_ambiguous():
    # Build a tree with two Login files at different paths
    tree = [
        {"type": "file", "name": "Login.jsx", "path": "src/Login.jsx"},
        {"type": "directory", "name": "pages", "path": "pages", "children": [
            {"type": "file", "name": "Login.jsx", "path": "pages/Login.jsx"},
        ]},
    ]
    resolver = FileResolver(tree)
    r = resolver.resolve("Login.jsx")
    assert not r.found
    assert len(r.candidates) == 2
    assert "Login.jsx" in r.message


# ─── Tests 13–14: GroqService configuration ──────────────────────────────────

def test_groq_not_configured_when_key_empty():
    svc = GroqService.__new__(GroqService)
    svc._key = ""
    svc._model = "llama-3.3-70b-versatile"
    assert svc.is_configured() is False


@pytest.mark.asyncio
async def test_groq_raises_when_key_missing():
    svc = GroqService.__new__(GroqService)
    svc._key = ""
    svc._model = "llama-3.3-70b-versatile"
    with pytest.raises(GroqError, match="GROQ_API_KEY"):
        await svc.complete("system", "user")


# ─── Tests 15–20: API endpoint tests ─────────────────────────────────────────

def test_assistant_status_no_key():
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/assistant/status")
    assert r.status_code == 200
    body = r.json()
    assert body["groq_configured"] is False
    assert "model" in body


def test_chat_missing_groq_key_returns_error_response():
    """With no API key, the chat endpoint should return an error message (not HTTP 500)."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/assistant/chat", json={"message": "Explain Login.jsx"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "explain_file"
    assert body["target_file"] == "src/components/Login.jsx"
    # Should return an error about the missing key, not a crash
    assert body["error"] is True
    assert "GROQ_API_KEY" in body["response"] or "api" in body["response"].lower()


def test_chat_missing_file_reference():
    """Requesting explain without a filename should get a helpful message."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/assistant/chat", json={"message": "Explain the file please"})
    assert r.status_code == 200
    body = r.json()
    # Should either be unsupported intent or explain_file with error
    assert body["intent"] in ("explain_file", "unsupported")


def test_chat_path_traversal_in_message():
    """A traversal attempt in the message should not expose server files."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/assistant/chat", json={"message": "Explain ../../etc/passwd"})
    assert r.status_code == 200
    body = r.json()
    # Either not found or error — must NOT return file contents
    assert body.get("error") is True or "not found" in body.get("response", "").lower()
    assert "root:x" not in body.get("response", "")


def test_chat_file_not_in_project():
    """Asking about a file that doesn't exist in the project returns a helpful message."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/assistant/chat", json={"message": "Explain GhostFile.tsx"})
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is True or body["target_file"] is None
    assert "not found" in body["response"].lower() or "GhostFile" in body["response"]


def test_chat_project_overview_no_key():
    """Project overview with no key returns a Groq error, not a crash."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/assistant/chat", json={"message": "Give me a project overview"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "project_overview"
    assert body["error"] is True


# ─── Async test helper ────────────────────────────────────────────────────────

def pytest_configure(config):
    """Register asyncio mode if pytest-asyncio is available."""
    pass
