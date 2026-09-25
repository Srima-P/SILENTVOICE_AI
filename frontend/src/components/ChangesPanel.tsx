/**
 * ChangesPanel — bottom panel showing workflow tabs.
 * Phase 2: Activity tab shows real events; Diff tab shows dependency graph.
 */

import { GitBranch, FileCode, Activity, Clock } from "lucide-react";
import { EmptyState } from "./EmptyState";
import { DependencyGraph } from "./DependencyGraph";
import { useApp } from "@/contexts/AppContext";
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

export function ChangesPanel() {
  const { state, setWorkflowTab } = useApp();
  const active = state.activeWorkflowTab;

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
        <EmptyState
          title="No proposed changes yet"
          description="When SilentVoice AI suggests code modifications they will appear here for review and approval."
        />
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
