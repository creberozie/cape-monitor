import { defineConfig } from "vite";
// maplibre-gl 6 ships its web worker as a separate ES module next to the main file; pre-bundling would break that link
export default defineConfig({ base: "./", optimizeDeps: { exclude: ["maplibre-gl"] }, build: { target: "es2022", chunkSizeWarningLimit: 1500 }, server: { port: 5173 } });
