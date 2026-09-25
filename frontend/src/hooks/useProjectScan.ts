/**
 * useProjectScan — encapsulates the full project scan + analysis flow.
 * Phase 2: calls real backend endpoints.
 */

import { useCallback } from "react";
import { useApp } from "@/contexts/AppContext";
import { getProjectTree, analyzeProject, getFile, convertTree } from "@/services/projectApi";
import type { FileNode } from "@/types";
import { uid } from "@/utils/helpers";

export function useProjectScan() {
  const { setProject, setScanStatus, setAnalysis, setFileLoading, setFileError, selectFile, addActivity } =
    useApp();

  const scanProject = useCallback(async () => {
    setScanStatus("scanning");
    addActivity({
      id: uid(),
      timestamp: new Date(),
      message: "Starting project scan…",
      type: "info",
    });

    try {
      // 1. Get the file tree
      const treeResponse = await getProjectTree();
      const tree = convertTree(treeResponse);

      setProject({
        name: treeResponse.name,
        tree,
      });

      addActivity({
        id: uid(),
        timestamp: new Date(),
        message: `Project scanned: ${treeResponse.total_files} files in ${treeResponse.total_dirs} directories.`,
        type: "success",
      });

      // 2. Run full analysis (deps + components)
      const analysis = await analyzeProject();
      setAnalysis(analysis);

      addActivity({
        id: uid(),
        timestamp: new Date(),
        message: `Analysis complete: ${analysis.source_files} source files, ${analysis.components.length} components detected.`,
        type: "success",
      });

      setScanStatus("ready");
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setScanStatus("error", msg);
      addActivity({
        id: uid(),
        timestamp: new Date(),
        message: `Scan failed: ${msg}`,
        type: "error",
      });
    }
  }, [setScanStatus, setProject, setAnalysis, addActivity]);

  const openFile = useCallback(
    async (node: FileNode) => {
      if (node.type !== "file") return;
      setFileLoading(node.path);

      try {
        const result = await getFile(node.path);
        // Merge language from backend response into the node
        const enrichedNode: FileNode = {
          ...node,
          language: result.language,
        };
        selectFile(enrichedNode, result.content);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setFileError(msg);
        addActivity({
          id: uid(),
          timestamp: new Date(),
          message: `Failed to read file "${node.path}": ${msg}`,
          type: "error",
        });
      }
    },
    [setFileLoading, selectFile, setFileError, addActivity]
  );

  return { scanProject, openFile };
}
