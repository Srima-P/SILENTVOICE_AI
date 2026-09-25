/**
 * chatApi.ts — Phase 3/4 frontend service for the AI assistant.
 * Routes through Vite proxy /api → backend, never hardcodes backend URL.
 *
 * Phase 4 additions:
 *   - sendMessage accepts optional selected_file and conversation_history
 *     for context-aware conversation memory.
 */

import type { ChatResponse, AssistantStatus, ConversationTurn } from "@/types";

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
 *
 * Phase 4: also sends `selected_file` and `conversation_history` so the
 * backend can resolve follow-up pronouns ("it", "this") correctly.
 */
export async function sendMessage(
  message: string,
  context?: {
    selected_file?: string;
    conversation_history?: ConversationTurn[];
  }
): Promise<ChatResponse> {
  return assistantFetch<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({
      message,
      selected_file: context?.selected_file ?? null,
      conversation_history: context?.conversation_history ?? [],
    }),
  });
}

/**
 * Check whether the Groq API key is configured on the backend.
 * Called once on mount so the panel can show an informative notice.
 */
export async function getAssistantStatus(): Promise<AssistantStatus> {
  return assistantFetch<AssistantStatus>("/status");
}
