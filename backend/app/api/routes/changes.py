"""
changes.py — Phase 6 API routes for the code-modification proposal pipeline.

Endpoints:
  POST /api/changes/propose        → Generate a modification proposal for a file
  GET  /api/changes/diff/{id}      → Re-fetch an existing proposal (no Groq call)
  POST /api/changes/apply          → Write approved change to disk (atomic)
  POST /api/changes/reject         → Discard a proposal (no filesystem operation)

Security responsibilities of this module:
  • /propose: delegates all filesystem and protection checks to
    CodeModificationService.propose().
  • /apply:  performs an independent write-path re-validation via
    _validate_write_target() AFTER the store lookup and hash check — this
    catches any filesystem change (e.g. a symlink created between propose and
    apply) that occurred since the proposal was stored.
  • /reject:  zero filesystem operations — only removes the store entry.
  • The file path used in /apply comes exclusively from the stored
    PendingChangeRecord.resolved_abs_path, never from the request body.
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Path as FPath

from app.config import settings
from app.schemas.changes import (
    ApplyChangeRequest,
    ApplyChangeResponse,
    ModifyRequest,
    ProposeChangeResponse,
    RejectRequest,
)
from app.services.code_modification_service import (
    CodeModificationService,
    FileTooLargeError,
)
from app.services.groq_service import GroqError
from app.services.pending_change_store import get_store
from app.utils.path_security import ProtectedFileError, _validate_write_target

router = APIRouter()
logger = logging.getLogger("silentvoice.api.changes")


# ── POST /propose ─────────────────────────────────────────────────────────────

@router.post(
    "/propose",
    response_model=ProposeChangeResponse,
    summary="Generate an AI code-modification proposal for a single file",
)
async def propose(body: ModifyRequest) -> ProposeChangeResponse:
    """
    Generate a code-modification proposal.

    Processing order:
      1. Pydantic validates ModifyRequest (path traversal, absolute paths, etc.)
      2. CodeModificationService.propose() runs the full pipeline.
      3. HTTP error codes map to domain exceptions.

    Error codes:
      400 — path traversal escape or other validation error
      403 — target matches a protected file pattern
      404 — file not found
      413 — file exceeds max_file_size_for_ai
      422 — Pydantic validation failure (bad file_path or missing fields)
      500 — Groq API failure or unexpected error
    """
    try:
        svc = CodeModificationService()
        return await svc.propose(body.file_path, body.instruction)
    except ProtectedFileError as exc:
        logger.warning("Propose rejected (403): %s", exc)
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        logger.warning("Propose rejected (400): %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        logger.warning("Propose rejected (404): %s", exc)
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {body.file_path}",
        )
    except FileTooLargeError as exc:
        logger.warning("Propose rejected (413): %s", exc)
        raise HTTPException(status_code=413, detail=str(exc))
    except GroqError as exc:
        logger.error("Groq error in /propose: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error in /propose")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


# ── GET /diff/{proposal_id} ───────────────────────────────────────────────────

@router.get(
    "/diff/{proposal_id}",
    response_model=ProposeChangeResponse,
    summary="Re-fetch a pending proposal by ID (idempotent, no Groq call)",
)
async def get_diff(
    proposal_id: str = FPath(..., min_length=36, max_length=36),
) -> ProposeChangeResponse:
    """
    Retrieve the diff payload for an existing proposal.

    Never touches the filesystem — reads only from the in-memory store.

    Error codes:
      404 — proposal not found or expired
    """
    record = get_store().get(proposal_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Proposal '{proposal_id}' not found or has expired.",
        )
    return ProposeChangeResponse(
        proposal_id=record.id,
        file_path=record.file_path,
        language=record.language,
        original_lines=len(record.original_content.splitlines()),
        new_lines=len(record.new_content.splitlines()),
        chunks=record.diff_chunks,
        summary=record.summary,
        created_at=record.created_at.isoformat(),
    )


# ── POST /apply ───────────────────────────────────────────────────────────────

@router.post(
    "/apply",
    response_model=ApplyChangeResponse,
    summary="Write an approved proposal to disk (the only endpoint that writes files)",
)
async def apply(body: ApplyChangeRequest) -> ApplyChangeResponse:
    """
    Apply an approved proposal to disk using an atomic write.

    Processing order (all steps must pass before any write):
      1. Pydantic validates ApplyChangeRequest — confirmed=False → 422.
      2. Resolve project root.
      3. Look up proposal in store → 404 if missing.
      4. Hash check: re-read file, compare SHA-256 → 409 if stale.
      5. Write-path security re-validation (_validate_write_target) → 400.
      6. Atomic write: write to .silentvoice_tmp → os.replace → unlink tmp.
      7. Remove proposal from store.
      8. Return ApplyChangeResponse.

    Error codes:
      400 — write-path security violation (protected file, symlink, etc.)
      404 — proposal not found or expired
      409 — file was modified on disk since the proposal was created
      422 — Pydantic validation failure (confirmed=False or bad proposal_id)
      500 — filesystem write failure
    """
    proposal_id = body.proposal_id
    root = Path(settings.project_root_path).resolve()

    # Step 3: Store lookup
    record = get_store().get(proposal_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Proposal '{proposal_id}' not found or has expired.",
        )

    abs_path = Path(record.resolved_abs_path)

    # Step 4: Hash check — detect if file was modified since proposal was created
    try:
        current_content = abs_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Cannot read file for hash check: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Cannot read file for hash verification: {exc}",
        )
    current_hash = hashlib.sha256(current_content.encode("utf-8")).hexdigest()
    if current_hash != record.original_hash:
        logger.warning(
            "Stale proposal %s: file '%s' was modified after proposal was created",
            proposal_id,
            record.file_path,
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "File was modified after proposal was created. "
                "Re-propose to pick up the latest version."
            ),
        )

    # Step 5: Write-path security re-validation (independent second check)
    try:
        _validate_write_target(abs_path, root)
    except (ProtectedFileError, ValueError) as exc:
        logger.warning("Apply rejected by write-path security (400): %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))

    # Step 6: Atomic write
    tmp_path = abs_path.with_suffix(abs_path.suffix + ".silentvoice_tmp")
    try:
        tmp_path.write_text(record.new_content, encoding="utf-8")
        os.replace(str(tmp_path), str(abs_path))
        bytes_written = len(record.new_content.encode("utf-8"))
        logger.info(
            "Applied proposal %s to '%s' (%d bytes)",
            proposal_id,
            record.file_path,
            bytes_written,
        )
    except OSError as exc:
        logger.error("Write failure for proposal %s: %s", proposal_id, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to write file: {exc}",
        )
    finally:
        # Always clean up the tmp file — even if os.replace succeeded or failed
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass  # best-effort cleanup; do not mask the original exception

    # Step 7: Remove proposal from store
    get_store().remove(proposal_id)

    # Step 8: Return response
    return ApplyChangeResponse(
        ok=True,
        file_path=record.file_path,
        bytes_written=bytes_written,
        proposal_id=proposal_id,
    )


# ── POST /reject ──────────────────────────────────────────────────────────────

@router.post(
    "/reject",
    summary="Discard a pending proposal (writes nothing to disk)",
)
async def reject(body: RejectRequest) -> dict:
    """
    Discard a pending proposal.

    Zero filesystem operations — only removes the store entry.

    Error codes:
      404 — proposal not found or expired
    """
    removed = get_store().remove(body.proposal_id)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"Proposal '{body.proposal_id}' not found or has expired.",
        )
    logger.info("Rejected proposal %s", body.proposal_id)
    return {"ok": True}
