/**
 * chatApi.ts — Phase 3 frontend service for the AI assistant.
 * Routes through Vite proxy /api → backend, never hardcodes backend URL.
 */

import type { ChatResponse, AssistantStatus } from "@/types";

const BASE = "/api/assistant";

async function assistantFetch<T>(
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
      // ignore
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

/**
 * Send a natural language message to the assistant.
 * Returns the structured ChatResponse from the backend.
 */
export async function sendMessage(message: string): Promise<ChatResponse> {
  return assistantFetch<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

/**
 * Check whether the Groq API key is configured on the backend.
 * Called once on mount so the panel can show an informative notice.
 */
export async function getAssistantStatus(): Promise<AssistantStatus> {
  return assistantFetch<AssistantStatus>("/status");
}
