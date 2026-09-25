/**
 * FileTree — recursive file/folder tree renderer.
 */

import { useState } from "react";
import { ChevronRight, ChevronDown, Folder, FolderOpen, FileCode, FileText } from "lucide-react";
import type { FileNode } from "@/types";
import { getExtension } from "@/utils/helpers";

interface Props {
  nodes: FileNode[];
  selectedPath?: string;
  loadingPath?: string;
  onSelect: (node: FileNode) => void;
  depth?: number;
}

function fileIcon(node: FileNode) {
  if (node.type === "directory") return null; // handled by Folder icons
  const ext = getExtension(node.name);
  const codeExts = ["ts", "tsx", "js", "jsx", "py", "json", "yaml", "yml", "css", "html"];
  return codeExts.includes(ext) ? (
    <FileCode size={13} className="text-text-muted flex-shrink-0" aria-hidden="true" />
  ) : (
    <FileText size={13} className="text-text-muted flex-shrink-0" aria-hidden="true" />
  );
}

function TreeNode({
  node,
  selectedPath,
  loadingPath,
  onSelect,
  depth = 0,
}: {
  node: FileNode;
  selectedPath?: string;
  loadingPath?: string;
  onSelect: (node: FileNode) => void;
  depth?: number;
}) {
  const [open, setOpen] = useState(depth < 2);
  const isDir = node.type === "directory";
  const isSelected = node.path === selectedPath;
  const isLoading = node.path === loadingPath;
  const indent = depth * 12;

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (isDir) setOpen((o) => !o);
      else onSelect(node);
    }
    if (e.key === "ArrowRight" && isDir && !open) {
      setOpen(true);
    }
    if (e.key === "ArrowLeft" && isDir && open) {
      setOpen(false);
    }
  }

  return (
    <li role="none">
      <button
        role={isDir ? "treeitem" : "treeitem"}
        aria-expanded={isDir ? open : undefined}
        aria-selected={isSelected}
        onClick={() => {
          if (isDir) setOpen((o) => !o);
          else onSelect(node);
        }}
        onKeyDown={handleKeyDown}
        className={[
            "flex items-center gap-1.5 w-full text-left px-2 py-0.5 rounded text-xs transition-colors",
            isSelected
              ? "bg-text-accent/15 text-text-primary"
              : isLoading
              ? "bg-surface-3 text-text-muted"
              : "text-text-secondary hover:text-text-primary hover:bg-surface-3",
          ].join(" ")}
        style={{ paddingLeft: `${indent + 8}px` }}
        title={node.path}
      >
        {isDir ? (
          <>
            <span aria-hidden="true">
              {open ? (
                <ChevronDown size={12} className="text-text-muted" />
              ) : (
                <ChevronRight size={12} className="text-text-muted" />
              )}
            </span>
            <span aria-hidden="true">
              {open ? (
                <FolderOpen size={13} className="text-status-warn flex-shrink-0" />
              ) : (
                <Folder size={13} className="text-status-warn flex-shrink-0" />
              )}
            </span>
          </>
        ) : (
          <>
            <span className="w-3 flex-shrink-0" aria-hidden="true" />
            {fileIcon(node)}
          </>
        )}
        <span className="truncate flex-1">{node.name}</span>
        {isLoading && (
          <span className="ml-1 flex-shrink-0">
            <svg className="animate-spin w-2.5 h-2.5 text-text-muted" fill="none" viewBox="0 0 24 24" aria-hidden="true">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
            </svg>
          </span>
        )}
      </button>

      {isDir && open && node.children && (
        <ul role="group">
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              selectedPath={selectedPath}
              loadingPath={loadingPath}
              onSelect={onSelect}
              depth={depth + 1}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function FileTree({ nodes, selectedPath, loadingPath, onSelect, depth = 0 }: Props) {
  return (
    <ul role="tree" aria-label="Project files" className="select-none">
      {nodes.map((node) => (
        <TreeNode
          key={node.id}
          node={node}
          selectedPath={selectedPath}
          loadingPath={loadingPath}
          onSelect={onSelect}
          depth={depth}
        />
      ))}
    </ul>
  );
}
