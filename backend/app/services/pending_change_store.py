"""
pending_change_store.py — in-memory store for Phase 6 code-modification proposals.

Design decisions:
  • A module-level singleton (_STORE) holds all pending proposals across requests.
    The singleton is private; callers always use get_store() so tests and future
    refactors can intercept the accessor without touching _STORE directly.

  • The store is bounded: put() evicts the oldest entry when capacity is reached.
    This prevents unbounded memory growth if proposals are never applied or rejected.

  • Expiry is opt-in: cleanup_expired() must be called explicitly (e.g. by a
    background task or on each write-path request) — the store does not spawn its
    own timer thread, keeping the module free of threading concerns.

  • Thread safety: Python's GIL protects individual dict operations in CPython.
    No asyncio.Lock is used because the store is only accessed from within a
    single FastAPI worker process during development.  Multi-worker production
    deployments are out of scope for Phase 6.

  • resolved_abs_path is set once at proposal time by CodeModificationService
    after full path validation and is never overwritten.  Apply-time code reads
    this field directly from the record — the /apply request body contains only
    a proposal_id.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import settings

logger = logging.getLogger("silentvoice.pending_change_store")


# ── Record ────────────────────────────────────────────────────────────────────

@dataclass
class PendingChangeRecord:
    """
    Immutable snapshot of a single pending code-modification proposal.

    All fields are set once at proposal time by CodeModificationService.
    The record is stored in PendingChangeStore until the user applies or
    rejects it, or until it expires.

    Field notes:
      id               — UUID4 string; used as the dict key in the store.
      file_path        — Relative path (display only).  Never used for writes.
      resolved_abs_path— Absolute path validated at proposal time.  The ONLY
                         path used when writing to disk at apply time.
      language         — Language label detected from the file extension.
      original_content — Full text of the file at proposal time, read with
                         Path.read_text(encoding="utf-8").
      original_hash    — sha256(original_content.encode("utf-8")).hexdigest().
                         Compared at apply time to detect stale proposals.
      new_content      — LLM-generated replacement text after fence stripping
                         and non-empty validation.  Treated as untrusted until
                         apply-time security validation completes.
      diff_chunks      — Pre-computed list[DiffChunk] from _compute_diff.
      summary          — instruction[:120].replace("\\n", " ").
      created_at       — UTC timestamp; used by cleanup_expired().
    """

    id: str
    file_path: str
    resolved_abs_path: str
    language: str
    original_content: str
    original_hash: str
    new_content: str
    diff_chunks: list = field(default_factory=list)   # list[DiffChunk] at runtime
    summary: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


# ── Store ─────────────────────────────────────────────────────────────────────

class PendingChangeStore:
    """
    Bounded in-memory store for PendingChangeRecord objects, keyed by UUID.

    Capacity is controlled by settings.max_pending_changes (default 50).
    Expiry is controlled by settings.pending_change_ttl_seconds (default 3600).

    Usage:
        store = get_store()
        store.put(record)          # store a proposal
        record = store.get(uid)    # retrieve by ID (or None)
        store.remove(uid)          # discard on apply / reject
        store.cleanup_expired()    # call periodically to free memory
    """

    def __init__(self) -> None:
        # Ordered dict: insertion order is maintained by Python 3.7+ dicts.
        # We also keep a separate list for O(1) oldest-entry lookup during eviction.
        self._records: dict[str, PendingChangeRecord] = {}
        # Insertion-order list of IDs — used for oldest-entry eviction.
        self._insertion_order: list[str] = []

    # ── Write operations ───────────────────────────────────────────────────────

    def put(self, record: PendingChangeRecord) -> str:
        """
        Store *record* in the store.

        If the store is at capacity (len >= max_pending_changes), the oldest
        entry (first in insertion order) is evicted before the new one is added.

        Args:
            record: A fully populated PendingChangeRecord.

        Returns:
            The record's id (convenience, same as record.id).
        """
        max_size: int = getattr(settings, "max_pending_changes", 50)

        # Evict oldest entries until we have room for one more
        while len(self._records) >= max_size:
            self._evict_oldest()

        self._records[record.id] = record
        self._insertion_order.append(record.id)
        logger.debug("Stored proposal %s for '%s'", record.id, record.file_path)
        return record.id

    def remove(self, proposal_id: str) -> bool:
        """
        Remove the record with *proposal_id* from the store.

        Args:
            proposal_id: UUID4 string of the proposal to remove.

        Returns:
            True if the record was found and removed; False if not present.
            Never raises for a missing ID.
        """
        if proposal_id not in self._records:
            return False
        del self._records[proposal_id]
        try:
            self._insertion_order.remove(proposal_id)
        except ValueError:
            # Defensive: insertion_order and _records should always be in sync,
            # but guard against any inconsistency rather than crashing.
            logger.warning(
                "proposal_id %s was in _records but not in _insertion_order", proposal_id
            )
        logger.debug("Removed proposal %s", proposal_id)
        return True

    def cleanup_expired(self) -> int:
        """
        Remove all records older than settings.pending_change_ttl_seconds.

        Should be called periodically (e.g. on each write-path request, or
        from a background task).

        Returns:
            Number of records removed.
        """
        ttl_seconds: int = getattr(settings, "pending_change_ttl_seconds", 3600)
        cutoff = datetime.now(tz=timezone.utc) - timedelta(seconds=ttl_seconds)
        expired_ids = [
            pid
            for pid, rec in self._records.items()
            if rec.created_at < cutoff
        ]
        for pid in expired_ids:
            self.remove(pid)
        if expired_ids:
            logger.info("Cleaned up %d expired proposal(s)", len(expired_ids))
        return len(expired_ids)

    # ── Read operations ────────────────────────────────────────────────────────

    def get(self, proposal_id: str) -> Optional[PendingChangeRecord]:
        """
        Retrieve the record for *proposal_id*.

        Args:
            proposal_id: UUID4 string of the proposal to retrieve.

        Returns:
            The PendingChangeRecord, or None if not present.  Never raises.
        """
        return self._records.get(proposal_id)

    def __len__(self) -> int:
        """Return the current number of stored proposals."""
        return len(self._records)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _evict_oldest(self) -> None:
        """Remove the oldest entry (first in insertion order)."""
        if not self._insertion_order:
            return
        oldest_id = self._insertion_order[0]
        logger.debug(
            "Store at capacity; evicting oldest proposal %s", oldest_id
        )
        self.remove(oldest_id)


# ── Module-level singleton ────────────────────────────────────────────────────

# Private — never import _STORE directly.  Use get_store() instead.
_STORE = PendingChangeStore()


def get_store() -> PendingChangeStore:
    """
    Return the module-level PendingChangeStore singleton.

    This is the single public entry-point for all store access.  Using an
    accessor function (rather than importing _STORE directly) allows tests to
    reset the store internals via get_store()._records.clear() without needing
    to patch a module-level name.

    Returns:
        The shared PendingChangeStore instance.
    """
    return _STORE
