import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  root: new URL(".", import.meta.url).pathname,
  base: "/app-next/",
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/auth": "http://127.0.0.1:8000",
      "/datasets": "http://127.0.0.1:8000",
      "/saved-cohorts": "http://127.0.0.1:8000",
      "/jobs": "http://127.0.0.1:8000",
      "/pheno-ranker": "http://127.0.0.1:8000",
      "/branding": "http://127.0.0.1:8000",
    },
  },
});
