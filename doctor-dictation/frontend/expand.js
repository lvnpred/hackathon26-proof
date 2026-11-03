// Expand on the draft (care-app clarity §4.7): what was captured (the recording, the transcript), what the engines
// returned, how the page used it (the draft as first produced) and what the doctor did (the edits since, field by field).
// app.js hands over the recording (DDExpand.keepAudio), the transcribe reply that heard it (DDExpand.heard: the words
// and the engine, paired with that recording) and each draft (DDExpand.drafted: a dictation's draft, or the draft a
// spoken correction produced, which becomes the new base for the doctor's edits); the current fields are
// read from the sheet when the view opens (app.js serializeForm). The button sits in the transcript box. All text is set
// with textContent, never as markup. The open view carries data-expand="open"; the button data-expand="closed".
(function (root) {
  "use strict";
  const TITLES = ["Captured", "Model returned", "How the app used it", "What a person did"];
  const keep = { audioUrl: null, transcript: "", engine: "", cached: false, first: null, stt: "" };
  let pending = null; // a recording not heard yet

  const label = (key) => {
    const words = String(key).replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/_/g, " ").toLowerCase();
    return words.charAt(0).toUpperCase() + words.slice(1);
  };
  // Any field value as one line of words: a list joins with "; ", a row joins its values.
  function plain(v) {
    if (v == null) return "";
    if (Array.isArray(v)) return v.map(plain).filter(Boolean).join("; ");
    if (typeof v === "object") return Object.keys(v).map((k) => plain(v[k])).filter(Boolean).join(" ");
    return String(v).trim();
  }
  const keysOf = (a, b) => Array.from(new Set(Object.keys(a || {}).concat(Object.keys(b || {}))));

  // { audioUrl, transcript, engine, stt, cached, first, current } -> the four parts, as words.
  function parts(s) {
    const first = s.first || null, current = s.current || first;
    const used = first ? keysOf(first).map((k) => [label(k), plain(first[k])]).filter((r) => r[1]).map((r) => r[0] + ": " + r[1]) : [];
    const changes = first ? keysOf(first, current).filter((k) => plain(first[k]) !== plain((current || {})[k]))
      .map((k) => ({ field: label(k), before: plain(first[k]) || "—", after: plain((current || {})[k]) || "—" })) : [];
    const returned = [];
    if (s.stt && s.transcript) returned.push("Transcribed by " + s.stt);
    if (first) returned.push("Drafted by " + (s.engine || "the engine") + (s.cached ? " (cached: the same words were drafted before)" : ""));
    if (!first) returned.push("No draft yet");
    const people = changes.length
      ? { text: "Changed by the doctor (" + changes.length + (changes.length === 1 ? " field)" : " fields)"), changes }
      : { text: "Not changed by the doctor yet", changes: [] };
    const out = {
      captured: { audio: s.audioUrl || null, transcript: s.transcript || "" },
      returned: { lines: returned },
      used: { lines: used },
      people,
    };
    out.list = TITLES.map((title) => ({ title }));
    return out;
  }

  function keepAudio(blob) {
    if (!root.URL || !blob) return;
    if (pending) root.URL.revokeObjectURL(pending);
    pending = root.URL.createObjectURL(blob);
  }
  // The transcribe reply: its words and engine go with the recording it heard.
  function heard(j) {
    if (pending) {
      if (keep.audioUrl) root.URL.revokeObjectURL(keep.audioUrl);
      keep.audioUrl = pending;
      pending = null;
    }
    keep.transcript = String((j && j.transcript) || "").trim();
    keep.stt = (j && j.engine) || "";
  }
  function drafted(transcript, j) {
    keep.transcript = transcript || keep.transcript;
    keep.engine = (j && j.engine) || "";
    keep.cached = Boolean(j && j.cached);
    keep.first = j && j.structured ? JSON.parse(JSON.stringify(j.structured)) : null;
  }

  // ---- the page -------------------------------------------------------------------------------------------------
  function el(tag, text, attrs) {
    const node = root.document.createElement(tag);
    if (text != null) node.textContent = text;
    Object.keys(attrs || {}).forEach((k) => node.setAttribute(k, attrs[k]));
    return node;
  }
  function list(lines) {
    const ul = el("ul");
    lines.forEach((line) => ul.appendChild(el("li", line)));
    return ul;
  }
  function current() {
    try { return typeof serializeForm === "function" ? serializeForm().structured : null; } // eslint-disable-line no-undef
    catch (_e) { return null; }
  }
  function section(title, nodes) {
    const s = el("section", null, { "aria-label": title });
    s.style.cssText = "display:grid;gap:6px;padding:10px 0;border-top:1px solid rgba(127,127,127,.3)";
    s.appendChild(el("h3", title));
    nodes.forEach((n) => n && s.appendChild(n));
    return s;
  }

  function render(p, box) {
    const audio = p.captured.audio ? el("audio", null, { controls: "", src: p.captured.audio, "aria-label": "The recording" }) : null;
    const said = el("p", p.captured.transcript ? "Heard: “" + p.captured.transcript + "”" : "No transcript yet.");
    const changes = p.people.changes.map((c) => c.field + ": " + c.before + " → " + c.after);
    box.appendChild(section(TITLES[0], [audio || el("p", "The recording is kept only on this page until it is reloaded."), said]));
    box.appendChild(section(TITLES[1], [list(p.returned.lines)]));
    box.appendChild(section(TITLES[2], [p.used.lines.length ? list(p.used.lines) : el("p", "Nothing drafted yet.")]));
    box.appendChild(section(TITLES[3], [el("p", p.people.text), changes.length ? list(changes) : null]));
  }

  function open() {
    const doc = root.document;
    const shade = el("div", null, { "data-expand": "open", role: "dialog", "aria-modal": "true", "aria-label": "Draft, expanded" });
    shade.style.cssText = "position:fixed;inset:0;z-index:60;background:rgba(0,0,0,.6);display:grid;place-items:center;padding:16px";
    const box = el("div");
    box.style.cssText = "background:var(--paper,#fff);color:inherit;width:min(720px,100%);max-height:calc(100vh - 32px);overflow:auto;padding:16px;border-radius:12px";
    const head = el("div");
    head.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:8px";
    head.appendChild(el("strong", "The draft, expanded"));
    const close = el("button", "Close ✕", { type: "button" });
    head.appendChild(close);
    box.appendChild(head);
    shade.appendChild(box);
    const shut = () => { shade.remove(); doc.removeEventListener("keydown", onKey); };
    const onKey = (e) => { if (e.key === "Escape") shut(); };
    close.addEventListener("click", shut);
    shade.addEventListener("click", (e) => { if (e.target === shade) shut(); });
    doc.addEventListener("keydown", onKey);
    render(parts({ ...keep, current: current() }), box);
    doc.body.appendChild(shade);
    close.focus();
  }

  function install() {
    const host = root.document.getElementById("transcriptBox");
    if (!host || root.document.getElementById("ddExpandBtn")) return;
    const btn = el("button", "Expand", { type: "button", id: "ddExpandBtn", "data-expand": "closed", "aria-haspopup": "dialog" });
    btn.className = "btn-quiet";
    btn.addEventListener("click", open);
    host.appendChild(btn);
  }

  const snapshot = () => JSON.parse(JSON.stringify(keep));
  const api = { parts, keepAudio, heard, drafted, open, snapshot, TITLES };
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    root.DDExpand = api;
    if (root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", install);
    else install();
  }
})(typeof window !== "undefined" ? window : globalThis);
