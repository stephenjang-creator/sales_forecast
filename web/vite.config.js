import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built assets are served from FastAPI at "/", so use relative base.
// In dev, proxy /api to the FastAPI server so the SPA and API share an origin.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
