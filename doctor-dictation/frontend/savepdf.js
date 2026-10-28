"use strict";
// Save PDF (owner feedback E6): saves the stored prescription PDF to a folder the doctor picks (File System Access
// picker), falling back to a download. The file name is built here from the sheet and never logged.
// Loaded BEFORE app.js; also loads under node for tests.
(function (root) {
  const CAP = 120;
  const UNSAFE = /[\\/:*?"<>|]|[\u0000-\u001f\u007f]|[\p{Extended_Pictographic}\u200d\ufe0f]/gu;

  const clean = (s) => String(s == null ? "" : s).replace(UNSAFE, "").replace(/\s+/g, " ").trim().slice(0, CAP).trim();

  function fileName(p) {                                 // p: { name, day, op } -> "Name 2026-10-25 OP-1.pdf"
    const stem = [p.name, p.day, p.op].map(clean).filter(Boolean).join(" ").slice(0, CAP).trim();
    return (stem || "prescription") + ".pdf";
  }

  async function fetchPdf(id, fetchFn) {
    const r = await (fetchFn || root.fetch)("/api/v1/documents/" + encodeURIComponent(id) + "/pdf", { cache: "no-store" });
    if (!r.ok) throw new Error("server answered " + r.status);
    if (!(r.headers.get("Content-Type") || "").toLowerCase().includes("application/pdf")) throw new Error("the server did not return a PDF");
    return r.blob();
  }

  function download(blob, name, env) {
    const url = env.URL.createObjectURL(blob);
    const a = env.document.createElement("a");
    a.href = url; a.download = name;
    env.document.body.append(a);
    a.click();
    a.remove();
    (env.setTimeout || setTimeout)(() => env.URL.revokeObjectURL(url), 30000);     // the browser may still be reading the blob
    return "downloaded";
  }

  async function save(blob, name, env) {                 // -> "picked" | "downloaded" | "cancelled"
    env = env || root;
    if (!env.showSaveFilePicker) return download(blob, name, env);
    try {
      const handle = await env.showSaveFilePicker({ suggestedName: name, types: [{ description: "PDF", accept: { "application/pdf": [".pdf"] } }] });
      const w = await handle.createWritable();
      await w.write(blob);
      await w.close();
      return "picked";
    } catch (e) {
      if (e && e.name === "AbortError") return "cancelled";
      if (e && e.name === "SecurityError") return download(blob, name, env);
      throw e;
    }
  }

  const api = { fileName, fetchPdf, save };
  root.SavePdf = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
