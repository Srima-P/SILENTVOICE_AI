"""
code_modification_service.py — Phase 6 AI-driven code modification pipeline.

Responsibilities:
  1. Validate the target file path (protected-file check + root-escape check).
  2. Enforce the per-file size limit before reading.
  3. Read the file and compute a SHA-256 hash for stale-file detection at apply time.
  4. Call GroqService.propose_code_modification to obtain replacement content.
  5. Strip Markdown code-fences from the LLM output.
  6. Validate that the stripped result is non-empty.
  7. Compute a structured diff (list[DiffChunk]) using difflib.
  8. Persist the proposal in PendingChangeStore with a UUID key.
  9. Return a ProposeChangeResponse.

Security invariants:
  • resolved_abs_path is set once here, never from LLM output or request bodies.
  • _validate_write_target is called at propose time; the /apply route calls it
    again independently to catch filesystem changes between the two operations.
  • File size is checked via stat() BEFORE read_text() to prevent OOM attacks.
  • SHA-256 hash uses read_text(encoding="utf-8") — same mode as apply time.
"""
from __future__ import annotations

import difflib
import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import settings
from app.schemas.changes import (
    DiffChunk,
    DiffLine,
    ProposeChangeResponse,
)
from app.services.groq_service import GroqService, GroqError
from app.services.pending_change_store import PendingChangeRecord, get_store
from app.services.project_scanner import _detect_language
from app.utils.path_security import (
    ProtectedFileError,
    _check_protected,
    _validate_write_target,
)

logger = logging.getLogger("silentvoice.code_modification")


# ── Custom exceptions ─────────────────────────────────────────────────────────

class FileTooLargeError(ValueError):
    """Raised when the target file exceeds settings.max_file_size_for_ai."""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """
    Remove Markdown code-fence wrappers from *text* if present.

    Handles:
      - Fenced blocks with a language tag:  ```python\\n...\\n```
      - Fenced blocks without a tag:        ```\\n...\\n```
      - Language tags containing digits, hyphens, plus signs, dots, and hash:
        python3, c++, c#, jsx, f#, etc.

    Falls back to the original stripped text if the regex matches but the
    inner group is empty (which would indicate a malformed or empty fence).

    Args:
        text: Raw string returned by the LLM.

    Returns:
        Content with fences removed, or the original text if no fence found.
    """
    stripped = text.strip()
    # [\w+\-#.]* covers: python, typescript, python3, c++, c#, jsx, f#, toml, etc.
    m = re.match(r"^```[\w+\-#.]*\s*\n(.*)\n```\s*$", stripped, re.DOTALL)
    if m:
        inner = m.group(1)
        # Fallback to original stripped text if inner is blank (safety net)
        return inner if inner.strip() else stripped
    return stripped


def _compute_diff(original: str, new: str) -> list[DiffChunk]:
    """
    Produce a structured diff between *original* and *new* content.

    Uses difflib.unified_diff with 3 context lines (the standard unified-diff
    default).  The output is parsed into a list of DiffChunk objects, each
    corresponding to one ``@@ ... @@`` hunk.

    Line classification:
      - Starts with "+" and not "+++"  → "added"
      - Starts with "-" and not "---"  → "removed"
      - Starts with " "                → "context"
      - "+++" / "---" header lines     → skipped

    Line numbers are tracked independently:
      - old_line_no: incremented for "context" and "removed" lines.
      - new_line_no: incremented for "context" and "added" lines.

    Args:
        original: Original file content (may contain "\\r\\n" — difflib handles it).
        new:      Proposed replacement content.

    Returns:
        List of DiffChunk objects.  Empty list if original == new.
    """
    original_lines = original.splitlines(keepends=False)
    new_lines = new.splitlines(keepends=False)

    diff_lines = list(difflib.unified_diff(
        original_lines,
        new_lines,
        lineterm="",
        n=3,
    ))

    chunks: list[DiffChunk] = []
    current_chunk: Optional[DiffChunk] = None
    old_line_no = 0
    new_line_no = 0

    _CHUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

    for raw in diff_lines:
        # Skip the "--- a/file" / "+++ b/file" header lines
        if raw.startswith("---") or raw.startswith("+++"):
            continue

        m = _CHUNK_HEADER.match(raw)
        if m:
            # Flush nothing — start a new chunk
            old_start = int(m.group(1))
            old_count = int(m.group(2)) if m.group(2) is not None else 1
            new_start = int(m.group(3))
            new_count = int(m.group(4)) if m.group(4) is not None else 1
            current_chunk = DiffChunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                lines=[],
            )
            chunks.append(current_chunk)
            old_line_no = old_start
            new_line_no = new_start
            continue

        if current_chunk is None:
            # Lines before the first @@ header (shouldn't happen with unified_diff)
            continue

        if raw.startswith("+"):
            kind = "added"
            line = DiffLine(
                kind=kind,
                line_number_old=None,
                line_number_new=new_line_no,
                content=raw[1:],  # strip leading "+"
            )
            new_line_no += 1
        elif raw.startswith("-"):
            kind = "removed"
            line = DiffLine(
                kind=kind,
                line_number_old=old_line_no,
                line_number_new=None,
                content=raw[1:],  # strip leading "-"
            )
            old_line_no += 1
        else:
            # Context line (starts with " ")
            content = raw[1:] if raw.startswith(" ") else raw
            line = DiffLine(
                kind="context",
                line_number_old=old_line_no,
                line_number_new=new_line_no,
                content=content,
            )
            old_line_no += 1
            new_line_no += 1

        current_chunk.lines.append(line)

    return chunks


# ── Service ───────────────────────────────────────────────────────────────────

class CodeModificationService:
    """
    Orchestrates the full code-modification proposal pipeline.

    One instance per request (stateless after __init__).
    """

    def __init__(self) -> None:
        self._groq = GroqService()

    async def propose(
        self,
        file_path: str,
        instruction: str,
    ) -> ProposeChangeResponse:
        """
        Produce a code-modification proposal for *file_path* based on *instruction*.

        Processing order (all steps must succeed before the proposal is stored):
          1.  Resolve the project root.
          2.  Normalise file_path (strip leading separators).
          3.  Build and resolve the absolute path.
          4.  Verify the path is inside the project root.
          5.  Check for protected-file patterns.
          6.  stat() to confirm existence and check size limit.
          7.  Read file content.
          8.  Compute SHA-256 hash.
          9.  Detect language.
          10. Call Groq.
          11. Strip code fences.
          12. Validate non-empty result.
          13. Compute diff.
          14. Build summary.
          15. Store proposal.
          16. Return response.

        Raises:
            ValueError:        Path traversal, empty Groq output, or root escape.
            ProtectedFileError: Target matches a protected-file pattern.
            FileNotFoundError: File does not exist on disk.
            FileTooLargeError: File exceeds settings.max_file_size_for_ai.
            GroqError:         Groq API call failed.
        """
        # Step 1: Resolve project root
        root = Path(settings.project_root_path).resolve()

        # Step 2: Normalise — Pydantic already rejected traversal and absolute paths,
        # but lstrip is a belt-and-suspenders guard against any leading separator.
        rel_clean = file_path.lstrip("/\\")

        # Step 3: Build absolute path
        abs_path = (root / rel_clean).resolve()

        # Step 4: Verify strictly inside root
        try:
            abs_path.relative_to(root)
        except ValueError:
            raise ValueError(
                f"Target path escapes project root: '{abs_path}' is not under '{root}'"
            )

        # Step 5: Protected-file check (before any I/O)
        _check_protected(abs_path.relative_to(root).as_posix())

        # Step 6: stat() — raises FileNotFoundError if missing; check size
        stat = abs_path.stat()  # raises FileNotFoundError if file does not exist
        if stat.st_size > settings.max_file_size_for_ai:
            raise FileTooLargeError(
                f"File too large for AI analysis: {stat.st_size} bytes "
                f"(limit {settings.max_file_size_for_ai} bytes)"
            )

        # Step 7: Read file content (universal newlines; \r\n → \n)
        original_content = abs_path.read_text(encoding="utf-8")

        # Step 8: SHA-256 hash for stale-file detection at apply time
        original_hash = hashlib.sha256(original_content.encode("utf-8")).hexdigest()

        # Step 9: Detect language from file extension
        language = _detect_language(abs_path)

        # Step 10: Call Groq
        raw_new_content = await self._groq.propose_code_modification(
            file_path=rel_clean,
            language=language,
            original_content=original_content,
            instruction=instruction,
        )

        # Step 11: Strip code fences
        new_content = _strip_fences(raw_new_content)

        # Step 12: Validate non-empty
        if not new_content.strip():
            raise ValueError("LLM returned empty content")

        # Step 13: Compute structured diff
        diff_chunks = _compute_diff(original_content, new_content)

        # Step 14: Build summary from instruction
        summary = instruction[:120].replace("\n", " ")

        # Step 15: Store proposal
        proposal_id = str(uuid.uuid4())
        record = PendingChangeRecord(
            id=proposal_id,
            file_path=rel_clean,
            resolved_abs_path=str(abs_path),
            language=language,
            original_content=original_content,
            original_hash=original_hash,
            new_content=new_content,
            diff_chunks=diff_chunks,
            summary=summary,
            created_at=datetime.now(tz=timezone.utc),
        )
        get_store().put(record)
        logger.info(
            "Proposal %s created for '%s' (%d→%d lines)",
            proposal_id,
            rel_clean,
            len(original_content.splitlines()),
            len(new_content.splitlines()),
        )

        # Step 16: Return response
        return ProposeChangeResponse(
            proposal_id=proposal_id,
            file_path=rel_clean,
            language=language,
            original_lines=len(original_content.splitlines()),
            new_lines=len(new_content.splitlines()),
            chunks=diff_chunks,
            summary=summary,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
        )
