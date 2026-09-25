/**
 * AppContext — application state management.
 * Phase 2: extended with project scan state, analysis, and file loading state.
 */

import React, {
  createContext,
  useContext,
  useReducer,
  useCallback,
  type ReactNode,
} from "react";
import type {
  AppState,
  ConnectionStatus,
  FileNode,
  ChatMessage,
  WorkflowTab,
  AccessibilityPreferences,
  ActivityEntry,
  ProposedChange,
  ProjectMeta,
  ProjectScanState,
  ScanStatus,
  ProjectAnalysisResponse,
} from "@/types";

// ─── Initial state ────────────────────────────────────────────────────────────

const DEFAULT_ACCESSIBILITY: AccessibilityPreferences = {
  enabled: false,
  largeText: false,
  highContrast: false,
  reducedMotion: false,
  strongFocus: false,
};

const INITIAL_SCAN_STATE: ProjectScanState = {
  status: "idle",
  analysis: null,
  error: null,
};

const INITIAL_STATE: AppState = {
  connectionStatus: "checking",
  project: null,
  scanState: INITIAL_SCAN_STATE,
  analysis: null,
  fileLoadingPath: null,
  fileLoadError: null,
  selectedFile: null,
  fileContent: null,
  conversation: [],
  assistantThinking: false,
  groqConfigured: null,
  voiceState: "idle",
  proposedChanges: [],
  activity: [],
  activeWorkflowTab: "changes",
  accessibility: DEFAULT_ACCESSIBILITY,
  pendingAssistantInput: null,
};

// ─── Actions ──────────────────────────────────────────────────────────────────

type Action =
  | { type: "SET_CONNECTION"; status: ConnectionStatus }
  | { type: "SET_PROJECT"; project: ProjectMeta | null }
  | { type: "SET_SCAN_STATUS"; status: ScanStatus; error?: string }
  | { type: "SET_ANALYSIS"; analysis: ProjectAnalysisResponse | null }
  | { type: "SET_FILE_LOADING"; path: string | null }
  | { type: "SET_FILE_ERROR"; error: string | null }
  | { type: "SET_SELECTED_FILE"; file: FileNode | null; content: string | null }
  | { type: "ADD_MESSAGE"; message: ChatMessage }
  | { type: "CLEAR_CONVERSATION" }
  | { type: "SET_ASSISTANT_THINKING"; thinking: boolean }
  | { type: "SET_GROQ_CONFIGURED"; configured: boolean }
  | { type: "SET_WORKFLOW_TAB"; tab: WorkflowTab }
  | { type: "SET_ACCESSIBILITY"; prefs: Partial<AccessibilityPreferences> }
  | { type: "ADD_ACTIVITY"; entry: ActivityEntry }
  | { type: "ADD_PROPOSED_CHANGE"; change: ProposedChange }
  // Phase 4
  | { type: "SET_PENDING_INPUT"; text: string | null };

// ─── Reducer ──────────────────────────────────────────────────────────────────

function appReducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "SET_CONNECTION":
      return { ...state, connectionStatus: action.status };

    case "SET_PROJECT":
      return { ...state, project: action.project };

    case "SET_SCAN_STATUS":
      return {
        ...state,
        scanState: {
          ...state.scanState,
          status: action.status,
          error: action.error ?? state.scanState.error,
        },
      };

    case "SET_ANALYSIS":
      return {
        ...state,
        analysis: action.analysis,
        scanState: {
          ...state.scanState,
          analysis: action.analysis,
          status: action.analysis ? "ready" : state.scanState.status,
        },
      };

    case "SET_FILE_LOADING":
      return { ...state, fileLoadingPath: action.path, fileLoadError: null };

    case "SET_FILE_ERROR":
      return { ...state, fileLoadError: action.error, fileLoadingPath: null };

    case "SET_SELECTED_FILE":
      return {
        ...state,
        selectedFile: action.file,
        fileContent: action.content,
        fileLoadingPath: null,
        fileLoadError: null,
      };

    case "ADD_MESSAGE":
      return {
        ...state,
        conversation: [...state.conversation, action.message],
      };

    case "CLEAR_CONVERSATION":
      return { ...state, conversation: [] };

    case "SET_ASSISTANT_THINKING":
      return { ...state, assistantThinking: action.thinking };

    case "SET_GROQ_CONFIGURED":
      return { ...state, groqConfigured: action.configured };

    case "SET_WORKFLOW_TAB":
      return { ...state, activeWorkflowTab: action.tab };

    case "SET_ACCESSIBILITY":
      return {
        ...state,
        accessibility: { ...state.accessibility, ...action.prefs },
      };

    case "ADD_ACTIVITY":
      return {
        ...state,
        activity: [action.entry, ...state.activity],
      };

    case "ADD_PROPOSED_CHANGE":
      return {
        ...state,
        proposedChanges: [...state.proposedChanges, action.change],
      };

    // Phase 4
    case "SET_PENDING_INPUT":
      return { ...state, pendingAssistantInput: action.text };

    default:
      return state;
  }
}

// ─── Context ──────────────────────────────────────────────────────────────────

interface AppContextValue {
  state: AppState;
  setConnection: (status: ConnectionStatus) => void;
  setProject: (project: ProjectMeta | null) => void;
  setScanStatus: (status: ScanStatus, error?: string) => void;
  setAnalysis: (analysis: ProjectAnalysisResponse | null) => void;
  setFileLoading: (path: string | null) => void;
  setFileError: (error: string | null) => void;
  selectFile: (file: FileNode | null, content: string | null) => void;
  addMessage: (message: ChatMessage) => void;
  clearConversation: () => void;
  setAssistantThinking: (thinking: boolean) => void;
  setGroqConfigured: (configured: boolean) => void;
  setWorkflowTab: (tab: WorkflowTab) => void;
  setAccessibility: (prefs: Partial<AccessibilityPreferences>) => void;
  addActivity: (entry: ActivityEntry) => void;
  /** Phase 4: signal the AssistantPanel to send a message (e.g. from Explain This) */
  setPendingAssistantInput: (text: string | null) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

// ─── Provider ─────────────────────────────────────────────────────────────────

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, INITIAL_STATE);

  const setConnection = useCallback(
    (status: ConnectionStatus) => dispatch({ type: "SET_CONNECTION", status }),
    []
  );
  const setProject = useCallback(
    (project: ProjectMeta | null) => dispatch({ type: "SET_PROJECT", project }),
    []
  );
  const setScanStatus = useCallback(
    (status: ScanStatus, error?: string) =>
      dispatch({ type: "SET_SCAN_STATUS", status, error }),
    []
  );
  const setAnalysis = useCallback(
    (analysis: ProjectAnalysisResponse | null) =>
      dispatch({ type: "SET_ANALYSIS", analysis }),
    []
  );
  const setFileLoading = useCallback(
    (path: string | null) => dispatch({ type: "SET_FILE_LOADING", path }),
    []
  );
  const setFileError = useCallback(
    (error: string | null) => dispatch({ type: "SET_FILE_ERROR", error }),
    []
  );
  const selectFile = useCallback(
    (file: FileNode | null, content: string | null) =>
      dispatch({ type: "SET_SELECTED_FILE", file, content }),
    []
  );
  const addMessage = useCallback(
    (message: ChatMessage) => dispatch({ type: "ADD_MESSAGE", message }),
    []
  );
  const clearConversation = useCallback(
    () => dispatch({ type: "CLEAR_CONVERSATION" }),
    []
  );
  const setAssistantThinking = useCallback(
    (thinking: boolean) => dispatch({ type: "SET_ASSISTANT_THINKING", thinking }),
    []
  );
  const setGroqConfigured = useCallback(
    (configured: boolean) => dispatch({ type: "SET_GROQ_CONFIGURED", configured }),
    []
  );
  const setWorkflowTab = useCallback(
    (tab: WorkflowTab) => dispatch({ type: "SET_WORKFLOW_TAB", tab }),
    []
  );
  const setAccessibility = useCallback(
    (prefs: Partial<AccessibilityPreferences>) =>
      dispatch({ type: "SET_ACCESSIBILITY", prefs }),
    []
  );
  const addActivity = useCallback(
    (entry: ActivityEntry) => dispatch({ type: "ADD_ACTIVITY", entry }),
    []
  );
  const setPendingAssistantInput = useCallback(
    (text: string | null) => dispatch({ type: "SET_PENDING_INPUT", text }),
    []
  );

  return (
    <AppContext.Provider
      value={{
        state,
        setConnection,
        setProject,
        setScanStatus,
        setAnalysis,
        setFileLoading,
        setFileError,
        selectFile,
        addMessage,
        clearConversation,
        setAssistantThinking,
        setGroqConfigured,
        setWorkflowTab,
        setAccessibility,
        addActivity,
        setPendingAssistantInput,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) {
    throw new Error("useApp must be used within <AppProvider>");
  }
  return ctx;
}
