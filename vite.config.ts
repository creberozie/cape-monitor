import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
const here = (p: string) => fileURLToPath(new URL(p, import.meta.url));
// maplibre-gl 6 ships its web worker as a separate ES module next to the main file; pre-bundling would break that link.
// Two pages: Cape Monitor (index.html) and Stellenbosch Watch (watch/index.html, served at /watch/).
export default defineConfig({ base: "./", publicDir: process.env.CM_NO_PUBLIC ? false : "public", optimizeDeps: { exclude: ["maplibre-gl"] },
  build: { target: "es2022", chunkSizeWarningLimit: 1500, rollupOptions: { input: { main: here("index.html"), watch: here("watch/index.html") } } },
  server: { port: 5173 } });
