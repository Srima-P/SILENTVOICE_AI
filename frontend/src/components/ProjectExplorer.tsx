/**
 * ProjectExplorer — left sidebar.
 * Phase 2: loads the real file tree from the backend via useProjectScan.
 * File contents are fetched on demand when a node is selected.
 */

import { FolderOpen, RefreshCw, AlertCircle, Loader2 } from "lucide-react";
import { FileTree } from "./FileTree";
import { EmptyState } from "./EmptyState";
import { ProjectInsightsPanel } from "./ProjectInsightsPanel";
import { useApp } from "@/contexts/AppContext";
import { useProjectScan } from "@/hooks/useProjectScan";
import type { FileNode } from "@/types";

export function ProjectExplorer() {
  const { state } = useApp();
  const { scanProject, openFile } = useProjectScan();
  const project = state.project;
  const { scanState, fileLoadingPath, fileLoadError } = state;
  const isScanning = scanState.status === "scanning";

  function handleSelect(node: FileNode) {
    if (node.type !== "file") return;
    void openFile(node);
  }

  return (
    <aside
      className="flex flex-col w-60 min-w-0 bg-surface-1 border-r border-border overflow-hidden flex-shrink-0"
      aria-label="Project explorer"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <FolderOpen size={13} className="text-text-muted flex-shrink-0" aria-hidden="true" />
          <span className="text-xs font-semibold text-text-muted uppercase tracking-widest truncate">
            {project ? project.name : "Project"}
          </span>
        </div>
        <button
          onClick={() => void scanProject()}
          disabled={isScanning}
          aria-label={isScanning ? "Scanning…" : "Scan / refresh project"}
          title={isScanning ? "Scanning…" : "Scan project"}
          className={[
            "flex-shrink-0 p-1 rounded transition-colors",
            isScanning
              ? "text-text-muted opacity-50 cursor-not-allowed"
              : "text-text-muted hover:text-text-primary hover:bg-surface-3",
          ].join(" ")}
        >
          {isScanning ? (
            <Loader2 size={12} className="animate-spin" aria-hidden="true" />
          ) : (
            <RefreshCw size={12} aria-hidden="true" />
          )}
        </button>
      </div>

      {/* Scan error banner */}
      {scanState.status === "error" && scanState.error && (
        <div
          className="flex items-start gap-2 px-3 py-2 bg-status-error/10 border-b border-status-error/20 text-xs text-status-error"
          role="alert"
        >
          <AlertCircle size={12} className="mt-0.5 flex-shrink-0" aria-hidden="true" />
          <span className="truncate" title={scanState.error}>
            {scanState.error}
          </span>
        </div>
      )}

      {/* File loading error */}
      {fileLoadError && (
        <div
          className="flex items-start gap-2 px-3 py-2 bg-status-error/10 border-b border-status-error/20 text-xs text-status-error"
          role="alert"
        >
          <AlertCircle size={12} className="mt-0.5 flex-shrink-0" aria-hidden="true" />
          <span className="truncate" title={fileLoadError}>
            {fileLoadError}
          </span>
        </div>
      )}

      {/* File tree */}
      <div className="flex-1 overflow-y-auto py-1 min-h-0">
        {isScanning ? (
          <div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
            <Loader2 size={20} className="animate-spin text-text-muted" aria-hidden="true" />
            <p className="text-xs text-text-muted">Scanning project…</p>
          </div>
        ) : project ? (
          <FileTree
            nodes={project.tree}
            selectedPath={state.selectedFile?.path}
            loadingPath={fileLoadingPath ?? undefined}
            onSelect={handleSelect}
          />
        ) : (
          <EmptyState
            icon={<FolderOpen size={28} />}
            title="No project loaded"
            description="Click the refresh button to scan the configured project."
          />
        )}
      </div>

      {/* Project insights */}
      <ProjectInsightsPanel />
    </aside>
  );
}
