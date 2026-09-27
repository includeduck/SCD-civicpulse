/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The app only ever calls relative /api/... paths (ADR 0002). In production
// nginx proxies them to the backend; in `npm run dev` Vite's dev server does.
// Nothing here is baked into the build.
const devBackend = process.env.DEV_BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": devBackend },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
});
