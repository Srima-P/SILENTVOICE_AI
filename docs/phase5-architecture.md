# Phase 5: Voice-Enabled Developer Onboarding Assistant

## Overview

Phase 5 adds two major capabilities to SilentVoice AI:

1. **Voice I/O** — users can speak commands (transcribed via Groq Whisper) and optionally
   listen to responses (browser SpeechSynthesis).
2. **Developer Onboarding** — a structured workflow that helps a new developer understand
   an unfamiliar repository using existing Phase 2 project analysis data.

Both features integrate into the existing Phase 3/4 assistant pipeline without replacing it.

---

## Voice Architecture

### Speech-to-Text Flow

```
Browser Microphone
    ↓  (MediaRecorder API)
Audio Capture (WebM/OGG chunks)
    ↓
User clicks Stop
    ↓
Blob assembled in browser memory
    ↓
POST /api/voice/transcribe  (multipart/form-data, no API key sent)
    ↓  (FastAPI — VoiceService)
MIME + size validation
    ↓
Groq Whisper API  (whisper-large-v3-turbo)
    ↓
{ "text": "Explain Login.jsx" }
    ↓
Transcript inserted into CommandInput
    ↓
User reviews, edits if needed, then presses Enter / Send
    ↓
Existing Phase 3/4 assistant pipeline
```

**Key design choices:**
- Audio bytes are never stored server-side; they are discarded after the Groq response.
- The GROQ_API_KEY is never transmitted to the browser.
- The user must manually confirm/send the transcript — no automatic submission.
- Recording is cancelled with Escape or the Cancel button.

### Text-to-Speech Flow

```
Assistant response rendered in ChatMessage
    ↓
User clicks "Read" button
    ↓
useSpeech hook → window.speechSynthesis.speak()
    ↓
Browser reads Markdown-stripped text aloud
    ↓
User clicks "Stop" to cancel at any time
```

**Key design choices:**
- Uses the browser's native Web Speech API — no additional API calls.
- Markdown syntax is stripped before speaking (headings, bold, code blocks, links).
- Speech is never auto-played unless the user explicitly clicks Read.

---

## Onboarding Architecture

### Workflow

```
User: "I'm new to this project"
    ↓
IntentClassifier (deterministic) → ONBOARDING_START
    ↓
ExplanationService.handle() → OnboardingService.handle()
    ↓
_build_project_context() (from Phase 2 ProjectAnalysisResponse)
    ↓
GroqService.onboarding_start()  (summarized metadata only — no full source)
    ↓
Structured Markdown response with follow-up suggestions
```

### Supported Onboarding Intents

| Intent | Example phrases | Service method |
|---|---|---|
| `onboarding_start` | "I'm new to this project", "Help me get started" | `OnboardingService._onboarding_start()` |
| `architecture_overview` | "Explain the architecture", "How is this structured?" | `OnboardingService._architecture_overview()` |
| `setup_guidance` | "How do I set up this?", "How do I run the project?" | `OnboardingService._setup_guidance()` |
| `beginner_tasks` | "Give me beginner tasks", "What should I do first?" | `OnboardingService._beginner_tasks()` |

### Onboarding Data Sources

The `OnboardingService` uses:
- `project_analysis.project_name`, `total_files`, `languages` — always available
- `project_analysis.components` — detected React/module components
- `project_analysis.dependencies.entries` — dependency graph sample
- Setup files read by `ProjectScanner.safe_read()`: `README.md`, `package.json`,
  `requirements.txt`, `pyproject.toml`, etc. (setup_guidance intent only)

**The service never sends full source code to Groq** — only compact summarized metadata.

---

## Security

| Concern | Mitigation |
|---|---|
| API key exposure | Key read from `settings.groq_api_key` only; never in any HTTP response |
| Audio storage | Bytes discarded after Groq response; no disk writes |
| Audio size | Hard limit: 25 MB (Groq's documented limit) |
| MIME validation | Only accepted types: webm, ogg, mpeg, mp4, wav, flac, m4a |
| Path traversal | All file reads use existing `ProjectScanner.safe_read()` protections |

---

## Backend Files

| File | Purpose |
|---|---|
| `app/services/voice_service.py` | Groq Whisper integration, validation |
| `app/services/onboarding_service.py` | Onboarding workflow, setup file reading |
| `app/api/routes/voice.py` | POST /api/voice/transcribe, GET /api/voice/status |
| `backend/tests/test_phase5.py` | 34 Phase 5 tests |

## Frontend Files

| File | Purpose |
|---|---|
| `src/hooks/useMicrophone.ts` | MediaRecorder state machine, audio upload |
| `src/hooks/useSpeech.ts` | SpeechSynthesis wrapper, Markdown stripping |
| `src/services/voiceApi.ts` | Frontend client for /api/voice/* |
| `src/components/CommandInput.tsx` | Microphone button, recording indicator |
| `src/components/ChatMessage.tsx` | TTS speaker button, Phase 5 intent labels |
| `src/components/AssistantPanel.tsx` | Onboarding quick-action buttons |

---

## Running the Application

```bash
# Backend
cd silentvoice-ai/backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd silentvoice-ai/frontend
npm install
npm run dev
```

Required `.env` in `silentvoice-ai/`:
```
GROQ_API_KEY=your_groq_key_here
```

## Running Tests

```bash
cd silentvoice-ai/backend
python -m pytest tests/ -v
```

---

## Phase 6 Boundary

Phase 5 deliberately does **not** implement:
- AI code modification or file editing
- Diff generation
- Apply/Reject workflow
- Sandbox modification

Those are reserved for Phase 6.
