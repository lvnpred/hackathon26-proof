"use strict";
// Letterhead panel (spec 7A.1/7A.3). Loaded after app.js; uses its global loadProfile().
(function () {
  const API = "/api/v1/templates";
  const MAX_BYTES = 8 * 1024 * 1024;            // mirrors TEMPLATE_MAX_IMAGE_BYTES
  const UPLOAD_TIMEOUT_MS = 120000;             // the vision call dominates
  const PROFILE_KEYS = ["doctor_name", "qualifications", "reg_no", "clinic_name", "address", "phone"];
  const PROFILE_LABEL = { doctor_name: "Doctor name", qualifications: "Qualifications",
    reg_no: "Registration no.", clinic_name: "Clinic name", address: "Address", phone: "Phone" };
  const MSG = {
    400: "That file could not be read as a picture. Use a JPEG, PNG or iPhone (HEIC) photo of the blank pad.",
    413: "That picture is too large. Use a photo under 8 MB, for example by scanning at a lower resolution.",
    429: "You have reached today's limit of letterhead uploads. Try again tomorrow, or keep the current layout.",
    502: "The AI could not read this letterhead, and nothing was saved. Try a clearer, straight-on photo, or use the built-in layout.",
    503: "Reading letterheads is not set up on this server (no AI model that can read pictures is configured). Ask your administrator. The built-in layout still works.",
  };
  const lh = { draft: null, abort: null, blobUrl: null, active: false };
  const el = (id) => document.getElementById(id);
  const status = (m) => { el("lhStatus").textContent = m; };
  function showErr(m) { const e = el("lhError"); e.textContent = m || ""; e.hidden = !m; }
  function httpMessage(code, what) {
    if (MSG[code] && what === "upload") return MSG[code];
    if (code === 404) return "This draft no longer exists (drafts expire after a day). Upload the picture again.";
    return "Something went wrong (code " + code + "). Try again; if it keeps happening, tell your administrator.";
  }
  function netMessage(e) {
    if (e && e.name === "AbortError") return "That took too long and was stopped. Check your connection and try again.";
    return "Could not reach the server. Check your connection and try again.";
  }
  function setBusy(on, label) {
    el("lhPanel").setAttribute("aria-busy", on ? "true" : "false");
    el("lhPanel").querySelectorAll("button.lh-act, #lhFile").forEach((b) => { b.disabled = on; });
    el("lhProgress").hidden = !on;
    el("lhProgressText").textContent = on ? label : "";
  }
  async function call(url, opts, ms) {
    const ac = new AbortController();
    lh.abort = ac;
    const timer = setTimeout(() => ac.abort(), ms || 30000);
    try { return await fetch(url, Object.assign({}, opts, { signal: ac.signal })); }
    finally { clearTimeout(timer); lh.abort = null; }
  }
  async function json(r) { try { return await r.json(); } catch (e) { return {}; } }
  // The stop button shows only with an active letterhead AND the upload view (never beside the review footer).
  function syncStop() { el("lhStopBtn").hidden = !(lh.active && !el("lhUpload").hidden); }
  async function refreshStatus() {
    try {
      const r = await call(API + "/active");
      lh.active = r.status === 200; syncStop();
      status(r.status === 200 ? "Your own letterhead is active: prescriptions print on it."
        : r.status === 404 ? "Using the built-in layout (no letterhead is active)."
        : "Could not check the current letterhead (code " + r.status + ").");
    } catch (e) { lh.active = false; syncStop(); status("Could not check the current letterhead. " + netMessage(e)); }
  }
  function show(view) {
    el("lhUpload").hidden = view !== "upload";
    el("lhReview").hidden = view !== "review";
    el("lhFoot").hidden = view !== "review";
    syncStop();
  }
  function openPanel() {
    showErr(""); el("lhDone").hidden = true;
    const p = el("lhPanel");
    if (typeof p.showModal === "function") p.showModal(); else p.setAttribute("open", "");
    refreshStatus();
    if (lh.draft) renderReview(lh.draft); else { show("upload"); el("lhFile").focus(); }
  }
  function closePanel() {
    const p = el("lhPanel");
    if (typeof p.close === "function") p.close(); else p.removeAttribute("open");
  }
  async function upload(ev) {
    ev.preventDefault();
    showErr("");
    const f = el("lhFile").files[0];
    if (!f) { showErr("Choose a picture of your blank prescription pad first."); el("lhFile").focus(); return; }
    if (f.size > MAX_BYTES) { showErr(MSG[413]); return; }
    const fd = new FormData();
    fd.append("image", f);
    setBusy(true, "Uploading and reading your letterhead. This can take up to a minute…");
    try {
      const r = await call(API, { method: "POST", body: fd }, UPLOAD_TIMEOUT_MS);
      const j = await json(r);
      if (r.status !== 201 && !r.ok) { showErr(httpMessage(r.status, "upload")); return; }
      lh.draft = j;
      renderReview(j);
    } catch (e) { showErr(netMessage(e)); }
    finally { setBusy(false); }
  }
  // Literal text lines are {type:"text", text} blocks in layout.header / layout.footer.
  function literalLines(layout) {
    const out = [];
    ["header", "footer"].forEach((part) => ((layout || {})[part] || []).forEach((b, i) => {
      if (b && b.type === "text" && typeof b.text === "string") out.push({ part: part, index: i, text: b.text });
    }));
    return out;
  }
  function field(id, label, value, tag) {
    const w = document.createElement("label");
    w.className = "field"; w.textContent = label;
    const i = document.createElement(tag || "input");
    i.id = id; i.value = value || ""; if (tag === "textarea") i.rows = 2;
    w.appendChild(i); return w;
  }
  function renderReview(d) {
    show("review");
    const lines = el("lhLines"); lines.textContent = "";
    const seen = { header: 0, footer: 0 };
    literalLines(d.layout).forEach((l, n) => {
      const w = field("lhLine" + n, (l.part === "header" ? "Top line " : "Bottom line ") + (++seen[l.part]), l.text);
      const inp = w.querySelector("input"); inp.dataset.section = l.part; inp.dataset.index = String(l.index);
      lines.appendChild(w);
    });
    el("lhLinesBox").hidden = !lines.children.length;
    const pf = el("lhProfileFields"); pf.textContent = "";
    PROFILE_KEYS.forEach((k) => pf.appendChild(field("lhProf_" + k, PROFILE_LABEL[k],
      (d.profile || {})[k], k === "address" ? "textarea" : "input")));
    loadPreview();
    const first = lines.querySelector("input") || el("lhProf_doctor_name"); first.focus();
  }
  function collect() {
    const profile = {};
    PROFILE_KEYS.forEach((k) => { profile[k] = el("lhProf_" + k).value.trim(); });
    const lines = [];
    el("lhLines").querySelectorAll("input").forEach((i) => lines.push({ section: i.dataset.section, index: Number(i.dataset.index), text: i.value.trim() }));
    return { profile: profile, lines: lines };
  }
  async function loadPreview() {
    const box = el("lhPreview"); box.textContent = "Drawing preview…";
    if (lh.blobUrl) { URL.revokeObjectURL(lh.blobUrl); lh.blobUrl = null; }
    try {
      const r = await call(API + "/" + lh.draft.id + "/preview.pdf?t=" + Date.now(), {}, 60000);
      if (!r.ok) { box.textContent = r.status === 404 ? httpMessage(404) :
        "The preview could not be drawn (code " + r.status + "). Press Update preview to try again."; return; }
      lh.blobUrl = URL.createObjectURL(new Blob([await r.arrayBuffer()], { type: "application/pdf" }));
      box.textContent = "";
      if (navigator.pdfViewerEnabled !== false) {
        const o = document.createElement("object");
        o.data = lh.blobUrl + "#view=Fit&toolbar=0"; o.type = "application/pdf"; o.setAttribute("aria-label", "Page 1 preview");
        box.appendChild(o);
      } else {
        const p = document.createElement("p");
        p.textContent = "This browser cannot show a PDF inside the page. ";
        const a = document.createElement("a");
        a.href = lh.blobUrl; a.target = "_blank"; a.rel = "noopener"; a.textContent = "Open the page 1 preview in a new tab";
        p.appendChild(a); box.appendChild(p);
      }
    } catch (e) { box.textContent = "The preview could not be loaded. " + netMessage(e); }
  }
  async function saveEdits() {
    const r = await call(API + "/" + lh.draft.id, { method: "PUT",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(collect()) });
    if (!r.ok) { showErr(httpMessage(r.status, "edit")); return false; }
    const j = await json(r);
    if (j && j.layout) lh.draft = Object.assign({}, lh.draft, j);
    return true;
  }
  async function updatePreview() {
    showErr(""); setBusy(true, "Saving your edits…");
    try { if (await saveEdits()) await loadPreview(); } catch (e) { showErr(netMessage(e)); } finally { setBusy(false); }
  }
  async function accept() {
    showErr(""); setBusy(true, "Saving your letterhead…");
    try {
      if (!(await saveEdits())) return;
      const r = await call(API + "/" + lh.draft.id + "/accept", { method: "POST" });
      if (!r.ok) { showErr(httpMessage(r.status, "accept")); return; }
      lh.draft = null;
      if (typeof loadProfile === "function") await loadProfile();
      show("upload"); el("lhFile").value = "";
      el("lhDone").hidden = false;
      el("lhDone").textContent = "Done. Your letterhead is saved, and its clinic details were saved to your Profile and shown at the top of the page. New prescriptions print on it.";
      refreshStatus();
    } catch (e) { showErr(netMessage(e)); } finally { setBusy(false); }
  }
  async function discard(thenUpload) {
    showErr(""); setBusy(true, "Discarding the draft…");
    try {
      const r = await call(API + "/" + lh.draft.id, { method: "DELETE" });
      if (!r.ok && r.status !== 404) { showErr(httpMessage(r.status, "discard")); return; }
      lh.draft = null; el("lhFile").value = ""; show("upload");
      refreshStatus();
      if (thenUpload) { setBusy(false); el("lhFile").focus(); }  // a disabled input cannot take focus
      else { el("lhDone").hidden = false; el("lhDone").textContent = "The draft was discarded. Nothing about your prescriptions changed."; }
    } catch (e) { showErr(netMessage(e)); } finally { setBusy(false); }
  }
  async function useDetails() {
    showErr(""); setBusy(true, "Saving your clinic details…");
    try {
      if (!(await saveEdits())) return;
      const r = await call(API + "/" + lh.draft.id + "/use-details", { method: "POST" });
      if (!r.ok) { showErr(httpMessage(r.status, "use-details")); return; }
      lh.draft = null;
      if (typeof loadProfile === "function") await loadProfile();
      el("lhFile").value = ""; show("upload");
      await refreshStatus();
      el("lhDone").hidden = false;
      el("lhDone").textContent = "Your clinic details were saved to your Profile. " +
        (lh.active ? "Your accepted letterhead stays active." : "The built-in layout stays in use.");
    } catch (e) { showErr(netMessage(e)); } finally { setBusy(false); }
  }
  async function stopUsing() {
    if (!window.confirm("Prescriptions will print on the built-in layout again. Your accepted letterhead is kept but no longer used. Continue?")) return;
    showErr(""); el("lhDone").hidden = true; setBusy(true, "Switching to the built-in layout…");
    try {
      const r = await call(API + "/deactivate", { method: "POST" });
      if (!r.ok) { showErr(httpMessage(r.status, "stop")); return; }
      await refreshStatus();
      el("lhDone").hidden = false;
      el("lhDone").textContent = "Done. Prescriptions now print on the built-in layout with your clinic details.";
    } catch (e) { showErr(netMessage(e)); } finally { setBusy(false); }
  }
  el("letterheadOpenBtn").addEventListener("click", openPanel);
  el("lhCloseBtn").addEventListener("click", closePanel);
  el("lhPanel").addEventListener("close", () => { if (lh.abort && !lh.draft) lh.abort.abort(); });
  el("lhStopBtn").addEventListener("click", stopUsing);
  el("lhUploadForm").addEventListener("submit", upload);
  el("lhUpdateBtn").addEventListener("click", updatePreview);
  el("lhAcceptBtn").addEventListener("click", accept);
  el("lhReuploadBtn").addEventListener("click", () => discard(true));
  el("lhBuiltinBtn").addEventListener("click", useDetails);
})();
