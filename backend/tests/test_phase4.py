"""
Phase 4 — Backend test suite.

Tests:
  1.  ConversationManager — resolves from explicit file ref
  2.  ConversationManager — resolves from selected_file when no explicit ref
  3.  ConversationManager — resolves from conversation history (memory)
  4.  ConversationManager — returns none when no context available
  5.  ConversationManager — does not use memory without a referback pronoun
  6.  ConversationManager — extracts second file reference for relationship queries
  7.  IntentClassifier — FIND_DEPENDENTS detected for "Which files depend on App.jsx?"
  8.  IntentClassifier — FIND_DEPENDENTS detected for "Who imports Login.jsx?"
  9.  IntentClassifier — EXPLAIN_RELATIONSHIP detected for "How does Login.jsx connect to App.jsx?"
  10. IntentClassifier — SHOW_RELATED detected for "Show related components"
  11. IntentClassifier — follow-up "summarize it" → SUMMARIZE_FILE (no file ref)
  12. IntentClassifier — follow-up "what are its dependencies?" → EXPLAIN_DEPENDENCIES
  13. IntentClassifier — follow-up "explain it simply" → SUMMARIZE_FILE
  14. API — POST /chat with selected_file resolves context from selected file
  15. API — POST /chat with conversation_history resolves context from memory
  16. API — POST /chat for find_dependents intent returns structured response
  17. API — POST /chat always contains follow_up_suggestions list
  18. API — POST /chat for show_related returns non-error response
  19. API — POST /chat backward compat: plain {message} still works (no context fields)
  20. ExplanationService — reverse dependency lookup returns correct files
"""
from __future__ import annotations

import sys
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.intent_classifier import classify, Intent
from app.services.conversation_manager import (
    ConversationManager,
    _extract_last_mentioned_file,
    _has_referback,
)
from app.schemas.assistant import ConversationTurn
from app.services.explanation_service import _reverse_deps


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


# ─── Tests 1–6: ConversationManager ──────────────────────────────────────────

def test_context_resolve_explicit_file_ref():
    """Explicit file reference in message takes highest priority."""
    manager = ConversationManager(DEMO_TREE)
    ctx = manager.resolve_context(
        message="Explain Login.jsx",
        selected_file="src/App.jsx",
        conversation_history=[],
    )
    assert ctx.context_source == "explicit"
    assert ctx.resolved_file is not None
    assert "Login.jsx" in ctx.resolved_file


def test_context_resolve_selected_file():
    """selected_file is used when no explicit ref in message."""
    manager = ConversationManager(DEMO_TREE)
    ctx = manager.resolve_context(
        message="Explain this",
        selected_file="src/App.jsx",
        conversation_history=[],
    )
    assert ctx.context_source == "selected"
    assert ctx.resolved_file == "src/App.jsx"


def test_context_resolve_conversation_memory():
    """Last file in conversation history is used when message has a referback pronoun."""
    manager = ConversationManager(DEMO_TREE)
    history = [
        ConversationTurn(role="user", content="Explain Login.jsx"),
        ConversationTurn(
            role="assistant",
            content="The file `src/components/Login.jsx` handles authentication.",
        ),
    ]
    ctx = manager.resolve_context(
        message="What are its dependencies?",
        selected_file=None,
        conversation_history=history,
    )
    assert ctx.context_source == "memory"
    assert ctx.resolved_file is not None
    assert "Login.jsx" in ctx.resolved_file


def test_context_resolve_none_when_no_context():
    """Returns context_source=none when nothing is available."""
    manager = ConversationManager(DEMO_TREE)
    ctx = manager.resolve_context(
        message="Hello how are you",
        selected_file=None,
        conversation_history=[],
    )
    assert ctx.context_source == "none"
    assert ctx.resolved_file is None


def test_context_memory_requires_referback_pronoun():
    """Memory is NOT used when the message does not contain a referback pronoun."""
    manager = ConversationManager(DEMO_TREE)
    history = [
        ConversationTurn(role="assistant", content="Here is info about `src/App.jsx`."),
    ]
    # "Give me a project overview" has no pronoun referring to a prior file
    ctx = manager.resolve_context(
        message="Give me a project overview",
        selected_file=None,
        conversation_history=history,
    )
    assert ctx.context_source == "none"


def test_context_extract_second_file():
    """extract_second_file returns the second file reference in a relationship query."""
    manager = ConversationManager(DEMO_TREE)
    second = manager.extract_second_file("How does Login.jsx connect to App.jsx?")
    assert second is not None
    assert "App.jsx" in second


# ─── Tests 7–13: Phase 4 intent classification ───────────────────────────────

@pytest.mark.parametrize("text,expected_intent,expected_file", [
    ("Which files depend on App.jsx?",      Intent.FIND_DEPENDENTS,      "App.jsx"),
    ("Who imports Login.jsx?",              Intent.FIND_DEPENDENTS,      "Login.jsx"),
    ("What uses Dashboard.jsx?",            Intent.FIND_DEPENDENTS,      "Dashboard.jsx"),
    ("Files that import Login.jsx",         Intent.FIND_DEPENDENTS,      "Login.jsx"),
    ("How does Login.jsx connect to App.jsx?", Intent.EXPLAIN_RELATIONSHIP, "Login.jsx"),
    ("Relationship between Navbar.jsx and App.jsx", Intent.EXPLAIN_RELATIONSHIP, "Navbar.jsx"),
    ("Show related components",             Intent.SHOW_RELATED,         None),
    ("Find related files",                  Intent.SHOW_RELATED,         None),
    ("What else is related to this?",       Intent.SHOW_RELATED,         None),
])
def test_phase4_intent_classification(text, expected_intent, expected_file):
    result = classify(text)
    assert result.intent == expected_intent, (
        f"Input: {text!r} → got {result.intent}, expected {expected_intent}"
    )
    if expected_file is not None:
        assert result.file_reference is not None
        assert expected_file.lower() in result.file_reference.lower()


def test_followup_summarize_it():
    """'summarize it' with no file ref → SUMMARIZE_FILE with file_reference=None."""
    result = classify("summarize it")
    assert result.intent == Intent.SUMMARIZE_FILE
    assert result.file_reference is None


def test_followup_what_are_its_dependencies():
    """'what are its dependencies?' → EXPLAIN_DEPENDENCIES with no file ref."""
    result = classify("what are its dependencies?")
    assert result.intent == Intent.EXPLAIN_DEPENDENCIES
    assert result.file_reference is None


def test_followup_explain_simply():
    """'explain it simply' → SUMMARIZE_FILE (treated as simple explanation)."""
    result = classify("explain it simply")
    assert result.intent == Intent.SUMMARIZE_FILE


# ─── Test 20: reverse dependency helper ──────────────────────────────────────

def test_reverse_deps_finds_correct_files():
    dep_entries = {
        "src/App.jsx":  ["src/components/Login.jsx", "src/components/Navbar.jsx"],
        "src/main.jsx": ["src/App.jsx"],
        "src/components/Navbar.jsx": [],
    }
    result = _reverse_deps("src/components/Login.jsx", dep_entries)
    assert result == ["src/App.jsx"]


def test_reverse_deps_by_filename():
    """Reverse dep lookup also matches by filename (without full path)."""
    dep_entries = {
        "src/App.jsx": ["src/components/Login.jsx"],
        "src/main.jsx": ["src/App.jsx"],
    }
    result = _reverse_deps("Login.jsx", dep_entries)
    assert "src/App.jsx" in result


def test_reverse_deps_empty_when_not_imported():
    dep_entries = {
        "src/App.jsx": ["src/components/Navbar.jsx"],
    }
    result = _reverse_deps("src/components/Login.jsx", dep_entries)
    assert result == []


# ─── Tests 14–19: API endpoint tests ─────────────────────────────────────────

def test_api_chat_with_selected_file_context():
    """selected_file in request body is used to resolve context."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    # "Explain this" has no explicit file ref; backend must use selected_file
    r = client.post("/api/assistant/chat", json={
        "message": "Explain this",
        "selected_file": "src/components/Login.jsx",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] in ("explain_file", "summarize_file")
    # context_source should reflect selected file resolution
    assert body["context_source"] in ("selected", "explicit")


def test_api_chat_with_conversation_history():
    """conversation_history is used to resolve file from memory when 'it' is used."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/assistant/chat", json={
        "message": "Summarize it",
        "conversation_history": [
            {"role": "user", "content": "Explain Login.jsx"},
            {"role": "assistant", "content": "The file `src/components/Login.jsx` handles login."},
        ],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "summarize_file"
    # Should resolve from memory
    assert body["context_source"] in ("memory", "explicit", "selected")


def test_api_chat_find_dependents_returns_response():
    """find_dependents intent produces a structured non-500 response."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/assistant/chat", json={
        "message": "Which files depend on Login.jsx?",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "find_dependents"
    assert "response" in body
    assert isinstance(body["response"], str)
    assert len(body["response"]) > 0


def test_api_chat_always_has_follow_up_suggestions():
    """Every successful assistant response includes a follow_up_suggestions list."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/assistant/chat", json={"message": "Give me a project overview"})
    assert r.status_code == 200
    body = r.json()
    assert "follow_up_suggestions" in body
    assert isinstance(body["follow_up_suggestions"], list)


def test_api_chat_show_related_returns_response():
    """show_related intent does not crash and returns a response."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/assistant/chat", json={
        "message": "Show related components",
        "selected_file": "src/components/Login.jsx",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "show_related"
    assert isinstance(body["response"], str)


def test_api_chat_backward_compat_plain_message():
    """Existing clients sending only {message} still work (no context fields required)."""
    import warnings; warnings.filterwarnings('ignore')
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/assistant/chat", json={"message": "Explain Login.jsx"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "explain_file"
    # follow_up_suggestions and context_source must always be present
    assert "follow_up_suggestions" in body
    assert "context_source" in body
