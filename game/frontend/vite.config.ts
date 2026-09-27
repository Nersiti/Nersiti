import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // Local development: backend runs on :8000
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  worker: {
    format: "es",
  },
  build: {
    target: "es2021",
    chunkSizeWarningLimit: 1500,
  },
});
