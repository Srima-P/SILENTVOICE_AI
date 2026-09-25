# Phase 4: Context-Aware Conversational Assistant — Implementation Plan

## Top-Level Overview

**Goal:** Extend SilentVoice AI's assistant with conversation memory, selected-file context, 
project-level relational queries, and follow-up suggestions — while preserving all 
existing Phase 1–3 functionality with backward compatibility.

**Approach:** Layer new capability onto existing services rather than replacing them.
- Backend: Enrich the `ChatRequest` schema with optional context fields, extend 
  `IntentClassifier` with new intents, add a `ConversationManager` service to resolve 
  the "active file" from multiple context sources, add new `GroqService` prompts, 
  and generate `follow_up_suggestions` in responses.
- Frontend: Pass `selected_file` and `conversation_history` in every chat request, 
  replace static suggestion chips after each response with dynamically generated ones, 
  and support "Explain this" shortcuts from the Project Explorer.

**Non-goals:**
- Persistent server-side session storage (memory lives in the frontend request payload).
- Streaming responses.
- Voice input changes.

---

## Sub-Tasks

---

### Sub-Task 1: Extend Backend Schemas and ChatRequest

**Intent**  
Allow the frontend to send context alongside each message so the backend can 
resolve the "active file" without guessing. Adds `selected_file` (the file 
highlighted in Project Explorer) and a `conversation_history` list (recent 
turns) to `ChatRequest`. Adds `follow_up_suggestions` to `ChatResponse`.

**Expected Outcomes**
- `ChatRequest` accepts optional `selected_file: str | None` and 
  `conversation_history: list[ConversationTurn]` (each turn: `role` + `content`).
- `ChatResponse` gains `follow_up_suggestions: list[str]` (default empty list).
- All existing fields and their defaults are unchanged; existing callers 
  sending `{"message": "..."}` continue to work without modification.

**Todo List**
1. Add `ConversationTurn` model to `app/schemas/assistant.py` with fields 
   `role: str` and `content: str`.
2. Extend `ChatRequest` with `selected_file: Optional[str] = None` and 
   `conversation_history: list[ConversationTurn] = []`.
3. Extend `ChatResponse` with `follow_up_suggestions: list[str] = []`.
4. Update `frontend/src/types/index.ts`: add `follow_up_suggestions: string[]` 
   to `ChatResponse`, add `selected_file?: string` and `conversation_history?` 
   to `ChatRequest`.

**Relevant Context**
- `backend/app/schemas/assistant.py` — `ChatRequest`, `ChatResponse`
- `frontend/src/types/index.ts` — `ChatRequest`, `ChatResponse`, `ChatMessage`

**Status** `[x] done`

---

### Sub-Task 2: Add ConversationManager Service (Context Resolution)

**Intent**  
Centralise the logic for determining the "active file" for a request. This keeps the 
route handler clean. Priority order: explicit file in message → selected file from 
Project Explorer → last file discussed in conversation history.

**Expected Outcomes**
- New service `app/services/conversation_manager.py` with a pure function 
  `resolve_context(message, selected_file, conversation_history, file_resolver)` 
  that returns a `ContextResolution` dataclass containing 
  `resolved_file: str | None` and `context_source: str` 
  (`"explicit"` | `"selected"` | `"memory"` | `"none"`).
- The function is stateless and accepts pre-built objects — easy to test in isolation.
- Handles follow-up pronoun phrases: "it", "this file", "this", "that file".

**Todo List**
1. Create `app/services/conversation_manager.py`.
2. Define `ContextResolution` dataclass with `resolved_file`, `context_source`, 
   and `candidates` fields.
3. Implement `resolve_context()`:
   a. If message contains an explicit file reference (via `_FILE_REF_PATTERN` from 
      `intent_classifier.py`) → use it, `context_source="explicit"`.
   b. Else if `selected_file` is provided → use it, `context_source="selected"`.
   c. Else scan `conversation_history` (most recent first) for a turn with 
      `target_file` metadata in the content or for assistant messages that 
      mentioned a file — use that file, `context_source="memory"`.
   d. Else return `resolved_file=None, context_source="none"`.
4. Add a helper `_extract_last_mentioned_file(history)` that walks recent 
   assistant turns looking for a file path pattern.

**Relevant Context**
- `backend/app/services/intent_classifier.py` — `_FILE_REF_PATTERN`, `classify()`
- `backend/app/services/file_resolver.py` — `FileResolver`
- `backend/app/api/routes/assistant.py` — current resolution logic to be replaced

**Status** `[x] done`

---

### Sub-Task 3: Extend IntentClassifier with Follow-Up and Relational Intents

**Intent**  
Add three new intents required for Phase 4 follow-up and project-relation queries, 
so the deterministic classifier handles them without an LLM call.

**New Intents**
- `FIND_DEPENDENTS` — "Which files depend on Login.jsx?", "Who imports App.jsx?"
- `EXPLAIN_RELATIONSHIP` — "How does Login.jsx connect to App.jsx?", 
  "How do these two files interact?"
- `SHOW_RELATED` — "Show related components", "What else is related to this?"

**Expected Outcomes**
- `Intent` enum has three new members: `FIND_DEPENDENTS`, `EXPLAIN_RELATIONSHIP`, 
  `SHOW_RELATED`.
- `ClassificationResult.is_file_intent` covers the new file-targeting intents.
- New patterns are added to `_INTENT_PATTERNS` above the fallback rule.
- Bare follow-up phrases with no filename ("summarize it", "what are its 
  dependencies?", "explain simply") correctly route to the corresponding 
  existing intents: when no file ref is in the message but one is resolved 
  by `ConversationManager`, the intent is still classified normally.

**Todo List**
1. Add `FIND_DEPENDENTS`, `EXPLAIN_RELATIONSHIP`, `SHOW_RELATED` to `Intent` enum.
2. Add regex patterns for each new intent to `_INTENT_PATTERNS`.
3. Update `is_file_intent` property to include the new file-targeting intents.
4. Handle "explain simply" / "explain it simply" as `SUMMARIZE_FILE` 
   (i.e., map "simply" as a summarize keyword).
5. Handle "what are its dependencies?" / "what does it import?" with no explicit 
   file ref — classify as `EXPLAIN_DEPENDENCIES` (the `ConversationManager` will 
   supply the file from context).

**Relevant Context**
- `backend/app/services/intent_classifier.py`

**Status** `[x] done`

---

### Sub-Task 4: Update Assistant Route to Use ConversationManager

**Intent**  
Wire the new `ConversationManager` into the `POST /api/assistant/chat` handler, 
replacing the current inline file-resolution logic. The handler becomes a thin 
orchestrator that delegates to the manager and the explanation service.

**Expected Outcomes**
- The route reads `body.selected_file` and `body.conversation_history` from 
  the enriched request.
- File resolution uses `ConversationManager.resolve_context()` as the single 
  authoritative source of truth for the active file.
- The route passes `context_source` through to `ExplanationService` (for 
  inclusion in the response metadata).
- All existing tests in `test_phase3.py` continue to pass unchanged.

**Todo List**
1. Import `ConversationManager` and `resolve_context` in `assistant.py`.
2. Replace the existing inline `if classification.is_file_intent and 
   classification.file_reference:` block with a call to `resolve_context()`.
3. Pass `context_source` into `ChatResponse` (add it to the schema in Sub-Task 1 
   or as a log annotation only).
4. Pass `conversation_history` to `ExplanationService.handle()` for new relational intents.

**Relevant Context**
- `backend/app/api/routes/assistant.py`
- `backend/app/services/conversation_manager.py` (new — Sub-Task 2)
- `backend/app/schemas/assistant.py`

**Status** `[x] done`

---

### Sub-Task 5: Add New GroqService Prompts and ExplanationService Handlers

**Intent**  
Implement the AI responses for the three new intents and the "relate to another 
file" scenario, using existing `project_analysis` dependency data wherever 
possible to minimise Groq calls.

**New Handlers**

| Intent | Approach |
|---|---|
| `FIND_DEPENDENTS` | Scan `project_analysis.dependencies.entries` for reverse deps; return structured list without Groq if data is available; call Groq for prose summary. |
| `EXPLAIN_RELATIONSHIP` | Read both files, pass dependency data, call Groq with a two-file relationship prompt. |
| `SHOW_RELATED` | Use dependency graph (forward + reverse) to list related files; call Groq for a brief summary. |

**Expected Outcomes**
- Three new async methods on `GroqService`: `find_dependents()`, 
  `explain_relationship()`, `show_related()`.
- Three new async handlers on `ExplanationService`: `_find_dependents()`, 
  `_explain_relationship()`, `_show_related()`.
- `ExplanationService.handle()` dispatches to the new handlers.
- `ExplanationService` generates `follow_up_suggestions` for every response 
  (3–4 contextually relevant suggestions based on intent + resolved file).

**Todo List**
1. Add `find_dependents()` to `GroqService` — system prompt is "software architect 
   explaining which parts of the codebase depend on a given module."
2. Add `explain_relationship()` to `GroqService` — two-file context prompt.
3. Add `show_related()` to `GroqService` — summarise the neighbourhood of a file.
4. Add `_find_dependents()` to `ExplanationService`: compute reverse-dependency 
   list from `project_analysis`, pass it to `GroqService.find_dependents()`.
5. Add `_explain_relationship()` to `ExplanationService`: read both files, extract 
   their deps, call `GroqService.explain_relationship()`.
6. Add `_show_related()` to `ExplanationService`: combine forward + reverse deps, 
   call `GroqService.show_related()`.
7. Add `_generate_follow_up_suggestions(intent, file_path, project_analysis)` 
   helper to `ExplanationService` — returns `list[str]` of 3–4 natural-language 
   follow-up prompts contextualised to the current result.
8. Populate `ExplanationResult` with a new `follow_up_suggestions: list[str]` field.
9. Propagate `follow_up_suggestions` through the route handler to `ChatResponse`.

**Relevant Context**
- `backend/app/services/groq_service.py`
- `backend/app/services/explanation_service.py`
- `backend/app/schemas/assistant.py` — `ExplanationResult`

**Status** `[x] done`

---

### Sub-Task 6: Update Frontend — ChatApi, Types, and Context Sending

**Intent**  
Update the frontend API layer to send the enriched request body on every message, 
passing the currently selected file and the recent conversation history. This 
enables all server-side context resolution without any changes to the 
conversation UX logic.

**Expected Outcomes**
- `chatApi.ts#sendMessage()` accepts and forwards `selected_file` and 
  `conversation_history`.
- `AssistantPanel.tsx` passes `state.selectedFile?.path` and the last N messages 
  (capped at 10 turns) from `state.conversation` to `sendMessage()`.
- Types in `index.ts` reflect the enriched request and the new 
  `follow_up_suggestions` field in the response.

**Todo List**
1. Update `sendMessage()` in `chatApi.ts` to accept an options object with 
   `selected_file?: string` and `conversation_history?: ConversationTurn[]`.
2. In `AssistantPanel.tsx#handleSend()`, read `state.selectedFile?.path` and 
   last 10 `state.conversation` entries (map to `{role, content}` tuples) and 
   pass to `sendMessage()`.
3. Store `follow_up_suggestions` from the API response in the `ChatMessage` type 
   for the assistant turn.

**Relevant Context**
- `frontend/src/services/chatApi.ts`
- `frontend/src/components/AssistantPanel.tsx`
- `frontend/src/types/index.ts`
- `frontend/src/contexts/AppContext.tsx` — `state.selectedFile`, `state.conversation`

**Status** `[ ] pending`

---

### Sub-Task 7: Frontend — Dynamic Follow-Up Suggestion Chips

**Intent**  
Replace the static hard-coded suggestion list shown in the empty state with 
dynamic chips rendered below each assistant response. When the conversation 
is empty the static chips remain for discoverability.

**Expected Outcomes**
- `ChatMessage.tsx` renders `follow_up_suggestions` as clickable chips below 
  each assistant message (visible only when suggestions exist and message is 
  not an error).
- Clicking a suggestion chip calls `onSuggestionClick(text)` — a callback 
  prop passed from `AssistantPanel`.
- The static `SUGGESTIONS` array in `AssistantPanel.tsx` is retained for the 
  empty-state, ensuring zero regression when there is no conversation.

**Todo List**
1. Add optional `follow_up_suggestions?: string[]` to the `ChatMessage` type.
2. Add an optional `onSuggestionClick?: (text: string) => void` prop to 
   `ChatMessage`.
3. Render suggestion chips below the assistant bubble in `ChatMessage.tsx` — 
   style them consistently with existing static chips.
4. In `AssistantPanel.tsx`, pass `handleSend` as `onSuggestionClick` to 
   each `ChatMessage`.
5. Populate `ChatMessage.follow_up_suggestions` from `result.follow_up_suggestions` 
   in `AssistantPanel#handleSend`.

**Relevant Context**
- `frontend/src/components/ChatMessage.tsx`
- `frontend/src/components/AssistantPanel.tsx`
- `frontend/src/types/index.ts` — `ChatMessage`

**Status** `[x] done` — 27 new tests pass; 75/78 total pass (3 pre-existing env-key failures unchanged)

---

### Sub-Task 8: Frontend — "Explain This" Shortcut from Project Explorer

**Intent**  
When a file is selected in the Project Explorer, expose a quick-action button 
(or context action) so the user can ask "Explain this file" without typing. 
The file is already in `state.selectedFile`, so no extra resolution is needed.

**Expected Outcomes**
- The `ProjectExplorer` header or the selected-file highlight row shows a 
  small "Explain" button when a file is selected.
- Clicking it calls `handleSend("Explain this")` on the `AssistantPanel` — 
  which already passes `selected_file` from Sub-Task 6, so the backend 
  resolves it via `context_source="selected"`.
- No new API endpoints; no new state fields.

**Implementation Note**  
The cleanest approach without tight coupling: expose a new action 
`sendAssistantMessage(text: string)` from `AppContext` that appends a 
user message to `state.conversation` AND signals the panel to submit it. 
The simplest workable mechanism: store a `pendingAssistantInput: string | null` 
in `AppState`; `AssistantPanel` watches it with `useEffect` and fires `handleSend` 
when it changes, then clears it. This avoids prop-drilling across the layout.

**Todo List**
1. Add `pendingAssistantInput: string | null` to `AppState` and `INITIAL_STATE`.
2. Add `SET_PENDING_INPUT` action and reducer case to `AppContext`.
3. Add `setPendingAssistantInput(text: string | null)` to context value.
4. In `AssistantPanel.tsx`, add a `useEffect` that watches 
   `state.pendingAssistantInput`: when non-null, call `handleSend(text)` then 
   `setPendingAssistantInput(null)`.
5. In `ProjectExplorer.tsx`, add a small "Explain" icon button next to the 
   selected file name that calls `setPendingAssistantInput("Explain this")`.

**Relevant Context**
- `frontend/src/contexts/AppContext.tsx`
- `frontend/src/components/ProjectExplorer.tsx`
- `frontend/src/components/AssistantPanel.tsx`
- `frontend/src/components/FileTree.tsx` — currently handles selection

**Status** `[ ] pending`

---

### Sub-Task 9: Tests — Backend Phase 4 Test Suite

**Intent**  
Add `tests/test_phase4.py` covering all new Phase 4 behaviour on the backend. 
No existing tests should be modified.

**Tests to Add**
1. `ConversationManager` — resolves from explicit file ref.
2. `ConversationManager` — resolves from `selected_file` when no explicit ref.
3. `ConversationManager` — resolves from conversation history when no other source.
4. `ConversationManager` — returns `none` when no context available.
5. `IntentClassifier` — `FIND_DEPENDENTS` detected for "Which files depend on App.jsx?".
6. `IntentClassifier` — `EXPLAIN_RELATIONSHIP` detected for "How does Login.jsx connect to App.jsx?".
7. `IntentClassifier` — `SHOW_RELATED` detected for "Show related components".
8. `IntentClassifier` — follow-up "summarize it" classifies as `SUMMARIZE_FILE`.
9. `IntentClassifier` — "what are its dependencies?" classifies as `EXPLAIN_DEPENDENCIES`.
10. API — `POST /api/assistant/chat` with `selected_file` resolves file from context.
11. API — `POST /api/assistant/chat` with `conversation_history` containing a 
    file reference resolves from memory.
12. API — `POST /api/assistant/chat` for `find_dependents` intent returns 
    structured response.
13. API — `ChatResponse` always contains `follow_up_suggestions` list (may be empty).

**Relevant Context**
- `backend/tests/test_phase3.py` — patterns to follow
- All new services created in Sub-Tasks 2–5

**Status** `[ ] pending`

---

## Dependency Order

```
Sub-Task 1 (schemas)
    ↓
Sub-Task 2 (ConversationManager)
Sub-Task 3 (IntentClassifier)      ← can be done in parallel with 2
    ↓
Sub-Task 4 (Route wiring)
Sub-Task 5 (GroqService + ExplanationService)  ← can be done in parallel with 4
    ↓
Sub-Task 6 (Frontend API layer)
    ↓
Sub-Task 7 (Follow-up chips)
Sub-Task 8 (Explain This shortcut)  ← can be done in parallel with 7
    ↓
Sub-Task 9 (Tests)
```

## Files to Create

| File | Purpose |
|---|---|
| `backend/app/services/conversation_manager.py` | Context resolution logic |
| `backend/tests/test_phase4.py` | Phase 4 test suite |

## Files to Modify

| File | Changes |
|---|---|
| `backend/app/schemas/assistant.py` | New fields on request/response, new `ConversationTurn` model |
| `backend/app/services/intent_classifier.py` | 3 new intents + patterns |
| `backend/app/services/groq_service.py` | 3 new prompt methods |
| `backend/app/services/explanation_service.py` | 3 new handlers + follow-up generation |
| `backend/app/api/routes/assistant.py` | Wire ConversationManager, propagate new fields |
| `frontend/src/types/index.ts` | New fields on ChatRequest/Response/ChatMessage/AppState |
| `frontend/src/services/chatApi.ts` | Pass context in sendMessage |
| `frontend/src/components/AssistantPanel.tsx` | Send context, wire pending input |
| `frontend/src/components/ChatMessage.tsx` | Render follow-up suggestion chips |
| `frontend/src/components/ProjectExplorer.tsx` | Explain This button |
| `frontend/src/contexts/AppContext.tsx` | pendingAssistantInput state + action |
