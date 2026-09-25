/**
 * TopBar — global application header.
 * Contains the brand, connection status, scan status, accessibility toggle, and settings link.
 */

import { Link } from "react-router-dom";
import { Settings, Mic, Loader2, RefreshCw } from "lucide-react";
import { StatusIndicator } from "./StatusIndicator";
import { AccessibilityToggle } from "./AccessibilityToggle";
import { useApp } from "@/contexts/AppContext";
import { useProjectScan } from "@/hooks/useProjectScan";

export function TopBar() {
  const { state } = useApp();
  const { scanProject } = useProjectScan();
  const isScanning = state.scanState.status === "scanning";

  return (
    <header
      className="flex items-center justify-between px-4 h-12 bg-surface-2 border-b border-border flex-shrink-0"
      role="banner"
    >
      {/* Brand */}
      <div className="flex items-center gap-2.5">
        <span
          className="flex items-center justify-center w-7 h-7 rounded bg-text-accent/20"
          aria-hidden="true"
        >
          <Mic size={14} className="text-text-accent" />
        </span>
        <span className="font-semibold text-text-primary text-sm tracking-wide">
          SilentVoice AI
        </span>
        <span className="hidden md:inline text-xs text-text-muted bg-surface-3 px-1.5 py-0.5 rounded font-mono">
          Phase 1
        </span>
      </div>

      {/* Right controls */}
      <nav
        className="flex items-center gap-3"
        aria-label="Global actions"
      >
        {/* Scan status */}
        {isScanning && (
          <span className="flex items-center gap-1.5 text-xs text-text-muted" aria-live="polite">
            <Loader2 size={12} className="animate-spin" aria-hidden="true" />
            Scanning…
          </span>
        )}
        {state.scanState.status === "ready" && !isScanning && (
          <button
            onClick={() => void scanProject()}
            title="Re-scan project"
            aria-label="Re-scan project"
            className="flex items-center gap-1 text-xs text-text-muted hover:text-text-primary transition-colors"
          >
            <RefreshCw size={11} aria-hidden="true" />
            <span className="hidden lg:inline">{state.project?.name ?? "Project"}</span>
          </button>
        )}

        <StatusIndicator status={state.connectionStatus} />

        <div className="h-4 w-px bg-border" aria-hidden="true" />

        <AccessibilityToggle />

        <Link
          to="/settings"
          aria-label="Settings"
          title="Settings"
          className="p-1.5 rounded text-text-secondary hover:text-text-primary hover:bg-surface-3 transition-colors"
        >
          <Settings size={15} aria-hidden="true" />
        </Link>
      </nav>
    </header>
  );
}
