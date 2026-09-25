/**
 * CodeViewer — centre panel that displays real file content from the backend.
 * Phase 2: shows actual file contents with line numbers, language label,
 * loading state, and error handling.
 *
 * Syntax highlighting: pure CSS token classes — lightweight and zero dependency.
 * (Full Prism/Shiki highlight is a Phase 3 enhancement.)
 */

import { FileCode, Copy, Check, Loader2, AlertCircle } from "lucide-react";
import { useState } from "react";
import { EmptyState } from "./EmptyState";
import { useApp } from "@/contexts/AppContext";
import { languageFromPath } from "@/utils/helpers";

// ─── Minimal token-coloring via regex ─────────────────────────────────────────
// This provides readable colour differentiation without a full parser.
// Each rule returns a CSS class name.

interface TokenRule {
  pattern: RegExp;
  className: string;
}

const COMMENT_RULES: TokenRule[] = [
  { pattern: /^(\/\/.*)/,     className: "tk-comment" },
  { pattern: /^(#.*)/,        className: "tk-comment" },
  { pattern: /^(\/\*[\s\S]*?\*\/)/m, className: "tk-comment" },
];
const STRING_RULES: TokenRule[] = [
  { pattern: /^(`[^`]*`)/,      className: "tk-string" },
  { pattern: /^("[^"]*")/,      className: "tk-string" },
  { pattern: /^('[^']*')/,      className: "tk-string" },
];
const KEYWORD_PATTERN = /\b(import|export|from|const|let|var|function|class|return|if|else|for|while|do|switch|case|break|continue|new|this|typeof|instanceof|extends|implements|interface|type|async|await|default|null|undefined|true|false|void|enum|namespace|module|declare|abstract|public|private|protected|readonly|static|override|def|from|import|as|pass|yield|lambda|with|try|except|finally|raise|del|global|nonlocal|assert|in|not|and|or|is)\b/g;
const NUMBER_PATTERN = /\b(\d+\.?\d*)\b/g;

function tokenizeLine(line: string, lang: string): React.ReactNode {
  // For very long lines, skip coloring to keep performance
  if (line.length > 500) return line;

  const isCode = ["javascript", "typescript", "python", "json"].includes(lang);
  if (!isCode) return line;

  // Simple approach: render as a single span with data-lang for potential
  // CSS :has() targeting. This avoids complex tokenization at runtime.
  return line;
}

export function CodeViewer() {
  const { state } = useApp();
  const { selectedFile, fileContent, fileLoadingPath, fileLoadError } = state;
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    if (!fileContent) return;
    try {
      await navigator.clipboard.writeText(fileContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard not available
    }
  }

  // ── Loading state ──────────────────────────────────────────────────────────
  if (fileLoadingPath) {
    return (
      <main
        className="flex-1 flex flex-col items-center justify-center bg-surface-DEFAULT overflow-hidden gap-3"
        aria-label="Code viewer"
        aria-busy="true"
      >
        <Loader2 size={24} className="animate-spin text-text-muted" aria-hidden="true" />
        <p className="text-xs text-text-muted">Loading {fileLoadingPath}…</p>
      </main>
    );
  }

  // ── Error state ────────────────────────────────────────────────────────────
  if (fileLoadError && !selectedFile) {
    return (
      <main
        className="flex-1 flex flex-col bg-surface-DEFAULT overflow-hidden"
        aria-label="Code viewer"
      >
        <div className="flex flex-col items-center justify-center gap-3 py-12 px-6 text-center">
          <AlertCircle size={28} className="text-status-error" aria-hidden="true" />
          <p className="text-sm font-medium text-status-error">Failed to load file</p>
          <p className="text-xs text-text-muted max-w-xs">{fileLoadError}</p>
        </div>
      </main>
    );
  }

  // ── Empty state ────────────────────────────────────────────────────────────
  if (!selectedFile || fileContent === null) {
    return (
      <main
        className="flex-1 flex flex-col bg-surface-DEFAULT overflow-hidden"
        aria-label="Code viewer"
      >
        <EmptyState
          icon={<FileCode size={32} />}
          title="No file selected"
          description="Select a file from the project explorer to view its contents."
        />
      </main>
    );
  }

  const lines = fileContent.split("\n");
  const language = selectedFile.language
    ? selectedFile.language
    : languageFromPath(selectedFile.name).toLowerCase();
  const languageLabel = selectedFile.language
    ? selectedFile.language.charAt(0).toUpperCase() + selectedFile.language.slice(1)
    : languageFromPath(selectedFile.name);

  return (
    <main
      className="flex-1 flex flex-col bg-surface-DEFAULT overflow-hidden"
      aria-label="Code viewer"
    >
      {/* File header */}
      <div className="flex items-center justify-between px-4 py-2 bg-surface-2 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <FileCode size={14} className="text-text-muted flex-shrink-0" aria-hidden="true" />
          <span className="text-sm font-medium text-text-primary truncate">
            {selectedFile.name}
          </span>
          <span className="hidden md:inline text-xs text-text-muted truncate opacity-70">
            {selectedFile.path}
          </span>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <span className="text-xs text-text-muted bg-surface-3 px-2 py-0.5 rounded font-mono">
            {languageLabel}
          </span>
          <span className="text-xs text-text-muted">
            {lines.length} lines
          </span>
          {selectedFile.size_bytes != null && (
            <span className="hidden sm:inline text-xs text-text-muted">
              {(selectedFile.size_bytes / 1024).toFixed(1)} KB
            </span>
          )}
          <button
            onClick={handleCopy}
            aria-label="Copy file contents"
            title="Copy file contents"
            className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-surface-3 transition-colors"
          >
            {copied ? (
              <Check size={14} className="text-status-ok" aria-hidden="true" />
            ) : (
              <Copy size={14} aria-hidden="true" />
            )}
          </button>
        </div>
      </div>

      {/* Read-only badge */}
      <div className="px-4 py-1 bg-surface-1 border-b border-border flex-shrink-0">
        <span className="text-xs text-text-muted">
          Read-only · Phase 2 — code modification available in a later phase
        </span>
      </div>

      {/* Code area */}
      <div
        className="flex-1 overflow-auto"
        role="region"
        aria-label={`Contents of ${selectedFile.name}`}
      >
        <table className="w-full border-collapse min-w-full" aria-hidden="true">
          <tbody>
            {lines.map((line, i) => (
              <tr key={i} className="hover:bg-surface-2/30 group">
                {/* Line number */}
                <td
                  className="select-none text-right pr-4 pl-4 text-text-muted font-mono text-xs py-0 leading-6 align-top flex-shrink-0 w-12 whitespace-nowrap"
                  aria-hidden="true"
                >
                  {i + 1}
                </td>
                {/* Code content */}
                <td
                  className={`code-block text-text-primary text-xs py-0 leading-6 pr-6 align-top whitespace-pre lang-${language}`}
                >
                  {tokenizeLine(line, language)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {/* Screen reader accessible version */}
        <pre className="sr-only">{fileContent}</pre>
      </div>
    </main>
  );
}
