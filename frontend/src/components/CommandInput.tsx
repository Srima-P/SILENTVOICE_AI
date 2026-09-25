/**
 * CommandInput — text area + microphone + send button.
 *
 * Phase 5:
 *   - Microphone button is now fully functional (replaced placeholder).
 *   - Uses useMicrophone hook for recording state management.
 *   - Transcript is inserted into the text input — user confirms before sending.
 *   - Visual states: idle / recording / processing / error.
 *   - Accessible: aria-labels update with state, focus managed, error visible.
 */

import { useRef, useState, useEffect } from "react";
import { Send, Mic, MicOff, Loader2, X } from "lucide-react";
import { useMicrophone, type MicState } from "@/hooks/useMicrophone";
import { useApp } from "@/contexts/AppContext";

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
}

// ── Mic button appearance by state ────────────────────────────────────────────

const MIC_CONFIG: Record<MicState, {
  icon: React.ReactNode;
  ariaLabel: string;
  title: string;
  className: string;
}> = {
  idle: {
    icon: <Mic size={15} aria-hidden="true" />,
    ariaLabel: "Start voice input",
    title: "Start voice input",
    className: "text-text-muted hover:text-text-accent hover:bg-surface-3",
  },
  recording: {
    icon: <MicOff size={15} aria-hidden="true" />,
    ariaLabel: "Stop voice recording",
    title: "Stop voice recording",
    className: "text-status-error animate-pulse bg-status-error/10",
  },
  processing: {
    icon: <Loader2 size={15} className="animate-spin" aria-hidden="true" />,
    ariaLabel: "Transcribing voice input",
    title: "Transcribing…",
    className: "text-text-accent opacity-70",
  },
  error: {
    icon: <Mic size={15} aria-hidden="true" />,
    ariaLabel: "Start voice input (previous attempt failed)",
    title: "Start voice input",
    className: "text-status-warn hover:text-text-accent hover:bg-surface-3",
  },
};

export function CommandInput({ onSend, disabled = false }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { addActivity } = useApp();

  const mic = useMicrophone({
    onTranscript: (text) => {
      setValue(text);
      textareaRef.current?.focus();
      addActivity({
        id: crypto.randomUUID(),
        timestamp: new Date(),
        message: `Voice transcription completed: "${text.slice(0, 60)}${text.length > 60 ? "…" : ""}"`,
        type: "success",
      });
    },
    onError: (msg) => {
      addActivity({
        id: crypto.randomUUID(),
        timestamp: new Date(),
        message: `Voice error: ${msg}`,
        type: "error",
      });
    },
    onRecordingStart: () => {
      addActivity({
        id: crypto.randomUUID(),
        timestamp: new Date(),
        message: "Voice recording started.",
        type: "info",
      });
    },
    onRecordingStop: () => {
      addActivity({
        id: crypto.randomUUID(),
        timestamp: new Date(),
        message: "Voice recording stopped. Transcribing…",
        type: "info",
      });
    },
    onProcessingDone: () => {
      addActivity({
        id: crypto.randomUUID(),
        timestamp: new Date(),
        message: "Transcription complete.",
        type: "success",
      });
    },
  });

  const micCfg = MIC_CONFIG[mic.micState];
  const isMicBusy = mic.micState === "processing";
  const isRecording = mic.micState === "recording";

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    // Cancel any ongoing recording if user force-sends
    if (isRecording) mic.cancel();
    onSend(trimmed);
    setValue("");
    textareaRef.current?.focus();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
    if (e.key === "Escape" && isRecording) {
      mic.cancel();
    }
  }

  // Auto-announce recording state changes to screen readers via aria-live
  // (handled by the status element below)

  return (
    <div className="flex flex-col border-t border-border bg-surface-2">
      {/* Recording indicator bar */}
      {isRecording && (
        <div
          className="flex items-center gap-2 px-3 py-1.5 bg-status-error/10 border-b border-status-error/20"
          role="status"
          aria-live="polite"
        >
          <span className="inline-block w-2 h-2 rounded-full bg-status-error animate-pulse" aria-hidden="true" />
          <span className="text-[10px] text-status-error font-medium">
            Recording — speak your command, then click ■ to stop
          </span>
          <button
            type="button"
            onClick={mic.cancel}
            aria-label="Cancel voice recording"
            className="ml-auto text-[10px] text-text-muted hover:text-status-error transition-colors"
          >
            <X size={10} aria-hidden="true" /> Cancel
          </button>
        </div>
      )}

      {/* Transcribing indicator */}
      {isMicBusy && (
        <div
          className="flex items-center gap-2 px-3 py-1.5 bg-text-accent/5 border-b border-text-accent/20"
          role="status"
          aria-live="polite"
        >
          <Loader2 size={10} className="animate-spin text-text-accent" aria-hidden="true" />
          <span className="text-[10px] text-text-accent">Transcribing voice input…</span>
        </div>
      )}

      {/* Voice error message */}
      {mic.micState === "error" && mic.errorMessage && (
        <div
          className="flex items-start gap-2 px-3 py-1.5 bg-status-error/10 border-b border-status-error/20"
          role="alert"
          aria-live="assertive"
        >
          <span className="text-[10px] text-status-error flex-1">{mic.errorMessage}</span>
          <button
            type="button"
            onClick={mic.cancel}
            aria-label="Dismiss error"
            className="text-text-muted hover:text-status-error"
          >
            <X size={10} aria-hidden="true" />
          </button>
        </div>
      )}

      {/* Unsupported browser notice (shown once) */}
      {!mic.isSupported && (
        <div
          className="px-3 py-1.5 bg-surface-3 border-b border-border text-[10px] text-text-muted"
          role="note"
        >
          Voice input is not supported in this browser. Text commands work normally.
        </div>
      )}

      {/* Input row */}
      <div className="flex gap-2 items-end px-3 py-2">
        {/* Microphone button */}
        <button
          type="button"
          onClick={mic.toggle}
          disabled={disabled || isMicBusy || !mic.isSupported}
          aria-label={micCfg.ariaLabel}
          aria-pressed={isRecording}
          title={micCfg.title}
          className={[
            "flex-shrink-0 p-2 rounded transition-colors focus-visible:ring-2 focus-visible:ring-text-accent",
            disabled || isMicBusy || !mic.isSupported
              ? "opacity-40 cursor-not-allowed text-text-muted"
              : micCfg.className,
          ].join(" ")}
        >
          {micCfg.icon}
        </button>

        {/* Text input */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            isRecording
              ? "Listening… (Enter to send, Esc to cancel)"
              : "Type or speak a command… (Enter to send)"
          }
          aria-label="Command input"
          aria-describedby={mic.errorMessage ? "mic-error" : undefined}
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
            "flex-shrink-0 p-2 rounded transition-colors focus-visible:ring-2 focus-visible:ring-text-accent",
            value.trim() && !disabled
              ? "text-text-accent hover:bg-text-accent/15"
              : "text-text-muted opacity-40 cursor-not-allowed",
          ].join(" ")}
        >
          <Send size={15} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
