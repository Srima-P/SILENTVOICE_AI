/**
 * usePendingChanges.ts — Phase 6 hook for the code-modification workflow.
 *
 * Orchestrates:
 *   • propose()  — call /api/changes/propose, store result in AppContext
 *   • approve()  — call /api/changes/apply, update status to "applied"
 *   • reject()   — call /api/changes/reject, remove from AppContext
 *
 * The hook never manages its own store — it delegates entirely to the
 * AppContext methods added in Pass 7 (addProposedChange, updatePendingChange,
 * removePendingChange, setPendingProposalRequest).
 */

import { useState, useCallback } from "react";
import { useApp } from "@/contexts/AppContext";
import {
  proposeChange,
  applyChange,
  rejectChange,
} from "@/services/changesApi";
import { uid } from "@/utils/helpers";
import type { ProposedChange } from "@/types";

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function usePendingChanges() {
  const {
    state,
    addProposedChange,
    updatePendingChange,
    removePendingChange,
    setPendingProposalRequest,
    addActivity,
  } = useApp();

  const [isProposing, setIsProposing] = useState(false);
  const [isApplying, setIsApplying] = useState(false);

  // ── propose ──────────────────────────────────────────────────────────────────

  /**
   * Generate a code-modification proposal for a file.
   *
   * Flow:
   *   1. Call POST /api/changes/propose.
   *   2. Map the response into a ProposedChange (proposal_id → id).
   *   3. Dispatch addProposedChange() to AppContext.
   *   4. Clear pendingProposalRequest.
   *   5. Log activity.
   *
   * @param filePath    Relative project path (e.g. "src/components/Login.jsx").
   * @param instruction Natural-language change description.
   */
  const propose = useCallback(
    async (filePath: string, instruction: string): Promise<void> => {
      setIsProposing(true);
      addActivity({
        id: uid(),
        timestamp: new Date(),
        message: `Generating proposal for "${filePath}"…`,
        type: "info",
      });

      try {
        const response = await proposeChange(filePath, instruction);

        // Explicit mapping: proposal_id (backend) → id (frontend ProposedChange)
        const change: ProposedChange = {
          id: response.proposal_id,
          filePath: response.file_path,
          description: response.summary,
          language: response.language,
          status: "pending",
          diff: response.chunks,
        };

        addProposedChange(change);

        // Clear the pending request now that it has been submitted
        setPendingProposalRequest(null);

        addActivity({
          id: uid(),
          timestamp: new Date(),
          message: `Proposal ready for "${response.file_path}" (+${response.new_lines - response.original_lines} lines net).`,
          type: "success",
        });
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        addActivity({
          id: uid(),
          timestamp: new Date(),
          message: `Proposal failed for "${filePath}": ${msg}`,
          type: "error",
        });
        // Re-throw so callers can handle UI state (e.g. show an error banner)
        throw err;
      } finally {
        setIsProposing(false);
      }
    },
    [addProposedChange, setPendingProposalRequest, addActivity]
  );

  // ── approve ──────────────────────────────────────────────────────────────────

  /**
   * Apply an approved proposal to disk.
   *
   * Flow:
   *   1. Locate the ProposedChange in state by changeId.
   *   2. Call POST /api/changes/apply (confirmed=true sent by applyChange).
   *   3. updatePendingChange() — status → "applied".
   *   4. Log activity.
   *
   * @param changeId  The ProposedChange.id (== proposal_id from the backend).
   */
  const approve = useCallback(
    async (changeId: string): Promise<void> => {
      const change = state.proposedChanges.find((c) => c.id === changeId);
      if (!change) {
        throw new Error(`No pending change found with id "${changeId}"`);
      }

      setIsApplying(true);
      addActivity({
        id: uid(),
        timestamp: new Date(),
        message: `Applying change to "${change.filePath}"…`,
        type: "info",
      });

      try {
        const response = await applyChange(changeId);

        updatePendingChange(changeId, { status: "applied" });

        addActivity({
          id: uid(),
          timestamp: new Date(),
          message: `Applied change to ${response.file_path}`,
          type: "success",
        });
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        updatePendingChange(changeId, { status: "failed" });
        addActivity({
          id: uid(),
          timestamp: new Date(),
          message: `Failed to apply change to "${change.filePath}": ${msg}`,
          type: "error",
        });
        throw err;
      } finally {
        setIsApplying(false);
      }
    },
    [state.proposedChanges, updatePendingChange, addActivity]
  );

  // ── reject ───────────────────────────────────────────────────────────────────

  /**
   * Discard a pending proposal (no filesystem operation).
   *
   * Flow:
   *   1. Call POST /api/changes/reject.
   *   2. removePendingChange() from AppContext.
   *   3. Log activity.
   *
   * @param changeId  The ProposedChange.id (== proposal_id from the backend).
   */
  const reject = useCallback(
    async (changeId: string): Promise<void> => {
      const change = state.proposedChanges.find((c) => c.id === changeId);
      const displayPath = change?.filePath ?? changeId;

      try {
        await rejectChange(changeId);
      } catch {
        // Rejection is best-effort: even if the backend call fails (e.g. the
        // proposal already expired), we still remove it from the frontend store
        // so the UI does not show a stale entry.
      }

      removePendingChange(changeId);

      addActivity({
        id: uid(),
        timestamp: new Date(),
        message: `Rejected proposal for "${displayPath}".`,
        type: "info",
      });
    },
    [state.proposedChanges, removePendingChange, addActivity]
  );

  // ─── Exposed interface ────────────────────────────────────────────────────────

  return {
    /** True while a propose() call is in flight. */
    isProposing,
    /** True while an approve() call is in flight. */
    isApplying,
    propose,
    approve,
    reject,
  };
}
