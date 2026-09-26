/**
 * changesApi.ts — Phase 6 frontend service for the code-modification pipeline.
 *
 * Routes through Vite proxy /api → backend; never hardcodes backend URL.
 *
 * Endpoints:
 *   POST /api/changes/propose       → proposeChange()
 *   GET  /api/changes/diff/{id}     → getDiff()
 *   POST /api/changes/apply         → applyChange()
 *   POST /api/changes/reject        → rejectChange()
 */

import type { ProposeChangeResponse, ApplyChangeResponse } from "@/types";

const BASE = "/api/changes";

// ─── Generic fetch helper (mirrors pattern from chatApi.ts) ───────────────────

async function changesFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body?.detail ?? body?.message ?? detail;
    } catch {
      // ignore parse errors — use statusText fallback
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

// ─── API functions ────────────────────────────────────────────────────────────

/**
 * Generate a code-modification proposal for a single project file.
 *
 * POST /api/changes/propose
 *
 * @param file_path   Relative path from the project root (e.g. "src/Login.jsx").
 * @param instruction Natural-language description of the desired change.
 * @returns           A ProposeChangeResponse containing the diff and proposal_id.
 */
export async function proposeChange(
  file_path: string,
  instruction: string
): Promise<ProposeChangeResponse> {
  return changesFetch<ProposeChangeResponse>("/propose", {
    method: "POST",
    body: JSON.stringify({ file_path, instruction }),
  });
}

/**
 * Re-fetch an existing proposal by ID (idempotent; no Groq call).
 *
 * GET /api/changes/diff/{proposal_id}
 */
export async function getDiff(
  proposal_id: string
): Promise<ProposeChangeResponse> {
  return changesFetch<ProposeChangeResponse>(`/diff/${encodeURIComponent(proposal_id)}`);
}

/**
 * Apply an approved proposal to disk (atomic write).
 *
 * POST /api/changes/apply
 * confirmed must always be true — the schema rejects false.
 */
export async function applyChange(
  proposal_id: string
): Promise<ApplyChangeResponse> {
  return changesFetch<ApplyChangeResponse>("/apply", {
    method: "POST",
    body: JSON.stringify({ proposal_id, confirmed: true }),
  });
}

/**
 * Discard a pending proposal (zero filesystem operations).
 *
 * POST /api/changes/reject
 */
export async function rejectChange(
  proposal_id: string
): Promise<{ ok: boolean }> {
  return changesFetch<{ ok: boolean }>("/reject", {
    method: "POST",
    body: JSON.stringify({ proposal_id }),
  });
}
