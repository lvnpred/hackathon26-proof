import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const api = { target: "http://127.0.0.1:8000", ws: true };
const morning = {
  target: "http://127.0.0.1:8000",
  bypass(req) {
    if ((req.headers.accept || "").includes("text/html")) return "/index.html";
  },
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/cases": api,
      "/frames": api,
      "/tracks": api,
      "/discrepancies": api,
      "/health": api,
      "/product": api,
      "/morning": morning,
    },
  },
});
