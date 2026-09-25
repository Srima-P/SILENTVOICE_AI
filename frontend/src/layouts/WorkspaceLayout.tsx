/**
 * WorkspaceLayout — the root layout for the main IDE-style workspace.
 * Composes TopBar + content area (ProjectExplorer | CodeViewer | AssistantPanel)
 * + ChangesPanel.
 *
 * Accessibility: uses landmark roles and skip-navigation.
 */

import { TopBar } from "@/components/TopBar";
import { ProjectExplorer } from "@/components/ProjectExplorer";
import { CodeViewer } from "@/components/CodeViewer";
import { AssistantPanel } from "@/components/AssistantPanel";
import { ChangesPanel } from "@/components/ChangesPanel";
import { useAccessibility } from "@/hooks/useAccessibility";

interface Props {
  children?: never; // layout manages its own children
}

export function WorkspaceLayout(_props: Props) {
  const { a11yClass } = useAccessibility();

  return (
    <div className={a11yClass("flex flex-col h-screen overflow-hidden")}>
      {/* Skip navigation for keyboard users */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:px-3 focus:py-2 focus:bg-text-accent focus:text-surface-DEFAULT focus:rounded text-sm font-medium"
      >
        Skip to main content
      </a>

      <TopBar />

      {/* Main workspace area */}
      <div id="main-content" className="flex flex-1 min-h-0 overflow-hidden">
        <ProjectExplorer />
        <CodeViewer />
        <AssistantPanel />
      </div>

      <ChangesPanel />
    </div>
  );
}
