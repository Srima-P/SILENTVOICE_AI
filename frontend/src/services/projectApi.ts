/**
 * projectApi.ts — Phase 2 frontend API service for project scanning.
 *
 * All calls go through the Vite proxy (/api → backend).
 * No hardcoded backend URLs.
 */

import type {
  ProjectTreeResponse,
  FileReadResponse,
  ProjectAnalysisResponse,
  ApiFileNode,
  FileNode,
} from "@/types";

const BASE = "/api/project";

// ─── Generic fetch helper ─────────────────────────────────────────────────────

async function projectFetch<T>(
  path: string,
  options?: RequestInit & { params?: Record<string, string> }
): Promise<T> {
  let url = `${BASE}${path}`;
  if (options?.params) {
    const qs = new URLSearchParams(options.params).toString();
    url = `${url}?${qs}`;
  }
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body?.detail ?? body?.message ?? detail;
    } catch {
      // ignore parse errors
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

// ─── API functions ────────────────────────────────────────────────────────────

/** Scan the configured project root and return the file tree. */
export async function getProjectTree(): Promise<ProjectTreeResponse> {
  return projectFetch<ProjectTreeResponse>("/tree");
}

/**
 * Read a single source file by its relative path.
 * The backend enforces path traversal protection.
 */
export async function getFile(path: string): Promise<FileReadResponse> {
  return projectFetch<FileReadResponse>("/file", {
    params: { path },
  });
}

/**
 * Perform full project analysis: stats, language breakdown,
 * components, and dependency map.
 */
export async function analyzeProject(): Promise<ProjectAnalysisResponse> {
  return projectFetch<ProjectAnalysisResponse>("/analyze");
}

// ─── Tree conversion ──────────────────────────────────────────────────────────

/**
 * Convert the backend ApiFileNode tree into the frontend FileNode tree,
 * adding synthetic `id` fields (using `path` as the id) so components
 * don't need to change.
 */
export function apiNodeToFileNode(node: ApiFileNode): FileNode {
  return {
    id: node.path || node.name,
    name: node.name,
    path: node.path,
    type: node.type,
    language: node.language,
    size_bytes: node.size_bytes,
    children: node.children?.map(apiNodeToFileNode),
  };
}

export function convertTree(response: ProjectTreeResponse): FileNode[] {
  return response.children.map(apiNodeToFileNode);
}
