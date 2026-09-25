/**
 * useSpeech — Phase 5 text-to-speech hook using the browser's SpeechSynthesis API.
 *
 * Usage:
 *   const { speak, stop, isSpeaking, isSupported } = useSpeech();
 *   speak("Hello, this is the response text.");
 *
 * Strips Markdown syntax before speaking so the user hears clean prose.
 * Does NOT automatically speak responses — the user must click the speaker button.
 */

import { useState, useCallback, useRef } from "react";

export interface UseSpeechReturn {
  /** True when speech is currently playing. */
  isSpeaking: boolean;
  /** True if the browser supports SpeechSynthesis. */
  isSupported: boolean;
  /** Speak the given text. Stops any current speech first. */
  speak: (text: string) => void;
  /** Stop speech playback. */
  stop: () => void;
}

/** Strip common Markdown syntax to produce clean speech text. */
function stripMarkdown(text: string): string {
  return text
    .replace(/#{1,6}\s+/g, "")          // headings
    .replace(/\*\*(.+?)\*\*/g, "$1")     // bold
    .replace(/\*(.+?)\*/g, "$1")         // italic
    .replace(/`{1,3}([^`]+)`{1,3}/g, "$1") // inline code / code blocks
    .replace(/\[(.+?)\]\(.+?\)/g, "$1") // links
    .replace(/^[-*+]\s+/gm, "")          // list bullets
    .replace(/^\d+\.\s+/gm, "")          // ordered list
    .replace(/^>\s+/gm, "")              // blockquotes
    .replace(/\n{2,}/g, " ")             // collapse blank lines
    .replace(/\n/g, " ")                 // newlines → spaces
    .trim();
}

function checkSupport(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function useSpeech(): UseSpeechReturn {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const isSupported = checkSupport();

  const stop = useCallback(() => {
    if (!isSupported) return;
    window.speechSynthesis.cancel();
    setIsSpeaking(false);
  }, [isSupported]);

  const speak = useCallback(
    (rawText: string) => {
      if (!isSupported) return;

      // Stop any current speech
      window.speechSynthesis.cancel();

      const cleanText = stripMarkdown(rawText);
      if (!cleanText) return;

      const utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;

      utterance.onstart = () => setIsSpeaking(true);
      utterance.onend = () => setIsSpeaking(false);
      utterance.onerror = () => setIsSpeaking(false);

      utteranceRef.current = utterance;
      window.speechSynthesis.speak(utterance);
    },
    [isSupported]
  );

  return { isSpeaking, isSupported, speak, stop };
}
