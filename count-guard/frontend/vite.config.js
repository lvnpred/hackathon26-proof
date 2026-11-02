import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  // Ports come from the .env shared with Doctor Dictation, at the workspace root.
  const env = { ...loadEnv(mode, "../..", ""), ...process.env };
  const apiTarget = `http://127.0.0.1:${env.CG_API_PORT || 8100}`;
  const api = { target: apiTarget, ws: true };

  // Only the API paths below go to the backend; any other /journey URL is the app's own page.
  const journeyApi = ["/journey/episodes", "/journey/demo", "/journey/models", "/journey/staff", "/journey/ai", "/journey/ops", "/journey/ward", "/journey/clock", "/journey/sync", "/journey/patients"];
  const journey = {
    target: apiTarget,
    bypass(req) {
      if (!journeyApi.some((path) => req.url.startsWith(path))) return "/index.html";
    },
  };

  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: Number(env.CG_WEB_PORT || 5173),
      strictPort: true,
      proxy: {
        "/health": api,
        "/product": api,
        "/journey": journey,
      },
    },
  };
});
