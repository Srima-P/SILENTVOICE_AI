/**
 * ChatMessage — renders a single conversation turn.
 * Phase 3: assistant messages render Markdown; intent metadata is displayed
 * as a small context badge below the bubble.
 */

import type { ChatMessage as ChatMessageType } from "@/types";
import { formatTime } from "@/utils/helpers";
import { Bot, User, FileCode, Zap, AlertCircle } from "lucide-react";
import { MarkdownRenderer } from "./MarkdownRenderer";

interface Props {
  message: ChatMessageType;
}

const INTENT_LABELS: Record<string, string> = {
  explain_file: "Explain file",
  summarize_file: "Summarize file",
  explain_dependencies: "Dependencies",
  project_overview: "Project overview",
  unsupported: "Unknown intent",
};

export function ChatMessage({ message }: Props) {
  const isUser = message.role === "user";
  const isError = message.is_error === true;
  const hasIntent = !isUser && message.intent && message.intent !== "unsupported";

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
      <div className={["flex flex-col gap-1", isUser ? "items-end" : "items-start"].join(" ")}>
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

        {/* Intent + file context badge (assistant messages only) */}
        {!isUser && (message.intent || message.target_file) && (
          <div className="flex flex-wrap items-center gap-1.5 px-1">
            {message.intent && (
              <span className="flex items-center gap-1 text-[10px] text-text-muted bg-surface-3 px-1.5 py-0.5 rounded">
                <Zap size={9} aria-hidden="true" />
                {INTENT_LABELS[message.intent] ?? message.intent}
              </span>
            )}
            {message.target_file && (
              <span className="flex items-center gap-1 text-[10px] text-text-muted bg-surface-3 px-1.5 py-0.5 rounded font-mono truncate max-w-[180px]" title={message.target_file}>
                <FileCode size={9} aria-hidden="true" />
                {message.target_file.split("/").pop()}
              </span>
            )}
          </div>
        )}

        {/* Ambiguous file candidates */}
        {!isUser && message.candidates && message.candidates.length > 1 && (
          <div className="px-1">
            <p className="text-[10px] text-text-muted mb-1">Did you mean one of these?</p>
            <ul className="space-y-0.5">
              {message.candidates.map((c) => (
                <li key={c} className="text-[10px] font-mono text-text-accent bg-surface-3 px-1.5 py-0.5 rounded">
                  {c}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
