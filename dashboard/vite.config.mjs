import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const BOARD_PORT = Number(process.env.CLAWTEAM_BOARD_PORT) || 8780;
const BOARD_TARGET = `http://127.0.0.1:${BOARD_PORT}`;

export default defineConfig({
  root: __dirname,
  base: "./",
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: BOARD_TARGET,
        changeOrigin: true,
        ws: false,
        // SSE: disable response buffering so events flush immediately
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            if ((proxyRes.headers["content-type"] || "").includes("text/event-stream")) {
              proxyRes.headers["cache-control"] = "no-cache";
            }
          });
        },
      },
    },
  },
  build: {
    outDir: resolve(__dirname, "../clawteam/board/static"),
    emptyOutDir: true,
    assetsDir: "assets",
  },
});
