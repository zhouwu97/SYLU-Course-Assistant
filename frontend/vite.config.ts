import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发时代理到本地 FastAPI；构建产物由 FastAPI 静态挂载（/frontend/dist）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/api/ws": { target: "http://127.0.0.1:8765", ws: true },
    },
  },
  build: { outDir: "dist" },
});
