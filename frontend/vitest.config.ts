import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "./src") } },
  // testTimeout: the userEvent-driven page tests take ~4 s on a laptop; shared CI/Pages builders are slower.
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"], css: false, testTimeout: 20000 },
})
