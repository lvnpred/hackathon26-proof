// Elapsed-seconds ticker on the status line during transcribe/structure (care-app clarity Task 9).
// app.js wraps its two model calls: StepInfo.during("transcribe"|"structure", () => fetch(...)).
// The line reads "Transcribing with Muse Voice… 3 s" / "Structuring with Spark… 12 s", with the engine
// from /api/health (fetched once, cached). Text is set with textContent, never as markup. After the call
// settles the ticker stops and the caller's own status stands; the draft's Expand (expand.js) keeps the rest.
(function (root) {
  "use strict";
  const VERB = { transcribe: "Transcribing", structure: "Structuring" };
  const STT = { muse: "Muse Voice", openai: "OpenAI", groq: "Groq", assemblyai: "AssemblyAI", "faster-whisper": "Whisper", onnx: "On-device" };
  const LLM = { meta: "Spark", openai: "OpenAI", groq: "Groq" };

  function label(kind, engine, seconds) {
    return `${VERB[kind] || "Working"} with ${engine}… ${Math.max(0, Math.floor(seconds))} s`;
  }

  function engineFor(h, kind) {
    const health = h || {};
    if (kind === "transcribe") return STT[health.stt_engine] || health.stt_engine || health.whisper_model || "Speech";
    if (health.llm_configured) return LLM[health.llm_provider] || health.llm_provider || "Model";
    return health.deepseek_configured ? "DeepSeek" : "Rules";
  }

  let healthPromise = null;
  function health() {
    if (!healthPromise) {
      healthPromise = root.fetch("/api/health").then((r) => r.json()).catch(() => ({}));
    }
    return healthPromise;
  }

  async function during(kind, fn, deps) {
    const d = deps || {};
    const el = d.el || root.document.getElementById("status");
    const getHealth = d.getHealth || health;
    const setI = d.setInterval || root.setInterval.bind(root);
    const clearI = d.clearInterval || root.clearInterval.bind(root);
    const now = d.now || Date.now;
    const t0 = now();
    let engine = kind === "transcribe" ? "Speech" : "Rules"; // until /api/health answers
    const paint = () => { if (el) el.textContent = label(kind, engine, (now() - t0) / 1000); };
    paint();
    const timer = setI(paint, 500);
    getHealth().then((h) => { engine = engineFor(h, kind); paint(); });
    try {
      return await fn();
    } finally {
      clearI(timer);
    }
  }

  const api = { label, engineFor, during };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.StepInfo = api;
})(typeof window !== "undefined" ? window : globalThis);
