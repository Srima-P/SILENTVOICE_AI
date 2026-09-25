/**
 * ChatMessage — renders a single conversation turn.
 * Phase 3: assistant messages render Markdown; intent metadata displayed as badge.
 * Phase 4: follow-up suggestion chips.
 * Phase 5: text-to-speech speaker button; Phase 5 intent labels.
 */

import type { ChatMessage as ChatMessageType } from "@/types";
import { formatTime } from "@/utils/helpers";
import { Bot, User, FileCode, Zap, AlertCircle, Volume2, VolumeX } from "lucide-react";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { useSpeech } from "@/hooks/useSpeech";

interface Props {
  message: ChatMessageType;
  /** Phase 4: called when the user clicks a follow-up suggestion chip */
  onSuggestionClick?: (text: string) => void;
  /** Phase 4: disable chips while the assistant is thinking */
  disabled?: boolean;
}

const INTENT_LABELS: Record<string, string> = {
  explain_file: "Explain file",
  summarize_file: "Summarize file",
  explain_dependencies: "Dependencies",
  project_overview: "Project overview",
  find_dependents: "Find dependents",
  explain_relationship: "Relationship",
  show_related: "Related files",
  // Phase 5
  onboarding_start: "Onboarding",
  architecture_overview: "Architecture",
  setup_guidance: "Setup guide",
  beginner_tasks: "Beginner tasks",
  unsupported: "Unknown intent",
};

export function ChatMessage({ message, onSuggestionClick, disabled }: Props) {
  const isUser = message.role === "user";
  const isError = message.is_error === true;
  const hasSuggestions =
    !isUser &&
    !isError &&
    message.follow_up_suggestions &&
    message.follow_up_suggestions.length > 0;

  const { speak, stop, isSpeaking, isSupported: ttsSupported } = useSpeech();

  function handleTts() {
    if (isSpeaking) {
      stop();
    } else {
      speak(message.content);
    }
  }

  return (
    <div
      className={[
        "flex gap-2.5 px-3 py-2",
        isUser ? "flex-row-reverse" : "flex-row",
      ].join(" ")}
      role="listitem"
    >
      {/* Avatar */}
      <span
        className={[
          "flex-shrink-0 flex items-center justify-center w-6 h-6 rounded-full text-xs mt-0.5",
          isUser
            ? "bg-text-accent/20 text-text-accent"
            : isError
            ? "bg-status-error/20 text-status-error"
            : "bg-surface-4 text-text-muted",
        ].join(" ")}
        aria-hidden="true"
      >
        {isUser ? (
          <User size={12} />
        ) : isError ? (
          <AlertCircle size={12} />
        ) : (
          <Bot size={12} />
        )}
      </span>

      {/* Bubble + metadata */}
      <div className={["flex flex-col gap-1 min-w-0 flex-1", isUser ? "items-end" : "items-start"].join(" ")}>
        {/* Bubble */}
        <div
          className={[
            "max-w-full rounded-lg px-3 py-2 leading-relaxed",
            isUser
              ? "bg-text-accent/15 text-text-primary rounded-tr-none text-xs"
              : isError
              ? "bg-status-error/10 border border-status-error/20 text-text-secondary rounded-tl-none"
              : "bg-surface-3 text-text-secondary rounded-tl-none",
          ].join(" ")}
        >
          {isUser ? (
            <p className="m-0 whitespace-pre-wrap break-words text-xs">{message.content}</p>
          ) : (
            <MarkdownRenderer content={message.content} />
          )}

          <time
            className="block mt-1.5 text-text-muted text-[10px]"
            dateTime={message.timestamp.toISOString()}
          >
            {formatTime(message.timestamp)}
          </time>
        </div>

        {/* Intent + file context + TTS (assistant messages only) */}
        {!isUser && (
          <div className="flex flex-wrap items-center gap-1.5 px-1">
            {message.intent && (
              <span className="flex items-center gap-1 text-[10px] text-text-muted bg-surface-3 px-1.5 py-0.5 rounded">
                <Zap size={9} aria-hidden="true" />
                {INTENT_LABELS[message.intent] ?? message.intent}
              </span>
            )}
            {message.target_file && (
              <span
                className="flex items-center gap-1 text-[10px] text-text-muted bg-surface-3 px-1.5 py-0.5 rounded font-mono truncate max-w-[180px]"
                title={message.target_file}
              >
                <FileCode size={9} aria-hidden="true" />
                {message.target_file.split("/").pop()}
              </span>
            )}

            {/* Phase 5: TTS speaker button */}
            {ttsSupported && !isError && (
              <button
                type="button"
                onClick={handleTts}
                aria-label={isSpeaking ? "Stop reading response aloud" : "Read response aloud"}
                title={isSpeaking ? "Stop" : "Read aloud"}
                className={[
                  "flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded transition-colors",
                  isSpeaking
                    ? "text-text-accent bg-text-accent/10"
                    : "text-text-muted hover:text-text-accent hover:bg-surface-3",
                ].join(" ")}
              >
                {isSpeaking ? <VolumeX size={9} aria-hidden="true" /> : <Volume2 size={9} aria-hidden="true" />}
                {isSpeaking ? "Stop" : "Read"}
              </button>
            )}
          </div>
        )}

        {/* Ambiguous file candidates */}
        {!isUser && message.candidates && message.candidates.length > 1 && (
          <div className="px-1">
            <p className="text-[10px] text-text-muted mb-1">Did you mean one of these?</p>
            <ul className="space-y-0.5">
              {message.candidates.map((c) => (
                <li
                  key={c}
                  className="text-[10px] font-mono text-text-accent bg-surface-3 px-1.5 py-0.5 rounded"
                >
                  {c}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Phase 4/5: Follow-up suggestion chips */}
        {hasSuggestions && onSuggestionClick && (
          <div className="px-1 mt-0.5">
            <p className="text-[10px] text-text-muted uppercase tracking-widest mb-1.5">
              Follow up:
            </p>
            <div className="flex flex-col gap-1">
              {message.follow_up_suggestions!.map((s) => (
                <button
                  key={s}
                  onClick={() => onSuggestionClick(s)}
                  disabled={disabled}
                  className={[
                    "text-left px-2 py-1 rounded border text-[10px] transition-colors",
                    "border-border/60 text-text-muted hover:text-text-primary hover:bg-surface-3 hover:border-text-accent/30",
                    disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer",
                  ].join(" ")}
                >
                  <Zap size={8} className="inline mr-1 text-text-accent opacity-70" aria-hidden="true" />
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
