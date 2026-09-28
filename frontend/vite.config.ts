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
    // Vitest shuffles test order too, so hidden coupling between tests fails
    // loudly instead of by luck; the seed is printed for reproduction.
    sequence: { shuffle: true },
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/main.tsx", "src/api/schema.d.ts"],
      reporter: ["text", "text-summary"],
      // A floor, not a target: we're at ~94 % of lines; this catches a PR
      // that adds untested UI.
      thresholds: { lines: 85, statements: 85, functions: 80, branches: 70 },
    },
  },
});
