import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const daemon = `http://127.0.0.1:${process.env.SESSIONTAP_PORT ?? "8711"}`;

export default defineConfig({
  plugins: [react()],
  build: {
    // Served by the daemon; packaged into the Python wheel.
    outDir: "../core/src/sessiontap/server/web",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    strictPort: true,
    host: "127.0.0.1",
    proxy: {
      "/v1": {
        target: daemon,
        changeOrigin: true, // Host becomes 127.0.0.1:PORT, which the daemon accepts
        configure: (proxy) => {
          // The daemon only accepts its own origin; dev requests come from :5173.
          proxy.on("proxyReq", (req) => req.removeHeader("origin"));
        },
      },
    },
  },
});
