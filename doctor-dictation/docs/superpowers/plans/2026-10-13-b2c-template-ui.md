# B2c Letterhead Panel UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Letterhead" button next to Profile opens a panel where a clinic uploads a blank-pad picture, reviews the recreated page 1 (preview, editable text lines, six profile fields), and accepts, re-uploads, or goes back to the built-in layout.

**Architecture:** New classic script `frontend/letterhead.js` (one IIFE, no globals added) plus new `frontend/letterhead.css`, and a static `<dialog id="lhPanel">` in `index.html`, the same pattern as the Profile panel. `app.js` changes by one line (`setWorking` also disables the new button); it already exposes `$` and `loadProfile`, which `letterhead.js` reuses. A separate CSS file keeps `styles.css` (181 lines) and `app.js` (900+ lines) from growing; the page already loads one stylesheet, so a second `<link>` costs nothing.

**Tech Stack:** Vanilla JS (classic script, no build step), `<dialog>`, `fetch`, Blob URLs, `<object type="application/pdf">`.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` sections 7A.1, 7A.3, 7A.8. Contracts: `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md` sections 2, 4.6, 5.

**Adds 0 automated tests.** Nothing in this repo can run frontend JS under pytest, and a JS test harness is out of scope. Instead every task has an explicit Playwright browser check with a screenshot you must LOOK at. A green run proves nothing about layout: open each screenshot and confirm text is readable, nothing is clipped, and every button is on screen. The pytest count must be unchanged at the end.

## Assumptions about earlier plans

- B2b routes of contract 4.6 exist under `/api/v1/templates` with the stated status codes. `POST` returns `{id, status, layout, profile}`; `layout.header` and `layout.footer` are lists of blocks, and a literal text line is `{"type":"text","text":"..."}`.
- **Edit route shape (contract 4.6, matches B2b-3 `service.edit`):** `PUT /api/v1/templates/{id}` takes `{"profile": {six fields}, "lines": [{"section": "header"|"footer", "index": <position in layout[section]>, "text": "..."}]}` and returns the same shape as `POST`. Only literal text blocks are editable. Before Task 2, run `grep -n "lines" doctor_dictation/api/templates.py` to confirm; if it differs, change only `collect()` and `literalLines()`.
- The stub LLM provider (`LLM_PROVIDER=stub`, `STUB_LLM_JSON`, `ALLOW_STUB_PROVIDERS=1`) and the Chromium renderer (B2a) work, so `preview.pdf` renders.
- `app.js` still has `const $`, `async function loadProfile()` and `setWorking(on, msg)` with the line `$("profileOpenBtn").disabled = on;` (`grep -n` them first; line numbers move).

## Global Constraints

- Vanilla JS, classic script, no build step; no file over 500 lines; no drag boxes, straighten or fit modes (spec 7A.3).
- Spec 7A.8: the screen states the image must be a blank pad and that it is sent to the LLM provider.
- Plain-language messages for 400, 413, 429, 502, 503. No git commits: tasks end "leave uncommitted".

## Review Focus

Each line is pinned by the browser check named in brackets.

1. A pad already carrying a patient's name gets uploaded: the blank-pad warning must be the most prominent box on the upload view. [Task 2 step 4]
2. The draft expires (24 h) while the panel is open: accept or preview gets 404; say "upload again", not "code 404". [Task 3 step 1]
3. Esc mid-review: the draft must still be there on reopening. [Task 3 step 2]
4. A double click on Upload during the slow LLM call must not send two uploads (each costs a call and counts against the daily limit). [Task 3 step 1]
5. The browser cannot embed PDFs, or the preview call fails: a link or a retry message replaces the blank box. [Task 3 step 1]
6. A laptop viewport 600 px tall: Accept stays reachable without scrolling the page. [Task 3 step 3]
7. Edits typed but never saved: Accept saves them first. [Task 2 step 4]

---

**Files:** create `frontend/letterhead.js` and `frontend/letterhead.css`; modify `frontend/index.html` and one line of `frontend/app.js`.

---

### Task 1: Markup, styles and the one-line hook

**Files:**
- Modify: `frontend/index.html`, `frontend/app.js` (`setWorking`)
- Create: `frontend/letterhead.css`

**Interfaces:**
- Produces: element ids used by Task 2: `letterheadOpenBtn`, `lhPanel`, `lhCloseBtn`, `lhStatus`, `lhDone`, `lhError`, `lhProgress`, `lhProgressText`, `lhUpload`, `lhUploadForm`, `lhFile`, `lhUploadBtn`, `lhReview`, `lhPreview`, `lhLinesBox`, `lhLines`, `lhProfileFields`, `lhFoot`, `lhBuiltinBtn`, `lhReuploadBtn`, `lhUpdateBtn`, `lhAcceptBtn`. Every button that must be disabled while busy carries class `lh-act`.

- [ ] **Step 1: Create `frontend/letterhead.css`**

```css
/* Letterhead panel. Reuses dialog.panel / .field / .primary from styles.css. */
.lh-panel [hidden] { display:none !important; }
dialog.lh-panel { width:min(980px, 96vw); max-height:92vh; }
dialog.lh-panel[open] { display:flex; }
.lh-wrap { display:flex; flex-direction:column; width:100%; max-height:92vh; }
.lh-head { display:flex; justify-content:space-between; align-items:center; padding:14px 20px; border-bottom:1px solid var(--soft); }
.lh-head h2 { margin:0; font-size:18px; }
.lh-body { padding:14px 20px; overflow-y:auto; flex:1 1 auto; display:flex; flex-direction:column; gap:12px; }
.lh-body h3 { margin:0 0 6px; font-size:14px; }
.lh-current { margin:0; font-size:14px; font-weight:600; }
.lh-warn { background:#fff8e1; border:2px solid var(--warn); border-radius:8px; padding:10px 14px; font-size:14px; line-height:1.4; }
.lh-error { background:#fdecea; border:1px solid var(--bad); color:var(--bad); border-radius:8px; padding:10px 14px; font-size:14px; }
.lh-done { background:#e6f4ea; border:1px solid var(--ok); color:var(--ok); border-radius:8px; padding:10px 14px; font-size:14px; }
.lh-progress { display:flex; align-items:center; gap:10px; font-size:14px; }
.lh-progress progress { width:140px; }
.lh-upload { display:flex; flex-direction:column; gap:10px; align-items:flex-start; margin-top:10px; }
.lh-upload .field { width:100%; font-size:14px; }
.lh-review { display:flex; flex-direction:column; gap:12px; }
.lh-cols { display:grid; grid-template-columns:minmax(260px, 5fr) 6fr; gap:20px; }
.lh-preview { border:1px solid var(--soft); background:#f4f5f7; border-radius:8px; height:min(56vh, 520px); padding:8px; font-size:13px; color:var(--muted); overflow:auto; }
.lh-preview object { width:100%; height:100%; border:0; }
.lh-form-col .field { margin-bottom:8px; }
.lh-foot { display:flex; justify-content:flex-end; flex-wrap:wrap; gap:10px; padding:12px 20px; border-top:1px solid var(--soft); background:#fff; }
.lh-panel button:focus-visible, .lh-panel input:focus-visible, .lh-panel textarea:focus-visible, .lh-panel a:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
@media (max-width: 760px) { .lh-cols { grid-template-columns:1fr; } .lh-preview { height:40vh; } }
```

The `[hidden]` rule is essential: `.lh-progress`, `.lh-review` and `.lh-foot` set `display`, which would otherwise override the `hidden` attribute and show every view at once (this happened in the prototype).

- [ ] **Step 2: Edit `frontend/index.html`.** (a) After the Profile button inside `.topbar-actions`, add:

```html
    <button id="letterheadOpenBtn" type="button" title="Print prescriptions on your own letterhead">📄 Letterhead</button>
```

(b) After `<link rel="stylesheet" href="styles.css" />` add `<link rel="stylesheet" href="letterhead.css?v=1" />`. (c) Replace the last line `<script src="app.js?v=<N>"></script>` (N is whatever the file has now; use N+1 below) with the dialog, then both scripts, in this order (`letterhead.js` must load after `app.js`):

```html
<!-- Letterhead panel (logic in letterhead.js). -->
<dialog id="lhPanel" class="panel lh-panel no-print" aria-labelledby="lhTitle">
  <div class="lh-wrap">
    <div class="lh-head">
      <h2 id="lhTitle">Letterhead</h2>
      <button id="lhCloseBtn" type="button" aria-label="Close the letterhead panel">Close</button>
    </div>
    <div class="lh-body">
      <p id="lhStatus" class="lh-current" role="status" aria-live="polite"></p>
      <div id="lhDone" class="lh-done" role="status" hidden></div>
      <div id="lhError" class="lh-error" role="alert" hidden></div>
      <div id="lhProgress" class="lh-progress" hidden>
        <progress aria-label="Working"></progress> <span id="lhProgressText"></span>
      </div>
      <section id="lhUpload" aria-label="Upload a letterhead picture">
        <div class="lh-warn" role="note">
          <strong>Blank pad only. No patient information.</strong>
          Photograph or scan an empty prescription pad. Do not use a used prescription:
          it may show a patient's name. The picture is sent to an AI service so it can
          be read, and this demo must only ever see fake data.
        </div>
        <form id="lhUploadForm" class="lh-upload">
          <label class="field">Picture of the blank pad (JPEG, PNG or iPhone HEIC, up to 8 MB)
            <input id="lhFile" type="file" accept="image/jpeg,image/png,image/heic,image/heif,.jpg,.jpeg,.png,.heic,.heif" />
          </label>
          <button id="lhUploadBtn" type="submit" class="primary lh-act">Upload and read letterhead</button>
        </form>
      </section>
      <section id="lhReview" class="lh-review" aria-label="Review the recreated letterhead" hidden>
        <div class="lh-warn" role="note"><strong>Check every line.</strong>
          The AI may misread text. Fix anything wrong, then Accept. Nothing prints on it until you accept.</div>
        <div class="lh-cols">
          <div class="lh-preview-col">
            <h3>Page 1 preview</h3>
            <div id="lhPreview" class="lh-preview" aria-live="polite"></div>
          </div>
          <div class="lh-form-col">
            <div id="lhLinesBox"><h3>Text lines on the pad</h3><div id="lhLines"></div></div>
            <h3>Clinic details</h3>
            <div id="lhProfileFields"></div>
          </div>
        </div>
      </section>
    </div>
    <div id="lhFoot" class="lh-foot" hidden>
      <button id="lhBuiltinBtn" type="button" class="lh-act">Use built-in layout instead</button>
      <button id="lhReuploadBtn" type="button" class="lh-act">Re-upload</button>
      <button id="lhUpdateBtn" type="button" class="lh-act">Update preview</button>
      <button id="lhAcceptBtn" type="button" class="primary lh-act">Accept</button>
    </div>
  </div>
</dialog>

<script src="app.js?v=<N+1>"></script>
<script src="letterhead.js?v=1"></script>
```

- [ ] **Step 3: Edit `frontend/app.js`.** In `setWorking`, directly under `$("profileOpenBtn").disabled = on;` add `  $("letterheadOpenBtn").disabled = on;`.

- [ ] **Step 4: Browser check (markup only, `letterhead.js` is not written yet).** Start the app (`.venv/bin/uvicorn doctor_dictation.main:app --port 8001`). With the Playwright tools: `browser_navigate` to `http://127.0.0.1:8001/`, `browser_resize` 1280x720, `browser_take_screenshot`. LOOK: the top bar shows "Letterhead" beside "Profile", not wrapped or clipped. `browser_console_messages` may show a 404 for `letterhead.js` (not written yet) and no error from `app.js`; the Letterhead button does nothing yet.

- [ ] **Step 5: Leave uncommitted.**

---

### Task 2: `letterhead.js`: status, upload, review, accept, discard

**Files:**
- Create: `frontend/letterhead.js`

**Interfaces:**
- Consumes: ids from Task 1; globals `loadProfile()` from `app.js`; the 4.6 routes (assumption A1 for `PUT`).
- Produces: nothing global. State is private: `lh.draft` (the last `POST`/`PUT` body), kept while the panel is closed so Esc does not lose a draft.

Design notes: `fetch` is used (not XHR) so the error-code check can stub it; it gives no upload progress, and the LLM call dominates the wait, so the panel shows an honest indeterminate bar ("can take up to a minute"). The preview is fetched as a Blob so a failed render shows a message and no cached PDF is reused. Only `textContent` and `value` are used, never `innerHTML`: layout text comes from an LLM and is untrusted (spec 7A.8).

- [ ] **Step 1: Locate `loadProfile`.** Run `grep -n "async function loadProfile" frontend/app.js`. Expected: one match. Then run `grep -n "lines" doctor_dictation/api/templates.py` and confirm the PUT shape above; adjust `collect()` below if it differs.

- [ ] **Step 2: Create `frontend/letterhead.js`** with exactly this content:

```js
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
  const lh = { draft: null, abort: null, blobUrl: null };
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
  async function refreshStatus() {
    try {
      const r = await call(API + "/active");
      status(r.status === 200 ? "Your own letterhead is active: prescriptions print on it."
        : r.status === 404 ? "Using the built-in layout (no letterhead has been accepted yet)."
        : "Could not check the current letterhead (code " + r.status + ").");
    } catch (e) { status("Could not check the current letterhead. " + netMessage(e)); }
  }
  function show(view) {
    el("lhUpload").hidden = view !== "upload";
    el("lhReview").hidden = view !== "review";
    el("lhFoot").hidden = view !== "review";
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
      el("lhDone").textContent = "Done. Your letterhead is saved and the clinic details at the top of the page have been updated. New prescriptions print on it.";
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
      if (thenUpload) el("lhFile").focus();
      else { el("lhDone").hidden = false; el("lhDone").textContent = "The draft was discarded. Nothing about your prescriptions changed."; }
    } catch (e) { showErr(netMessage(e)); } finally { setBusy(false); }
  }
  el("letterheadOpenBtn").addEventListener("click", openPanel);
  el("lhCloseBtn").addEventListener("click", closePanel);
  el("lhPanel").addEventListener("close", () => { if (lh.abort && !lh.draft) lh.abort.abort(); });
  el("lhUploadForm").addEventListener("submit", upload);
  el("lhUpdateBtn").addEventListener("click", updatePreview);
  el("lhAcceptBtn").addEventListener("click", accept);
  el("lhReuploadBtn").addEventListener("click", () => discard(true));
  el("lhBuiltinBtn").addEventListener("click", () => discard(false));
})();
```

- [ ] **Step 3: Make a real test image and start the app with the stub vision LLM.** The image is a plain white A4-like page with a coloured block and rules, written with the standard library (Pillow is not needed here):

```bash
SCR=$(mktemp -d)/b2c && mkdir -p "$SCR" && echo "$SCR"
python3 - "$SCR/pad.png" <<'EOF'
import sys, zlib, struct
w, h, rows = 600, 800, []
for y in range(h):
    r = bytearray([255] * (w * 3))
    for x in range(40, 560):
        if 60 <= y < 64 or 740 <= y < 744 or (20 <= y < 56 and x < 110): r[x*3:x*3+3] = bytes([26, 60, 110])
    rows.append(b"\0" + bytes(r))
ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
open(sys.argv[1], "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(b"".join(rows))) + ch(b"IEND", b""))
EOF
ALLOW_STUB_PROVIDERS=1 LLM_PROVIDER=stub DB_PATH="$SCR/app.db" STUB_LLM_JSON='{"header":[{"type":"text","field":"doctor_name","role":"title","align":"center","color":"#1a3c6e"},{"type":"text","field":"qualifications","role":"small","align":"center"},{"type":"text","text":"Care for the whole family","role":"small","align":"center"},{"type":"rule","color":"#1a3c6e","thickness":"thin"}],"footer":[{"type":"text","field":"address","role":"small","align":"center"},{"type":"text","text":"Open Mon-Sat 9am-6pm","role":"small","align":"center"}],"body":{"top":0.22,"bottom":0.92},"profile":{"doctor_name":"Dr. A. Rao","qualifications":"MBBS, MD","reg_no":"KMC 12345","clinic_name":"Rao Family Clinic","address":"12 MG Road, Bengaluru","phone":"080 5555 0100"}}' \
  .venv/bin/uvicorn doctor_dictation.main:app --port 8001
```

Expected: the file `"$SCR/pad.png"` exists (about 3 KB) and uvicorn reports `Uvicorn running on http://127.0.0.1:8001`. Use a throwaway `DB_PATH` so the walk-through does not change the developer's profile.

- [ ] **Step 4: Browser walk-through, recipe 1 (real backend, stub LLM).** Replace `<SCR>` with the folder printed above. Run this with `browser_run_code_unsafe` (or the same calls in a scratch Playwright script), viewport 1280x720:

```js
async (page) => {
  const D = '<SCR>/';
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto('http://127.0.0.1:8001/');
  await page.click('#letterheadOpenBtn');
  await page.waitForTimeout(400); await page.screenshot({ path: D + 'upload.png' });
  const focusOnOpen = await page.evaluate(() => document.activeElement.id);
  await page.setInputFiles('#lhFile', D + 'pad.png');
  await page.click('#lhUploadBtn');
  await page.waitForSelector('#lhReview:not([hidden])', { timeout: 60000 });
  await page.waitForTimeout(800); await page.screenshot({ path: D + 'review.png' });
  await page.fill('#lhProf_doctor_name', 'Dr. Anita Rao');
  await page.fill('#lhLine0', 'Care for every family');
  await page.click('#lhAcceptBtn');          // never pressed Update: Accept must save the edits (Review Focus 7)
  await page.waitForSelector('#lhDone:not([hidden])');
  await page.waitForTimeout(500); await page.screenshot({ path: D + 'accepted.png' });
  return await page.evaluate((f) => [f, document.getElementById('topDoctor').textContent,
    document.getElementById('cDoctor').textContent, document.getElementById('lhStatus').textContent], focusOnOpen);
}
```

Expected return: `["lhFile", "Dr. Anita Rao", "Dr. Anita Rao MBBS, MD", "Your own letterhead is active: prescriptions print on it."]`. Now LOOK at the three screenshots with the Read tool:
  - `upload.png`: the amber "Blank pad only. No patient information." box is the most prominent thing in the panel, fully readable; the file picker and "Upload and read letterhead" button are visible; nothing clipped.
  - `review.png`: a PDF page (or the "Open the page 1 preview" link) on the left, the two text lines and six clinic fields on the right, the four footer buttons (Use built-in layout instead, Re-upload, Update preview, Accept) fully on screen. The right column scrolls inside the panel; the footer does not move.
  - `accepted.png`: green success box, and the clinic name and doctor in the page behind the panel changed.
  Also check `GET /api/v1/templates/active` returns 200 (`curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/api/v1/templates/active`).

- [ ] **Step 5: Discard path.** Upload again and click `#lhBuiltinBtn`. Expected: `#lhDone` reads "The draft was discarded..." and `lhStatus` still says the accepted letterhead is active ("built-in layout instead" only drops the draft; stopping an accepted letterhead is added later by plan B2d, so change nothing here). Upload again and click `#lhReuploadBtn`: the upload view returns with the file field focused.

- [ ] **Step 6: Leave uncommitted.**

---

### Task 3: Error codes, keyboard path, laptop viewport

**Files:** none new. Fix `frontend/letterhead.js` / `letterhead.css` only if a check fails.

- [ ] **Step 1: Recipe 2, every error code with `fetch` stubbed.** Reload the page, open the panel, choose the file, then run (viewport 1280x720):

```js
async (page) => {
  const D = '<SCR>/'; const out = {};
  await page.goto('http://127.0.0.1:8001/'); await page.click('#letterheadOpenBtn');
  await page.setInputFiles('#lhFile', D + 'pad.png');
  for (const code of [400, 413, 429, 502, 503, 500, 'net']) {
    await page.evaluate((c) => { const real = window.__real || (window.__real = window.fetch.bind(window));
      window.fetch = (u, o) => (o && o.method === 'POST') ? (c === 'net' ? Promise.reject(new TypeError('x'))
        : Promise.resolve(new Response('{}', { status: c }))) : real(u, o); }, code);
    await page.click('#lhUploadBtn'); await page.waitForSelector('#lhError:not([hidden])');
    out[code] = await page.textContent('#lhError');
    if (code === 503) await page.screenshot({ path: D + 'err503.png' });
    await page.evaluate(() => { document.getElementById('lhError').hidden = true; });
  }
  return out;
}
```

Expected: seven different plain-language sentences, none containing "undefined" or raw JSON. LOOK at `err503.png`: the red box sits above the amber notice, text wraps inside the panel, Upload still reachable. Then with a draft showing (do Task 2 step 4 up to `#lhReview`), stub preview as 503 and accept as 404 and click Update preview then Accept:

```js
await page.evaluate(() => { const real = window.fetch.bind(window);
  window.fetch = (u, o) => String(u).includes('/preview.pdf') ? Promise.resolve(new Response('', { status: 503 }))
    : (o && o.method === 'POST' && String(u).endsWith('/accept')) ? Promise.resolve(new Response('{}', { status: 404 })) : real(u, o); });
```

Expected: the preview box reads "The preview could not be drawn (code 503). Press Update preview to try again."; the error box reads "This draft no longer exists (drafts expire after a day). Upload the picture again." Then simulate a browser without a PDF viewer: `await page.evaluate(() => Object.defineProperty(navigator, 'pdfViewerEnabled', { value: false }))` before the upload; expected preview box text "This browser cannot show a PDF inside the page. Open the page 1 preview in a new tab" with a working link. Double-click guard: on a fresh load, choose the file and run `await page.dblclick('#lhUploadBtn')` against the real stub backend; `browser_network_requests` must show exactly one `POST /api/v1/templates`.

- [ ] **Step 2: Recipe 3, keyboard only.** After a fresh page load run:

```js
async (page) => {
  const D = '<SCR>/'; const id = () => page.evaluate(() => document.activeElement.id); const t = [];
  await page.goto('http://127.0.0.1:8001/');
  await page.focus('#letterheadOpenBtn'); await page.keyboard.press('Enter'); await page.waitForTimeout(300); t.push(await id());
  await page.setInputFiles('#lhFile', D + 'pad.png');   // the OS file dialog cannot be keyed; this is the one exception
  await page.keyboard.press('Tab'); t.push(await id()); await page.keyboard.press('Enter');
  await page.waitForSelector('#lhReview:not([hidden])', { timeout: 60000 }); await page.waitForTimeout(500); t.push(await id());
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);
  t.push('open=' + await page.evaluate(() => document.getElementById('lhPanel').open));
  await page.keyboard.press('Enter'); await page.waitForTimeout(300);
  t.push('draft-kept=' + await page.evaluate(() => !document.getElementById('lhReview').hidden));
  for (let i = 0; i < 12; i++) { await page.keyboard.press('Tab'); t.push(await id()); }
  return t;
}
```

Expected: `lhFile`, `lhUploadBtn`, `lhLine0`, `open=false`, `draft-kept=true`, then a Tab trail through `lhLine1`, the six `lhProf_*` fields, `lhBuiltinBtn`, `lhReuploadBtn`, `lhUpdateBtn`, `lhAcceptBtn` (an unnamed stop on the PDF or the dialog's Close button may follow); focus never leaves the dialog. Take a screenshot while focus is on `lhAcceptBtn` and LOOK: a visible blue focus ring around Accept.

- [ ] **Step 3: Laptop viewport.** `browser_resize` 1280x600, repeat the upload to reach review, `browser_take_screenshot`. LOOK: the dialog is inside the window, the footer buttons are visible without scrolling the page, and the fields scroll inside the panel. Repeat at 390x800: the columns stack and nothing is clipped sideways.

- [ ] **Step 4: Leave uncommitted.** Fix and re-run any failing check above before moving on.

---

### Task 4: Final verification (contracts section 5)

- [ ] **Step 1: Full suite.** Run `.venv/bin/python -m pytest tests/ -q`. Expected: the same count as before this plan (this plan adds 0 tests); note the count in the report.

- [ ] **Step 2: One more pass on the running app.** With the Task 2 step 3 server still up, repeat the Task 2 step 4 walk-through once, then confirm `⚙ Profile` still opens and Esc closes it, and `browser_console_messages` shows no errors from either script.

- [ ] **Step 3: Report** the four changed files, the test count, and the screenshots you looked at. State what this plan cannot prove: a real HEIC upload, a real vision model's output, non-Chromium PDF embedding, a screen reader. Do not commit.
