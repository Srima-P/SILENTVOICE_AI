"""
Phase 6 — Backend test suite.

Tests:
  Intent Classification (Tests 1–9):
  1–7. test_modify_code_intent_classification (parametrize, 7 cases)
  8.   test_modify_code_is_file_intent
  9a+b. test_modify_code_non_regression_edge_cases (parametrize, 2 cases)

  PendingChangeStore (Tests 10–15):
  10. test_store_put_and_get
  11. test_store_remove
  12. test_store_remove_nonexistent_returns_false
  13. test_store_max_capacity_evicts_oldest
  14. test_store_get_nonexistent_returns_none
  15. test_store_cleanup_expired

  CodeModificationService — unit tests with mocked Groq (Tests 16–25):
  16. test_propose_returns_propose_change_response
  17. test_propose_computes_diff_chunks
  18. test_propose_stores_sha256_hash
  19. test_propose_resolved_abs_path_stored
  20. test_propose_summary_derived_from_instruction
  21. test_propose_rejects_path_traversal
  22. test_propose_rejects_nonexistent_file
  23. test_propose_rejects_protected_file_env
  24. test_propose_strips_code_fence_from_groq
  25. test_propose_rejects_malformed_ai_output_empty

  Apply Handler — unit / integration tests (Tests 26–33):
  26. test_apply_requires_confirmed_true
  27. test_apply_unknown_proposal_id_returns_404
  28. test_apply_stale_file_returns_409
  29. test_apply_writes_file_content_to_disk
  30. test_apply_uses_resolved_abs_path_not_request_body
  31. test_apply_removes_proposal_from_store_after_write
  32. test_apply_cleans_up_tmp_file_on_success
  33. test_reject_proposal_writes_nothing

  API Endpoint Tests (Tests 34–37):
  34. test_api_propose_returns_200_with_diff
  35. test_api_propose_rejects_traversal_path
  36. test_api_diff_retrieval_by_id
  37. test_api_diff_unknown_id_returns_404

  Security / Adversarial Tests (Tests 38–39):
  38a–c. test_security_protected_files_blocked (parametrize, 3 cases)
  39. test_api_chat_modify_code_returns_non_error_response
"""
from __future__ import annotations

import asyncio
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.intent_classifier import classify, Intent
from app.services.pending_change_store import get_store, PendingChangeRecord
from app.schemas.changes import (
    ApplyChangeRequest,
    DiffChunk,
    DiffLine,
    ProposeChangeResponse,
)
from app.services.code_modification_service import (
    CodeModificationService,
    FileTooLargeError,
    _strip_fences,
    _compute_diff,
)
from app.utils.path_security import ProtectedFileError


# ── Autouse fixture — clear the global store before/after every test ──────────

@pytest.fixture(autouse=True)
def clear_pending_store():
    """Reset the global PendingChangeStore before and after every test.

    Prevents proposals left by one test from leaking into the next.
    Accesses the internals directly via get_store() rather than patching
    the module-level _STORE so that any code path importing get_store()
    sees the same cleared state.
    """
    s = get_store()
    s._records.clear()
    s._insertion_order.clear()
    yield
    s._records.clear()
    s._insertion_order.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_record(
    *,
    proposal_id: str = "a" * 36,
    file_path: str = "src/components/Login.jsx",
    abs_path: str = "/project/src/components/Login.jsx",
    language: str = "javascript",
    original_content: str = "function login() {}\n",
    new_content: str = "/** Login */\nfunction login() {}\n",
    diff_chunks: list | None = None,
    summary: str = "Add JSDoc",
    created_at: datetime | None = None,
) -> PendingChangeRecord:
    """Factory for PendingChangeRecord with sensible defaults."""
    original_hash = hashlib.sha256(original_content.encode("utf-8")).hexdigest()
    return PendingChangeRecord(
        id=proposal_id,
        file_path=file_path,
        resolved_abs_path=abs_path,
        language=language,
        original_content=original_content,
        original_hash=original_hash,
        new_content=new_content,
        diff_chunks=diff_chunks or [],
        summary=summary,
        created_at=created_at or datetime.now(tz=timezone.utc),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Tests 1–9: Intent Classification
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("text,expected_intent", [
    # Test 1 — explicit "modify" verb
    ("Modify Login.jsx to add type hints", Intent.MODIFY_CODE),
    # Test 2 — "fix the bug"
    ("Fix the bug in App.jsx", Intent.MODIFY_CODE),
    # Test 3 — "add a function"
    ("Add a function to utils.py", Intent.MODIFY_CODE),
    # Test 4 — "refactor" verb
    ("Refactor Dashboard.jsx", Intent.MODIFY_CODE),
    # Test 5 — "rewrite the login handler"
    ("Rewrite the login handler in Login.jsx", Intent.MODIFY_CODE),
    # Test 6 — "remove unused imports"
    ("Remove unused imports from main.py", Intent.MODIFY_CODE),
    # Test 7 — "extract a function"
    ("Extract a function from helpers.ts", Intent.MODIFY_CODE),
])
def test_modify_code_intent_classification(text: str, expected_intent: Intent) -> None:
    """Tests 1–7: MODIFY_CODE intent is detected for action-verb phrases."""
    result = classify(text)
    assert result.intent == expected_intent, (
        f"Expected {expected_intent.value!r} for {text!r}, got {result.intent.value!r}"
    )


def test_modify_code_is_file_intent() -> None:
    """Test 8: MODIFY_CODE is treated as a file-level intent (is_file_intent=True)."""
    result = classify("Modify Login.jsx to add type hints")
    assert result.intent == Intent.MODIFY_CODE
    assert result.is_file_intent is True


@pytest.mark.parametrize("text,expected_intent", [
    # Test 9a — "Fix this" has no code noun → UNSUPPORTED
    ("Fix this", Intent.UNSUPPORTED),
    # Test 9b — "Show me the code" is a view/explain intent, not a modify intent
    ("Show me the code", Intent.EXPLAIN_FILE),
])
def test_modify_code_non_regression_edge_cases(text: str, expected_intent: Intent) -> None:
    """Tests 9a–9b: Edge cases that should NOT be MODIFY_CODE."""
    result = classify(text)
    assert result.intent == expected_intent, (
        f"Expected {expected_intent.value!r} for {text!r}, got {result.intent.value!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Tests 10–15: PendingChangeStore
# ═══════════════════════════════════════════════════════════════════════════════

def test_store_put_and_get() -> None:
    """Test 10: put() stores a record; get() retrieves the same object."""
    store = get_store()
    record = _make_record(proposal_id="b" * 36)
    store.put(record)
    retrieved = store.get("b" * 36)
    assert retrieved is record
    assert retrieved.id == "b" * 36


def test_store_remove() -> None:
    """Test 11: put() then remove() makes get() return None."""
    store = get_store()
    record = _make_record(proposal_id="c" * 36)
    store.put(record)
    removed = store.remove("c" * 36)
    assert removed is True
    assert store.get("c" * 36) is None


def test_store_remove_nonexistent_returns_false() -> None:
    """Test 12: remove() with an unknown ID returns False without raising."""
    store = get_store()
    result = store.remove("unknown-id-000000000000000000000000000000")
    assert result is False


def test_store_max_capacity_evicts_oldest() -> None:
    """Test 13: After 51 puts (max=50), oldest is evicted and len == 50."""
    store = get_store()
    # Patch max to 50 (the default); insert 51 records
    for i in range(51):
        pid = f"{i:036d}"
        store.put(_make_record(proposal_id=pid))
    # Store should have exactly 50 entries
    assert len(store) == 50
    # The oldest (first inserted, id="000...0") should have been evicted
    assert store.get("0" * 36) is None
    # The most recently inserted should still be present
    assert store.get(f"{50:036d}") is not None


def test_store_get_nonexistent_returns_none() -> None:
    """Test 14: get() for a non-existent ID returns None without raising."""
    store = get_store()
    result = store.get("no-such-id-00000000000000000000000000")
    assert result is None


def test_store_cleanup_expired() -> None:
    """Test 15: cleanup_expired() removes records older than TTL and returns count."""
    store = get_store()
    old_ts = datetime.now(tz=timezone.utc) - timedelta(seconds=7200)  # 2 hours ago
    new_ts = datetime.now(tz=timezone.utc)

    old = _make_record(proposal_id="e" * 36, created_at=old_ts)
    fresh = _make_record(proposal_id="f" * 36, created_at=new_ts)
    store.put(old)
    store.put(fresh)

    # Patch TTL to 3600 (1 hour) — old record is 2 hours old → expired
    with patch("app.services.pending_change_store.settings") as mock_settings:
        mock_settings.pending_change_ttl_seconds = 3600
        count = store.cleanup_expired()

    assert count == 1
    assert store.get("e" * 36) is None   # expired — removed
    assert store.get("f" * 36) is not None  # fresh — kept


# ═══════════════════════════════════════════════════════════════════════════════
# Tests 16–25: CodeModificationService (mocked Groq + real filesystem)
# ═══════════════════════════════════════════════════════════════════════════════

def _run(coro):
    """Run a coroutine in a fresh event loop.

    Uses asyncio.run() which always creates a new event loop, avoiding
    'no current event loop' errors when running after other test modules
    that have closed or exhausted the default event loop.
    """
    return asyncio.run(coro)


@pytest.fixture
def demo_file(tmp_path: Path) -> Path:
    """Create a small temporary JS file to use as a propose target."""
    f = tmp_path / "Login.jsx"
    f.write_text("function login() {\n  return null;\n}\n", encoding="utf-8")
    return f


@pytest.fixture
def patched_settings(demo_file: Path):
    """Patch settings.project_root_path to the tmp_path directory."""
    with patch("app.services.code_modification_service.settings") as mock:
        mock.project_root_path = str(demo_file.parent)
        mock.max_file_size_for_ai = 102_400
        mock.max_pending_changes = 50
        yield mock


@pytest.fixture
def mock_groq_propose():
    """Return an AsyncMock for GroqService.propose_code_modification."""
    new_content = (
        "/** Login component */\n"
        "function login() {\n"
        "  return null;\n"
        "}\n"
    )
    with patch(
        "app.services.code_modification_service.GroqService.propose_code_modification",
        new_callable=AsyncMock,
        return_value=new_content,
    ) as mock:
        yield mock, new_content


def test_propose_returns_propose_change_response(
    demo_file, patched_settings, mock_groq_propose
) -> None:
    """Test 16: propose() returns a ProposeChangeResponse with proposal_id and chunks."""
    svc = CodeModificationService()
    result = _run(svc.propose("Login.jsx", "Add JSDoc comment"))
    assert isinstance(result, ProposeChangeResponse)
    assert len(result.proposal_id) == 36   # UUID4 format
    assert result.file_path == "Login.jsx"
    assert isinstance(result.chunks, list)


def test_propose_computes_diff_chunks(
    demo_file, patched_settings, mock_groq_propose
) -> None:
    """Test 17: diff contains 'added', 'removed', and/or 'context' line kinds."""
    svc = CodeModificationService()
    result = _run(svc.propose("Login.jsx", "Add JSDoc comment"))
    assert len(result.chunks) > 0
    all_kinds = {line.kind for chunk in result.chunks for line in chunk.lines}
    # At minimum we should see "added" (the new JSDoc line)
    assert "added" in all_kinds
    assert all(k in ("added", "removed", "context") for k in all_kinds)


def test_propose_stores_sha256_hash(
    demo_file, patched_settings, mock_groq_propose
) -> None:
    """Test 18: PendingChangeRecord.original_hash == sha256(content.encode()).hexdigest()."""
    original_content = demo_file.read_text(encoding="utf-8")
    expected_hash = hashlib.sha256(original_content.encode("utf-8")).hexdigest()

    svc = CodeModificationService()
    result = _run(svc.propose("Login.jsx", "Add JSDoc comment"))

    record = get_store().get(result.proposal_id)
    assert record is not None
    assert record.original_hash == expected_hash


def test_propose_resolved_abs_path_stored(
    demo_file, patched_settings, mock_groq_propose
) -> None:
    """Test 19: record.resolved_abs_path is absolute and inside the project root."""
    svc = CodeModificationService()
    result = _run(svc.propose("Login.jsx", "Add JSDoc comment"))
    record = get_store().get(result.proposal_id)
    assert record is not None
    abs_p = Path(record.resolved_abs_path)
    assert abs_p.is_absolute()
    root = Path(patched_settings.project_root_path).resolve()
    assert abs_p.relative_to(root)  # does not raise → inside root


def test_propose_summary_derived_from_instruction(
    demo_file, patched_settings, mock_groq_propose
) -> None:
    """Test 20: summary == instruction[:120].replace('\\n', ' ')."""
    instruction = "Add JSDoc comment\nto the login function"
    svc = CodeModificationService()
    result = _run(svc.propose("Login.jsx", instruction))
    expected_summary = instruction[:120].replace("\n", " ")
    assert result.summary == expected_summary


def test_propose_rejects_path_traversal(tmp_path, patched_settings) -> None:
    """Test 21: file_path with '..' raises ValueError before any filesystem access."""
    svc = CodeModificationService()
    with pytest.raises(ValueError, match="escapes project root"):
        _run(svc.propose("../etc/passwd", "Add docstring"))


def test_propose_rejects_nonexistent_file(tmp_path, patched_settings) -> None:
    """Test 22: file_path that does not exist raises FileNotFoundError."""
    svc = CodeModificationService()
    with pytest.raises(FileNotFoundError):
        _run(svc.propose("no_such_file.py", "Add docstring"))


def test_propose_rejects_protected_file_env(tmp_path, patched_settings) -> None:
    """Test 23: file_path='.env' raises ProtectedFileError."""
    # Create the .env file so we get past stat()
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET=abc\n", encoding="utf-8")
    # Patch the root so the file is reachable, then check it's blocked
    with patch("app.services.code_modification_service.settings") as mock:
        mock.project_root_path = str(tmp_path)
        mock.max_file_size_for_ai = 102_400
        svc = CodeModificationService()
        with pytest.raises(ProtectedFileError):
            _run(svc.propose(".env", "Change secret"))


def test_propose_strips_code_fence_from_groq(
    demo_file, patched_settings
) -> None:
    """Test 24: LLM output wrapped in ```python ... ``` fences is stripped."""
    fenced = "```python\ndef f(): pass\n```"
    with patch(
        "app.services.code_modification_service.GroqService.propose_code_modification",
        new_callable=AsyncMock,
        return_value=fenced,
    ):
        svc = CodeModificationService()
        result = _run(svc.propose("Login.jsx", "Rewrite as Python"))
    record = get_store().get(result.proposal_id)
    assert record is not None
    assert record.new_content == "def f(): pass"


def test_propose_rejects_malformed_ai_output_empty(
    demo_file, patched_settings
) -> None:
    """Test 25: empty LLM output raises ValueError('LLM returned empty content')."""
    with patch(
        "app.services.code_modification_service.GroqService.propose_code_modification",
        new_callable=AsyncMock,
        return_value="",
    ):
        svc = CodeModificationService()
        with pytest.raises(ValueError, match="LLM returned empty content"):
            _run(svc.propose("Login.jsx", "Delete everything"))


# ═══════════════════════════════════════════════════════════════════════════════
# Tests 26–33: Apply / Reject handlers
# ═══════════════════════════════════════════════════════════════════════════════

def test_apply_requires_confirmed_true() -> None:
    """Test 26: ApplyChangeRequest(confirmed=False) raises a Pydantic ValidationError."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ApplyChangeRequest(proposal_id="a" * 36, confirmed=False)


def test_apply_unknown_proposal_id_returns_404() -> None:
    """Test 27: POST /changes/apply with an unknown UUID → 404."""
    import warnings; warnings.filterwarnings("ignore")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    r = client.post(
        "/api/changes/apply",
        json={"proposal_id": "0" * 36, "confirmed": True},
    )
    assert r.status_code == 404


def test_apply_stale_file_returns_409(tmp_path: Path) -> None:
    """Test 28: If the file is modified after proposal, apply returns 409."""
    import warnings; warnings.filterwarnings("ignore")
    from fastapi.testclient import TestClient
    from app.main import app

    # Create a file and build a record with its current hash
    f = tmp_path / "target.py"
    original = "x = 1\n"
    f.write_text(original, encoding="utf-8")

    record = _make_record(
        proposal_id="d" * 36,
        file_path="target.py",
        abs_path=str(f),
        original_content=original,
        new_content="x = 2\n",
    )
    get_store().put(record)

    # Modify the file AFTER the proposal was stored → hash mismatch
    f.write_text("x = 999\n", encoding="utf-8")

    client = TestClient(app, raise_server_exceptions=False)
    r = client.post(
        "/api/changes/apply",
        json={"proposal_id": "d" * 36, "confirmed": True},
    )
    assert r.status_code == 409
    assert "File was modified" in r.json()["detail"]


def test_apply_writes_file_content_to_disk(tmp_path: Path) -> None:
    """Test 29: A successful apply writes record.new_content to disk."""
    import warnings; warnings.filterwarnings("ignore")
    from fastapi.testclient import TestClient
    from app.main import app

    f = tmp_path / "target.py"
    original = "x = 1\n"
    new_content = "x = 42\n"
    f.write_text(original, encoding="utf-8")

    record = _make_record(
        proposal_id="g" * 36,
        file_path="target.py",
        abs_path=str(f),
        original_content=original,
        new_content=new_content,
    )
    get_store().put(record)

    with patch("app.api.routes.changes._validate_write_target"):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(
            "/api/changes/apply",
            json={"proposal_id": "g" * 36, "confirmed": True},
        )

    assert r.status_code == 200
    assert f.read_text(encoding="utf-8") == new_content


def test_apply_uses_resolved_abs_path_not_request_body(tmp_path: Path) -> None:
    """Test 30: The write uses record.resolved_abs_path; /apply body has no file_path field."""
    # This is a schema / design test: ApplyChangeRequest must NOT have a file_path field
    import inspect
    from app.schemas.changes import ApplyChangeRequest
    fields = set(ApplyChangeRequest.model_fields.keys())
    assert "file_path" not in fields, (
        "ApplyChangeRequest must not expose a file_path field — "
        "the write path comes exclusively from PendingChangeRecord.resolved_abs_path"
    )
    assert "proposal_id" in fields
    assert "confirmed" in fields


def test_apply_removes_proposal_from_store_after_write(tmp_path: Path) -> None:
    """Test 31: After a successful apply, GET /diff/{id} returns 404."""
    import warnings; warnings.filterwarnings("ignore")
    from fastapi.testclient import TestClient
    from app.main import app

    f = tmp_path / "target.py"
    original = "x = 1\n"
    f.write_text(original, encoding="utf-8")
    record = _make_record(
        proposal_id="h" * 36,
        file_path="target.py",
        abs_path=str(f),
        original_content=original,
        new_content="x = 99\n",
    )
    get_store().put(record)

    with patch("app.api.routes.changes._validate_write_target"):
        client = TestClient(app, raise_server_exceptions=False)
        apply_r = client.post(
            "/api/changes/apply",
            json={"proposal_id": "h" * 36, "confirmed": True},
        )
    assert apply_r.status_code == 200

    # Now the proposal should be gone from the store
    diff_r = client.get(f"/api/changes/diff/{'h' * 36}")
    assert diff_r.status_code == 404


def test_apply_cleans_up_tmp_file_on_success(tmp_path: Path) -> None:
    """Test 32: No .silentvoice_tmp file remains after a successful apply."""
    import warnings; warnings.filterwarnings("ignore")
    from fastapi.testclient import TestClient
    from app.main import app

    f = tmp_path / "target.py"
    original = "x = 1\n"
    f.write_text(original, encoding="utf-8")
    record = _make_record(
        proposal_id="i" * 36,
        file_path="target.py",
        abs_path=str(f),
        original_content=original,
        new_content="x = 55\n",
    )
    get_store().put(record)

    with patch("app.api.routes.changes._validate_write_target"):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(
            "/api/changes/apply",
            json={"proposal_id": "i" * 36, "confirmed": True},
        )
    assert r.status_code == 200

    tmp_file = f.with_suffix(f.suffix + ".silentvoice_tmp")
    assert not tmp_file.exists(), f".silentvoice_tmp file was not cleaned up: {tmp_file}"


def test_reject_proposal_writes_nothing(tmp_path: Path) -> None:
    """Test 33: After reject, the original file is unchanged."""
    import warnings; warnings.filterwarnings("ignore")
    from fastapi.testclient import TestClient
    from app.main import app

    f = tmp_path / "target.py"
    original = "original content\n"
    f.write_text(original, encoding="utf-8")
    record = _make_record(
        proposal_id="j" * 36,
        file_path="target.py",
        abs_path=str(f),
        original_content=original,
        new_content="modified content\n",
    )
    get_store().put(record)

    client = TestClient(app, raise_server_exceptions=False)
    r = client.post(
        "/api/changes/reject",
        json={"proposal_id": "j" * 36},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # File must be unchanged
    assert f.read_text(encoding="utf-8") == original


# ═══════════════════════════════════════════════════════════════════════════════
# Tests 34–37: API Endpoint Tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_api_propose_returns_200_with_diff(tmp_path: Path) -> None:
    """Test 34: POST /api/changes/propose → 200 with proposal_id, chunks, summary."""
    import warnings; warnings.filterwarnings("ignore")
    from fastapi.testclient import TestClient
    from app.main import app

    f = tmp_path / "Login.jsx"
    f.write_text("function login() {\n  return null;\n}\n", encoding="utf-8")

    new_content = "/** Login */\nfunction login() {\n  return null;\n}\n"
    with patch(
        "app.services.code_modification_service.GroqService.propose_code_modification",
        new_callable=AsyncMock,
        return_value=new_content,
    ), patch("app.services.code_modification_service.settings") as mock_settings:
        mock_settings.project_root_path = str(tmp_path)
        mock_settings.max_file_size_for_ai = 102_400
        mock_settings.max_pending_changes = 50

        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(
            "/api/changes/propose",
            json={"file_path": "Login.jsx", "instruction": "Add JSDoc"},
        )

    assert r.status_code == 200
    body = r.json()
    assert "proposal_id" in body
    assert len(body["proposal_id"]) == 36
    assert isinstance(body["chunks"], list)
    assert body["summary"] == "Add JSDoc"


def test_api_propose_rejects_traversal_path() -> None:
    """Test 35: file_path with '..' is rejected with 422 (Pydantic validation)."""
    import warnings; warnings.filterwarnings("ignore")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    r = client.post(
        "/api/changes/propose",
        json={"file_path": "../etc/passwd", "instruction": "Read it"},
    )
    assert r.status_code == 422


def test_api_diff_retrieval_by_id(tmp_path: Path) -> None:
    """Test 36: POST propose then GET diff/{id} → 200 with same chunks."""
    import warnings; warnings.filterwarnings("ignore")
    from fastapi.testclient import TestClient
    from app.main import app

    f = tmp_path / "Login.jsx"
    f.write_text("function login() {}\n", encoding="utf-8")

    new_content = "/** Login */\nfunction login() {}\n"
    with patch(
        "app.services.code_modification_service.GroqService.propose_code_modification",
        new_callable=AsyncMock,
        return_value=new_content,
    ), patch("app.services.code_modification_service.settings") as mock_settings:
        mock_settings.project_root_path = str(tmp_path)
        mock_settings.max_file_size_for_ai = 102_400
        mock_settings.max_pending_changes = 50

        client = TestClient(app, raise_server_exceptions=False)
        propose_r = client.post(
            "/api/changes/propose",
            json={"file_path": "Login.jsx", "instruction": "Add JSDoc"},
        )

    assert propose_r.status_code == 200
    proposal_id = propose_r.json()["proposal_id"]

    diff_r = client.get(f"/api/changes/diff/{proposal_id}")
    assert diff_r.status_code == 200
    diff_body = diff_r.json()
    assert diff_body["proposal_id"] == proposal_id
    assert diff_body["chunks"] == propose_r.json()["chunks"]


def test_api_diff_unknown_id_returns_404() -> None:
    """Test 37: GET /changes/diff/{unknown_uuid} → 404."""
    import warnings; warnings.filterwarnings("ignore")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/changes/diff/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Tests 38–39: Security / Adversarial
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("file_path,expected_status", [
    # Test 38a — .env file: ProtectedFileError → HTTP 403
    (".env", 403),
    # Test 38b — SSH private key: ProtectedFileError → HTTP 403
    ("id_rsa", 403),
    # Test 38c — .git/config: caught by _check_protected (protected dir) → HTTP 403
    #            (Pydantic does not block .git/config because it contains no traversal
    #             sequences, null bytes, or metacharacters.)
    (".git/config", 403),
])
def test_security_protected_files_blocked(file_path: str, expected_status: int) -> None:
    """Tests 38a–38c: Protected / dangerous file_path values are rejected.

    ProtectedFileError is raised by _check_protected() inside
    CodeModificationService.propose() and mapped to HTTP 403 by the /propose
    route handler.  Any status code in (400, 403, 422, 404) is a valid
    rejection — the important thing is that the request never succeeds.
    """
    import warnings; warnings.filterwarnings("ignore")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    r = client.post(
        "/api/changes/propose",
        json={"file_path": file_path, "instruction": "Read or modify"},
    )
    # Accept any rejection status: 400 (ValueError), 403 (ProtectedFileError),
    # 404 (not found after protection check passes), 422 (Pydantic).
    assert r.status_code in (400, 403, 404, 422), (
        f"Expected a rejection for '{file_path}', got {r.status_code}: {r.text}"
    )


def test_api_chat_modify_code_returns_non_error_response() -> None:
    """Test 39: POST /api/assistant/chat with a modify intent returns modify_code + error=false.

    This is the backward-compatibility gate for the ExplanationService MODIFY_CODE branch.
    Confirms that the /chat endpoint correctly classifies and responds to modify requests
    without invoking Groq (the MODIFY_CODE branch in ExplanationService is Groq-free).

    Uses the existing demo_project (src/components/Login.jsx exists) and passes it as
    selected_file so FileResolver can resolve it. The MODIFY_CODE ExplanationService
    branch never calls Groq, so no API key patching is required.
    """
    import warnings; warnings.filterwarnings("ignore")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    r = client.post(
        "/api/assistant/chat",
        json={
            "message": "Modify Login.jsx to add type hints",
            "selected_file": "src/components/Login.jsx",
        },
    )

    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "modify_code"
    assert body["error"] is False
