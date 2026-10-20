/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backendPort = process.env.VIDEOCUT_PORT ?? "8000";
const frontendPort = Number(process.env.VIDEOCUT_FRONTEND_PORT ?? "5173");

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: frontendPort,
    strictPort: true,
    proxy: {
      "/api": `http://127.0.0.1:${backendPort}`,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
