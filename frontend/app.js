"use strict";
// Professional two-pane workspace (the approved "A + B"): top bar, "Today"
// sidebar, the dictation/assistant middle pane, and the prescription document on
// the right. Vanilla JS, no build step, no framework, no model picker.
const $ = (id) => document.getElementById(id);

// Review Focus #5: a whole-visit dictation (~5 min) must not silently lose the
// transcript. The abort is generous, and an abort surfaces a visible error.
const TRANSCRIBE_TIMEOUT_MS = 300000; // 5 minutes
const FORMAT_TIMEOUT_MS = 90000;
const CORRECT_TIMEOUT_MS = 90000;
const SAVE_TIMEOUT_MS = 60000;
const MAX_RECORD_S = 300;   // a dictation stops itself at 5 minutes (reccap.js) ...
const WARN_RECORD_S = 270;  // ... after a warning 30 seconds before

const recBtn = $("recBtn");
const timerEl = $("timer");
const wave = $("wave");
const statusEl = $("status");
const errorEl = $("error");
const groundingEl = $("grounding");
const sheetEl = $("sheet");
const rxBody = $("pRx");
const saveBtn = $("saveBtn");
const printBtn = $("printBtn");
const savePdfBtn = $("savePdfBtn");
const blockPanel = $("blockPanel");
const todayList = $("todayList");
const transcriptBox = $("transcriptBox");
const transcriptText = $("transcriptText");
const agentChip = $("agentChip");
const resaveNote = $("resaveNote");
const profilePanel = $("profilePanel");

const state = {
  visitDate: "", // ISO visit day of the open document ("" = a new sheet: today); the sheet date is read-only
  structured: null, // last server-validated form (source for edits)
  transcript: "",
  transcriptSha: "",
  engine: "",
  confirmed: new Set(), // rx row *ids* (stable) the doctor explicitly confirmed
  lastBlock: [],        // rows the last save refused on ({index,name,status,rowid})
  dirty: false,         // the sheet has changes since the last save / open
  editGen: 0,           // bumps on every edit: Save/Open/Print detect a change made while in flight
  sheetSeq: 0,          // bumps whenever a different sheet is rendered or cleared
  savedPatientName: null, // patient name when the document was last saved/opened
  printing: false,      // a Print fetch is in flight (double-click guard)
  retry: null,          // {mode, transcript} for a failed format/correct
  working: false,
  pendingMode: "dictate",
  documentId: null,     // set only when opened from "Today" -> a re-save updates it
  profile: null,        // last loaded clinic profile
  today: [],            // last loaded "Today" rows
  listDay: "",          // the day the list shows: "" = today, else an earlier ISO day (daynav.js moves it)
  shownDay: "",         // the day whose rows are on screen (listDay goes back to it when a fetch fails)
};

// Stable identity for Rx rows. Confirmations key on this, not on the positional
// index, so pruning/renumbering a blank row can never shift a confirmation onto
// a different medicine (Review Finding 1).
let rowSeq = 0;

// ---- small helpers ---------------------------------------------------------
const text = (el) => (el ? el.textContent : "").replace(/\s+/g, " ").trim();
const setText = (el, v) => { if (el) el.textContent = v == null ? "" : String(v); };
const inputVal = (id) => { const el = $(id); return el ? String(el.value || "").trim() : ""; };
const setInput = (id, v) => { const el = $(id); if (el) el.value = v == null ? "" : String(v); };
const today = () => (window.Dates ? window.Dates.today() : "");        // "17 Oct 2026" in the clinic zone (dates.js)
const fmtTime = (s) => String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
const cellText = (tr, col) => text(tr.querySelector('[data-col="' + col + '"]'));

async function safeJson(r) { try { return await r.json(); } catch { return {}; } }

function setStatus(msg) { statusEl.textContent = msg || ""; }
// #error holds #errorText plus a Retry button: a failed format/correct keeps the
// transcript so the doctor never has to re-dictate the visit (Finding 2).
function showError(msg, retry) {
  $("errorText").textContent = msg || "";
  errorEl.hidden = !msg;
  $("retryBtn").hidden = !(msg && retry);
}
function clearError() { showError(""); }
function errorMessage(e, fallback) {
  if (e && e.aborted && (!e.message || e.message === "timed out")) return fallback + " (timed out).";
  if (e && e.message) return e.message;
  return fallback + ".";
}

// ---- assistant status: four steps the page really knows (steps.js): Listening, Transcribing (/api/transcribe in flight),
// Structuring and checking (/api/format or /api/v1/correct in flight: one request, so no finer split), Your review.
const wordCount = (t) => String(t || "").split(/\s+/).filter(Boolean).length;
function setStep(stage, info) { if (window.Steps) Steps.main(stage, info); }          // steps.js also updates the top-bar chip

// ---- health badge: hidden from end users; ?debug=1 shows the engine, an offline backend always says so --------
const DEBUG_BADGE = new URLSearchParams(window.location.search).get("debug") === "1";
fetch("/api/health").then(r => r.json()).then(h => {
  if (window.Dates) window.Dates.initFrom(h, $("pDate"));    // locale and clinic zone from the server; a typed sheet date is kept
  if (!DEBUG_BADGE) return;
  const llm = h.llm_configured ? `${h.llm_provider}:${h.llm_model}`
    : (h.deepseek_configured ? "DeepSeek" : "rules-fallback");
  $("engineBadge").textContent = `${h.stt_engine || h.whisper_model} • ${llm}`;
  $("engineBadge").hidden = false;
}).catch(() => { $("engineBadge").textContent = "backend offline"; $("engineBadge").hidden = false; });

// ---- working state ---------------------------------------------------------
function setWorking(on, msg) {
  state.working = on;
  if (window.SpellModal) SpellModal.sync();
  if (msg) setStatus(msg);
  recBtn.disabled = on;
  saveBtn.disabled = on;
  if (on) { printBtn.disabled = true; savePdfBtn.disabled = true; if (window.Share) Share.sync(printBtn); } else refreshPrintButton();
  $("newPatientBtn").disabled = on;
  $("profileOpenBtn").disabled = on;
  $("profileLetterheadBtn").disabled = on;
  const rb = $("retryBtn");
  if (rb) rb.disabled = on;
  document.querySelectorAll("#sheet .x-btn, #undoBtn, #undoDictBtn").forEach(b => { b.disabled = on; });
  recBtn.classList.toggle("busy", on);
  if (!(mr && mr.state === "recording")) { if (on) setMicLabel("Working…"); else refreshMicLabel(); }   // the words beside the mic follow
  RxView.sync();                                     // after :128 Save follows the medicines, not just "busy"
  if (window.Authorship) Authorship.enforce();      // last word: view-only must not rest on CSS hiding the x/confirm buttons
}

// ---- clinic profile --------------------------------------------------------
// The six profile fields render at the top of the sheet (mirrors backend PDF
// header) and give the top bar its clinic/doctor identity. A blank profile is
// fine: Save is never blocked, and a hint nudges a first-run entry.
function renderProfileHeader(p) {
  p = p || {};
  const viewOnly = !!(window.Authorship && (Authorship.isViewOnly() || Authorship.keepsOwnHeader()));   // an opened prescription keeps its author's doctor lines
  if (!viewOnly && window.Authorship) Authorship.renderDoctorLines($("cDoctor"), p.doctor_name, p.qualifications, p.reg_no);
  setText($("cClinic"), p.clinic_name || "");
  setText($("cPhone"), p.phone ? "Ph: " + p.phone : "");
  setText($("cAddr"), p.address || "");
  const any = !!(p.doctor_name || p.qualifications || p.reg_no || p.clinic_name || p.address || p.phone);
  const hint = $("profileHint");
  if (hint) hint.hidden = any;
  setText($("topClinic"), p.clinic_name || (window.DDUser && window.DDUser.clinic_name) || "Clinic");   // Profile name first, the account's clinic name only as a fallback
  setText($("topDoctor"), p.doctor_name || (window.DDUser && window.DDUser.display_name) || "Doctor");   // the signed-in user's own details, never the sheet's author
}

function fillProfileForm(p) {
  p = p || {};
  setInput("profDoctor", p.doctor_name || "");
  setInput("profQual", p.qualifications || "");
  setInput("profReg", p.reg_no || "");
  setInput("profClinic", p.clinic_name || "");
  setInput("profAddress", p.address || "");
  setInput("profPhone", p.phone || "");
  setInput("profOpPrefix", p.op_prefix || "");
  if (typeof DoctorGrid !== "undefined") DoctorGrid.refresh("profDoctorGrid");   // redraw the doctors' cells from the hidden inputs
}

async function loadProfile() {
  try {
    const r = await fetch("/api/v1/profile");
    const p = await safeJson(r);
    if (!r.ok) throw new Error(p.error || ("Could not load profile (" + r.status + ")"));
    state.profile = p || {};
    renderProfileHeader(state.profile);
    fillProfileForm(state.profile);
  } catch (e) {
    // Non-fatal: the workspace still works with a blank profile.
    renderProfileHeader({});
  }
}

function openProfilePanel() {
  fillProfileForm(state.profile || {});
  setText($("profileStatus"), "");
  if (profilePanel && typeof profilePanel.showModal === "function") profilePanel.showModal();
  else if (profilePanel) profilePanel.setAttribute("open", "");
  const first = $("profClinic") || $("profDoctor");   // the first field of the first fieldset
  if (first) first.focus();
}

function closeProfilePanel() {
  if (!profilePanel) return;
  if (typeof profilePanel.close === "function") profilePanel.close();
  else profilePanel.removeAttribute("open");
}

async function saveProfile(e) {
  if (e) e.preventDefault();
  const body = {
    doctor_name: inputVal("profDoctor"),
    qualifications: inputVal("profQual"),
    reg_no: inputVal("profReg"),
    clinic_name: inputVal("profClinic"),
    address: inputVal("profAddress"),
    phone: inputVal("profPhone"),
    op_prefix: inputVal("profOpPrefix").toUpperCase() || undefined,   // blank: not sent, the prefix stays as it is
  };
  setText($("profileStatus"), "Saving…");
  try {
    const r = await fetch("/api/v1/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const p = await safeJson(r);
    if (!r.ok) throw new Error(p.error || ("Could not save profile (" + r.status + ")"));
    state.profile = p || body;
    renderProfileHeader(state.profile);
    fillProfileForm(state.profile);
    setText($("profileStatus"), "Saved.");
    closeProfilePanel();
  } catch (err) {
    setText($("profileStatus"), errorMessage(err, "Could not save the profile"));
  }
}

// ---- "Today" sidebar -------------------------------------------------------
function fmtClock(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return window.Dates ? window.Dates.time(iso) : "";
}

function renderToday(rows) {
  state.today = Array.isArray(rows) ? rows : [];
  todayList.innerHTML = "";
  if (!state.today.length) {
    const empty = document.createElement("div");
    empty.className = "today-empty";
    empty.textContent = window.DayNav ? DayNav.emptyText(state.listDay) : "No patients completed yet today.";
    todayList.appendChild(empty);
    return;
  }
  for (const row of state.today) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "today-item";
    btn.dataset.docid = String(row.document_id);
    const name = document.createElement("span");
    name.className = "today-name";
    name.textContent = row.patient_name || "Unnamed";
    const meta = document.createElement("span");
    meta.className = "today-meta";
    const bits = [];
    if (row.op_no) bits.push("OP " + row.op_no);
    const t = fmtClock(row.created_at);
    if (t) bits.push(t);
    const who = window.Authorship ? Authorship.authorLabel(row) : "";
    if (who) bits.push(who);
    meta.textContent = bits.join(" · ");
    btn.append(name, meta);
    btn.title = "Reopen this prescription";
    btn.addEventListener("click", () => openDocument(row));
    todayList.appendChild(btn);
  }
  highlightToday();
}

function highlightToday() {
  const active = state.documentId == null ? "" : String(state.documentId);
  [...todayList.querySelectorAll(".today-item")].forEach(btn => {
    btn.classList.toggle("active", btn.dataset.docid === active);
  });
}

let todaySeq = 0;   // only the newest request may render (a late answer to an earlier scope click is dropped)
async function loadToday() {
  const seq = ++todaySeq;
  try {
    const q = window.Authorship ? Authorship.todayQuery() : "";
    const r = await fetch(window.DayNav ? DayNav.url("/api/v1/encounters/today", q, state.listDay) : "/api/v1/encounters/today" + q);
    if (!r.ok) throw new Error("today " + r.status);
    const rows = await safeJson(r);
    if (seq !== todaySeq) return;
    state.shownDay = state.listDay;
    if (window.DayNav) DayNav.render();
    renderToday(rows);
  } catch {
    // Leave the sidebar as-is; a refresh failure must not disturb the sheet. The title goes back to the day whose rows
    // are still on screen.
    if (seq === todaySeq && window.DayNav) { state.listDay = state.shownDay || ""; DayNav.render(); }
  }
}

// Click a "today" patient -> load its prescription back onto the sheet, and
// remember document_id so a Save updates that document in place (design #1).
async function openDocument(row) {
  // Never switch documents mid-flight: a correction applied after a switch
  // could land on the wrong document (Finding #2). Busy/recording -> refuse,
  // but say so rather than silently doing nothing.
  if (state.working || state.printing || (mr && mr.state === "recording")) {
    setStatus("Finish the current recording, save or print before opening another patient.");
    return;
  }
  // Opening another patient overwrites the in-progress draft. Confirm first so a
  // dictated-but-unsaved visit is never lost silently (mirrors newPatient). A
  // re-click of the already-open document loses nothing and needs no prompt.
  const sameDoc = state.documentId != null && String(state.documentId) === String(row.document_id);
  if (isUnsaved() && !sameDoc &&
      !window.confirm("Open " + (row.patient_name || "this document") +
        "? The current draft stays unsaved.")) {
    return;
  }
  clearError();
  const gen = state.editGen; // an edit made while the GET is in flight must not be discarded
  setWorking(true, "Loading " + (row.patient_name || "document") + "…");
  try {
    const r = await fetch("/api/v1/documents/" + encodeURIComponent(row.document_id));
    const j = await safeJson(r);
    if (!r.ok) throw new Error(j.error || ("Could not load document (" + r.status + ")"));
    if (state.editGen !== gen) {
      setStatus("You changed the sheet while the document was loading, so it was not opened. Save or finish your edit, then open it again.");
      return;
    }
    state.structured = j.structured || {};
    state.engine = j.engine || "";
    state.transcriptSha = j.transcript_sha256 || "";
    state.transcript = "";
    state.dirty = false; // a saved document: edits/corrections allowed, re-save updates in place
    state.documentId = j.document_id != null ? j.document_id : row.document_id;
    state.visitDate = j.visit_date || "";
    state.savedPatientName = String((state.structured || {}).patientName || "");
    state.retry = null;
    DictGuard.clear(); Cues.clearFlags();          // flags named the previous sheet's empty sections
    state.confirmed.clear();
    state.lastBlock = [];
    hideBlockPanel();
    clearError();
    renderTranscript();
    renderSheet(state.structured, savedConfirmations(state.structured));
    updateResaveNote();
    if (window.Authorship) Authorship.onOpen(j);   // a colleague's prescription opens view-only
    RxView.focusFirst();                           // view-only: no focus move
    highlightToday();
    refreshPrintButton();
    const viewOnlyNow = !!(window.Authorship && Authorship.isViewOnly());
    setStep("opened", { viewOnly: viewOnlyNow, ...stepCounts() });       // openDocument: nothing was heard this time
    const author = viewOnlyNow ? window.Authorship.viewOnlyAuthor() : "";
    refreshMicLabel();
    setStatus(viewOnlyNow && !author && j.past
      ? "Viewing " + (row.patient_name || "document") + " from " + ((window.Dates && Dates.date(j.visit_date)) || j.visit_date || "an earlier day") +
        ". Past prescriptions are view and reprint only."
      : viewOnlyNow
      ? "Viewing " + (row.patient_name || "document") + " (" + author + "'s prescription). You can print it, not edit it."
      : "Reopened " + (row.patient_name || "document") + " — Print it as is, or edit and Save to update this document.");
  } catch (e) {
    setStatus("");
    showError(errorMessage(e, "Could not load the document"));
  } finally {
    setWorking(false);
  }
}

function updateResaveNote() {
  if (!resaveNote) return;
  if (state.documentId == null) { resaveNote.hidden = true; resaveNote.textContent = ""; return; }
  resaveNote.hidden = false;
  resaveNote.textContent = "Editing today's document #" + state.documentId + " — Save updates it in place.";
}

// ---- recorder --------------------------------------------------------------
let mr = null, chunks = [], tick = null, t0 = 0;
const recCap = RecCap.create({ max: MAX_RECORD_S, warn: WARN_RECORD_S, timer: timerEl, status: setStatus, stop: () => { if (mr && mr.state === "recording") mr.stop(); } });

recBtn.addEventListener("click", () => {
  if (state.working || (window.SpellModal && SpellModal.busy())) return;
  if (mr && mr.state === "recording") { mr.stop(); return; }
  beginRecording();
});

async function beginRecording() {
  clearError();
  state.retry = null;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    showError("Microphone unavailable: " + ((e && e.message) || e) + ". Allow mic access and try again."); setStep("failed-listening", { reason: "Microphone unavailable" });
    return;
  }
  chunks = [];
  const mime = ["audio/webm", "audio/mp4"].find(t => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || "";
  try {
    mr = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
  } catch (e) {
    stopStream(stream);
    showError("Recording is not supported in this browser."); setStep("failed-listening", { reason: "Recording not supported" });
    return;
  }
  // No sheet yet -> first dictation. A sheet exists -> the mic is a correction.
  // After a save the next dictation is a fresh encounter, not a correction.
  state.pendingMode = canCorrect() ? "correct" : "dictate";
  mr.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
  mr.onstop = () => { stopStream(stream); onRecordingStop(); };
  mr.start();
  Cues.clearFlags();
  DictGuard.banner(state.pendingMode === "correct" ? { name: text($("pName")), op: text($("pOp")), saved: state.documentId != null } : null);
  refreshPrintButton();
  t0 = Date.now();
  timerEl.textContent = "00:00";
  recCap.reset();
  tick = setInterval(() => { const s = Math.floor((Date.now() - t0) / 1000); timerEl.textContent = fmtTime(s); recCap.tick(s); }, 500);
  recBtn.classList.add("recording");
  setMicLabel("Tap to stop");
  wave.classList.add("on");
  state.transcript = "";
  renderTranscript();
  setStep("listening");
  setStatus(state.pendingMode === "correct"
    ? "Recording correction — speak the change, then Stop."
    : "Recording — dictate the whole visit, then Stop.");
}

function stopStream(stream) { try { stream.getTracks().forEach(t => t.stop()); } catch {} }
function endRecordingUI() {
  DictGuard.banner(null);
  if (tick) { clearInterval(tick); tick = null; }
  timerEl.classList.remove("rec-warn");
  recBtn.classList.remove("recording");
  wave.classList.remove("on");
  refreshMicLabel();
  refreshPrintButton();
}
function setMicLabel(t) { const l = $("micLabel"); if (l) l.textContent = t; recBtn.setAttribute("aria-label", t); }
// The mic follows the visible sheet: any sheet on screen takes corrections (a
// saved document re-saves in place). Only "New patient" makes a dictation a fresh visit.
function canCorrect() { return !!state.structured; }
// Unsaved work = something on screen that is not a saved, unchanged document.
function isUnsaved() {
  return !!(state.structured || state.transcript) && (state.documentId == null || state.dirty);
}
// Any change to the sheet leaves it unsaved until the next successful Save.
function markDirty() { state.dirty = true; state.editGen++; refreshPrintButton(); }
// Print is enabled only for a saved document with no unsaved changes.
function refreshPrintButton() {
  const recording = !!(mr && mr.state === "recording");
  const saved = state.documentId != null;
  printBtn.disabled = !(saved && !state.dirty && !state.working && !recording) || state.printing;
  savePdfBtn.disabled = printBtn.disabled;
  printBtn.title = !saved ? "Save first, then print"
    : state.dirty ? "Save your changes first"
    : "Print this prescription (letterhead PDF)";
  if (window.Authorship) Authorship.enforce();      // setWorking/setPrinting re-enable the mic and Save
  if (window.Share) Share.sync(printBtn);
}
// Persistent cue next to the mic: which prescription a dictation would correct.
function updateCue() {
  const el = $("correctingCue");
  if (!el) return;
  if (!state.structured) { el.hidden = true; el.textContent = ""; return; }
  const name = text($("pName")), op = text($("pOp"));
  el.hidden = false;
  el.textContent = "Correcting: " + (name || "this prescription") + (op ? " · " + op : "") +
    (state.documentId != null ? " (document " + state.documentId + ")" : " (not saved yet)");
}
function refreshMicLabel() {
  const off = !!(window.Authorship && Authorship.isViewOnly());   // a colleague's prescription: the mic is off
  setMicLabel(off ? "Dictation off" : canCorrect() ? "Dictate correction" : "Tap to dictate");
  updateCue();
}

async function onRecordingStop() {
  const mode = state.pendingMode;
  endRecordingUI();
  const snap = DictGuard.capture();
  if (!chunks.length) { showError("No audio was captured — check your microphone and try again."); setStep("failed-listening", { reason: "No audio captured" }); return; }
  const blob = new Blob(chunks, { type: (mr && mr.mimeType) || "audio/webm" });
  chunks = [];
  setStep("transcribing", { recorded: timerEl.textContent });
  try {
    const transcript = await transcribe(blob);
    if (!transcript) { showError("No speech detected — nothing was changed. Press the mic and speak again."); setStep("failed-transcribing", { reason: "No words found" }); return; }
    // Transcription is one-shot: show it in the middle pane as soon as we have it.
    state.transcript = transcript;
    renderTranscript();
    if (mode === "correct" && state.structured) await applyCorrection(transcript, snap);
    else await formatTranscript(transcript, snap);
  } catch (e) {
    showError(errorMessage(e, "Dictation failed"));
    setStep(state.transcript ? "failed-structuring" : "failed-transcribing", { reason: "Dictation failed" });   // a throw after the transcript is a structuring failure
  }
}

// ---- network ---------------------------------------------------------------
async function postJson(url, body, timeoutMs, outer) {
  const ctrl = new AbortController();
  if (outer) outer.addEventListener("abort", () => ctrl.abort());   // the caller can cancel (Spell it: a newer search replaces the older)
  const to = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    const j = await safeJson(r);
    if (!r.ok) {
      const err = new Error(j.error || j.hint || ("Request failed (" + r.status + ")"));
      err.status = r.status;
      err.data = j;
      throw err;
    }
    return j;
  } catch (e) {
    if (e && e.name === "AbortError") { const err = new Error("timed out"); err.aborted = true; throw err; }
    throw e;
  } finally {
    clearTimeout(to);
  }
}

function patientContext() {   // SH-H4: the sheet's patient, for the server only (never sent to a speech engine)
  const cut = (v) => String(v == null ? "" : v).trim().slice(0, 200);
  return { name: cut(text($("pName"))), age_sex: cut(text($("pAge"))), op_no: cut(text($("pOp"))) };
}

// A spoken correction tells the server the sheet's diagnosis and patient (plan SH-H3). The server never sends it to a speech engine.
function speechContext() {
  const cut = (v) => String(v == null ? "" : v).trim().slice(0, 200);
  const ctx = { diagnosis: readList("pDx").map(cut).filter(Boolean).slice(0, 10), patient: patientContext() };
  while (ctx.diagnosis.length && new TextEncoder().encode(JSON.stringify(ctx)).length > 4096) ctx.diagnosis.pop();
  return JSON.stringify(ctx);
}

async function transcribe(blob) {
  setWorking(true, recCap.capped() ? recCap.stopText : "Transcribing…");   // a 5-minute stop keeps saying why it stopped
  setStep("transcribing");
  const fd = new FormData();
  fd.append("audio", blob, "dictation.webm");
  if (state.pendingMode === "correct" && state.structured) fd.append("context", speechContext());   // corrections only (plan SH-H3)
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), TRANSCRIBE_TIMEOUT_MS);
  try {
    const r = await fetch("/api/transcribe", { method: "POST", body: fd, signal: ctrl.signal });
    const j = await safeJson(r);
    if (!r.ok) throw new Error(j.hint || j.error || ("Transcription failed (" + r.status + ")"));
    return String(j.transcript || "").trim();
  } catch (e) {
    if (e && e.name === "AbortError") {
      const err = new Error("Transcription timed out after 5 minutes. Your dictation was not saved — press the mic to try again.");
      err.aborted = true;
      throw err;
    }
    throw e;
  } finally {
    clearTimeout(to);
    setWorking(false);
  }
}

// Spell it voice input (plan I2-c): the same route as dictation, a short timeout, no page-wide "working" state.
async function transcribeName(blob) {
  const fd = new FormData(); fd.append("audio", blob, "name.webm");
  fd.append("context", speechContext()); fd.append("mode", "name");
  const ctrl = new AbortController(), to = setTimeout(() => ctrl.abort(), 20000);
  try {
    const r = await fetch("/api/transcribe", { method: "POST", body: fd, signal: ctrl.signal }), j = await safeJson(r);
    if (!r.ok) { const err = new Error(j.hint || j.error || ""); err.status = r.status; throw err; }
    return String(typeof j.name === "string" && j.name.trim() ? j.name : j.transcript || "").trim();
  } catch (e) { if (e && e.name === "AbortError") { const err = new Error("timed out"); err.aborted = true; throw err; } throw e; }
  finally { clearTimeout(to); }
}

// The server's notes on a draft or a correction, appended to the status line.
function warningNote(j) { return j.warnings && j.warnings.length ? " ⚠ " + j.warnings.join(" ") : ""; }

async function formatTranscript(transcript, snap) {
  // Retain the transcript immediately, before the LLM call: a slow format must
  // never lose the visit (Finding 2).
  state.transcript = transcript;
  renderTranscript();
  state.documentId = null; // a fresh dictation is a new encounter, not a re-save
  state.visitDate = "";
  refreshPrintButton();
  updateResaveNote();
  setWorking(true, "Structuring the prescription…");
  setStep("structuring", { words: wordCount(transcript), mode: "dictate" });
  try {
    const j = await postJson("/api/format", { transcript }, FORMAT_TIMEOUT_MS);
    state.transcriptSha = j.transcript_sha256 || "";
    state.engine = j.engine || "";
    state.structured = j.structured || {};
    state.dirty = false; // documentId is null here, so the sheet still counts as unsaved
    state.retry = null;
    if (snap) DictGuard.keep(snap);
    state.confirmed.clear();
    state.lastBlock = [];
    hideBlockPanel();
    renderSheet(state.structured);
    Sections.showProseCheck(j.prose_check);
    Cues.flagEmpty(state.structured);
    setStep("ready", stepCounts());
    const open = openRows().length;
    setStatus("Draft ready via " + (j.engine || "engine") + (j.cached ? " (cached)" : "") + ". " +
      (open ? open + (open > 1 ? " need you." : " needs you.") : "All medicines ready.") +
      " Edit, dictate a correction, or Save." + warningNote(j));
    RxView.focusFirst();
  } catch (e) {
    state.retry = { mode: "dictate", transcript, snap };
    showError(errorMessage(e, "Could not structure the dictation") +
      " Your dictation is kept — press Retry; there is no need to dictate again.", true);
    setStep("failed-structuring", { reason: "Could not structure it" });
  } finally {
    setWorking(false);
  }
}

async function applyCorrection(transcript, snap) {
  const before = serializeForm(), current = before.structured;
  state.transcript = transcript; // retained before the call (Finding 2)
  renderTranscript();
  setWorking(true, "Applying your correction…");
  setStep("structuring", { words: wordCount(transcript), mode: "correct" });
  try {
    const j = await postJson("/api/v1/correct", { transcript, current_form: current, document_id: state.documentId }, CORRECT_TIMEOUT_MS);
    if (j.other_patient && await DictGuard.ask(j.other_patient, text($("pName"))) === "new") {
      // Nothing was applied; the snapshot is kept first so a failed follow-up format can still be undone. The finally re-enables the page.
      if (snap) DictGuard.keep(snap);
      resetSheet();
      return await formatTranscript(transcript, snap);
    }
    const kept = j.other_patient ? DictGuard.keptNote(j.structured || current, current) : "";
    if (j.other_patient) j.structured = DictGuard.keepIdentity(j.structured || current, current);   // "Apply": the sheet keeps its own patient
    state.structured = j.structured || current;
    const carry = RxState.carryRowids(before.indexToRowid, current.rx, (state.structured || {}).rx, j.changed_rows);
    markDirty();
    // A correction re-grounds the rows it changed; confirmations stay on the rest (changed_rows).
    state.retry = null;
    if (snap) DictGuard.keep(snap);
    [...state.confirmed].forEach(id => { if (!carry.includes(id)) state.confirmed.delete(id); });
    state.lastBlock = [];
    hideBlockPanel();
    const how = {}; rxBody.querySelectorAll("tr[data-rowid]").forEach(tr => { if (tr._rx && tr._rx.how && carry.includes(tr.dataset.rowid)) how[tr.dataset.rowid] = tr._rx.how; });
    renderSheet(state.structured, carry);
    rxBody.querySelectorAll("tr[data-rowid]").forEach(tr => { if (how[tr.dataset.rowid]) { tr._rx.how = how[tr.dataset.rowid]; renderCheck(tr); } });   // a kept row keeps "You chose..."; a changed row got a fresh id and has none
    Sections.showProseCheck(j.prose_check);
    Cues.flagEmpty(state.structured);
    setStep("ready", stepCounts());
    const open = openRows().length;
    setStatus("Correction merged via " + (j.engine || "engine") + ". " +
      (open ? open + (open > 1 ? " need you." : " needs you.") : "All medicines ready.") +
      " Review, then Save." + warningNote(j) + (kept && " " + kept));
    RxView.focusFirst();                           // owner: after a spoken correction, start on the first flagged row
  } catch (e) {
    state.retry = { mode: "correct", transcript, snap };
    showError(errorMessage(e, "Could not apply the correction") +
      " Your form is unchanged and your correction is kept — press Retry, or edit the form directly.", true);
    setStep("failed-structuring", { reason: "Could not apply it" });
  } finally {
    setWorking(false);
  }
}

// Re-run the last failed format/correct with its retained transcript.
function retryLast() {
  const r = state.retry;
  if (!r || state.working) return;
  clearError();
  if (r.mode === "correct" && state.structured) applyCorrection(r.transcript, r.snap);
  else formatTranscript(r.transcript, r.snap);
}

// ---- transcript display ----------------------------------------------------
function renderTranscript() {
  const t = state.transcript || "";
  if (transcriptText) transcriptText.textContent = t;
  if (transcriptBox) transcriptBox.hidden = !t;
}

// ---- reading the form back out of the DOM ----------------------------------
function readList(id) {
  return [...$(id).querySelectorAll("li")].map(liText).filter(Boolean);
}

function readRx() {
  const rows = [...rxBody.querySelectorAll("tr[data-index]")];
  const kept = [];
  for (const tr of rows) {
    const rec = {
      form: cellText(tr, "form"), name: cellText(tr, "name"), strength: cellText(tr, "strength"),
      dose: cellText(tr, "dose"), timing: cellText(tr, "timing"), duration: cellText(tr, "duration"),
      instructions: cellText(tr, "instructions"),
      status: tr.dataset.status || "",
      lexicon_match: tr.dataset.lexicon || "",
    };
    Object.assign(rec, RxView.wire(tr));                 // heard + lookalike: the server restores them from this copy of the row
    if (!(rec.form || rec.name || rec.strength || rec.dose || rec.timing || rec.duration || rec.instructions)) {
      tr.remove(); // fully blank row -> drop it and renumber the rest
      continue;
    }
    kept.push({ tr, rec, rowid: tr.dataset.rowid });
  }
  // Positional index is renumbered for the wire, but the confirmation set is
  // keyed to the stable data-rowid, so a dropped/renumbered row can never move a
  // confirmation onto a different medicine (Review Finding 1).
  kept.forEach(({ tr }, i) => {
    setRowNum(tr, i);
  });
  return kept;
}

// Serialise the whole sheet once; returns the wire form, the confirmed row
// indices (derived from the stable row ids), and the index->rowid map used to
// translate a 409 `block[].index` back to a row.
function serializeForm() {
  const base = state.structured ? JSON.parse(JSON.stringify(state.structured)) : {};
  base.patientName = text($("pName"));
  base.ageSex = text($("pAge"));
  base.opNo = text($("pOp"));
  base.vitals = Vitals.read();
  base.diagnosis = readList("pDx");
  base.complaints = readList("pCc");
  base.findings = readList("pFx");
  base.investigations = IxList.read($("pIx"));      // items {text, canonical, status, source}; blanks dropped as the server does
  base.advice = readList("pAdv");
  SheetSecs.readBack(base);
  base.review = text($("pRev"));
  const kept = readRx();
  base.rx = kept.map(k => k.rec);
  const confirmed_rows = [];
  const indexToRowid = [];
  kept.forEach((k, i) => {
    indexToRowid.push(k.rowid);
    if (state.confirmed.has(k.rowid)) confirmed_rows.push(i);
  });
  return { structured: base, confirmed_rows, indexToRowid, remember_generics: GenericEdit.rememberIndexes(kept.map(k => k.tr)), remember_investigations: IxList.rememberIndexes($("pIx")) };   // same order as confirmed_rows
}

function readForm() { return serializeForm().structured; }

function hasContent(s) {
  if (!s) return false;
  if ((s.patientName || "").trim()) return true;
  if ((s.opNo || "").trim()) return true;
  if ((s.diagnosis || []).length || (s.complaints || []).length || (s.findings || []).length) return true;
  return (s.rx || []).some(r => r && (r.name || r.strength));
}

// ---- delete (x) buttons + one-level undo -----------------------------------
function xBtn(action, label, title) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "x-btn no-print";
  b.dataset.action = action;
  b.setAttribute("aria-label", label);
  b.title = title;
  b.textContent = "×";
  b.disabled = state.working;
  if (action === "delete-item") b.contentEditable = "false";
  return b;
}
// List item text excludes the x button (and an Enter-split li may hold stray ones).
function liText(li) {
  const c = li.cloneNode(true);
  c.querySelectorAll(".x-btn").forEach(b => b.remove());
  return text(c);
}
// Every li keeps exactly one trailing x; `blank` drives the "—" placeholder.
function normalizeLi(li) {
  const btns = li.querySelectorAll(".x-btn");
  if (btns.length !== 1 || li.lastChild !== btns[0]) {
    btns.forEach(b => b.remove());
    li.appendChild(xBtn("delete-item", "Delete item", "Delete this item"));
  }
  const blank = !liText(li);
  li.classList.toggle("blank", blank);
  const t = liText(li);
  li.querySelector(".x-btn").setAttribute("aria-label", t ? "Delete item: " + t.slice(0, 30) : "Delete item");
  // A caret cannot sit before a lone non-editable button; a <br> gives it a home.
  const br = li.querySelector("br");
  if (blank && !br) li.insertBefore(document.createElement("br"), li.firstChild);
  else if (!blank && br) br.remove();
}
function makeLi(v) {
  const li = document.createElement("li");
  li.contentEditable = "true";
  if (v) li.appendChild(document.createTextNode(v));
  normalizeLi(li);
  return li;
}
function normalizeList(ul) { ul.querySelectorAll("li").forEach(normalizeLi); }
function setRowNum(tr, i) {
  tr.dataset.index = String(i);
  const n = tr.querySelector(".rownum");
  if (n) n.textContent = String(i + 1);
  const b = tr.querySelector(".x-btn");
  if (b) b.setAttribute("aria-label", "Delete medicine row " + (i + 1));
}
function renumberRx() {
  [...rxBody.querySelectorAll("tr[data-index]")].forEach((tr, i) => setRowNum(tr, i));
}
function emptyRxRow() {
  const tr = document.createElement("tr");
  tr.className = "rx-empty";
  tr.innerHTML = '<td colspan="8">—</td>';
  return tr;
}

const undoBar = document.createElement("div");
undoBar.className = "undo-bar no-print";
undoBar.hidden = true;
undoBar.setAttribute("role", "status");
undoBar.innerHTML = '<span id="undoText"></span> <button id="undoBtn" type="button" class="undo-btn">Undo</button>';
statusEl.after(undoBar);
const undoStack = []; // up to 5 deletions, most recent last
let lastDeleteAt = 0; // a double-click must never delete two rows
function clearUndo() { undoStack.length = 0; undoBar.hidden = true; }
function showUndo() {
  const r = undoStack[undoStack.length - 1];
  if (!r) { undoBar.hidden = true; return; }
  $("undoText").textContent = r.msg + (undoStack.length > 1 ? " (" + undoStack.length + " can be undone)" : "");
  undoBar.hidden = false;
}
function setUndo(rec, msg) {
  rec.msg = msg;
  undoStack.push(rec);
  if (undoStack.length > 5) undoStack.shift();
  lastDeleteAt = Date.now();
  showUndo();
}

function snapshotRow(tr) {
  const rec = { status: tr.dataset.status || "", lexicon_match: tr.dataset.lexicon || "" };
  for (const c of ["form", "name", "strength", "dose", "timing", "duration", "instructions"]) rec[c] = cellText(tr, c);
  return Object.assign(rec, RxView.meta(tr));       // :756 snapshotRow: heard, generic, chips survive delete + undo
}
function deleteRow(tr) {
  const rows = [...rxBody.querySelectorAll("tr[data-index]")];
  const pos = rows.indexOf(tr), rowid = tr.dataset.rowid;
  const rec = { type: "row", pos, rowid, data: snapshotRow(tr), wasConfirmed: state.confirmed.has(rowid) };
  state.confirmed.delete(rowid);
  tr.remove();
  if (rows.length === 1) rxBody.appendChild(emptyRxRow());
  renumberRx();
  updateGrounding();
  if (!blockPanel.hidden) refreshBlockPanel();
  markDirty();
  setUndo(rec, "Deleted medicine row " + (pos + 1) + ".");
}
function deleteItem(li) {
  const ul = li.parentElement;
  const lis = [...ul.children];
  const rec = { type: "item", ulId: ul.id, pos: lis.indexOf(li), txt: liText(li) };
  li.remove();
  if (!ul.children.length) ul.appendChild(makeLi(""));
  markDirty();
  setUndo(rec, "Deleted item.");
}
function undoDelete() {
  if (!undoStack.length || state.working) return;
  const r = undoStack.pop();
  let focusEl = null;
  if (r.type === "row") {
    const empty = rxBody.querySelector("tr.rx-empty");
    if (empty) empty.remove();
    const rows = [...rxBody.querySelectorAll("tr[data-index]")];
    if (r.wasConfirmed) state.confirmed.add(r.rowid);   // before the first render, so "you chose the strength" survives
    const tr = rxRow(r.data, r.pos, r.rowid);           // same identity, so a pending block/confirm still matches
    rxBody.insertBefore(tr, rows[r.pos] || null);
    renumberRx();
    updateGrounding();
    if (!blockPanel.hidden) refreshBlockPanel();
    focusEl = tr.querySelector(".x-btn");
  } else if (r.type === "ix") {                       // a deleted test comes back where it was, with its status
    focusEl = IxList.insert($("pIx"), r.item, r.pos).querySelector(".x-btn");
  } else if (r.type === "respell") {                  // undo of Spell it "Use this": the row goes back as it was
    focusEl = RxView.restore(r);
    updateGrounding();
    if (!blockPanel.hidden) refreshBlockPanel();
  } else {
    const ul = $(r.ulId);
    const lis = [...ul.children];
    const only = lis.length === 1 && lis[0].classList.contains("blank") ? lis[0] : null;
    const li = makeLi(r.txt);
    if (only) only.remove();
    ul.insertBefore(li, only ? null : (lis[r.pos] || null));
    focusEl = li.querySelector(".x-btn");
  }
  markDirty();
  showUndo();
  if (focusEl) focusEl.focus();
}
sheetEl.addEventListener("click", (e) => {
  const b = e.target && e.target.closest ? e.target.closest(".x-btn") : null;
  if (!b || state.working || Date.now() - lastDeleteAt < 500) return;
  if (b.dataset.action === "delete") deleteRow(b.closest("tr[data-index]"));
  else if (b.dataset.action === "delete-item") deleteItem(b.closest("li"));
  else if (b.dataset.action === "delete-ix") IxList.remove(b.closest("li"));   // pushes its Undo through IxList's onRemove hook
  else return;
  $("undoBtn").focus();
});
$("undoBtn").addEventListener("click", undoDelete);
// Enter/Backspace/paste inside a list li can split, merge or drop the x button.
function fixLists(e) {
  const ul = e.target && e.target.closest ? e.target.closest("ul.editable-list") : null;
  if (ul) normalizeList(ul);
  if (ul && ul.id === "pCc") Sections.clearProse("complaints");
  if (ul && ul.id === "pDx") Sections.clearProse("diagnosis");
  if (ul && ul.id === "pFx") Sections.clearProse("findings");
}
sheetEl.addEventListener("input", fixLists);
sheetEl.addEventListener("keyup", fixLists);
sheetEl.addEventListener("paste", (e) => setTimeout(() => fixLists(e), 0));
$("pRev").addEventListener("input", () => Sections.onReviewInput(text($("pRev"))));

// ---- rendering -------------------------------------------------------------
function renderList(ul, values) {
  ul.innerHTML = "";
  const list = Array.isArray(values) ? values.filter(v => String(v || "").trim()) : [];
  if (!list.length) list.push("");
  for (const v of list) ul.appendChild(makeLi(v));
}

function editable(tag, col, value) {
  const el = document.createElement(tag);
  el.className = "cell";
  el.contentEditable = "true";
  el.dataset.col = col;
  el.textContent = value;
  return el;
}

function rxRow(r, index, rowid) {                      // rowid: Undo restores a row under its old id, before the first render
  r = r || {};
  const tr = document.createElement("tr");
  tr.dataset.index = String(index);
  tr.dataset.rowid = rowid != null ? String(rowid) : String(++rowSeq);
  tr.dataset.status = r.status || "";
  tr.dataset.lexicon = r.lexicon_match || "";

  const num = document.createElement("td");
  num.className = "rownum";
  num.textContent = String(index + 1);
  tr.appendChild(num);

  const med = document.createElement("td");
  med.className = "med";
  for (const col of ["form", "name", "strength"]) {
    const span = editable("span", col, r[col] || "");
    if (col === "name") span.classList.add("rx-name");
    med.appendChild(span);
  }
  tr.appendChild(med);

  for (const col of ["dose", "timing", "duration", "instructions"]) {
    tr.appendChild(editable("td", col, r[col] || ""));
  }

  const check = document.createElement("td");
  check.className = "check";
  tr.appendChild(check);
  RxView.attach(tr, r);                               // :874 rxRow keeps the extra row fields
  renderCheck(tr);

  const del = document.createElement("td");
  del.className = "del no-print";
  del.appendChild(xBtn("delete", "Delete medicine row " + (index + 1), "Delete this medicine"));
  tr.appendChild(del);
  return tr;
}

// Row ids for a reopened document; a row Save stored as doctor_confirmed opens confirmed (before the first render, like Undo).
function savedConfirmations(s) {
  const rows = s && Array.isArray(s.rx) ? s.rx : [];
  return rows.map(r => { const id = String(++rowSeq); if (r && r.doctor_confirmed === true) state.confirmed.add(id); return id; });
}

function renderRx(rows, rowids) {
  rxBody.innerHTML = "";
  const list = Array.isArray(rows) ? rows : [];
  if (!list.length) {
    rxBody.appendChild(emptyRxRow());
    return;
  }
  list.forEach((r, i) => rxBody.appendChild(rxRow(r, i, rowids && rowids[i])));
}

// The row's state cell is built by rxview.js from the rules in rxstate.js.
function renderCheck(tr) { RxView.renderRow(tr); }

function renderSheet(s, rowids) {
  s = s || {};
  state.sheetSeq++;
  setText($("pName"), s.patientName || "");
  setText($("pAge"), s.ageSex || "");
  setText($("pOp"), s.opNo || "");
  Vitals.render(s.vitals);
  setText($("pDate"), state.visitDate ? window.Dates.date(state.visitDate) : today());   // read-only: the document's own visit day, else today
  renderList($("pDx"), s.diagnosis);
  renderList($("pCc"), s.complaints);
  IxList.render($("pIx"), s.investigations);
  renderList($("pFx"), s.findings);
  renderList($("pAdv"), s.advice);
  setText($("pRev"), s.review || "");
  Sections.showDate(s.review_date || "");
  renderRx(s.rx, rowids);
  SheetSecs.render(s);
  clearUndo(); // any new/reloaded sheet invalidates the one-level undo
  sheetEl.classList.remove("empty"); $("sheetBody").inert = false;
  saveBtn.hidden = false;
  printBtn.hidden = false;
  savePdfBtn.hidden = printBtn.hidden;
  refreshMicLabel();
  refreshPrintButton();
  updateGrounding();
}

const stepCounts = () => ({ rows: [...rxBody.querySelectorAll("tr[data-index]")].filter(tr => !RxView.isBlank(tr)).length, needs: openRows().length });
function openRows() {
  return [...rxBody.querySelectorAll("tr[data-index]")].filter(tr =>
    RxView.needsYou(tr));
}

function updateGrounding() {                            // :954 now a sentence plus the summary bar
  if (!state.structured) { groundingEl.hidden = true; RxView.sync(); return; }
  const open = openRows().length;
  groundingEl.hidden = false;
  groundingEl.className = "grounding " + (open ? "warn" : "ok");
  groundingEl.textContent = open
    ? open + (open > 1 ? " medicines need" : " medicine needs") + " you. Resolve each one in the sheet, then Save."
    : "All medicines are ready. You can Save.";
  RxView.sync();
  if (window.Steps) Steps.needs(stepCounts());                                  // keeps the review line in step with the count
}

// ---- inline-edit invalidation (Review Focus #2) ----------------------------
sheetEl.addEventListener("input", (e) => {
  markDirty();
  updateCue();
  const tr = e.target && e.target.closest ? e.target.closest("tr[data-index]") : null;
  if (!tr) return;
  // Any hand-edit of an Rx cell clears verification AND any confirmation, so a
  // hand-edited medicine can never keep a stale ✓.
  state.confirmed.delete(tr.dataset.rowid);
  tr.dataset.status = "";
  RxView.onEdit(tr, e.target);                        // :974 a hand edit drops stale reasons
  renderCheck(tr);
  updateGrounding();
  if (!blockPanel.hidden) refreshBlockPanel();
});

// ---- confirm interactions --------------------------------------------------
rxBody.addEventListener("click", (e) => {
  const btn = e.target && e.target.closest ? e.target.closest('[data-action="confirm"]') : null;
  if (!btn) return;
  if (state.working || (window.Authorship && Authorship.isViewOnly())) return;   // no confirming mid-flight or on a colleague's prescription
  const tr = btn.closest("tr[data-index]");
  if (!tr) return;
  const rowid = tr.dataset.rowid, reopening = state.confirmed.has(rowid);
  if (reopening) state.confirmed.delete(rowid);
  else { state.confirmed.add(rowid); if (RxView.stripMarker(tr)) markDirty(); }   // the doctor accepted the name: the check-row marker leaves the Instructions
  renderCheck(tr);
  updateGrounding();
  if (!blockPanel.hidden) refreshBlockPanel();
  if (!reopening) RxView.afterConfirm(tr);            // the cursor moves on to the next row that needs the doctor (after the re-render)
});

function refreshBlockPanel() {
  const list = $("blockList");
  const remaining = state.lastBlock.filter(b => { const tr = b.rowid != null && rxBody.querySelector('tr[data-rowid="' + b.rowid + '"]');
    return !!tr && RxView.blockStands(tr, b); });       // open rows, and a confirmed row while the generic the server refused still stands
  if (!remaining.length) { blockPanel.hidden = true; return; }
  list.innerHTML = "";
  for (const b of remaining) {
    const li = document.createElement("li");
    const rowTr = rxBody.querySelector('tr[data-rowid="' + b.rowid + '"]');
    const why = rowTr ? RxView.blockReason(rowTr, b) : RxState.rowState({ status: b.status }, {}).reason;
    li.append((b.name ? b.name + " — " : "row " + (b.index + 1) + " — ") + why + " ");
    const btn = document.createElement("button");        // :1010-1020 refreshBlockPanel: jump to the row, no confirming here
    btn.type = "button";
    btn.textContent = "Go to row";
    btn.addEventListener("click", () => {
      const tr = rxBody.querySelector('tr[data-rowid="' + b.rowid + '"]');
      if (tr) { tr.scrollIntoView({ block: "center" }); const s = tr.querySelector(".rx-state"); if (s) s.focus(); }
    });
    li.appendChild(btn);
    list.appendChild(li);
  }
  blockPanel.hidden = false;
}

function hideBlockPanel() { blockPanel.hidden = true; state.lastBlock = []; }

// ---- Save, then Print (two separate actions) ---------------------------------
async function saveDocument() {
  if (state.working || (window.Authorship && Authorship.isViewOnly())) return;
  clearError();
  const { structured, confirmed_rows, indexToRowid, remember_generics, remember_investigations } = serializeForm();
  state.structured = structured;
  updateGrounding();
  if (!hasContent(structured)) { showError("Nothing to save yet — dictate the visit first."); return; }
  // Saving over an existing document with a different patient name is almost
  // certainly "next patient dictated without New patient": ask first.
  if (state.documentId != null && state.savedPatientName) {
    const was = state.savedPatientName.trim(), now = String(structured.patientName || "").trim();
    if (was.toLowerCase() !== now.toLowerCase() &&
        !window.confirm("The patient name changed from “" + was + "” to “" + now +
          "”. Save over this prescription anyway? To record a different patient, cancel and press New patient.")) {
      setStatus("Not saved. Press “New patient” to record a different patient.");
      return;
    }
  }
  const gen = state.editGen; // edits after this point are NOT in the payload
  const wasNew = state.documentId == null;   // a NEW document is today's: the list goes back to today to show it

  setWorking(true, "Saving…");
  try {
    const payload = {
      structured,
      confirmed_rows,
      remember_generics,
      remember_investigations,
      engine: state.engine || "",
      transcript_sha256: state.transcriptSha || "",
    };
    // Opened from "Today" -> update that document in place (design #1).
    if (state.documentId != null) payload.document_id = state.documentId;
    const j = await postJson("/api/v1/documents", payload, SAVE_TIMEOUT_MS);
    clearUndo(); // only a successful save retires the undo (a blocked/failed one keeps it)
    hideBlockPanel();
    const verb = state.documentId != null ? "Updated" : "Saved";
    // A fresh INSERT returns the new document id: remember it so a second Save
    // updates this document in place instead of inserting a duplicate. "New
    // patient" (and a fresh dictation) clears it again.
    if (state.documentId == null) state.documentId = j.document_id;
    if (j.visit_date) state.visitDate = j.visit_date;
    const changedWhileSaving = state.editGen !== gen;
    if (!changedWhileSaving) state.dirty = false; // otherwise keep dirty: the PDF would lack the edit
    state.savedPatientName = String(structured.patientName || "");
    // A server-generated OP number goes on the sheet so the printout and any
    // re-save carry it. A typed value is never overwritten.
    if (j.op_no && !$("pOp").textContent.trim()) {
      setText($("pOp"), j.op_no);
      if (state.structured) state.structured.opNo = j.op_no;
    }
    updateResaveNote();
    refreshMicLabel();
    setWorking(false); // also refreshes Print (now enabled)
    if (wasNew) state.listDay = "";
    loadToday();
    refreshPrintButton();
    setStatus(changedWhileSaving
      ? "Saved — but you changed the sheet while saving; press Save again before printing."
      : verb + " — document " + j.document_id + ". Press Print to print it. Need a change? " +
        "Edit the sheet or dictate a correction, then Save again. Press “New patient” before the next visit.");
  } catch (e) {
    setWorking(false);
    if (e && e.status === 409 && e.data && Array.isArray(e.data.block)) {
      // Translate the server's positional block indices back to the stable row
      // ids at the moment of the save, so confirming a row always names the
      // medicine the doctor actually saw (Finding 1).
      state.lastBlock = e.data.block.map(b => ({ ...b, rowid: indexToRowid[b.index] }));
      refreshBlockPanel();
      const n = state.lastBlock.length, ix = Array.isArray(e.data.investigations_block) ? e.data.investigations_block : [];
      IxList.showBlocked($("pIx"), ix);                // red tests on the sheet: Keep or remove each
      setStatus(n ? "Some medicines still need confirmation before saving." : "Some tests were not heard in the dictation.");
      showError(IxList.blockedMessage(n, ix.length));
    } else {
      showError((e && e.status === 409 && e.data && e.data.hint) || errorMessage(e, "Save failed"));   // e.g. a past prescription
      if (e && e.status === 409 && e.data && e.data.error === "past prescription") {
        if (window.Authorship) Authorship.lockPast(state.visitDate);   // opened before midnight, saved after: view and reprint only
        refreshMicLabel();
      }
    }
  }
}

saveBtn.addEventListener("click", saveDocument);

// ---- Print a saved document (any number of times; never writes to the server) --
function shortReason(e, status) {
  if (status) return "server answered " + status;
  return (e && e.message) ? String(e.message).slice(0, 60) : "network error";
}
const IFRAME_LOAD_WAIT_MS = 3000;
// Resolves "iframe" (print dialog requested), "tab" (opened in a new tab) or
// "blocked" (popup blocked: caller shows a link; blob kept alive 5 minutes).
function printBlob(url) {
  // Hidden off-screen iframe (not display:none, which blocks printing in some
  // browsers). Falls back to a new tab with the browser's PDF viewer.
  return new Promise((resolve) => {
    const f = document.createElement("iframe");
    f.setAttribute("aria-hidden", "true");
    f.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;";
    let done = false, timer = null;
    const cleanup = (ms) => setTimeout(() => { f.remove(); URL.revokeObjectURL(url); }, ms);
    const finish = (how) => {
      if (done) return;
      done = true; clearTimeout(timer);
      if (how === "tab") {
        let w = null;
        try { w = window.open(url, "_blank"); } catch { w = null; }
        if (!w || w.closed) how = "blocked";
        cleanup(300000);
      } else {
        cleanup(60000);
      }
      resolve(how);
    };
    timer = setTimeout(() => finish("tab"), IFRAME_LOAD_WAIT_MS);
    f.addEventListener("load", () => {
      if (done) return;
      try {
        // Ignore the initial about:blank load; a cross-origin PDF viewer may
        // throw here, which means "cannot inspect": go ahead and print.
        if (f.contentWindow.location.href === "about:blank") return;
      } catch { /* cannot inspect */ }
      try { f.contentWindow.focus(); f.contentWindow.print(); finish("iframe"); }
      catch { finish("tab"); }
    });
    f.src = url;
    document.body.appendChild(f);
  });
}
// New patient / Today / mic are frozen while a print is prepared, so the sheet
// the doctor pressed Print on cannot change underneath it.
function setPrinting(on) {
  state.printing = on;
  $("newPatientBtn").disabled = on;
  if (!(mr && mr.state === "recording")) recBtn.disabled = on || state.working;
  todayList.querySelectorAll("button").forEach(b => { b.disabled = on; });
  refreshPrintButton();
}
function showBlockedLink(url) {
  statusEl.textContent = "Your browser blocked the new tab. Open the PDF: ";
  const a = document.createElement("a");
  a.href = url; a.target = "_blank"; a.rel = "noopener";
  a.textContent = "Open prescription PDF";
  statusEl.appendChild(a);
}
async function printDocument() {
  if (state.printing || printBtn.disabled || state.documentId == null) return;
  const id = state.documentId, gen = state.editGen, seq = state.sheetSeq;
  const unchanged = () => state.documentId === id && !state.dirty && state.editGen === gen && state.sheetSeq === seq;
  const CHANGED = "The sheet changed while preparing the print; press Print again.";
  setPrinting(true);
  clearError();
  setStatus("Preparing document " + id + " for printing…");
  let fallbackWhy = "";
  try {
    let r = null;
    try {
      r = await fetch("/api/v1/documents/" + encodeURIComponent(id) + "/pdf", { cache: "no-store" });
    } catch (e) { fallbackWhy = shortReason(e); }
    if (r && !r.ok) fallbackWhy = shortReason(null, r.status);
    if (r && r.ok) {
      const ct = (r.headers.get("Content-Type") || "").toLowerCase();
      if (!ct.includes("application/pdf")) fallbackWhy = "the server did not return a PDF";
      else {
        const blob = await r.blob();
        if (!unchanged()) { setStatus(CHANGED); return; }
        const url = URL.createObjectURL(blob);
        const how = await printBlob(url);
        if (how === "blocked") showBlockedLink(url);
        else setStatus(how === "iframe" ? "Printing document " + id + "…"
          : "Opened document " + id + " in a new tab — press Print there.");
        return;
      }
    }
    if (!unchanged()) { setStatus(CHANGED); return; }
    setStatus("The PDF could not be prepared (" + fallbackWhy + "), so the on-screen sheet was printed instead.");
    window.print();
  } catch (e) {
    if (!unchanged()) { setStatus(CHANGED); return; }
    setStatus("The PDF could not be prepared (" + shortReason(e) + "), so the on-screen sheet was printed instead.");
    window.print();
  } finally {
    setPrinting(false);
  }
}
printBtn.addEventListener("click", printDocument);
async function savePdf() {
  if (state.printing || savePdfBtn.disabled || state.documentId == null) return;
  const id = state.documentId, gen = state.editGen, seq = state.sheetSeq;
  const unchanged = () => state.documentId === id && !state.dirty && state.editGen === gen && state.sheetSeq === seq;
  setPrinting(true);
  clearError();
  try {
    const blob = await SavePdf.fetchPdf(id);
    if (!unchanged()) { setStatus("The sheet changed while preparing the PDF; press Save PDF again."); return; }
    const how = await SavePdf.save(blob, SavePdf.fileName({ name: text($("pName")), day: state.visitDate || (window.Dates ? Dates.todayIso() : ""), op: text($("pOp")) }));
    if (how !== "cancelled") setStatus(how === "picked" ? "Saved PDF." : "Downloaded PDF.");
  } catch (e) { setStatus("The PDF could not be saved (" + shortReason(e) + ")."); }
  finally { setPrinting(false); }
}
savePdfBtn.addEventListener("click", savePdf);
$("retryBtn").addEventListener("click", retryLast);

// ---- New patient -----------------------------------------------------------
function newPatient() {
  if (state.printing) return; // a print is being prepared for the current sheet
  if (isUnsaved() && !window.confirm("Start a new patient? The current draft stays unsaved.")) return;
  // Only past the confirm may state change: a cancel must be a perfect no-op.
  DictGuard.clear();
  resetSheet();
}

// The sheet reset shared by New patient and the name check's "Start new patient" (which keeps the Undo snapshot).
function resetSheet() {
  state.sheetSeq++;
  Cues.clearFlags();
  SheetSecs.render({});
  state.savedPatientName = null;
  clearUndo();
  state.structured = null;
  state.transcript = "";
  state.transcriptSha = "";
  state.engine = "";
  state.dirty = false;
  state.documentId = null;
  state.visitDate = "";
  state.retry = null;
  state.confirmed.clear();
  state.lastBlock = [];
  hideBlockPanel();
  clearError();
  renderTranscript();
  updateResaveNote();
  backToToday();
  if (window.Authorship) Authorship.clear();
  sheetEl.classList.add("empty"); $("sheetBody").inert = true;
  saveBtn.hidden = true;
  printBtn.hidden = true;
  savePdfBtn.hidden = printBtn.hidden;
  refreshPrintButton();
  setText($("pName"), "");
  setText($("pAge"), "");
  setText($("pOp"), "");
  Vitals.render({});
  setText($("pDate"), today());
  ["pDx", "pCc", "pIx", "pFx", "pAdv"].forEach(id => { $(id).innerHTML = ""; });
  rxBody.innerHTML = "";
  setText($("pRev"), "");
  Sections.showDate(""); Sections.showProseCheck([]);
  groundingEl.hidden = true;
  RxView.sync();                                      // :1251 newPatient hides the bar
  highlightToday();
  refreshMicLabel();
  setStep("idle");
  setStatus("Ready — press the mic and dictate the visit.");
}

// The list shows today again (New patient): reloaded only when it showed an earlier day.
function backToToday() {
  if (!state.listDay) return;
  state.listDay = "";
  loadToday();
}

$("newPatientBtn").addEventListener("click", newPatient);

// ---- settings panel wiring -------------------------------------------------
$("profileOpenBtn").addEventListener("click", openProfilePanel);
$("profileCancelBtn").addEventListener("click", closeProfilePanel);
$("profileForm").addEventListener("submit", saveProfile);

// ---- init ------------------------------------------------------------------
if (window.Share) Share.init({ documentId: () => state.documentId });
Sections.init({ post: postJson });
SheetSecs.init({ get: (u) => fetch(u).then(safeJson), renderList }); Cues.init({ list: () => SheetSecs.list() }); SheetSecs.load().then(() => SheetSecs.render(state.structured ? readForm() : {})).catch(() => {}).finally(() => Cues.show());
IxList.init({ post: postJson, working: () => state.working, onChange: () => { markDirty(); updateCue(); },
  onRemove: (item, pos) => setUndo({ type: "ix", item, pos }, "Deleted test.") });
RxView.init({
  body: rxBody, saveBtn, confirmed: () => state.confirmed, working: () => state.working,
  transcript: () => state.transcript, ageSex: () => text($("pAge")), post: postJson, snapshot: snapshotRow, pushUndo: setUndo, notify: setStatus,
  changed: () => { markDirty(); updateGrounding(); if (!blockPanel.hidden) refreshBlockPanel(); }, hasSheet: () => !sheetEl.classList.contains("empty"),
});
DictGuard.init({
  state: () => state, serialize: serializeForm, render: renderSheet, rows: () => rxBody.querySelectorAll("tr[data-rowid]"), renderCheck, notify: setStatus,
  working: () => state.working || !!(mr && mr.state === "recording"),
  restored: () => { Cues.clearFlags(); markDirty(); hideBlockPanel(); updateResaveNote(); Sections.showProseCheck([]); updateGrounding(); refreshMicLabel(); },
});
SpellModal.init({ dialog: $("spellDlg"), working: () => state.working, recording: () => !!(mr && mr.state === "recording"),
  viewOnly: () => !!(window.Authorship && Authorship.isViewOnly()), transcribe: transcribeName, media: () => navigator.mediaDevices, Recorder: () => window.MediaRecorder });
setText($("pDate"), today());
refreshMicLabel();
setStep("idle");
setStatus("Ready — press the mic and dictate the visit.");
if (window.DayNav) DayNav.init({ day: () => state.listDay, go: (d) => { state.listDay = d; loadToday(); } });
loadProfile();
loadToday();
