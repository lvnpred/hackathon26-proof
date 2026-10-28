/* Vitals row (plan PQ-d): BP, pulse, weight, SpO2, temp under the patient row. Screen only (no-print).
   Browser global window.Vitals; also loads under node with a fake DOM (tests/test_frontend_vitals.py).
   A typed value is never blocked: an unusual one only shows a gentle hint beside the row. */
(function () {
  "use strict";
  const KEYS = ["bp", "pulse", "weight", "spo2", "temp"];
  const IDS = { bp: "vBp", pulse: "vPulse", weight: "vWeight", spo2: "vSpo2", temp: "vTemp" };
  const NAMES = { bp: "BP", pulse: "Pulse", weight: "Weight", spo2: "SpO2", temp: "Temp" };
  const ALLOWED = /^[0-9A-Za-z .,/%°:+-]*$/;    // the same characters the server keeps on Save
  const MAX_LEN = 20;
  const $ = (id) => document.getElementById(id);
  const clean = (s) => String(s == null ? "" : s).replace(/\s+/g, " ").trim();

  function render(v) {
    const src = v && typeof v === "object" ? v : {};
    KEYS.forEach((k) => {
      const n = $(IDS[k]);
      if (n) n.textContent = typeof src[k] === "string" ? src[k] : "";
    });
    showHints();
  }

  function read() {
    const out = {};
    KEYS.forEach((k) => { const n = $(IDS[k]); out[k] = n ? clean(n.textContent) : ""; });
    return out;
  }

  const num = (s) => { const m = /^\s*(-?\d+(?:\.\d+)?)/.exec(s); return m ? parseFloat(m[1]) : null; };
  const within = (x, lo, hi) => x != null && x >= lo && x <= hi;

  function unusual(key, text) {                   // true when the value parses but sits outside the plausible range
    if (key === "bp") {
      const m = /^\s*(\d+)\s*\/\s*(\d+)/.exec(text);
      return !!m && !(within(+m[1], 50, 260) && within(+m[2], 30, 160));
    }
    const x = num(text);
    if (x == null) return false;
    if (key === "pulse") return !within(x, 20, 250);
    if (key === "spo2") return !within(x, 50, 100);
    if (key === "weight") return !within(x, 1, 300);
    if (key === "temp") return !(within(x, 30, 45) || within(x, 90, 110));
    return false;
  }

  function hints(v) {                             // one short message per problem, in field order
    const out = [];
    KEYS.forEach((k) => {
      const t = v[k];
      if (!t) return;
      if (t.length > MAX_LEN || !ALLOWED.test(t)) out.push(NAMES[k] + ": this value will not be saved (use letters, numbers and . , / % \u00b0 : + -, at most 20 characters)");
      else if (unusual(k, t)) out.push(NAMES[k] + " " + t + " looks unusual — check it");
    });
    return out;
  }

  function showHints() {
    const n = $("vHint");
    if (!n) return;
    const msgs = hints(read());
    n.textContent = msgs.join(" · ");
    n.hidden = msgs.length === 0;
  }

  window.Vitals = { KEYS, render, read, hints, showHints };
  if (typeof document !== "undefined" && document.addEventListener) {
    const row = $("pVitals");
    if (row && row.addEventListener) row.addEventListener("input", showHints);
  }
})();
