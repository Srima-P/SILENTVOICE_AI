/**
 * useMicrophone — Phase 5 voice recording hook.
 *
 * States:
 *   idle        → microphone button available, not recording
 *   recording   → actively capturing audio (MediaRecorder running)
 *   processing  → audio uploaded to backend, waiting for transcript
 *   error       → something went wrong (message in `errorMessage`)
 *
 * Usage:
 *   const mic = useMicrophone({ onTranscript: (text) => setInput(text) });
 *   <button onClick={mic.toggle}>...</button>
 *
 * Audio is recorded in the best format the browser supports, sent to
 * POST /api/voice/transcribe, and the transcript is returned via onTranscript.
 * The raw audio is never stored; it is discarded after upload.
 */

import { useState, useRef, useCallback } from "react";
import { transcribeAudio } from "@/services/voiceApi";

export type MicState = "idle" | "recording" | "processing" | "error";

export interface UseMicrophoneOptions {
  /** Called with the transcript text on successful transcription. */
  onTranscript: (text: string) => void;
  /** Called with a user-friendly error description. */
  onError?: (message: string) => void;
  /** Called when recording starts. */
  onRecordingStart?: () => void;
  /** Called when recording stops (before processing). */
  onRecordingStop?: () => void;
  /** Called when processing (transcription) completes successfully. */
  onProcessingDone?: () => void;
}

export interface UseMicrophoneReturn {
  micState: MicState;
  errorMessage: string | null;
  /** True when the browser supports MediaRecorder / getUserMedia. */
  isSupported: boolean;
  /** Start recording if idle, stop recording if recording. */
  toggle: () => void;
  /** Stop recording without processing (cancel). */
  cancel: () => void;
}

/** Returns true if the browser supports the required audio APIs. */
function checkSupport(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof navigator?.mediaDevices?.getUserMedia === "function" &&
    typeof MediaRecorder !== "undefined"
  );
}

/** Pick the best supported MIME type for MediaRecorder. */
function getBestMimeType(): string {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/ogg",
  ];
  for (const type of candidates) {
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return "";   // let the browser pick its default
}

export function useMicrophone(options: UseMicrophoneOptions): UseMicrophoneReturn {
  const { onTranscript, onError, onRecordingStart, onRecordingStop, onProcessingDone } = options;

  const [micState, setMicState] = useState<MicState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const mimeTypeRef = useRef<string>("");

  const isSupported = checkSupport();

  const _setError = useCallback((msg: string) => {
    setMicState("error");
    setErrorMessage(msg);
    onError?.(msg);
  }, [onError]);

  const _stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  const startRecording = useCallback(async () => {
    if (!isSupported) {
      _setError("Voice input is not supported in this browser. You can continue using text commands.");
      return;
    }

    setErrorMessage(null);

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    } catch (err) {
      const msg =
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Microphone permission denied. Please allow microphone access in your browser settings."
          : err instanceof DOMException && err.name === "NotFoundError"
          ? "No microphone found. Please connect a microphone and try again."
          : "Could not access the microphone. Please check your browser permissions.";
      _setError(msg);
      return;
    }

    streamRef.current = stream;
    chunksRef.current = [];

    const mimeType = getBestMimeType();
    mimeTypeRef.current = mimeType;

    let recorder: MediaRecorder;
    try {
      recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
    } catch {
      _stopStream();
      _setError("Could not start audio recording. Your browser may not support this feature.");
      return;
    }

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };

    recorder.onerror = () => {
      _stopStream();
      _setError("Recording failed unexpectedly. Please try again.");
    };

    recorder.onstop = async () => {
      _stopStream();
      const effectiveMime = mimeTypeRef.current || "audio/webm";
      const audioBlob = new Blob(chunksRef.current, { type: effectiveMime });
      chunksRef.current = [];

      if (audioBlob.size === 0) {
        setMicState("idle");
        _setError("No audio was captured. Please try again.");
        return;
      }

      setMicState("processing");
      onRecordingStop?.();

      try {
        const result = await transcribeAudio(audioBlob, effectiveMime);
        const transcript = result.text?.trim();
        if (!transcript) {
          _setError("No speech detected. Please speak clearly and try again.");
          return;
        }
        setMicState("idle");
        onTranscript(transcript);
        onProcessingDone?.();
      } catch (err) {
        const msg =
          err instanceof Error ? err.message : "Transcription failed. Please try again.";
        _setError(msg);
      }
    };

    mediaRecorderRef.current = recorder;
    recorder.start(250);   // collect chunks every 250ms
    setMicState("recording");
    onRecordingStart?.();
  }, [isSupported, _setError, _stopStream, onTranscript, onRecordingStart, onRecordingStop, onProcessingDone]);

  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
    mediaRecorderRef.current = null;
  }, []);

  const toggle = useCallback(() => {
    if (micState === "idle" || micState === "error") {
      void startRecording();
    } else if (micState === "recording") {
      stopRecording();
    }
    // ignore clicks during "processing"
  }, [micState, startRecording, stopRecording]);

  const cancel = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      // Prevent the onstop handler from uploading by clearing chunks first
      recorder.ondataavailable = null;
      recorder.onstop = null;
      recorder.stop();
      mediaRecorderRef.current = null;
    }
    _stopStream();
    chunksRef.current = [];
    setMicState("idle");
    setErrorMessage(null);
  }, [_stopStream]);

  return { micState, errorMessage, isSupported, toggle, cancel };
}
