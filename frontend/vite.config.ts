import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendHost = env.VITE_BACKEND_HOST ?? "127.0.0.1";
  const backendPort = env.VITE_BACKEND_PORT ?? "8000";

  return {
    plugins: [react()],
    server: {
      port: parseInt(env.VITE_FRONTEND_PORT ?? "5173"),
      proxy: {
        "/api": {
          target: `http://${backendHost}:${backendPort}`,
          changeOrigin: true,
        },
      },
    },
    resolve: {
      alias: {
        "@": "/src",
      },
    },
  };
});
