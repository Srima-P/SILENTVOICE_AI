/**
 * SettingsPage — application settings and status information.
 */

import { Link } from "react-router-dom";
import { ArrowLeft, Server, Accessibility, Info } from "lucide-react";
import { StatusIndicator } from "@/components/StatusIndicator";
import { AccessibilityToggle } from "@/components/AccessibilityToggle";
import { useApp } from "@/contexts/AppContext";
import { useAccessibility } from "@/hooks/useAccessibility";
import { useHealthCheck } from "@/hooks/useHealthCheck";

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-surface-2 border border-border rounded-lg overflow-hidden">
      <header className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <span className="text-text-muted" aria-hidden="true">
          {icon}
        </span>
        <h2 className="text-sm font-semibold text-text-secondary">{title}</h2>
      </header>
      <div className="px-4 py-4 space-y-3">{children}</div>
    </section>
  );
}

function Row({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="text-xs text-text-primary">{value}</span>
    </div>
  );
}

export function SettingsPage() {
  const { state } = useApp();
  const { accessibility, setAccessibility } = useAccessibility();

  // Poll health on settings page too
  useHealthCheck();

  return (
    <div className="flex flex-col h-screen bg-surface-DEFAULT overflow-auto">
      {/* Header */}
      <header className="flex items-center gap-3 px-6 py-4 border-b border-border bg-surface-2 flex-shrink-0">
        <Link
          to="/"
          aria-label="Back to workspace"
          className="p-1.5 rounded text-text-muted hover:text-text-primary hover:bg-surface-3 transition-colors"
        >
          <ArrowLeft size={16} aria-hidden="true" />
        </Link>
        <h1 className="text-base font-semibold text-text-primary">Settings</h1>
      </header>

      {/* Content */}
      <main className="flex-1 max-w-2xl w-full mx-auto px-6 py-8 space-y-6">

        {/* Backend status */}
        <Section title="Backend Connection" icon={<Server size={14} />}>
          <Row
            label="Status"
            value={<StatusIndicator status={state.connectionStatus} />}
          />
          <Row label="Endpoint" value={<code className="font-mono text-xs">/api/health</code>} />
          <p className="text-xs text-text-muted mt-2">
            The frontend communicates with the FastAPI backend via Vite's dev
            proxy at <code className="font-mono">/api</code>. Ensure the backend
            is running on the configured port.
          </p>
        </Section>

        {/* Accessibility */}
        <Section title="Accessibility" icon={<Accessibility size={14} />}>
          <Row
            label="Accessibility mode"
            value={<AccessibilityToggle />}
          />
          <div className="space-y-2 mt-2">
            {(
              [
                ["largeText", "Large text"],
                ["highContrast", "High contrast"],
                ["reducedMotion", "Reduce motion"],
                ["strongFocus", "Strong focus indicators"],
              ] as [keyof typeof accessibility, string][]
            ).map(([key, label]) => (
              <label
                key={key}
                className="flex items-center gap-2.5 cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={accessibility[key] as boolean}
                  onChange={(e) =>
                    setAccessibility({ [key]: e.target.checked })
                  }
                  className="w-3.5 h-3.5 rounded accent-text-accent cursor-pointer"
                  aria-label={label}
                />
                <span className="text-xs text-text-secondary">{label}</span>
              </label>
            ))}
          </div>
        </Section>

        {/* Application info */}
        <Section title="Application" icon={<Info size={14} />}>
          <Row label="Application" value="SilentVoice AI" />
          <Row label="Phase" value="Phase 1 — Foundation" />
          <Row label="Frontend" value="React 18 + Vite + TypeScript + Tailwind CSS" />
          <Row label="Backend" value="Python 3 + FastAPI + Uvicorn" />
          <Row
            label="Phase 2 features"
            value={
              <span className="text-text-muted">
                Voice, AI assistant, project scanner, diff, sandbox
              </span>
            }
          />
        </Section>
      </main>
    </div>
  );
}
