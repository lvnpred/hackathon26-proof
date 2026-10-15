"use strict";
// Authorship in the browser (spec 7.1, 7.2). A colleague's prescription opens read-only (banner, mic and
// Save off, sheet not editable, Print on), and the Today list switches between "My prescriptions" and
// "Whole clinic". Loaded after auth.js and BEFORE app.js: app.js calls in only at run time, always through
// `window.Authorship`. The server enforces every rule (403); this file only reflects it. Single-database
// mode sends no author data, so nothing here changes the page there.
window.Authorship = (function () {
  const el = (id) => document.getElementById(id);
  const busy = () => typeof state !== "undefined" && !!state.working;   // app.js's state
  let viewOnly = null;      // the author's name while a colleague's prescription is on the sheet
  let ownHeader = false;    // an opened prescription's own doctor lines are on the sheet header
  let scope = "mine";       // the Today list: "mine" | "clinic"

  // The sheet header shows the doctor who prints on this prescription: its author.
  function showAuthor(a) {
    const dr = el("cDoctor"), reg = el("cReg");
    if (dr) dr.textContent = [a.doctor_name || a.name, a.qualifications].filter(Boolean).join(" ");
    if (reg) reg.textContent = a.reg_no ? "Reg. No: " + a.reg_no : "";
  }

  // Re-applied from app.js refreshPrintButton(), which runs after every setWorking/setPrinting: those
  // re-enable the mic and Save, so view-only must win again each time.
  function enforce() {
    const banner = el("viewOnlyBanner");
    if (banner) {
      banner.hidden = !viewOnly;
      banner.textContent = viewOnly ? viewOnly + "'s prescription: view only" : "";
    }
    if (!viewOnly) return;
    ["recBtn", "saveBtn", "confirmAllBtn"].forEach((id) => { const b = el(id); if (b) b.disabled = true; });
    const sheet = el("sheet");
    if (sheet) {
      sheet.classList.add("view-only");
      sheet.querySelectorAll('[contenteditable="true"]').forEach((n) => { n.contentEditable = "false"; n.dataset.ro = "1"; });
      sheet.querySelectorAll(".x-btn, .confirm-btn").forEach((b) => { b.disabled = true; });
    }
    const note = el("resaveNote");
    if (note) note.hidden = true;
    const cue = el("correctingCue");
    if (cue) cue.hidden = true;
  }

  // Leave view-only (New patient, or opening a prescription you may edit). Outside view-only nothing on the
  // sheet was locked, so single-database mode leaves every button exactly as app.js has it.
  function clear() {
    const was = viewOnly;
    viewOnly = null;
    ownHeader = false;
    if (was) {
      const sheet = el("sheet");
      if (sheet) {
        sheet.classList.remove("view-only");
        sheet.querySelectorAll('[data-ro="1"]').forEach((n) => { n.contentEditable = "true"; delete n.dataset.ro; });
        sheet.querySelectorAll(".x-btn").forEach((b) => { b.disabled = busy(); });
        sheet.querySelectorAll(".confirm-btn").forEach((b) => { b.disabled = false; });   // setWorking never manages these
      }
      ["recBtn", "saveBtn"].forEach((id) => { const b = el(id); if (b) b.disabled = busy(); });
      const all = el("confirmAllBtn");
      if (all) all.disabled = false;
    }
    if (typeof renderProfileHeader === "function" && typeof state !== "undefined") renderProfileHeader(state.profile || {});
    enforce();
  }

  // app.js openDocument() hands over the GET /api/v1/documents/{id} body once the sheet is rendered.
  function onOpen(doc) {
    clear();
    const a = doc && doc.author;
    if (!a) return;                                   // single-database mode: no author data
    showAuthor(a);
    ownHeader = true;                                 // a later Profile save must not swap these for the viewer's
    if (doc.can_edit === false) viewOnly = a.name || "Another doctor";
    enforce();
  }

  function isViewOnly() { return viewOnly !== null; }
  function viewOnlyAuthor() { return viewOnly || ""; }
  function keepsOwnHeader() { return ownHeader; }
  function todayQuery() { return "?scope=" + scope; }
  // Whole clinic rows name their author; "My prescriptions" rows are all yours, so they do not.
  function authorLabel(row) { return scope === "clinic" && row && row.doctor_name ? row.doctor_name : ""; }

  function setScope(next) {
    scope = next === "clinic" ? "clinic" : "mine";
    document.querySelectorAll("#todayScope [data-scope]").forEach((b) => {
      b.setAttribute("aria-pressed", String(b.dataset.scope === scope));
    });
    if (typeof loadToday === "function") loadToday();
  }

  async function init() {
    const box = el("todayScope");
    if (!box) return;
    box.addEventListener("click", (e) => {
      const b = e.target && e.target.closest ? e.target.closest("[data-scope]") : null;
      if (b) setScope(b.dataset.scope);
    });
    let signedIn = false;
    try { signedIn = (await fetch("/api/v1/auth/me")).status === 200; } catch (e) { signedIn = false; }
    box.hidden = !signedIn;                           // single-database mode (404): no toggle
  }
  init();

  return { onOpen, clear, enforce, isViewOnly, viewOnlyAuthor, keepsOwnHeader, todayQuery, authorLabel };
})();
