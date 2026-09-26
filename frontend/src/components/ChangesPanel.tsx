/**
 * ChangesPanel — bottom panel showing workflow tabs.
 * Phase 2: Activity tab shows real events; Diff tab shows dependency graph.
 * Phase 6: Changes tab integrates usePendingChanges — renders pending proposals,
 *           DiffViewer, Approve/Reject buttons, and watches pendingProposalRequest
 *           to trigger propose() automatically.
 */

import { useEffect } from "react";
import { GitBranch, FileCode, Activity, Clock, CheckCircle, XCircle, Loader2 } from "lucide-react";
import { EmptyState } from "./EmptyState";
import { DependencyGraph } from "./DependencyGraph";
import { DiffViewer } from "./DiffViewer";
import { useApp } from "@/contexts/AppContext";
import { usePendingChanges } from "@/hooks/usePendingChanges";
import { formatTime } from "@/utils/helpers";
import type { WorkflowTab } from "@/types";

const TABS: { id: WorkflowTab; label: string; icon: React.ReactNode }[] = [
  { id: "changes", label: "Changes", icon: <GitBranch size={13} /> },
  { id: "diff", label: "Dependencies", icon: <FileCode size={13} /> },
  { id: "activity", label: "Activity", icon: <Activity size={13} /> },
];

const STATUS_COLORS: Record<string, string> = {
  info: "text-status-info",
  warn: "text-status-warn",
  error: "text-status-error",
  success: "text-status-ok",
};

const CHANGE_STATUS_BADGE: Record<string, string> = {
  pending:  "bg-status-warn/15 text-status-warn border-status-warn/30",
  applied:  "bg-status-ok/15 text-status-ok border-status-ok/30",
  rejected: "bg-surface-3 text-text-muted border-border",
  failed:   "bg-status-error/15 text-status-error border-status-error/30",
  approved: "bg-status-info/15 text-status-info border-status-info/30",
  invalid:  "bg-status-error/15 text-status-error border-status-error/30",
  stale:    "bg-surface-3 text-text-muted border-border",
};

export function ChangesPanel() {
  const { state, setWorkflowTab } = useApp();
  const { propose, approve, reject, isProposing, isApplying } = usePendingChanges();
  const active = state.activeWorkflowTab;

  // ── Phase 6: Watch pendingProposalRequest and call propose() ────────────────
  useEffect(() => {
    if (state.pendingProposalRequest) {
      const { filePath, instruction } = state.pendingProposalRequest;
      // Switch to the Changes tab so the user sees the proposal arrive
      setWorkflowTab("changes");
      void propose(filePath, instruction);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.pendingProposalRequest]);

  return (
    <section
      className="flex flex-col h-40 min-h-0 bg-surface-1 border-t border-border flex-shrink-0"
      aria-label="Workflow panel"
    >
      {/* Tab bar */}
      <div
        className="flex items-center border-b border-border flex-shrink-0"
        role="tablist"
        aria-label="Workflow tabs"
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={active === tab.id}
            aria-controls={`panel-${tab.id}`}
            onClick={() => setWorkflowTab(tab.id)}
            className={[
              "flex items-center gap-1.5 px-4 py-2 text-xs font-medium border-b-2 transition-colors",
              active === tab.id
                ? "border-text-accent text-text-primary"
                : "border-transparent text-text-muted hover:text-text-secondary",
            ].join(" ")}
          >
            <span aria-hidden="true">{tab.icon}</span>
            {tab.label}
            {/* Badge for pending change count */}
            {tab.id === "changes" && state.proposedChanges.filter((c) => c.status === "pending").length > 0 && (
              <span className="ml-0.5 px-1 py-0 rounded text-[9px] font-bold bg-status-warn/20 text-status-warn">
                {state.proposedChanges.filter((c) => c.status === "pending").length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Changes tab */}
      <div
        id="panel-changes"
        role="tabpanel"
        aria-label="Proposed changes"
        hidden={active !== "changes"}
        className="flex-1 overflow-y-auto"
      >
        {/* Proposing spinner */}
        {isProposing && (
          <div className="flex items-center gap-2 px-3 py-2 text-xs text-text-muted border-b border-border">
            <Loader2 size={11} className="animate-spin flex-shrink-0" aria-hidden="true" />
            Generating proposal…
          </div>
        )}

        {state.proposedChanges.length === 0 && !isProposing ? (
          <EmptyState
            title="No proposed changes yet"
            description="When SilentVoice AI suggests code modifications they will appear here for review and approval."
          />
        ) : (
          <ul className="divide-y divide-border/50">
            {state.proposedChanges.map((change) => (
              <li key={change.id} className="py-2 px-3 space-y-1.5">
                {/* Header row */}
                <div className="flex items-center justify-between gap-2 min-w-0">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span
                      className={[
                        "flex-shrink-0 text-[9px] font-semibold px-1.5 py-0.5 rounded border uppercase tracking-wide",
                        CHANGE_STATUS_BADGE[change.status] ?? "bg-surface-3 text-text-muted border-border",
                      ].join(" ")}
                    >
                      {change.status}
                    </span>
                    <span
                      className="font-mono text-[10px] text-text-muted truncate max-w-[160px]"
                      title={change.filePath}
                    >
                      {change.filePath.split("/").pop()}
                    </span>
                  </div>

                  {/* Approve / Reject — only for pending proposals */}
                  {change.status === "pending" && (
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <button
                        type="button"
                        onClick={() => void approve(change.id)}
                        disabled={isApplying}
                        aria-label={`Approve change for ${change.filePath}`}
                        title="Approve"
                        className={[
                          "flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] border transition-colors",
                          "border-status-ok/40 text-status-ok hover:bg-status-ok/10",
                          isApplying ? "opacity-40 cursor-not-allowed" : "",
                        ].join(" ")}
                      >
                        <CheckCircle size={10} aria-hidden="true" />
                        Approve
                      </button>
                      <button
                        type="button"
                        onClick={() => void reject(change.id)}
                        disabled={isApplying}
                        aria-label={`Reject change for ${change.filePath}`}
                        title="Reject"
                        className={[
                          "flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] border transition-colors",
                          "border-status-error/40 text-status-error hover:bg-status-error/10",
                          isApplying ? "opacity-40 cursor-not-allowed" : "",
                        ].join(" ")}
                      >
                        <XCircle size={10} aria-hidden="true" />
                        Reject
                      </button>
                    </div>
                  )}
                </div>

                {/* Description */}
                <p className="text-[10px] text-text-secondary leading-snug">{change.description}</p>

                {/* Diff preview */}
                <DiffViewer diff={change.diff} />
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Dependencies tab (was Diff) */}
      <div
        id="panel-diff"
        role="tabpanel"
        aria-label="Dependencies"
        hidden={active !== "diff"}
        className="flex-1 overflow-y-auto"
      >
        <DependencyGraph />
      </div>

      {/* Activity tab */}
      <div
        id="panel-activity"
        role="tabpanel"
        aria-label="Activity log"
        hidden={active !== "activity"}
        className="flex-1 overflow-y-auto"
      >
        {state.activity.length === 0 ? (
          <EmptyState
            title="No activity yet"
            description="Project scan events and commands will be logged here."
          />
        ) : (
          <ul className="py-1">
            {state.activity.map((entry) => (
              <li
                key={entry.id}
                className="flex items-start gap-2 px-3 py-1 hover:bg-surface-2/30"
              >
                <Clock
                  size={10}
                  className="text-text-muted mt-0.5 flex-shrink-0"
                  aria-hidden="true"
                />
                <time
                  className="text-[10px] text-text-muted flex-shrink-0 mt-px"
                  dateTime={entry.timestamp.toISOString()}
                >
                  {formatTime(entry.timestamp)}
                </time>
                <span
                  className={`text-xs truncate ${STATUS_COLORS[entry.type] ?? "text-text-secondary"}`}
                  title={entry.message}
                >
                  {entry.message}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
