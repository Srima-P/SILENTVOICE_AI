/**
 * ProjectInsightsPanel — shows real project statistics from backend analysis.
 * Phase 2: all values come from the backend, nothing is hardcoded.
 */

import { BarChart2, Package, FileCode, Layers, AlertCircle, RefreshCw } from "lucide-react";
import { useApp } from "@/contexts/AppContext";
import { useProjectScan } from "@/hooks/useProjectScan";

function StatRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-1 border-b border-border/50 last:border-0">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="text-xs font-medium text-text-primary">{value}</span>
    </div>
  );
}

function LanguageBadge({ lang, count }: { lang: string; count: number }) {
  const COLOR_MAP: Record<string, string> = {
    javascript: "text-status-warn",
    typescript: "text-status-info",
    python: "text-status-ok",
    css: "text-text-accent",
    html: "text-status-error",
    json: "text-text-muted",
    markdown: "text-text-secondary",
  };
  const color = COLOR_MAP[lang] ?? "text-text-secondary";
  return (
    <span className="flex items-center gap-1.5 text-xs">
      <span className={`font-medium ${color}`}>{lang}</span>
      <span className="text-text-muted">{count}</span>
    </span>
  );
}

export function ProjectInsightsPanel() {
  const { state } = useApp();
  const { scanProject } = useProjectScan();
  const { analysis, scanState } = state;

  const isScanning = scanState.status === "scanning";

  return (
    <section
      className="flex flex-col border-t border-border bg-surface-1 flex-shrink-0"
      aria-label="Project insights"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <div className="flex items-center gap-2">
          <BarChart2 size={13} className="text-text-muted" aria-hidden="true" />
          <span className="text-xs font-semibold text-text-muted uppercase tracking-widest">
            Insights
          </span>
        </div>
        <button
          onClick={() => void scanProject()}
          disabled={isScanning}
          aria-label={isScanning ? "Scanning project…" : "Refresh project scan"}
          title={isScanning ? "Scanning…" : "Refresh scan"}
          className={[
            "p-1 rounded transition-colors",
            isScanning
              ? "text-text-muted opacity-50 cursor-not-allowed"
              : "text-text-muted hover:text-text-primary hover:bg-surface-3",
          ].join(" ")}
        >
          <RefreshCw
            size={12}
            className={isScanning ? "animate-spin" : ""}
            aria-hidden="true"
          />
        </button>
      </div>

      {/* Content */}
      <div className="px-3 py-2 space-y-3 overflow-y-auto max-h-64">
        {!analysis ? (
          <p className="text-xs text-text-muted py-2 text-center">
            {isScanning ? "Scanning…" : "No data — scan the project first."}
          </p>
        ) : (
          <>
            {/* Stats */}
            <div>
              <StatRow label="Project" value={analysis.project_name} />
              <StatRow label="Total files" value={analysis.total_files} />
              <StatRow label="Source files" value={analysis.source_files} />
              <StatRow
                label="Components"
                value={analysis.components.length}
              />
              <StatRow
                label="Dependencies"
                value={Object.keys(analysis.dependencies.entries).length}
              />
            </div>

            {/* Languages */}
            {Object.keys(analysis.languages).length > 0 && (
              <div>
                <p className="text-[10px] font-semibold text-text-muted uppercase tracking-widest mb-1.5">
                  Languages
                </p>
                <div className="flex flex-wrap gap-x-3 gap-y-1">
                  {Object.entries(analysis.languages)
                    .sort(([, a], [, b]) => b - a)
                    .map(([lang, count]) => (
                      <LanguageBadge key={lang} lang={lang} count={count} />
                    ))}
                </div>
              </div>
            )}

            {/* Components */}
            {analysis.components.length > 0 && (
              <div>
                <p className="text-[10px] font-semibold text-text-muted uppercase tracking-widest mb-1.5 flex items-center gap-1">
                  <Layers size={10} aria-hidden="true" />
                  Components
                </p>
                <ul className="space-y-0.5">
                  {analysis.components.slice(0, 8).map((c) => (
                    <li key={c.path} className="flex items-center gap-1.5">
                      <Package
                        size={10}
                        className="text-text-muted flex-shrink-0"
                        aria-hidden="true"
                      />
                      <span className="text-xs text-text-secondary truncate">
                        {c.name}
                      </span>
                    </li>
                  ))}
                  {analysis.components.length > 8 && (
                    <li className="text-xs text-text-muted">
                      +{analysis.components.length - 8} more…
                    </li>
                  )}
                </ul>
              </div>
            )}

            {/* Scan errors (non-fatal) */}
            {analysis.scan_errors.length > 0 && (
              <div>
                <p className="text-[10px] font-semibold text-status-warn uppercase tracking-widest mb-1 flex items-center gap-1">
                  <AlertCircle size={10} aria-hidden="true" />
                  Scan warnings
                </p>
                <ul className="space-y-0.5">
                  {analysis.scan_errors.slice(0, 3).map((e, i) => (
                    <li key={i} className="text-xs text-text-muted truncate" title={e}>
                      {e}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
