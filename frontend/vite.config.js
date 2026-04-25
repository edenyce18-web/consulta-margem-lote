import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/upload-lote": "http://backend:8000",
      "/status-lote": "http://backend:8000",
      "/lotes": "http://backend:8000",
      "/auth": "http://backend:8000",
    },
  },
});
