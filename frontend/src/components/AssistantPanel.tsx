/**
 * AssistantPanel — right sidebar with the real AI conversation interface.
 * Phase 3: connects to POST /api/assistant/chat via chatApi.ts.
 * Phase 4: sends selected_file + conversation_history; pendingAssistantInput.
 * Phase 5: onboarding quick actions in empty state.
 * Phase 6: dispatches setPendingProposalRequest for modify_code intent
 *           instead of calling the changes API directly.
 */

import { useRef, useEffect, useCallback } from "react";
import { Bot, Trash2, Loader2, AlertCircle, Zap, BookOpen } from "lucide-react";
import { ChatMessage } from "./ChatMessage";
import { CommandInput } from "./CommandInput";
import { EmptyState } from "./EmptyState";
import { useApp } from "@/contexts/AppContext";
import { sendMessage, getAssistantStatus } from "@/services/chatApi";
import { uid } from "@/utils/helpers";
import type { ChatMessage as ChatMessageType, ConversationTurn } from "@/types";

// ─── Suggested prompts shown in the empty state ───────────────────────────────

const SUGGESTIONS = [
  "Explain Login.jsx",
  "Summarize Dashboard.jsx",
  "Explain dependencies of App.jsx",
  "Give me a project overview",
];

// ─── Phase 5: Onboarding quick actions ───────────────────────────────────────

const ONBOARDING_ACTIONS = [
  { label: "Start Onboarding",      message: "I'm new to this project" },
  { label: "Explain Architecture",  message: "Explain the architecture" },
  { label: "Setup Guide",           message: "How do I set up this project?" },
  { label: "Beginner Tasks",        message: "Give me beginner tasks" },
];

// Max conversation history turns sent to backend (keep context window small)
const MAX_HISTORY_TURNS = 10;

export function AssistantPanel() {
  const {
    state,
    addMessage,
    clearConversation,
    setAssistantThinking,
    setGroqConfigured,
    addActivity,
    setPendingAssistantInput,
    setPendingProposalRequest,
  } = useApp();
  const { conversation, assistantThinking, groqConfigured } = state;
  const bottomRef = useRef<HTMLDivElement>(null);

  // ── Check Groq status on mount ────────────────────────────────────────────
  useEffect(() => {
    if (groqConfigured === null) {
      getAssistantStatus()
        .then((s) => setGroqConfigured(s.groq_configured))
        .catch(() => setGroqConfigured(false));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Auto-scroll ───────────────────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversation.length, assistantThinking]);

  // ── Send handler ──────────────────────────────────────────────────────────
  const handleSend = useCallback(
    async (text: string) => {
      // 1. Add user message immediately
      const userMsg: ChatMessageType = {
        id: uid(),
        role: "user",
        content: text,
        timestamp: new Date(),
      };
      addMessage(userMsg);
      setAssistantThinking(true);

      addActivity({
        id: uid(),
        timestamp: new Date(),
        message: `Message sent: "${text.slice(0, 60)}${text.length > 60 ? "…" : ""}"`,
        type: "info",
      });

      // Phase 4: build context to send alongside the message
      const recentHistory: ConversationTurn[] = state.conversation
        .slice(-MAX_HISTORY_TURNS)
        .map((msg) => ({ role: msg.role, content: msg.content }));

      try {
        const result = await sendMessage(text, {
          selected_file: state.selectedFile?.path ?? undefined,
          conversation_history: recentHistory,
        });

        addActivity({
          id: uid(),
          timestamp: new Date(),
          message: `Intent detected: ${result.intent}${result.target_file ? ` → ${result.target_file}` : ""}${result.context_source !== "none" ? ` (context: ${result.context_source})` : ""}`,
          type: "info",
        });

        if (result.groq_used) {
          addActivity({
            id: uid(),
            timestamp: new Date(),
            message: "Groq response received.",
            type: "success",
          });
        }

        // Phase 6: for modify_code intent, route to ChangesPanel via context
        if (result.intent === "modify_code" && result.target_file) {
          setPendingProposalRequest({
            filePath: result.target_file,
            instruction: text,
          });
        }

        const assistantMsg: ChatMessageType = {
          id: uid(),
          role: "assistant",
          content: result.response,
          timestamp: new Date(),
          intent: result.intent,
          target_file: result.target_file,
          is_error: result.error,
          candidates: result.candidates,
          // Phase 4: store follow-up suggestions in the message
          follow_up_suggestions: result.follow_up_suggestions,
        };
        addMessage(assistantMsg);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        addActivity({
          id: uid(),
          timestamp: new Date(),
          message: `Assistant error: ${msg}`,
          type: "error",
        });
        const errMsg: ChatMessageType = {
          id: uid(),
          role: "assistant",
          content: `**Connection error:** ${msg}\n\nMake sure the backend is running.`,
          timestamp: new Date(),
          is_error: true,
        };
        addMessage(errMsg);
      } finally {
        setAssistantThinking(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [addMessage, setAssistantThinking, addActivity, state.selectedFile, state.conversation]
  );

  // ── Phase 4: Watch pendingAssistantInput (set by "Explain This" button) ──
  useEffect(() => {
    if (state.pendingAssistantInput) {
      const text = state.pendingAssistantInput;
      setPendingAssistantInput(null);
      void handleSend(text);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.pendingAssistantInput]);

  function handleSuggestion(text: string) {
    void handleSend(text);
  }

  return (
    <aside
      className="flex flex-col w-80 min-w-0 bg-surface-1 border-l border-border overflow-hidden flex-shrink-0"
      aria-label="AI assistant panel"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <Bot size={14} className="text-text-accent" aria-hidden="true" />
          <span className="text-xs font-semibold text-text-secondary uppercase tracking-widest">
            Assistant
          </span>
          {assistantThinking && (
            <span className="flex items-center gap-1 text-[10px] text-text-muted" aria-live="polite">
              <Loader2 size={10} className="animate-spin" aria-hidden="true" />
              Thinking…
            </span>
          )}
        </div>
        {conversation.length > 0 && (
          <button
            onClick={clearConversation}
            aria-label="Clear conversation"
            title="Clear conversation"
            className="p-1 rounded text-text-muted hover:text-status-error hover:bg-surface-3 transition-colors"
          >
            <Trash2 size={13} aria-hidden="true" />
          </button>
        )}
      </div>

      {/* Groq not configured warning */}
      {groqConfigured === false && (
        <div
          className="flex items-start gap-2 px-3 py-2 bg-status-warn/10 border-b border-status-warn/20 text-xs"
          role="alert"
        >
          <AlertCircle size={12} className="mt-0.5 flex-shrink-0 text-status-warn" aria-hidden="true" />
          <span className="text-text-secondary">
            <strong>GROQ_API_KEY not set.</strong> Add your key to <code className="font-mono text-[10px]">.env</code> to enable AI features.
          </span>
        </div>
      )}

      {/* Conversation */}
      <div
        className="flex-1 overflow-y-auto py-1 min-h-0"
        role="list"
        aria-label="Conversation history"
        aria-live="polite"
        aria-atomic="false"
      >
        {conversation.length === 0 ? (
          <div className="flex flex-col gap-4 p-3">
            <EmptyState
              icon={<Bot size={28} />}
              title="AI Assistant ready"
              description="Ask anything about your project files."
            />

            {/* Phase 5: Onboarding quick actions */}
            <div className="space-y-1.5">
              <p className="text-[10px] text-text-muted uppercase tracking-widest px-1 flex items-center gap-1">
                <BookOpen size={9} aria-hidden="true" />
                New developer?
              </p>
              <div className="grid grid-cols-2 gap-1">
                {ONBOARDING_ACTIONS.map((a) => (
                  <button
                    key={a.label}
                    onClick={() => handleSuggestion(a.message)}
                    disabled={assistantThinking}
                    className={[
                      "text-left px-2 py-1.5 rounded border text-[10px] transition-colors",
                      "border-text-accent/30 text-text-accent hover:bg-text-accent/10",
                      assistantThinking ? "opacity-50 cursor-not-allowed" : "",
                    ].join(" ")}
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Static suggestion chips (empty state) */}
            <div className="space-y-1.5">
              <p className="text-[10px] text-text-muted uppercase tracking-widest px-1">
                Try asking:
              </p>
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => handleSuggestion(s)}
                  disabled={assistantThinking}
                  className={[
                    "w-full text-left px-2.5 py-1.5 rounded border text-xs transition-colors",
                    "border-border text-text-secondary hover:text-text-primary hover:bg-surface-3 hover:border-text-accent/30",
                    assistantThinking ? "opacity-50 cursor-not-allowed" : "",
                  ].join(" ")}
                >
                  <Zap size={10} className="inline mr-1.5 text-text-accent" aria-hidden="true" />
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {conversation.map((msg) => (
              <ChatMessage
                key={msg.id}
                message={msg}
                onSuggestionClick={handleSuggestion}
                disabled={assistantThinking}
              />
            ))}
            {/* Thinking indicator */}
            {assistantThinking && (
              <div className="flex gap-2.5 px-3 py-2" aria-live="polite" aria-label="Assistant is thinking">
                <span className="flex-shrink-0 flex items-center justify-center w-6 h-6 rounded-full bg-surface-4 text-text-muted mt-0.5" aria-hidden="true">
                  <Bot size={12} />
                </span>
                <div className="bg-surface-3 rounded-lg rounded-tl-none px-3 py-2 flex items-center gap-1.5">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-text-muted animate-bounce [animation-delay:0ms]" />
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-text-muted animate-bounce [animation-delay:150ms]" />
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-text-muted animate-bounce [animation-delay:300ms]" />
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </>
        )}
      </div>

      {/* Input */}
      <CommandInput onSend={(t) => void handleSend(t)} disabled={assistantThinking} />
    </aside>
  );
}
