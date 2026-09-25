/**
 * WorkspacePage — entry point for the main workspace.
 * Phase 2: automatically scans the backend-configured project on mount.
 */

import { useEffect } from "react";
import { WorkspaceLayout } from "@/layouts/WorkspaceLayout";
import { useApp } from "@/contexts/AppContext";
import { useHealthCheck } from "@/hooks/useHealthCheck";
import { useProjectScan } from "@/hooks/useProjectScan";

export function WorkspacePage() {
  const { state } = useApp();
  const { scanProject } = useProjectScan();

  // Kick off backend health polling
  useHealthCheck();

  // Auto-scan the project when the page loads and no project is loaded yet.
  // Phase 2: calls the real backend scanner.
  // Phase 3+: could prompt for a project path instead.
  useEffect(() => {
    if (!state.project && state.scanState.status === "idle") {
      void scanProject();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <WorkspaceLayout />;
}
