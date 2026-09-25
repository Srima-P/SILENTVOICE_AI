/**
 * voiceApi.ts — Phase 5 client for the voice/transcription backend.
 * Routes through Vite proxy /api → backend, never hardcodes backend URL.
 * The GROQ_API_KEY is never sent from the browser — all key usage happens server-side.
 */

export interface TranscribeResponse {
  text: string;
  duration_hint?: string;
}

export interface VoiceStatusResponse {
  configured: boolean;
  model: string;
  max_audio_mb: number;
}

const BASE = "/api/voice";

async function voiceFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, options);

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
 * Check whether the backend voice (Groq) key is configured.
 */
export async function getVoiceStatus(): Promise<VoiceStatusResponse> {
  return voiceFetch<VoiceStatusResponse>("/status");
}

/**
 * Upload an audio Blob to the backend and receive the Whisper transcript.
 *
 * The audio Blob is sent as a multipart/form-data upload.
 * No API key is transmitted from the browser — all key handling is server-side.
 */
export async function transcribeAudio(
  audioBlob: Blob,
  mimeType: string
): Promise<TranscribeResponse> {
  const form = new FormData();
  // Use .webm extension for all MediaRecorder output; backend normalises MIME
  const ext = mimeType.includes("ogg") ? ".ogg" : ".webm";
  form.append("file", audioBlob, `recording${ext}`);

  // Content-Type is set automatically by the browser for FormData
  return voiceFetch<TranscribeResponse>("/transcribe", {
    method: "POST",
    body: form,
  });
}
