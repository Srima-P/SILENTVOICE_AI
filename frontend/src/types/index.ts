// ─── Backend / API ────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  environment: string;
}

export type ConnectionStatus = "connected" | "disconnected" | "checking";

// ─── Project / File Tree ──────────────────────────────────────────────────────

export type FileNodeType = "file" | "directory";

export interface FileNode {
  id: string;       // client-side synthetic id (path used as id for backend nodes)
  name: string;
  path: string;
  type: FileNodeType;
  language?: string;
  size_bytes?: number;
  children?: FileNode[];
}

export interface ProjectMeta {
  name: string;
  tree: FileNode[];
}

// ─── Phase 2: Backend project API response shapes ─────────────────────────────

/** Raw FileNodeSchema from GET /api/project/tree (children use same shape). */
export interface ApiFileNode {
  name: string;
  path: string;
  type: "file" | "directory";
  language?: string;
  size_bytes?: number;
  children?: ApiFileNode[];
}

export interface ProjectTreeResponse {
  name: string;
  /** root_path is excluded from server responses (server-side only). */
  root_path?: string;
  type: string;
  total_files: number;
  total_dirs: number;
  children: ApiFileNode[];
}

export interface FileReadResponse {
  path: string;
  name: string;
  language: string;
  size_bytes: number;
  lines: number;
  content: string;
  encoding: string;
}

export interface ComponentInfo {
  name: string;
  path: string;
  type: string;
}

export interface DependencyMap {
  entries: Record<string, string[]>;
  unresolved: Record<string, string[]>;
}

export interface ProjectAnalysisResponse {
  project_name: string;
  /** root_path is excluded from server responses (server-side only). */
  root_path?: string;
  total_files: number;
  source_files: number;
  languages: Record<string, number>;
  components: ComponentInfo[];
  dependencies: DependencyMap;
  scan_errors: string[];
}

// ─── Frontend project scan state ──────────────────────────────────────────────

export type ScanStatus = "idle" | "scanning" | "ready" | "error";

export interface ProjectScanState {
  status: ScanStatus;
  analysis: ProjectAnalysisResponse | null;
  error: string | null;
}

// ─── Phase 3/4: Assistant / Chat API ──────────────────────────────────────────

/** A single turn sent as part of conversation history. Phase 4. */
export interface ConversationTurn {
  role: string;
  content: string;
}

export interface ChatRequest {
  message: string;
  /** Phase 4: currently selected file in Project Explorer */
  selected_file?: string;
  /** Phase 4: recent conversation turns for memory/context */
  conversation_history?: ConversationTurn[];
}

export interface ChatResponse {
  intent: string;
  target_file: string | null;
  response: string;
  error: boolean;
  candidates: string[];
  groq_used: boolean;
  /** Phase 4: suggested follow-up prompts */
  follow_up_suggestions: string[];
  /** Phase 4: how the active file was resolved */
  context_source: string;
}

export interface AssistantStatus {
  groq_configured: boolean;
  model: string;
}

// ─── Assistant conversation ───────────────────────────────────────────────────

export type MessageRole = "user" | "assistant" | "system";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  /** Phase 3: metadata from the backend response */
  intent?: string;
  target_file?: string | null;
  is_error?: boolean;
  candidates?: string[];
  /** Phase 4: follow-up suggestion chips */
  follow_up_suggestions?: string[];
}

export type VoiceState = "idle" | "listening" | "processing";

// ─── Assistant panel state ────────────────────────────────────────────────────

export type AssistantStatus2 = "idle" | "thinking" | "error";

// ─── Workflow / Changes ───────────────────────────────────────────────────────

export type WorkflowTab = "changes" | "diff" | "activity";

export interface ProposedChange {
  id: string;
  filePath: string;
  description: string;
  status: "pending" | "approved" | "rejected";
}

export interface ActivityEntry {
  id: string;
  timestamp: Date;
  message: string;
  type: "info" | "warn" | "error" | "success";
}

// ─── Accessibility ────────────────────────────────────────────────────────────

export interface AccessibilityPreferences {
  enabled: boolean;
  largeText: boolean;
  highContrast: boolean;
  reducedMotion: boolean;
  strongFocus: boolean;
}

// ─── App State (root) ─────────────────────────────────────────────────────────

export interface AppState {
  connectionStatus: ConnectionStatus;
  project: ProjectMeta | null;
  scanState: ProjectScanState;
  analysis: ProjectAnalysisResponse | null;
  fileLoadingPath: string | null;     // path currently being fetched
  fileLoadError: string | null;
  selectedFile: FileNode | null;
  fileContent: string | null;
  conversation: ChatMessage[];
  assistantThinking: boolean;         // Phase 3: true while waiting for Groq
  groqConfigured: boolean | null;     // null = not yet checked
  voiceState: VoiceState;
  proposedChanges: ProposedChange[];
  activity: ActivityEntry[];
  activeWorkflowTab: WorkflowTab;
  accessibility: AccessibilityPreferences;
  /** Phase 4: a pending message to send to the assistant (e.g. from "Explain This" button) */
  pendingAssistantInput: string | null;
}
