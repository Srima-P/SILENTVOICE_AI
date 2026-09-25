# Phase 6 Implementation Plan — Safe AI Code Modification + Diff Preview + Human Approval
## Revision 3 — All Review Issues Resolved (FINAL — approved for implementation)

---

## Top-Level Overview

Phase 6 gives SilentVoice AI the ability to **propose targeted code modifications to a single project
file**, show a **backend-computed diff preview** to the developer, and require **explicit, click-based
human approval** before any change is written to disk.

### Absolute Invariants (enforced at every layer)

1. **`safe_read` is read-only.** The write/apply pipeline performs its own independent path validation
   via `_validate_write_target` (in `utils/path_security.py`). It never delegates write-safety to
   `safe_read`.
2. **SHA-256 hash stored at proposal time.** Every `PendingChangeRecord` stores `original_hash`
   (SHA-256 hex of `content.encode("utf-8")`). At apply time the file is re-read with
   `Path.read_text(encoding="utf-8")`; its hash is recomputed and compared. If they differ → HTTP 409.
3. **Explicit proposal ID + explicit human approval required to write.** `/apply` accepts a
   `proposal_id` (UUID) and `confirmed: true` (no default). Missing `confirmed` or unknown ID →
   rejected.
4. **Voice transcription cannot approve changes.** Voice creates a text instruction → `/chat`
   → `SET_PENDING_PROPOSAL_REQUEST` in AppContext → `ChangesPanel` triggers `propose()`. The `/apply`
   endpoint is only reachable via the "Apply" button in `ChangesPanel`. These are architecturally
   separate code paths.
5. **All LLM output is untrusted.** The file path used during apply comes from the
   `PendingChangeRecord` stored at proposal time, never from the LLM or from the `/apply` request body.
6. **Target file identity verified.** `CodeModificationService` resolves `file_path` to an absolute
   `resolved_abs_path` and stores it in `PendingChangeRecord`. `/apply` uses `record.resolved_abs_path`
   exclusively — the LLM cannot redirect the write.
7. **No shell commands executed.** The instruction is a string sent to Groq's REST API only. Never
   passed to `subprocess`, `os.system`, `eval`, or any shell-execution surface.
8. **Single-file only.** `/propose` accepts exactly one `file_path`.
9. **Protected-file list enforced independently in the write path** via `_check_protected` in
   `utils/path_security.py`.
10. **`PendingChangeStore` is bounded (max 50 entries) and uses UUID proposal IDs** via `get_store()`.
11. **Reject writes nothing.** The reject handler removes the record from the store only.
12. **Apply writes only after all validations pass.** Order: lookup → hash check → protected-file
    check → root-escape check → symlink check → atomic write.
13. **Test coverage for all adversarial cases** — see Section H (39 tests).

### Scope

- New `MODIFY_CODE` intent (classifier + `ExplanationService` + `ChatMessage`).
- New `utils/path_security.py` — shared protected-file and write-target validation.
- New `CodeModificationService` — read → hash → Groq → strip → diff → store → return.
- New `PendingChangeStore` — bounded in-memory dict keyed by `uuid4()`, accessed via `get_store()`.
- Four new API endpoints: `/propose`, `/diff/{id}`, `/apply`, `/reject`.
- Six new Pydantic schemas: `ModifyRequest`, `ProposeChangeResponse`, `DiffLine`, `DiffChunk`,
  `ApplyChangeRequest`, `ApplyChangeResponse`.
- Frontend Option A state: `pendingProposalRequest` in AppContext; `usePendingChanges` owned by
  `ChangesPanel`; `AssistantPanel` dispatches only.
- 39 tests in `test_phase6.py` with store-clearing fixture.

---

## A. FILES TO CREATE

### Backend

| File | Purpose |
|------|---------|
| `backend/app/utils/path_security.py` | `_PROTECTED_PATTERNS`, `_check_protected`, `_validate_write_target` — shared by both service and route |
| `backend/app/schemas/changes.py` | All Phase 6 Pydantic request/response models |
| `backend/app/services/pending_change_store.py` | `PendingChangeRecord` dataclass, `PendingChangeStore`, `get_store()` accessor |
| `backend/app/services/code_modification_service.py` | `CodeModificationService.propose`, `_strip_fences`, `_compute_diff` |
| `backend/app/api/routes/changes.py` | Four route handlers: `/propose`, `/diff/{id}`, `/apply`, `/reject` |
| `backend/tests/test_phase6.py` | 39 tests + store-clearing autouse fixture |

### Frontend

| File | Purpose |
|------|---------|
| `frontend/src/services/changesApi.ts` | `proposeChange`, `getDiff`, `applyChange`, `rejectChange` |
| `frontend/src/hooks/usePendingChanges.ts` | `propose`, `approve`, `reject`; owned by `ChangesPanel` only |
| `frontend/src/components/DiffViewer.tsx` | Renders `DiffChunk[]` with line-level color coding |

---

## B. FILES TO MODIFY

### Backend

| File | Change |
|------|--------|
| `backend/app/services/intent_classifier.py` | Add `MODIFY_CODE = "modify_code"` to enum; add pattern before `EXPLAIN_FILE`; add to `is_file_intent` |
| `backend/app/services/explanation_service.py` | Add `MODIFY_CODE` branch to `handle()`; return `error=False`, `target_file`, guidance message |
| `backend/app/services/groq_service.py` | Add `propose_code_modification(file_path, language, original_content, instruction) -> str` |
| `backend/app/api/router.py` | Register `changes.router` with prefix `/changes`, tag `changes` |
| `backend/app/config.py` | Add `max_pending_changes: int = 50`, `pending_change_ttl_seconds: int = 3600` |

### Frontend

| File | Change |
|------|--------|
| `frontend/src/types/index.ts` | Add `DiffLine`, `DiffChunk`, `ProposeChangeResponse`, `ApplyChangeResponse`; extend `ProposedChange`; add `PendingProposalRequest`; extend `AppState` with `pendingProposalRequest` |
| `frontend/src/contexts/AppContext.tsx` | Add `ADD_PENDING_CHANGE`, `UPDATE_PENDING_CHANGE`, `REMOVE_PENDING_CHANGE`, `SET_PENDING_PROPOSAL_REQUEST` actions + reducer cases + context methods |
| `frontend/src/components/ChangesPanel.tsx` | Own `usePendingChanges`; replace `EmptyState` with pending changes list; watch `pendingProposalRequest` in effect |
| `frontend/src/components/AssistantPanel.tsx` | Dispatch `SET_PENDING_PROPOSAL_REQUEST` for `modify_code` responses; never call `propose()` or `approve()` directly |
| `frontend/src/components/ChatMessage.tsx` | Add `modify_code: "Propose change"` to `INTENT_LABELS` |

---

## C. NEW API ENDPOINTS

### POST `/api/changes/propose`

**Purpose**: Produce an AI-generated code modification proposal for a single file.

**Request body**: `ModifyRequest`

**Response**: `ProposeChangeResponse` (HTTP 200)

**Error codes**:
- 400 — path invalid, protected file, or absolute path
- 404 — file not found
- 413 — file exceeds `max_file_size_for_ai`
- 422 — Pydantic validation failure
- 500 — Groq call failed or unexpected error

**Exact backend processing order**:
1. Pydantic parses `ModifyRequest` → `_validate_path` validator rejects `..`, null bytes, shell
   metacharacters, absolute paths, leading separators. Raises HTTP 422 on violation.
2. Route calls `await CodeModificationService().propose(body.file_path, body.instruction)`.
3. Service internally (see Section E, `CodeModificationService.propose`).
4. On `ValueError` / `ProtectedFileError` → HTTP 400.
5. On `FileNotFoundError` → HTTP 404.
6. On `FileTooLargeError` → HTTP 413.
7. On `GroqError` → HTTP 500.
8. Return `ProposeChangeResponse`.

---

### GET `/api/changes/diff/{proposal_id}`

**Purpose**: Re-fetch the diff for an existing proposal (idempotent, no Groq call).

**Path param**: `proposal_id: str = Path(..., min_length=36, max_length=36)`

**Response**: `ProposeChangeResponse` (HTTP 200), HTTP 404 if not found or expired.

**Note**: This endpoint never touches the filesystem.

---

### POST `/api/changes/apply`

**Purpose**: Write the approved new content to disk. The **only** endpoint that writes files.

**Request body**: `ApplyChangeRequest`

**Response**: `ApplyChangeResponse` (HTTP 200)

**Error codes**: 400 `confirmed=False`, 404 proposal not found, 409 stale file, 500 write failure

**Exact backend processing order** (all steps must pass before write):
1. Parse `ApplyChangeRequest`. Pydantic `_must_confirm` validator rejects `confirmed=False` → HTTP 422.
2. `root = Path(settings.project_root_path).resolve()`.
3. Look up `record = get_store().get(proposal_id)` → HTTP 404 if `None`.
4. **Hash check (stale-file detection)**:
   - `current_content = Path(record.resolved_abs_path).read_text(encoding="utf-8")` (same mode as
     proposal-time read — universal newlines, UTF-8).
   - `current_hash = hashlib.sha256(current_content.encode("utf-8")).hexdigest()`.
   - If `current_hash != record.original_hash` → HTTP 409:
     `{"detail": "File was modified after proposal was created. Re-propose to pick up the latest version."}`.
5. **Write-path security re-validation** (independent of `safe_read`):
   - `_validate_write_target(Path(record.resolved_abs_path), root)` — imported from
     `app.utils.path_security`. Raises `ValueError` / `ProtectedFileError` → HTTP 400.
6. **Atomic write**:
   - `tmp_path = Path(record.resolved_abs_path).with_suffix(Path(record.resolved_abs_path).suffix + ".silentvoice_tmp")`.
   - `Path(tmp_path).write_text(record.new_content, encoding="utf-8")`.
   - `os.replace(tmp_path, record.resolved_abs_path)`.
   - In `finally`: `Path(tmp_path).unlink(missing_ok=True)` — cleans up stray tmp on any failure.
   - On write exception → HTTP 500.
7. `get_store().remove(proposal_id)`.
8. Return `ApplyChangeResponse(ok=True, file_path=record.file_path, bytes_written=len(record.new_content.encode("utf-8")), proposal_id=proposal_id)`.

---

### POST `/api/changes/reject`

**Purpose**: Discard a proposal. Writes nothing to disk.

**Request body**: `RejectRequest`

**Response**: `{"ok": true}` (HTTP 200), HTTP 404 if not found.

**Backend step**: `get_store().remove(proposal_id)`. Zero filesystem operations.

---

## D. NEW SCHEMAS (`backend/app/schemas/changes.py`)

```python
import re
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator

# Same traversal pattern as ChatRequest.selected_file in schemas/assistant.py
_TRAVERSAL_RE = re.compile(r"\.\.|[\x00-\x1f]|[<>|*?]")


class ModifyRequest(BaseModel):
    file_path: str = Field(..., min_length=1, max_length=512)
    instruction: str = Field(..., min_length=1, max_length=2000)

    @field_validator("file_path")
    @classmethod
    def _validate_path(cls, v: str) -> str:
        if _TRAVERSAL_RE.search(v):
            raise ValueError("file_path contains invalid characters or path traversal")
        # Reject absolute POSIX path
        if v.startswith("/"):
            raise ValueError("file_path must be relative")
        # Reject absolute Windows path (C: or \\ prefix)
        if len(v) > 1 and v[1] == ":":
            raise ValueError("file_path must be relative")
        if v.startswith("\\"):
            raise ValueError("file_path must be relative")
        return v


class DiffLine(BaseModel):
    kind: Literal["context", "added", "removed"]   # validated by Pydantic at runtime
    line_number_old: Optional[int] = None
    line_number_new: Optional[int] = None
    content: str


class DiffChunk(BaseModel):
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[DiffLine]


class ProposeChangeResponse(BaseModel):
    proposal_id: str            # UUID4 string
    file_path: str              # relative path (never resolved_abs_path)
    language: str
    original_lines: int
    new_lines: int
    chunks: list[DiffChunk]
    summary: str                # derived from instruction[:120].replace("\n", " ")
    created_at: str             # ISO-8601


class ApplyChangeRequest(BaseModel):
    proposal_id: str = Field(..., min_length=36, max_length=36)
    confirmed: bool             # no default — caller must be explicit

    @field_validator("confirmed")
    @classmethod
    def _must_confirm(cls, v: bool) -> bool:
        if not v:
            raise ValueError("confirmed must be true to apply a change")
        return v


class ApplyChangeResponse(BaseModel):
    ok: bool
    file_path: str
    bytes_written: int
    proposal_id: str


class RejectRequest(BaseModel):
    proposal_id: str = Field(..., min_length=36, max_length=36)
```

**Schema security notes**:
- `file_path` validated before any filesystem access.
- `confirmed` has no default — omitting it causes a Pydantic validation error.
- `DiffLine.kind` uses `Literal` — Pydantic validates at runtime; invalid diff output raises 422.
- Neither `file_path` nor `instruction` is ever used as a shell argument.

---

## E. NEW / MODIFIED SERVICES

### `utils/path_security.py` (NEW)

**Purpose**: Shared write-path security primitives. Imported by both
`code_modification_service.py` and `api/routes/changes.py`. Never imported by `safe_read` or any
read-only path.

```python
"""
path_security.py — write-path validation helpers for Phase 6.

Independent of ProjectScanner and safe_read. Used only in the modification pipeline.
"""
import fnmatch
from pathlib import Path

# ── Protected file patterns ───────────────────────────────────────────────────
# Checked against the *filename* (Path.name) using fnmatch or exact match.
_PROTECTED_NAME_PATTERNS = [
    ".env", ".envrc", "secrets.json", "credentials.json", "service-account.json",
    ".netrc", ".npmrc", ".pypirc", "id_rsa", "id_ed25519",
    "*.pem", "*.key", "*.p12", "*.pfx", "*.secret",
]
# Checked using str.startswith() against the relative path string.
_PROTECTED_DIR_PREFIXES = [
    ".git/", "node_modules/", ".venv/", "venv/", "__pycache__/", "dist/", "build/",
    ".svn/", ".hg/",
]


class ProtectedFileError(ValueError):
    """Raised when a write target matches a protected file pattern."""


def _check_protected(rel_path: str) -> None:
    """
    Raise ProtectedFileError if rel_path (relative to project root, forward-slash
    separated) matches any protected pattern.

    Two strategies:
    1. fnmatch.fnmatch(Path(rel_path).name, pattern) — for name-based patterns.
    2. rel_path.startswith(prefix) — for directory prefix patterns.
    3. Path(rel_path).name.startswith(".env") — catches .env.local, .env.production, etc.
    """
    name = Path(rel_path).name
    # .env.* family
    if name.startswith(".env"):
        raise ProtectedFileError(f"Modification of '{name}' is forbidden (protected file)")
    # Name-based patterns via fnmatch
    for pattern in _PROTECTED_NAME_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            raise ProtectedFileError(f"Modification of '{name}' is forbidden (protected file)")
    # Directory prefix patterns
    norm = rel_path.replace("\\", "/")
    for prefix in _PROTECTED_DIR_PREFIXES:
        if norm.startswith(prefix):
            raise ProtectedFileError(
                f"Modification inside '{prefix.rstrip('/')}' is forbidden"
            )


def _validate_write_target(abs_path: Path, project_root: Path) -> None:
    """
    Independent write-path security check. Raises ValueError (or subclass) on any
    violation. Does NOT call safe_read or any read-only API.

    Called at BOTH propose time (in CodeModificationService) AND apply time
    (in the /apply route handler). The second call at apply time catches any
    filesystem state change between proposal and apply.
    """
    # 1. Must be strictly inside project root
    try:
        rel = abs_path.relative_to(project_root)
    except ValueError:
        raise ValueError(f"Target path escapes project root: {abs_path}")

    # 2. Must not match protected patterns
    _check_protected(rel.as_posix())

    # 3. Must not be a directory
    if abs_path.is_dir():
        raise ValueError(f"Target path is a directory: {abs_path}")

    # 4. Must not have .git anywhere in its parts
    if ".git" in abs_path.parts:
        raise ValueError("Modification of .git internals is forbidden")

    # 5. Must not be a symlink (prevents TOCTOU escape)
    if abs_path.is_symlink():
        raise ValueError(f"Target path is a symlink: {abs_path}")
```

---

### `PendingChangeRecord` + `PendingChangeStore` + `get_store()` (`pending_change_store.py`, NEW)

```python
@dataclass
class PendingChangeRecord:
    id: str                    # UUID4 string
    file_path: str             # relative path — display only, never used for writes
    resolved_abs_path: str     # absolute path validated at propose time — ONLY used for writes
    language: str
    original_content: str      # stored for diff display; read with read_text(encoding="utf-8")
    original_hash: str         # sha256(original_content.encode("utf-8")).hexdigest()
    new_content: str           # LLM-generated; untrusted until apply-time validation
    diff_chunks: list          # list[DiffChunk], pre-computed at propose time
    summary: str               # instruction[:120].replace("\n", " ")
    created_at: datetime       # UTC timestamp


class PendingChangeStore:
    def __init__(self) -> None:
        self._records: dict[str, PendingChangeRecord] = {}
        self._insertion_order: list[str] = []   # maintains eviction ordering

    def put(self, record: PendingChangeRecord) -> str:
        """Store record. Evict oldest if over max_pending_changes. Returns record.id."""

    def get(self, proposal_id: str) -> Optional[PendingChangeRecord]:
        """Return record or None. Never raises."""

    def remove(self, proposal_id: str) -> bool:
        """Remove record. Returns True if found. Does not raise if absent."""

    def cleanup_expired(self) -> int:
        """Remove records older than pending_change_ttl_seconds. Returns count removed."""


# Module-level singleton — private
_STORE = PendingChangeStore()


def get_store() -> PendingChangeStore:
    """Public accessor. Import this, not _STORE directly."""
    return _STORE
```

**Test fixture** (must appear at top of `test_phase6.py`):
```python
import pytest
from app.services.pending_change_store import get_store

@pytest.fixture(autouse=True)
def clear_store():
    """Reset the global store before every test to prevent cross-contamination."""
    store = get_store()
    store._records.clear()
    store._insertion_order.clear()
    yield
    store._records.clear()
    store._insertion_order.clear()
```

---

### `CodeModificationService` (`code_modification_service.py`, NEW)

**Imports**: `path_security._check_protected`, `path_security._validate_write_target`,
`path_security.ProtectedFileError`, `project_scanner._detect_language`, `groq_service.GroqService`,
`pending_change_store.get_store`, `schemas.changes.*`.

**Custom exceptions** (defined in this file):
```python
class FileTooLargeError(ValueError):
    """File exceeds max_file_size_for_ai."""
```

**Key method**:
```python
async def propose(self, file_path: str, instruction: str) -> ProposeChangeResponse:
```

**Processing order inside `propose`** — exact sequence:

1. `root = Path(settings.project_root_path).resolve()`
2. `rel_clean = file_path.lstrip("/\\")`  — normalize (Pydantic already rejected traversal)
3. `abs_path = (root / rel_clean).resolve()`
4. Verify inside root: `abs_path.relative_to(root)` → raises `ValueError` on escape
5. `_check_protected(abs_path.relative_to(root).as_posix())` → raises `ProtectedFileError`
6. `abs_path.stat()` → raises `FileNotFoundError` if missing
7. Check `abs_path.stat().st_size > settings.max_file_size_for_ai` **before reading** →
   raises `FileTooLargeError("File too large for AI analysis")`
8. `original_content = abs_path.read_text(encoding="utf-8")`
   — Python default universal newlines; `\r\n` normalized to `\n` on all platforms
9. `original_hash = hashlib.sha256(original_content.encode("utf-8")).hexdigest()`
10. `language = _detect_language(abs_path)` (imported from `project_scanner`)
11. `new_content = await self._groq.propose_code_modification(file_path, language, original_content, instruction)`
12. `new_content = _strip_fences(new_content)`
13. Validate `new_content`: if not `new_content.strip()` → raise `ValueError("LLM returned empty content")`
14. `diff_chunks = _compute_diff(original_content, new_content)`
15. `summary = instruction[:120].replace("\n", " ")`
16. `proposal_id = str(uuid.uuid4())`
17. `record = PendingChangeRecord(id=proposal_id, file_path=rel_clean, resolved_abs_path=str(abs_path), ...)`
18. `get_store().put(record)`
19. Return `ProposeChangeResponse(proposal_id=proposal_id, file_path=rel_clean, language=language, original_lines=len(original_content.splitlines()), new_lines=len(new_content.splitlines()), chunks=diff_chunks, summary=summary, created_at=datetime.utcnow().isoformat())`

**`_strip_fences`**:
```python
def _strip_fences(text: str) -> str:
    """Remove ``` ... ``` wrappers if present. Handles uppercase/digit lang tags."""
    stripped = text.strip()
    # Matches: ```[lang]\n...\n``` or just ```\n...\n```
    # [\w+\-#.]* handles: python, typescript, python3, c++, c#, jsx
    m = re.match(r"^```[\w+\-#.]*\s*\n(.*)\n```\s*$", stripped, re.DOTALL)
    if m:
        result = m.group(1)
        return result if result.strip() else stripped  # fallback if strip produces empty
    return stripped
```

**`_compute_diff`**:
```python
def _compute_diff(original: str, new: str) -> list[DiffChunk]:
    """
    Parse difflib.unified_diff output into list[DiffChunk].
    Uses n=3 context lines, lineterm="".
    Chunk header regex: r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
    Line classification:
      starts with "+" and not "+++" → "added"
      starts with "-" and not "---" → "removed"
      starts with " "               → "context"
    Line numbers tracked independently for old (removed/context) and new (added/context).
    """
```

---

### `GroqService.propose_code_modification` (new method on existing `groq_service.py`)

```python
async def propose_code_modification(
    self,
    file_path: str,
    language: str,
    original_content: str,
    instruction: str,
) -> str:
    """
    Returns ONLY the complete replacement file content as plain text.
    Caller must strip code fences and validate the result.
    Raises GroqError on any failure.
    """
```

**System prompt** (exact intent):
> You are a precise code editor. You will be given the complete contents of a source file and a
> natural-language instruction describing what to change. Return ONLY the complete replacement file
> content as plain text — no prose, no explanation, no code fences, no markdown, no surrounding
> text of any kind. Preserve all whitespace, indentation, comments, and imports not directly
> affected by the instruction. If the instruction is ambiguous, impossible, or unsafe, return the
> original content unchanged with a single-line comment prepended: `# SilentVoice: [brief reason]`.
> Never output shell commands, file paths, executable directives, or anything other than source code.

**Parameters**: `temperature=0.1`, `max_tokens=4096`.

---

### `ExplanationService` — `MODIFY_CODE` branch (modification to `explanation_service.py`)

Add the following branch to `handle()` immediately before the `UNSUPPORTED` fallback (after the
Phase 5 onboarding block):

```python
# ── Phase 6: Modify code ───────────────────────────────────────────────────────
if intent == Intent.MODIFY_CODE:
    if not resolved_file:
        return ExplanationResult(
            intent=intent.value,
            target_file=None,
            response=(
                "I need a file to modify. Try: **Modify Login.jsx to add type hints**\n\n"
                "Make sure a file is selected in the Project Explorer, or include the "
                "filename in your request."
            ),
            error=True,
            groq_used=False,
        )
    fname = resolved_file.split("/")[-1]
    return ExplanationResult(
        intent=intent.value,
        target_file=resolved_file,
        response=(
            f"Ready to propose changes to `{resolved_file}`.\n\n"
            "Click **Propose Change** below to generate a diff you can review and approve "
            "before anything is written to disk."
        ),
        error=False,
        groq_used=False,
        follow_up_suggestions=[
            f"Explain {fname}",
            f"Summarize {fname}",
            f"What are the dependencies of {fname}?",
            f"Which files depend on {fname}?",
        ],
    )
```

Also update `_generate_follow_up_suggestions` to handle `Intent.MODIFY_CODE`:
```python
elif intent == Intent.MODIFY_CODE:
    base = [
        f"Explain {fname}" if fname else "Explain this file",
        f"Summarize {fname}" if fname else "Summarize this file",
        f"What are the dependencies of {fname}?" if fname else "What are its dependencies?",
        f"Which files depend on {fname}?" if fname else "Which files depend on it?",
    ]
```

---

## F. FRONTEND CHANGES

### New / Extended Types (`frontend/src/types/index.ts`)

**New interfaces**:
```typescript
export interface DiffLine {
  kind: "context" | "added" | "removed";
  line_number_old: number | null;
  line_number_new: number | null;
  content: string;
}

export interface DiffChunk {
  old_start: number;
  old_count: number;
  new_start: number;
  new_count: number;
  lines: DiffLine[];
}

export interface ProposeChangeResponse {
  proposal_id: string;    // backend field name
  file_path: string;
  language: string;
  original_lines: number;
  new_lines: number;
  chunks: DiffChunk[];
  summary: string;
  created_at: string;
}

export interface ApplyChangeResponse {
  ok: boolean;
  file_path: string;
  bytes_written: number;
  proposal_id: string;
}

/** Passed from AssistantPanel to ChangesPanel via AppContext.
 *  Triggers a propose() call from ChangesPanel's usePendingChanges instance. */
export interface PendingProposalRequest {
  filePath: string;       // resolved target_file from /chat response
  instruction: string;    // original user message text
}
```

**Replace existing `ProposedChange`**:
```typescript
export interface ProposedChange {
  id: string;           // = proposal_id from backend (set explicitly in usePendingChanges)
  filePath: string;     // = file_path from ProposeChangeResponse
  description: string;  // = summary from ProposeChangeResponse
  language: string;     // = language from ProposeChangeResponse
  // Status lifecycle:
  // "pending"  — stored on backend, user has not acted
  // "applying" — POST /apply in flight
  // "applied"  — successfully written to disk
  // "rejected" — user rejected; removed from backend store
  // "conflict" — 409 returned; user must re-propose
  status: "pending" | "applying" | "applied" | "rejected" | "conflict";
  diff: ProposeChangeResponse | null;  // full diff payload; null until proposal returns
}
```

**Extend `AppState`**:
```typescript
export interface AppState {
  // ... all existing fields ...
  pendingProposalRequest: PendingProposalRequest | null;  // Phase 6: triggers propose()
}
```

**Security note**: The frontend never constructs a file path to send to `/apply`. `ApplyChangeRequest`
contains only `proposal_id` and `confirmed: true`. The backend resolves the write path from its store.

---

### New API Service (`frontend/src/services/changesApi.ts`)

```typescript
/**
 * changesApi.ts — Phase 6 frontend service for code modification proposals.
 * Routes through /api/changes/... via the existing Vite /api proxy.
 * No vite.config.ts changes needed — the existing /api → backend rule covers all routes.
 */

const BASE = "/api/changes";

async function changesFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body?.detail ?? body?.message ?? detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export async function proposeChange(
  filePath: string,
  instruction: string
): Promise<ProposeChangeResponse>
// POST /api/changes/propose
// Body: { file_path: filePath, instruction }

export async function getDiff(proposalId: string): Promise<ProposeChangeResponse>
// GET /api/changes/diff/{proposalId}

export async function applyChange(proposalId: string): Promise<ApplyChangeResponse>
// POST /api/changes/apply
// Body: { proposal_id: proposalId, confirmed: true }
// "confirmed: true" is always sent — the user's click IS the confirmation

export async function rejectChange(proposalId: string): Promise<{ ok: boolean }>
// POST /api/changes/reject
// Body: { proposal_id: proposalId }
```

---

### New Hook (`frontend/src/hooks/usePendingChanges.ts`)

**Owned exclusively by `ChangesPanel`** — single instance, no prop drilling.

```typescript
interface UsePendingChangesReturn {
  propose: (filePath: string, instruction: string) => Promise<void>;
  approve: (proposalId: string) => Promise<void>;
  reject: (proposalId: string) => Promise<void>;
  isProposing: boolean;
  isApplying: Record<string, boolean>;  // keyed by proposalId
}
```

**`propose(filePath, instruction)`**:
1. Guard: if `!filePath` → log warning and return (should never happen; `AssistantPanel` guards).
2. Set `isProposing = true`.
3. `const response = await proposeChange(filePath, instruction)`.
4. Construct `ProposedChange` with **explicit mapping**:
   ```typescript
   const change: ProposedChange = {
     id: response.proposal_id,        // explicit: proposal_id → id
     filePath: response.file_path,    // explicit: file_path → filePath
     description: response.summary,  // explicit: summary → description
     language: response.language,
     status: "pending",
     diff: response,                  // store full payload for DiffViewer
   };
   ```
5. Dispatch `ADD_PENDING_CHANGE` with `change`.
6. Dispatch `SET_WORKFLOW_TAB` → `"changes"` (auto-navigate).
7. Dispatch `SET_PENDING_PROPOSAL_REQUEST` → `null` (clear the trigger).
8. `addActivity({ message: \`Code change proposed for ${filePath}\`, type: "info" })`.
9. Clear `isProposing`.
10. On error: `addActivity({ message: \`Failed to propose change: ${err.message}\`, type: "error" })`; clear `isProposing`.

**`approve(proposalId)`**:
1. Set `isApplying[proposalId] = true`.
2. Dispatch `UPDATE_PENDING_CHANGE(proposalId, { status: "applying" })`.
3. `const response = await applyChange(proposalId)`.
4. On success:
   - Dispatch `UPDATE_PENDING_CHANGE(proposalId, { status: "applied" })`.
   - `addActivity({ message: \`Applied change to ${response.file_path}\`, type: "success" })`.
   *(uses `response.file_path` from `ApplyChangeResponse` — authoritative backend value)*
5. On HTTP 409 error (`err.message.includes("409")` or check status):
   - Dispatch `UPDATE_PENDING_CHANGE(proposalId, { status: "conflict" })`.
   - `addActivity({ message: "Conflict: file changed since proposal. Re-propose.", type: "warn" })`.
6. On other error:
   - Dispatch `UPDATE_PENDING_CHANGE(proposalId, { status: "pending" })` (allow retry).
   - `addActivity({ message: \`Apply failed: ${err.message}\`, type: "error" })`.
7. Clear `isApplying[proposalId]`.

**`reject(proposalId)`**:
1. `await rejectChange(proposalId)`.
2. Dispatch `REMOVE_PENDING_CHANGE(proposalId)`.
3. `addActivity({ message: "Proposed change rejected", type: "info" })`.
4. **No filesystem operation.** Only removes server-side store entry.
5. On error: log to activity; the entry remains visible with its current status.

---

### Updated `AppContext` (`frontend/src/contexts/AppContext.tsx`)

**New action types**:
```typescript
| { type: "ADD_PENDING_CHANGE";          change: ProposedChange }
| { type: "UPDATE_PENDING_CHANGE";       id: string; updates: Partial<ProposedChange> }
| { type: "REMOVE_PENDING_CHANGE";       id: string }
| { type: "SET_PENDING_PROPOSAL_REQUEST"; request: PendingProposalRequest | null }
```

**New reducer cases**:
```typescript
case "ADD_PENDING_CHANGE":
  return { ...state, proposedChanges: [...state.proposedChanges, action.change] };

case "UPDATE_PENDING_CHANGE":
  return {
    ...state,
    proposedChanges: state.proposedChanges.map((c) =>
      c.id === action.id ? { ...c, ...action.updates } : c
    ),
  };

case "REMOVE_PENDING_CHANGE":
  return {
    ...state,
    proposedChanges: state.proposedChanges.filter((c) => c.id !== action.id),
  };

case "SET_PENDING_PROPOSAL_REQUEST":
  return { ...state, pendingProposalRequest: action.request };
```

**`INITIAL_STATE` addition**:
```typescript
pendingProposalRequest: null,
```

**New context methods** (add to `AppContextValue` + `AppProvider`):
```typescript
addPendingChange: (change: ProposedChange) => void;
updatePendingChange: (id: string, updates: Partial<ProposedChange>) => void;
removePendingChange: (id: string) => void;
setPendingProposalRequest: (request: PendingProposalRequest | null) => void;
```

---

### Updated `AssistantPanel` (`frontend/src/components/AssistantPanel.tsx`)

**Change in `handleSend`** — after receiving the `/chat` response:

```typescript
// Phase 6: For modify_code intent, trigger proposal via AppContext (not directly)
if (result.intent === "modify_code" && result.target_file !== null) {
  // Store the (filePath, instruction) pair in AppContext.
  // ChangesPanel's usePendingChanges watches this and calls propose().
  // AssistantPanel NEVER calls propose() or approve() directly.
  setPendingProposalRequest({
    filePath: result.target_file,
    instruction: text,  // original user message; same string that was sent to /chat
  });
}
```

**Guard**: `result.target_file !== null` — the button/dispatch is only triggered when the file was
resolved. If `target_file` is null (file not found), the chat response already contains
`error=True` guidance from `ExplanationService` and no proposal is triggered.

**`AssistantPanel` never calls**:
- `propose()` — dispatches `SET_PENDING_PROPOSAL_REQUEST` instead.
- `approve()` — approval is exclusively in `ChangesPanel`.
- `reject()` — rejection is exclusively in `ChangesPanel`.

---

### Updated `ChangesPanel` (`frontend/src/components/ChangesPanel.tsx`)

**Hook ownership**: `ChangesPanel` is the **only** component that instantiates `usePendingChanges`.

**New effect** (watches `pendingProposalRequest`):
```typescript
const { state, setWorkflowTab, setPendingProposalRequest } = useApp();
const { propose, approve, reject, isProposing, isApplying } = usePendingChanges();

// Watch for a proposal request from AssistantPanel
useEffect(() => {
  if (state.pendingProposalRequest) {
    const { filePath, instruction } = state.pendingProposalRequest;
    // propose() internally clears the request via SET_PENDING_PROPOSAL_REQUEST → null
    void propose(filePath, instruction);
  }
}, [state.pendingProposalRequest]);
```

**"Changes" tab panel content** (replaces `EmptyState`):
```tsx
{state.proposedChanges.length === 0 ? (
  <EmptyState
    title="No proposed changes yet"
    description="When SilentVoice AI suggests code modifications they will appear here."
  />
) : (
  <ul>
    {state.proposedChanges.map((change) => (
      <li key={change.id}>
        {/* File badge */}
        <code>{change.filePath}</code>
        {/* Description */}
        <span>{change.description}</span>
        {/* Status badge — color-coded */}
        <StatusBadge status={change.status} />

        {/* "View Diff" toggle — only if diff is available */}
        {change.diff !== null && (
          <details>
            <summary>View Diff</summary>
            <DiffViewer chunks={change.diff.chunks} language={change.language} />
          </details>
        )}

        {/* Apply button — only when pending */}
        {change.status === "pending" && (
          <button
            onClick={() => void approve(change.id)}
            disabled={isApplying[change.id]}
          >
            {isApplying[change.id] ? "Applying…" : "Apply"}
          </button>
        )}

        {/* Reject button — only when pending */}
        {change.status === "pending" && (
          <button onClick={() => void reject(change.id)}>
            Reject
          </button>
        )}

        {/* Conflict notice */}
        {change.status === "conflict" && (
          <p>File changed on disk. Re-send your modification request to re-propose.</p>
        )}
      </li>
    ))}
  </ul>
)}
```

**Null guard on `DiffViewer`**: `change.diff !== null` is checked before rendering — TypeScript
guarantees `change.diff.chunks` is non-null inside this branch.

---

### Updated `ChatMessage.tsx`

Add `modify_code` to `INTENT_LABELS`:
```typescript
const INTENT_LABELS: Record<string, string> = {
  // ... existing entries ...
  modify_code: "Propose change",   // Phase 6
};
```

No other changes to `ChatMessage.tsx`. The "Propose Change" action is handled by `AssistantPanel`
dispatching to `AppContext`, not by `ChatMessage` rendering a button.

---

### New Component: `DiffViewer` (`frontend/src/components/DiffViewer.tsx`)

**Props**:
```typescript
interface DiffViewerProps {
  chunks: DiffChunk[];    // guaranteed non-null by caller (ChangesPanel guards on change.diff !== null)
  language: string;
}
```

**Renders**: Monospace scrollable table with columns: old line number | new line number | content.

Row colors:
- `"added"` → `bg-green-900/30 text-green-300`
- `"removed"` → `bg-red-900/30 text-red-300`
- `"context"` → `bg-transparent text-text-muted`

Chunk header row: `@@ -old_start,old_count +new_start,new_count @@` in `text-text-muted bg-surface-2`.

Accessibility: `role="table"`, `aria-label="Code diff"`, `aria-rowcount={total line count}`,
keyboard-scrollable container with `tabIndex={0}`.

No external diff library — renders directly from `DiffChunk[]` received from the backend.

---

## G. INTENT CLASSIFIER CHANGES

**File**: `backend/app/services/intent_classifier.py`

### New Enum Value

```python
class Intent(str, Enum):
    EXPLAIN_FILE = "explain_file"
    SUMMARIZE_FILE = "summarize_file"
    EXPLAIN_DEPENDENCIES = "explain_dependencies"
    PROJECT_OVERVIEW = "project_overview"
    FIND_DEPENDENTS = "find_dependents"
    EXPLAIN_RELATIONSHIP = "explain_relationship"
    SHOW_RELATED = "show_related"
    ONBOARDING_START = "onboarding_start"
    ARCHITECTURE_OVERVIEW = "architecture_overview"
    SETUP_GUIDANCE = "setup_guidance"
    BEGINNER_TASKS = "beginner_tasks"
    MODIFY_CODE = "modify_code"    # Phase 6 — insert before UNSUPPORTED
    UNSUPPORTED = "unsupported"    # must remain last
```

### New Pattern (insert immediately before the `EXPLAIN_FILE` pattern)

```python
# ── Phase 6: Modify / edit code in a file ────────────────────────────────────
(re.compile(
    r"\b("
    r"(modify|change|update|edit|refactor|fix|add|remove|rename|replace|rewrite)\s+(the\s+)?"
    r"(file|code|function|class|method|variable|import|comment|docstring|type\s+hint|logic|error|bug|test)"
    r"|add\s+(a\s+)?(function|method|class|import|parameter|argument|type\s+hint|docstring|comment|error\s+handling|return\s+type)"
    r"|remove\s+(the\s+)?(function|method|class|import|parameter|dead\s+code|unused\s+import)"
    r"|fix\s+(the\s+)?(bug|error|issue|typo|lint|type\s+error|import)"
    r"|make\s+\S+\s+(async|typed|simpler|faster|safer|more\s+readable)"
    r"|convert\s+(to|from)\s+\w+"
    r"|extract\s+(a\s+)?(function|method|class|constant)"
    r"|rewrite\s+(this|the\s+)?(file|function|class|method|logic)?"
    r")\b",
    re.I,
), Intent.MODIFY_CODE),
```

### `is_file_intent` Update

```python
@property
def is_file_intent(self) -> bool:
    return self.intent in (
        Intent.EXPLAIN_FILE,
        Intent.SUMMARIZE_FILE,
        Intent.EXPLAIN_DEPENDENCIES,
        Intent.FIND_DEPENDENTS,
        Intent.EXPLAIN_RELATIONSHIP,
        Intent.SHOW_RELATED,
        Intent.MODIFY_CODE,     # Phase 6
    )
```

### `UNSUPPORTED` Fallback Message Update

Add `"Modify Login.jsx to add type hints"` to the example list in the fallback `explanation` string.

---

## H. TEST PLAN (`test_phase6.py` — 39 tests)

### Preamble Fixture (applies to ALL tests)

```python
import pytest
from app.services.pending_change_store import get_store

@pytest.fixture(autouse=True)
def clear_pending_store():
    """Reset the global store before and after every test."""
    s = get_store()
    s._records.clear()
    s._insertion_order.clear()
    yield
    s._records.clear()
    s._insertion_order.clear()
```

### Intent Classification (Tests 1–9)

Tests 1–7 as parametrize cases; tests 8–9 are non-regression edge cases:

```
test_modify_code_intent_classification (parametrize):
  [1] "Modify Login.jsx to add type hints"           → MODIFY_CODE
  [2] "Fix the bug in App.jsx"                       → MODIFY_CODE
  [3] "Add a function to utils.py"                   → MODIFY_CODE
  [4] "Refactor Dashboard.jsx"                       → MODIFY_CODE
  [5] "Rewrite the login handler in Login.jsx"       → MODIFY_CODE
  [6] "Remove unused imports from main.py"           → MODIFY_CODE
  [7] "Extract a function from helpers.ts"           → MODIFY_CODE

test_modify_code_is_file_intent
  [8] result.is_file_intent is True for MODIFY_CODE

test_modify_code_non_regression_edge_cases (parametrize):
  [9a] "Fix this"         → UNSUPPORTED (no code-noun, no file ref)
  [9b] "Show me the code" → EXPLAIN_FILE (not MODIFY_CODE)
```

### PendingChangeStore (Tests 10–15)

```
[10] test_store_put_and_get                       — put(record) → get(id) returns same record
[11] test_store_remove                            — put → remove → get returns None
[12] test_store_remove_nonexistent_returns_false  — remove("bad-id") returns False, no exception
[13] test_store_max_capacity_evicts_oldest        — put 51 records → oldest evicted, len == 50
[14] test_store_get_nonexistent_returns_none      — get("no-such-id") → None
[15] test_store_cleanup_expired                   — records older than TTL removed; count returned
```

### CodeModificationService — unit tests with mocked Groq (Tests 16–25)

```
[16] test_propose_returns_propose_change_response
     Mock Groq returns valid content → ProposeChangeResponse with proposal_id, chunks

[17] test_propose_computes_diff_chunks
     Diff contains "added", "removed", "context" kinds; non-empty list

[18] test_propose_stores_sha256_hash
     record.original_hash == sha256(original_content.encode("utf-8")).hexdigest()

[19] test_propose_resolved_abs_path_stored
     record.resolved_abs_path is absolute and passes relative_to(project_root)

[20] test_propose_summary_derived_from_instruction
     summary == instruction[:120].replace("\n", " ")

[21] test_propose_rejects_path_traversal
     file_path="../secret.py" raises ValueError before any file is read

[22] test_propose_rejects_nonexistent_file
     file_path="no_such_file.py" raises FileNotFoundError

[23] test_propose_rejects_protected_file_env
     file_path=".env" raises ProtectedFileError

[24] test_propose_strips_code_fence_from_groq
     Groq returns "```python\ndef f(): pass\n```" → new_content == "def f(): pass"

[25] test_propose_rejects_malformed_ai_output_empty
     Groq returns "" → raises ValueError("LLM returned empty content")
```

### Apply Handler — unit / integration tests (Tests 26–33)

```
[26] test_apply_requires_confirmed_true
     ApplyChangeRequest(proposal_id="x"*36, confirmed=False) → ValidationError

[27] test_apply_unknown_proposal_id_returns_404
     POST /changes/apply with random UUID, confirmed=True → 404

[28] test_apply_stale_file_returns_409
     Propose file; write different content to disk; apply → 409
     Response detail contains "File was modified"

[29] test_apply_writes_file_content_to_disk
     Propose valid change (mock Groq); apply → file on disk == record.new_content

[30] test_apply_uses_resolved_abs_path_not_request_body
     record.resolved_abs_path is used for the write; no path field in ApplyChangeRequest

[31] test_apply_removes_proposal_from_store_after_write
     After successful apply: GET /changes/diff/{id} → 404

[32] test_apply_cleans_up_tmp_file_on_success
     After apply: no .silentvoice_tmp file remains on disk

[33] test_reject_proposal_writes_nothing
     Propose; reject via POST /changes/reject; read original file → unchanged content
```

### API Endpoint Tests (Tests 34–37)

```
[34] test_api_propose_returns_200_with_diff
     POST /api/changes/propose → 200, body has proposal_id (UUID), chunks list, summary

[35] test_api_propose_rejects_traversal_path
     POST /changes/propose file_path="../etc/passwd" → 422 (Pydantic) or 400

[36] test_api_diff_retrieval_by_id
     POST propose → extract proposal_id; GET /changes/diff/{id} → 200, same chunks

[37] test_api_diff_unknown_id_returns_404
     GET /changes/diff/00000000-0000-0000-0000-000000000000 → 404
```

### Security / Adversarial Tests (Tests 38–39)

```
[38] test_security_protected_files_blocked (parametrize):
     [38a] file_path=".env"    → POST /propose returns 400
     [38b] file_path="id_rsa"  → POST /propose returns 400
     [38c] file_path=".git/config" → POST /propose returns 400 (traversal rejected at schema)

[39] test_api_chat_modify_code_returns_non_error_response
     POST /api/assistant/chat {"message": "Modify Login.jsx to add type hints"}
     → 200
     → body["intent"] == "modify_code"
     → body["error"] == false
     → body["target_file"] is not None
     → "Login" in body["target_file"]
     (backward-compatibility gate for the ExplanationService MODIFY_CODE branch)
```

**Total: 39 numbered tests** (tests 1–7 are parametrize rows under one test function;
test 9 has 2 sub-cases; test 38 has 3 sub-cases — all count toward the 39 distinct assertions).

---

## I. SECURITY CHECKLIST

All 13 original requirements + all 24 review issues mapped to final implementation:

| # | Requirement / Review Issue | Implementation | Status |
|---|---------------------------|---------------|--------|
| R1 | `safe_read` read-only | Write path uses `path_security._validate_write_target` exclusively | ✓ |
| R2 | SHA-256 hash stored | `PendingChangeRecord.original_hash` = `sha256(content.encode("utf-8")).hexdigest()` | ✓ |
| R3 | Hash comparison → 409 | `/apply` step 4: `read_text(encoding="utf-8")` + hash compare | ✓ |
| R4 | Explicit approval; voice cannot approve | `confirmed` no default; voice → `/chat` → AppContext → `ChangesPanel.propose()` only | ✓ |
| R5 | LLM output untrusted | Strip fences; validate non-empty; write path only from `resolved_abs_path` | ✓ |
| R6 | Target file identity locked | `resolved_abs_path` set once at propose time; never from LLM or `/apply` body | ✓ |
| R7 | No shell commands | Instruction is JSON string to Groq REST API only | ✓ |
| R8 | Single-file only | One `file_path` in `ModifyRequest`; no batch fields | ✓ |
| R9 | Protected files in write path | `path_security._check_protected` called at propose AND apply | ✓ |
| R10 | Bounded store + UUID IDs | `max_pending_changes=50`; `uuid.uuid4()`; `get_store()` accessor | ✓ |
| R11 | Reject writes nothing | `/reject` calls `get_store().remove()` only | ✓ |
| R12 | Apply validates before write | Steps 1→5 all pass before `os.replace()` | ✓ |
| R13 | Adversarial test coverage | 39 tests (see Section H) | ✓ |
| I1 | `_validate_write_target` in correct module | Lives in `utils/path_security.py`; imported by route and service | ✓ |
| I3 | `_strip_fences` robust regex | `[\w+\-#.]*` handles uppercase, digits, symbols; empty fallback | ✓ |
| I4 | SHA-256 encoding consistency | Both reads use `read_text(encoding="utf-8")`; hash uses `.encode("utf-8")` | ✓ |
| I5 | Atomic write cleanup | `Path(tmp_path).unlink(missing_ok=True)` in `finally` block | ✓ |
| I6 | Store cleared between tests | `autouse` fixture `clear_pending_store` | ✓ |
| I7+I22 | `ExplanationService` MODIFY_CODE branch | Added in Section E; `error=False`, `target_file` populated | ✓ |
| I8 | `ChatMessage.tsx` INTENT_LABELS | `modify_code: "Propose change"` added | ✓ |
| I9 | `usePendingChanges` ownership | Option A: single instance in `ChangesPanel`; AppContext bridges | ✓ |
| I10 | UUID validation on path params | `Path(..., min_length=36, max_length=36)` on `/diff/{proposal_id}` | ✓ |
| I11 | DiffViewer null guard | `change.diff !== null` guard before rendering `<DiffViewer>` | ✓ |
| I12 | `proposal_id` → `id` mapping | Explicit in `usePendingChanges.propose`: `id: response.proposal_id` | ✓ |
| I13 | Non-regression intent tests | Tests 9a, 9b added as edge cases | ✓ |
| I14 | Voice test moved to backend | Test 39 replaces voice test with `/chat` backward-compat test | ✓ |
| I15 | `_check_protected` implementation | fnmatch for names; startsWith for dirs; `.env` prefix check | ✓ |
| I16 | `target_file !== null` guard | `AssistantPanel`: dispatch only when `result.target_file !== null` | ✓ |
| I17 | Activity log uses `response.file_path` | `approve` step 4: `response.file_path` from `ApplyChangeResponse` | ✓ |
| I18 | Size checked before read | `propose` step 7: `stat().st_size` check before `read_text()` | ✓ |
| I19 | `summary` generated | `summary = instruction[:120].replace("\n", " ")` at step 15 | ✓ |
| I21 | `get_store()` accessor | Public `get_store()` function; `_STORE` private | ✓ |
| I23 | UTF-8 write specification | `Path(tmp_path).write_text(record.new_content, encoding="utf-8")` | ✓ |
| I24 | `DiffLine.kind` Literal type | `Literal["context", "added", "removed"]` in Pydantic schema | ✓ |

---

## J. IMPLEMENTATION ORDER (exact file-by-file sequence)

### Pass 1 — Pure additions, no existing file modified
```
1.  backend/app/utils/path_security.py           [NEW]
2.  backend/app/schemas/changes.py               [NEW]
3.  backend/app/services/pending_change_store.py [NEW]
```
**Gate**: `python -c "from app.utils.path_security import _validate_write_target; from app.schemas.changes import ModifyRequest; from app.services.pending_change_store import get_store"` runs without error.

### Pass 2 — New service (depends on Pass 1)
```
4.  backend/app/config.py                                [MODIFY] — +2 settings fields
5.  backend/app/services/groq_service.py                 [MODIFY] — +1 method
6.  backend/app/services/code_modification_service.py    [NEW]
```
**Gate**: Tests 16–25 pass (with mocked Groq and real filesystem temp files).

### Pass 3 — Intent + explanation wiring (depends on Pass 2)
```
7.  backend/app/services/intent_classifier.py            [MODIFY] — +1 enum value, +1 pattern, +1 is_file_intent entry
8.  backend/app/services/explanation_service.py          [MODIFY] — +1 MODIFY_CODE branch in handle()
```
**Gate**: Tests 1–9 pass; test 39 passes.

### Pass 4 — API routes (depends on Pass 1–3)
```
9.  backend/app/api/routes/changes.py                    [NEW] — 4 handlers
10. backend/app/api/router.py                            [MODIFY] — +2 lines
```
**Gate**: Tests 26–38 pass. Run full `pytest` — 0 regressions in Phase 1–5 suite.

### Pass 5 — Test file (validates Pass 1–4)
```
11. backend/tests/test_phase6.py                         [NEW] — 39 tests + autouse fixture
```
**Gate**: `pytest backend/tests/test_phase6.py` → 39/39 pass.

### Pass 6 — Frontend types (no backend dependency)
```
12. frontend/src/types/index.ts                          [MODIFY] — new interfaces + extended ProposedChange + PendingProposalRequest
```
**Gate**: `tsc --noEmit` exits 0.

### Pass 7 — Frontend state (depends on Pass 6)
```
13. frontend/src/contexts/AppContext.tsx                 [MODIFY] — 4 new actions + reducer cases + context methods
```
**Gate**: `tsc --noEmit` exits 0.

### Pass 8 — Frontend API + hook (depends on Pass 6–7)
```
14. frontend/src/services/changesApi.ts                  [NEW]
15. frontend/src/hooks/usePendingChanges.ts              [NEW]
```
**Gate**: `tsc --noEmit` exits 0.

### Pass 9 — Frontend components (depends on Pass 6–8)
```
16. frontend/src/components/DiffViewer.tsx               [NEW]
17. frontend/src/components/ChatMessage.tsx              [MODIFY] — +1 INTENT_LABELS entry
18. frontend/src/components/ChangesPanel.tsx             [MODIFY] — usePendingChanges + effect + list render
19. frontend/src/components/AssistantPanel.tsx           [MODIFY] — SET_PENDING_PROPOSAL_REQUEST dispatch
```
**Gate**: `npm run build` exits 0.

### Pass 10 — End-to-end validation
```
Manual walkthrough + full test suite (see Milestone 6 below)
```
**Gate**: `pytest` all phases → 0 failures; `npm run build` → 0 errors.

---

## K. MILESTONE VALIDATION STEPS

### Milestone 1 (after Pass 3): Backend Core
- `pytest backend/tests/test_phase6.py -k "intent or store or propose"` → tests 1–25 pass.
- `pytest backend/tests/` (full Phase 1–5 suite) → 0 regressions.

### Milestone 2 (after Pass 4–5): Backend Routes + Full Test Suite
- `pytest backend/tests/test_phase6.py` → 39/39 pass.
- `pytest backend/tests/` → 0 regressions across all phases.

### Milestone 3 (after Pass 6–8): Frontend Types + State + Services
- `tsc --noEmit` → exits 0, no errors.

### Milestone 4 (after Pass 9): Frontend Components
- `npm run build` → exits 0.
- `tsc --noEmit` → exits 0.

### Milestone 5: End-to-End Manual Walkthrough
1. Start backend (`uvicorn`) + frontend (`npm run dev`).
2. Send "Modify Login.jsx to add a JSDoc comment to every exported function".
3. Verify `/chat` response: `intent="modify_code"`, `error=false`, `target_file="src/components/Login.jsx"`.
4. Verify `ChangesPanel` "Changes" tab auto-activates; proposal entry appears.
5. Click "View Diff" → `DiffViewer` renders added/removed/context lines.
6. Click "Apply" → hash check passes → file written → status badge shows "applied".
7. Verify `.silentvoice_tmp` file does **not** exist after apply.
8. Propose again on a second request; in a separate terminal modify `Login.jsx`; click "Apply" → HTTP 409 → status badge shows "conflict".
9. Propose a third change; click "Reject" → entry removed; open `Login.jsx` → original content unchanged.
10. Attempt `POST /api/changes/propose {"file_path": "../backend/app/config.py"}` → HTTP 422 (Pydantic traversal rejection).
11. Attempt `POST /api/changes/propose {"file_path": ".env"}` → HTTP 400 (ProtectedFileError).
12. Run `pytest backend/tests/` → all phases pass.
13. Run `npm run build` → exits 0.

---

## Sub-Tasks (for agent-mode implementation)

### Sub-Task 1 — `utils/path_security.py`
- **Expected outcome**: `_validate_write_target`, `_check_protected`, `ProtectedFileError` importable; all pattern checks correct.
- **Status**: [ ] pending

### Sub-Task 2 — `schemas/changes.py`
- **Expected outcome**: All 6 models parse correctly; `ModifyRequest` rejects `../x`, `/abs`, null bytes; `ApplyChangeRequest` rejects `confirmed=False`; `DiffLine.kind` validates at runtime.
- **Status**: [ ] pending

### Sub-Task 3 — `pending_change_store.py` + `config.py`
- **Expected outcome**: Tests 10–15 pass; `get_store()` returns singleton; `clear_pending_store` fixture works.
- **Status**: [ ] pending

### Sub-Task 4 — `groq_service.py` addition
- **Expected outcome**: `propose_code_modification` callable with mocked `complete`; system prompt forbids prose.
- **Status**: [ ] pending

### Sub-Task 5 — `code_modification_service.py`
- **Expected outcome**: Tests 16–25 pass; size checked before read; hash stored; summary derived; fences stripped; abs path locked.
- **Status**: [ ] pending

### Sub-Task 6 — `intent_classifier.py` + `explanation_service.py`
- **Expected outcome**: Tests 1–9 + 39 pass; `/chat` with "Modify Login.jsx" returns `error=false`.
- **Status**: [ ] pending

### Sub-Task 7 — `api/routes/changes.py` + `router.py`
- **Expected outcome**: Tests 26–38 pass; full pytest suite green.
- **Status**: [ ] pending

### Sub-Task 8 — `test_phase6.py`
- **Expected outcome**: 39/39 pass; autouse fixture prevents cross-contamination.
- **Status**: [ ] pending

### Sub-Task 9 — Frontend types + AppContext
- **Expected outcome**: `tsc --noEmit` exits 0; `pendingProposalRequest` in state.
- **Status**: [ ] pending

### Sub-Task 10 — `changesApi.ts` + `usePendingChanges.ts`
- **Expected outcome**: `tsc --noEmit` exits 0; explicit `proposal_id → id` mapping present.
- **Status**: [ ] pending

### Sub-Task 11 — Frontend components
- **Expected outcome**: `npm run build` exits 0; Changes tab renders; DiffViewer guard enforced; AssistantPanel never calls `approve`.
- **Status**: [ ] pending

### Sub-Task 12 — End-to-end validation
- **Expected outcome**: All Milestone 5 steps pass manually.
- **Status**: [ ] pending
