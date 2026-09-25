"""
Phase 6 — Changes API schemas.

Request and response models for the code-modification proposal pipeline:
  POST /api/changes/propose  → ModifyRequest → ProposeChangeResponse
  GET  /api/changes/diff/{id} → ProposeChangeResponse
  POST /api/changes/apply    → ApplyChangeRequest → ApplyChangeResponse
  POST /api/changes/reject   → RejectRequest → {"ok": true}

Security notes:
  • ModifyRequest.file_path is validated before any filesystem access:
      - Rejects path traversal (..)
      - Rejects null bytes and control characters
      - Rejects shell metacharacters (<>|*?)
      - Rejects absolute paths (both POSIX "/" and Windows "C:" / "\\")
  • ApplyChangeRequest.confirmed has NO default value — callers must be
    explicit, preventing accidental approval via missing field.
  • DiffLine.kind uses Literal so Pydantic validates it at parse time;
    a malformed _compute_diff output will raise a 422 before any route
    handler logic executes.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# ── Path validation ───────────────────────────────────────────────────────────
# Reuse the same regex as ChatRequest.selected_file in schemas/assistant.py.
# Matches: ".." sequences, C0 control characters (null bytes etc.), and the
# shell metacharacters <  >  |  *  ? that have no place in a relative file path.
_TRAVERSAL_RE = re.compile(r"\.\.|[\x00-\x1f]|[<>|*?]")


# ── Request schemas ───────────────────────────────────────────────────────────

class ModifyRequest(BaseModel):
    """
    Body for POST /api/changes/propose.

    Instructs the backend to generate a code-modification proposal for a single
    project file.  Both fields are validated strictly before any filesystem access.
    """

    file_path: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description=(
            "Relative path from the project root, e.g. 'src/components/Login.jsx'. "
            "Must be relative — absolute paths, path traversal, and shell "
            "metacharacters are rejected."
        ),
    )
    instruction: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description=(
            "Natural-language description of the desired change, "
            "e.g. 'Add JSDoc comments to every exported function'."
        ),
    )

    @field_validator("file_path")
    @classmethod
    def _validate_path(cls, v: str) -> str:
        """
        Reject unsafe file paths before any filesystem access.

        Blocks:
          - Path traversal sequences (..)
          - Null bytes and C0 control characters
          - Shell metacharacters: < > | * ?
          - Absolute POSIX paths (starting with /)
          - Absolute Windows paths (C: drive letter prefix)
          - UNC / Windows absolute paths (starting with \\)
        """
        if _TRAVERSAL_RE.search(v):
            raise ValueError(
                "file_path contains invalid characters or path traversal sequences"
            )
        # Reject absolute POSIX path
        if v.startswith("/"):
            raise ValueError("file_path must be a relative path, not an absolute POSIX path")
        # Reject absolute Windows drive-letter path (e.g. "C:\..." or "C:/...")
        if len(v) > 1 and v[1] == ":":
            raise ValueError("file_path must be a relative path, not an absolute Windows path")
        # Reject UNC or backslash-prefixed Windows path
        if v.startswith("\\"):
            raise ValueError("file_path must be a relative path")
        return v


class ApplyChangeRequest(BaseModel):
    """
    Body for POST /api/changes/apply.

    Requires both a valid proposal_id AND confirmed=True.  The absence of a
    default on ``confirmed`` means that omitting it causes a Pydantic
    ValidationError (HTTP 422) rather than silently defaulting to True or False.
    """

    proposal_id: str = Field(
        ...,
        min_length=36,
        max_length=36,
        description="UUID4 string identifying the pending proposal to apply.",
    )
    confirmed: bool = Field(
        ...,
        description=(
            "Must be true. Explicitly requiring this field prevents accidental "
            "approval caused by a missing or default value."
        ),
    )

    @field_validator("confirmed")
    @classmethod
    def _must_confirm(cls, v: bool) -> bool:
        """Reject requests that do not carry an affirmative confirmation."""
        if not v:
            raise ValueError(
                "confirmed must be true to apply a change; "
                "set confirmed=true to proceed"
            )
        return v


class RejectRequest(BaseModel):
    """Body for POST /api/changes/reject."""

    proposal_id: str = Field(
        ...,
        min_length=36,
        max_length=36,
        description="UUID4 string identifying the pending proposal to discard.",
    )


# ── Diff representation ───────────────────────────────────────────────────────

class DiffLine(BaseModel):
    """
    A single line within a diff chunk.

    ``kind`` is validated as a Literal at parse time — Pydantic raises a
    ValidationError (HTTP 422) if _compute_diff emits an unexpected value,
    which prevents corrupted diff data from reaching the frontend.
    """

    kind: Literal["context", "added", "removed"] = Field(
        ...,
        description=(
            "'added' for lines present only in the new version, "
            "'removed' for lines present only in the original, "
            "'context' for unchanged surrounding lines."
        ),
    )
    line_number_old: Optional[int] = Field(
        None,
        description="1-based line number in the original file. None for added lines.",
    )
    line_number_new: Optional[int] = Field(
        None,
        description="1-based line number in the new file. None for removed lines.",
    )
    content: str = Field(
        ...,
        description="The raw line content, without the leading +/- diff prefix.",
    )


class DiffChunk(BaseModel):
    """
    A contiguous block of changes from the unified diff, including context lines.
    Corresponds to one ``@@ ... @@`` hunk in the unified diff format.
    """

    old_start: int = Field(..., description="Starting line number in the original file (1-based).")
    old_count: int = Field(..., description="Number of lines from the original file in this chunk.")
    new_start: int = Field(..., description="Starting line number in the new file (1-based).")
    new_count: int = Field(..., description="Number of lines from the new file in this chunk.")
    lines: list[DiffLine] = Field(
        ...,
        description="Ordered list of diff lines (context, added, removed) for this chunk.",
    )


# ── Response schemas ──────────────────────────────────────────────────────────

class ProposeChangeResponse(BaseModel):
    """
    Returned by POST /api/changes/propose and GET /api/changes/diff/{proposal_id}.

    Contains everything the frontend needs to render the diff and present the
    approve / reject decision to the user.  The ``resolved_abs_path`` is
    intentionally NOT included — it is stored server-side only in
    PendingChangeRecord and never sent to the client.
    """

    proposal_id: str = Field(
        ...,
        description="UUID4 string. Use this value in ApplyChangeRequest and RejectRequest.",
    )
    file_path: str = Field(
        ...,
        description="Relative path from the project root (display value, not the write path).",
    )
    language: str = Field(
        ...,
        description="Detected language label for the file (e.g. 'python', 'typescript').",
    )
    original_lines: int = Field(..., description="Line count of the original file content.")
    new_lines: int = Field(..., description="Line count of the proposed new content.")
    chunks: list[DiffChunk] = Field(
        ...,
        description="Unified diff represented as structured chunks. May be empty if no changes.",
    )
    summary: str = Field(
        ...,
        description=(
            "Human-readable one-line description of the change, "
            "derived from the first 120 characters of the instruction."
        ),
    )
    created_at: str = Field(
        ...,
        description="ISO-8601 UTC timestamp of when the proposal was created.",
    )


class ApplyChangeResponse(BaseModel):
    """Returned by POST /api/changes/apply on success."""

    ok: bool = Field(..., description="Always true on a successful apply.")
    file_path: str = Field(
        ...,
        description=(
            "Relative path of the file that was written (from the stored record, "
            "not from the request body)."
        ),
    )
    bytes_written: int = Field(
        ...,
        description="Number of UTF-8 bytes written to disk.",
    )
    proposal_id: str = Field(
        ...,
        description="The proposal ID that was applied (for frontend state reconciliation).",
    )
