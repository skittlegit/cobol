import path from "node:path"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from "vite"

// The site is served from https://<owner>.github.io/cobol/, so assets are
// relative. The build goes to ../site, which the Pages workflow publishes.
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "./src") } },
  build: { outDir: "../site", emptyOutDir: true, chunkSizeWarningLimit: 1000 },
})
