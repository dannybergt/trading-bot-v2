import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// In dev, /api and /ws hit the local backend on port 18090 (the default
// BACKEND_PORT used by ops/automation/start.sh). In production the static
// bundle is served behind Nginx, which proxies /api and /ws to the backend
// container — see ops/docker/frontend.nginx.conf.
const BACKEND_TARGET = process.env.VITE_BACKEND_URL ?? "http://127.0.0.1:18090";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "prompt",
      includeAssets: ["icon.svg"],
      manifest: {
        name: "NexusPulse Trade",
        short_name: "NexusPulse",
        description:
          "AI-assisted trading workstation: combined fundamentals, news, technical, and ML signals with a net-yield-gated recommendation pipeline.",
        theme_color: "#22c55e",
        background_color: "#0f172a",
        display: "standalone",
        orientation: "any",
        start_url: "/",
        scope: "/",
        icons: [
          {
            src: "/icon.svg",
            sizes: "any",
            type: "image/svg+xml",
            purpose: "any",
          },
          {
            src: "/icon.svg",
            sizes: "any",
            type: "image/svg+xml",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        // Static assets get cache-first; the API path is network-first
        // with a short cache fallback so offline clients still see the
        // last-known data instead of a blank page.
        runtimeCaching: [
          {
            urlPattern: /\/api\/.*/i,
            handler: "NetworkFirst",
            options: {
              cacheName: "api-cache",
              networkTimeoutSeconds: 5,
              expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: /\.(?:js|css|woff2?|ttf|svg|png|jpg|jpeg|webp)$/i,
            handler: "CacheFirst",
            options: {
              cacheName: "static-assets",
              expiration: { maxEntries: 200, maxAgeSeconds: 7 * 24 * 60 * 60 },
            },
          },
        ],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//, /^\/ws/],
      },
      devOptions: {
        enabled: false,
      },
    }),
  ],
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
