/**
 * CommandInput — text area + voice placeholder + send button.
 */

import { useRef, useState } from "react";
import { Send, Mic } from "lucide-react";

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function CommandInput({ onSend, disabled = false }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    textareaRef.current?.focus();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="flex gap-2 items-end px-3 py-2 border-t border-border bg-surface-2">
      {/* Voice button (Phase 1 placeholder) */}
      <button
        type="button"
        disabled
        aria-label="Voice input — coming in a later phase"
        title="Voice input — coming in a later phase"
        className="flex-shrink-0 p-2 rounded text-text-muted opacity-40 cursor-not-allowed"
      >
        <Mic size={15} aria-hidden="true" />
      </button>

      {/* Text input */}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Type a command… (Enter to send)"
        aria-label="Command input"
        rows={1}
        disabled={disabled}
        className={[
          "flex-1 resize-none bg-surface-3 border border-border rounded px-3 py-2",
          "text-xs text-text-primary placeholder:text-text-muted",
          "focus:outline-none focus:border-border-focus",
          "leading-relaxed min-h-[36px] max-h-24",
          "disabled:opacity-50 disabled:cursor-not-allowed",
        ].join(" ")}
      />

      {/* Send button */}
      <button
        type="button"
        onClick={submit}
        disabled={disabled || !value.trim()}
        aria-label="Send command"
        className={[
          "flex-shrink-0 p-2 rounded transition-colors",
          value.trim() && !disabled
            ? "text-text-accent hover:bg-text-accent/15"
            : "text-text-muted opacity-40 cursor-not-allowed",
        ].join(" ")}
      >
        <Send size={15} aria-hidden="true" />
      </button>
    </div>
  );
}
