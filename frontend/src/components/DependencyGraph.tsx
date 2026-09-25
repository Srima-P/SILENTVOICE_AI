/**
 * DependencyGraph — visual representation of the static import dependency map.
 * Phase 2: data comes from the real backend analyzer.
 *
 * Layout: simple tree list — each top-level file with its resolved dependents.
 * No external graph libraries needed; pure CSS/HTML is sufficient.
 */

import { GitBranch, ChevronDown, ChevronRight, FileCode } from "lucide-react";
import { useState } from "react";
import { useApp } from "@/contexts/AppContext";
import { EmptyState } from "./EmptyState";
import { getFile } from "@/services/projectApi";

function basename(path: string): string {
  return path.split("/").pop() ?? path;
}

interface NodeRowProps {
  filePath: string;
  deps: string[];
  isExpanded: boolean;
  onToggle: () => void;
  onSelect: (path: string) => void;
}

function NodeRow({ filePath, deps, isExpanded, onToggle, onSelect }: NodeRowProps) {
  const hasDeps = deps.length > 0;
  return (
    <li>
      <button
        onClick={hasDeps ? onToggle : () => onSelect(filePath)}
        className="flex items-center gap-1.5 w-full text-left px-2 py-1 rounded hover:bg-surface-3 transition-colors group"
        aria-expanded={hasDeps ? isExpanded : undefined}
      >
        {hasDeps ? (
          <span className="text-text-muted" aria-hidden="true">
            {isExpanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
          </span>
        ) : (
          <span className="w-3 flex-shrink-0" aria-hidden="true" />
        )}
        <FileCode size={11} className="text-text-muted flex-shrink-0" aria-hidden="true" />
        <span
          className="text-xs text-text-secondary group-hover:text-text-primary truncate"
          title={filePath}
        >
          {basename(filePath)}
        </span>
        {hasDeps && (
          <span className="ml-auto text-[10px] text-text-muted flex-shrink-0">
            {deps.length}
          </span>
        )}
      </button>

      {hasDeps && isExpanded && (
        <ul className="ml-4 border-l border-border/50 pl-2 mt-0.5 mb-1 space-y-0.5">
          {deps.map((dep) => (
            <li key={dep}>
              <button
                onClick={() => onSelect(dep)}
                className="flex items-center gap-1.5 w-full text-left px-2 py-0.5 rounded hover:bg-surface-3 transition-colors"
                title={dep}
              >
                <span className="text-text-muted" aria-hidden="true">↳</span>
                <span className="text-xs text-text-muted hover:text-text-secondary truncate">
                  {basename(dep)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export function DependencyGraph() {
  const { state, selectFile, setFileLoading, setFileError } = useApp();
  const { analysis } = state;
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loadingPath, setLoadingPathLocal] = useState<string | null>(null);

  function toggle(path: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  async function handleSelect(path: string) {
    // Find the node in the project tree
    const node = state.project?.tree ? findNode(state.project.tree, path) : null;
    if (!node) return;

    setLoadingPathLocal(path);
    setFileLoading(path);
    try {
      const result = await getFile(path);
      selectFile({ ...node, language: result.language }, result.content);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setFileError(msg);
    } finally {
      setLoadingPathLocal(null);
    }
  }

  if (!analysis || Object.keys(analysis.dependencies.entries).length === 0) {
    return (
      <div className="py-4">
        <EmptyState
          icon={<GitBranch size={24} />}
          title="No dependency data"
          description="Scan the project to see import relationships."
        />
      </div>
    );
  }

  const entries = Object.entries(analysis.dependencies.entries);

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
        <GitBranch size={13} className="text-text-muted" aria-hidden="true" />
        <span className="text-xs font-semibold text-text-muted uppercase tracking-widest">
          Dependencies
        </span>
        <span className="ml-auto text-xs text-text-muted">{entries.length} files</span>
      </div>
      <ul
        className="overflow-y-auto max-h-64 py-1 px-1"
        role="tree"
        aria-label="Dependency tree"
      >
        {entries.map(([file, deps]) => (
          <NodeRow
            key={file}
            filePath={file}
            deps={deps}
            isExpanded={expanded.has(file)}
            onToggle={() => toggle(file)}
            onSelect={handleSelect}
          />
        ))}
      </ul>
    </div>
  );
}

// ─── Helper ───────────────────────────────────────────────────────────────────

import type { FileNode } from "@/types";

function findNode(nodes: FileNode[], path: string): FileNode | null {
  for (const node of nodes) {
    if (node.path === path) return node;
    if (node.children) {
      const found = findNode(node.children, path);
      if (found) return found;
    }
  }
  return null;
}
