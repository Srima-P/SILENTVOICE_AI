/**
 * useHealthCheck — polls the backend health endpoint and updates the
 * application's connection status accordingly.
 */

import { useEffect, useRef } from "react";
import { checkHealth } from "@/services/api";
import { useApp } from "@/contexts/AppContext";

const POLL_INTERVAL_MS = 30_000; // re-check every 30 s

export function useHealthCheck() {
  const { setConnection } = useApp();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function ping() {
    try {
      const result = await checkHealth();
      setConnection(result.status === "ok" ? "connected" : "disconnected");
    } catch {
      setConnection("disconnected");
    }
  }

  useEffect(() => {
    void ping(); // immediate check on mount

    intervalRef.current = setInterval(() => {
      void ping();
    }, POLL_INTERVAL_MS);

    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
