/**
 * StatusIndicator — shows backend connection status with a coloured dot
 * and a text label.  Does not rely on color alone (screen-reader label included).
 */

import type { ConnectionStatus } from "@/types";

interface Props {
  status: ConnectionStatus;
}

const CONFIG: Record<
  ConnectionStatus,
  { dot: string; label: string; text: string }
> = {
  connected: {
    dot: "bg-status-ok",
    label: "Backend connected",
    text: "Connected",
  },
  disconnected: {
    dot: "bg-status-error",
    label: "Backend offline",
    text: "Offline",
  },
  checking: {
    dot: "bg-status-warn animate-pulse",
    label: "Checking backend connection",
    text: "Checking…",
  },
};

export function StatusIndicator({ status }: Props) {
  const cfg = CONFIG[status];
  return (
    <span
      className="flex items-center gap-1.5 text-xs text-text-secondary"
      role="status"
      aria-label={cfg.label}
    >
      <span
        className={`inline-block h-2 w-2 rounded-full flex-shrink-0 ${cfg.dot}`}
        aria-hidden="true"
      />
      {cfg.text}
    </span>
  );
}
