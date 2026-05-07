import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, /api and /ws hit the local backend on port 18090 (the default
// BACKEND_PORT used by ops/automation/start.sh). In production the static
// bundle is served behind Nginx, which proxies /api and /ws to the backend
// container — see ops/docker/frontend.nginx.conf.
const BACKEND_TARGET = process.env.VITE_BACKEND_URL ?? "http://127.0.0.1:18090";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: BACKEND_TARGET,
        changeOrigin: true,
      },
      "/ws": {
        target: BACKEND_TARGET,
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
