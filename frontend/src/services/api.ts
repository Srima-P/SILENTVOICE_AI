/**
 * api.ts — frontend service layer for SilentVoice AI backend communication.
 *
 * All backend calls are centralised here so future phases can extend this
 * file without touching components.
 */

import type { HealthResponse } from "@/types";

// Vite proxies /api → backend, so we don't need an absolute base URL in dev.
const BASE = "/api";

// ─── Generic fetch helper ─────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body?.message ?? body?.detail ?? detail;
    } catch {
      // ignore parse errors
    }
    throw new Error(`API error ${response.status}: ${detail}`);
  }

  return response.json() as Promise<T>;
}

// ─── Health ───────────────────────────────────────────────────────────────────

export async function checkHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

// ─── Future service contracts (Phase 2+) ─────────────────────────────────────
// These stubs document the planned API surface without implementing it.

// export async function scanProject(rootPath: string): Promise<ProjectMeta> { ... }
// export async function readFile(filePath: string): Promise<string> { ... }
// export async function classifyIntent(text: string): Promise<IntentResult> { ... }
// export async function explainCode(filePath: string, range?: CodeRange): Promise<string> { ... }
// export async function generateDiff(modification: CodeModification): Promise<DiffResult> { ... }
// export async function applyChange(changeId: string): Promise<void> { ... }
// export async function transcribeVoice(audio: Blob): Promise<string> { ... }
