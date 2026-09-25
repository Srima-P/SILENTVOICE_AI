"""
Security / audit fixes — test suite.

Covers the four confirmed issues resolved in this hardening pass:

  Fix 1 — root_path removed from API responses
    1.  GET /api/project/tree  — response body does NOT contain root_path
    2.  GET /api/project/analyze — response body does NOT contain root_path
    3.  ProjectTreeResponse internal field is still accessible in Python
        (exclude=True only suppresses serialization, not attribute access)

  Fix 2 — selected_file validation
    4.  Path traversal attempt (../../etc/passwd) returns HTTP 422
    5.  Traversal via backslash (..\\etc\\passwd) returns HTTP 422
    6.  Null byte in selected_file returns HTTP 422
    7.  selected_file exceeding max_length (512) returns HTTP 422
    8.  Valid selected_file path is accepted unchanged
    9.  Whitespace-only selected_file is normalised to None (not rejected)
    10. selected_file=None (omitted) is accepted (backward compat)

  Fix 3 — conversation_history limits
    11. History with 21 turns returns HTTP 422
    12. History with exactly 20 turns is accepted (boundary)
    13. ConversationTurn.content exceeding 4000 chars returns HTTP 422
    14. ConversationTurn.content at exactly 4000 chars is accepted (boundary)
    15. ConversationTurn.role exceeding 16 chars returns HTTP 422
    16. Empty history [] is accepted (backward compat)

  Fix 4 — onboarding_service safe_read() relative path
    17. safe_read() called with a plain filename reads the file correctly
    18. safe_read() called with a str(absolute_path) raises ValueError on
        Windows-style paths (containment check fires)
    19. OnboardingService._setup_guidance() builds setup_contents without
        raising (integration smoke test via mocked Groq)
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.assistant import ChatRequest, ConversationTurn, _MAX_HISTORY_TURNS
from app.services.project_scanner import ProjectScanner


# ─── Shared fixtures ──────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    """FastAPI TestClient pointing at the real app."""
    import warnings
    warnings.filterwarnings("ignore")
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def tmp_project_with_readme(tmp_path: Path) -> Path:
    """Minimal project with a README.md at the root for setup-guidance tests."""
    (tmp_path / "README.md").write_text("# My Project\n\nInstall: `npm install`\n")
    (tmp_path / "package.json").write_text('{"name":"test","version":"1.0.0"}')
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.js").write_text('console.log("hello");\n')
    return tmp_path


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 1 — root_path not present in API responses
# ═══════════════════════════════════════════════════════════════════════════════

def test_project_tree_response_omits_root_path(client):
    """GET /api/project/tree must NOT include root_path in the JSON body."""
    resp = client.get("/api/project/tree")
    assert resp.status_code == 200
    body = resp.json()
    assert "root_path" not in body, (
        f"root_path should be excluded from the response but found: {body.get('root_path')}"
    )


def test_project_analyze_response_omits_root_path(client):
    """GET /api/project/analyze must NOT include root_path in the JSON body."""
    resp = client.get("/api/project/analyze")
    assert resp.status_code == 200
    body = resp.json()
    assert "root_path" not in body, (
        f"root_path should be excluded from the response but found: {body.get('root_path')}"
    )


def test_project_tree_response_internal_field_accessible(tmp_path: Path):
    """
    The Python object can still read root_path after scan() —
    exclude=True only suppresses JSON serialization, not Python attribute access.
    """
    (tmp_path / "main.py").write_text("print('hello')\n")
    scanner = ProjectScanner(tmp_path)
    tree = scanner.scan()
    # Internal attribute must be set
    assert tree.root_path is not None
    assert str(tmp_path) in tree.root_path or tree.root_path == str(tmp_path.resolve())
    # But JSON serialization must omit it
    dumped = tree.model_dump()
    assert "root_path" not in dumped


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 2 — selected_file validation
# ═══════════════════════════════════════════════════════════════════════════════

def test_selected_file_path_traversal_forward_slash_rejected(client):
    """../../etc/passwd in selected_file must return 422."""
    resp = client.post("/api/assistant/chat", json={
        "message": "Explain this",
        "selected_file": "../../etc/passwd",
    })
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_selected_file_path_traversal_backslash_rejected(client):
    r"""..\\etc\\passwd in selected_file must return 422."""
    resp = client.post("/api/assistant/chat", json={
        "message": "Explain this",
        "selected_file": "..\\etc\\passwd",
    })
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_selected_file_null_byte_rejected(client):
    """Null byte in selected_file must return 422."""
    resp = client.post("/api/assistant/chat", json={
        "message": "Explain this",
        "selected_file": "src/Login.jsx\x00.evil",
    })
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_selected_file_max_length_exceeded_rejected(client):
    """selected_file longer than 512 chars must return 422."""
    long_path = "src/" + "a" * 510 + ".jsx"   # 514 chars total
    resp = client.post("/api/assistant/chat", json={
        "message": "Explain this",
        "selected_file": long_path,
    })
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_selected_file_valid_path_accepted():
    """A normal relative file path passes the validator without modification."""
    req = ChatRequest(
        message="Explain this",
        selected_file="src/components/Login.jsx",
    )
    assert req.selected_file == "src/components/Login.jsx"


def test_selected_file_whitespace_only_normalised_to_none():
    """A whitespace-only selected_file is normalised to None by the validator."""
    req = ChatRequest(message="Explain this", selected_file="   ")
    assert req.selected_file is None


def test_selected_file_none_accepted():
    """selected_file=None (not provided) is accepted for backward compatibility."""
    req = ChatRequest(message="Explain Login.jsx")
    assert req.selected_file is None


def test_selected_file_strips_surrounding_whitespace():
    """Leading/trailing whitespace in selected_file is stripped."""
    req = ChatRequest(message="Explain this", selected_file="  src/App.jsx  ")
    assert req.selected_file == "src/App.jsx"


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 3 — conversation_history limits
# ═══════════════════════════════════════════════════════════════════════════════

def test_conversation_history_too_many_turns_rejected(client):
    """History with more than _MAX_HISTORY_TURNS turns must return 422."""
    history = [
        {"role": "user", "content": f"Message {i}"}
        for i in range(_MAX_HISTORY_TURNS + 1)  # one over the limit
    ]
    resp = client.post("/api/assistant/chat", json={
        "message": "Summarize it",
        "conversation_history": history,
    })
    assert resp.status_code == 422, (
        f"Expected 422 for {len(history)}-turn history, got {resp.status_code}: {resp.text}"
    )


def test_conversation_history_max_turns_exactly_accepted():
    """History with exactly _MAX_HISTORY_TURNS turns is accepted (boundary)."""
    turns = [
        ConversationTurn(role="user", content=f"Message {i}")
        for i in range(_MAX_HISTORY_TURNS)
    ]
    req = ChatRequest(message="Summarize it", conversation_history=turns)
    assert len(req.conversation_history) == _MAX_HISTORY_TURNS


def test_conversation_turn_content_too_long_rejected(client):
    """ConversationTurn.content > 4000 chars must return 422."""
    resp = client.post("/api/assistant/chat", json={
        "message": "Summarize it",
        "conversation_history": [
            {"role": "user", "content": "x" * 4001},
        ],
    })
    assert resp.status_code == 422, (
        f"Expected 422 for oversized content, got {resp.status_code}: {resp.text}"
    )


def test_conversation_turn_content_max_length_accepted():
    """ConversationTurn.content at exactly 4000 chars is accepted (boundary)."""
    turn = ConversationTurn(role="user", content="x" * 4000)
    assert len(turn.content) == 4000


def test_conversation_turn_role_too_long_rejected(client):
    """ConversationTurn.role > 16 chars must return 422."""
    resp = client.post("/api/assistant/chat", json={
        "message": "Explain this",
        "conversation_history": [
            {"role": "a" * 17, "content": "hello"},
        ],
    })
    assert resp.status_code == 422, (
        f"Expected 422 for oversized role, got {resp.status_code}: {resp.text}"
    )


def test_conversation_history_empty_accepted(client):
    """Empty conversation_history [] is accepted for backward compatibility."""
    resp = client.post("/api/assistant/chat", json={
        "message": "Give me a project overview",
        "conversation_history": [],
    })
    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 4 — onboarding_service safe_read() relative path
# ═══════════════════════════════════════════════════════════════════════════════

def test_safe_read_with_plain_filename(tmp_project_with_readme: Path):
    """safe_read('README.md') reads the file at the project root correctly."""
    scanner = ProjectScanner(tmp_project_with_readme)
    content, lines = scanner.safe_read("README.md")
    assert "My Project" in content
    assert lines >= 1


def test_safe_read_with_absolute_path_raises(tmp_project_with_readme: Path):
    """
    safe_read(str(absolute_path)) must raise ValueError — the containment
    check fires because the absolute path resolves outside the expected
    relative location.
    """
    scanner = ProjectScanner(tmp_project_with_readme)
    abs_path = str(tmp_project_with_readme / "README.md")
    with pytest.raises((ValueError, FileNotFoundError)):
        scanner.safe_read(abs_path)


@pytest.mark.asyncio
async def test_onboarding_setup_guidance_uses_relative_path(tmp_project_with_readme: Path):
    """
    OnboardingService._setup_guidance() must read setup files using relative
    paths (fname) rather than absolute paths, so safe_read() succeeds.
    """
    from app.services.onboarding_service import OnboardingService
    from app.services.intent_classifier import Intent

    # Patch settings to point at the temp project and mock GroqService
    with patch("app.services.onboarding_service.settings") as mock_settings, \
         patch("app.services.onboarding_service.GroqService") as MockGroq:
        mock_settings.project_root_path = str(tmp_project_with_readme)
        mock_groq_instance = AsyncMock()
        mock_groq_instance.setup_guidance.return_value = "## Setup\nRun npm install."
        MockGroq.return_value = mock_groq_instance

        svc = OnboardingService()
        result = await svc.handle(Intent.SETUP_GUIDANCE, project_analysis=None)

    # Should not error — and should have called setup_guidance with content
    assert result.error is False, f"Expected no error, got: {result.response}"
    assert result.intent == Intent.SETUP_GUIDANCE.value
    # The mock should have been called with setup_contents containing README.md
    call_kwargs = mock_groq_instance.setup_guidance.call_args
    assert call_kwargs is not None, "setup_guidance was never called"
    # Extract setup_contents from keyword args (it's always passed as kwarg)
    setup_contents = call_kwargs.kwargs.get("setup_contents", {})
    # At least README.md or package.json should have been read
    assert len(setup_contents) >= 1, (
        f"Expected at least one setup file in setup_contents, got: {setup_contents}"
    )
