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
  let pastDay = null;       // the ISO visit day while an earlier day's prescription is on the sheet (view and reprint only)
  const locked = () => viewOnly !== null || pastDay !== null;
  let ownHeader = false;    // an opened prescription's own doctor lines are on the sheet header
  let scope = "mine";       // the Today list: "mine" | "clinic"

  // Several doctors are written 'A; B' / 'quals A; quals B' / 'reg A; reg B' (the backend's doctors_text.py): doctor i
  // takes part i of each field. The doctors sit side by side in a two-column table (the pad's layout), each cell two
  // lines: the name then the qualifications, and 'Reg. No: x'. Text wraps in its cell and is never cut.
  const parts = (v) => (typeof v === "string" && v.trim() ? v.split(";").map((t) => t.trim()) : []);   // empty parts kept: index pairing
  function renderDoctorLines(box, name, quals, reg) {
    if (!box) return;
    const cols = [parts(name), parts(quals), parts(reg)];
    const idx = [];                                  // a doctor is skipped only when all three of its parts are empty
    for (let i = 0; i < Math.max(cols[0].length, cols[1].length, cols[2].length); i++) {
      if (cols[0][i] || cols[1][i] || cols[2][i]) idx.push(i);
    }
    const count = idx.length;
    box.textContent = "";
    if (box.previousElementSibling && box.previousElementSibling.classList.contains("clinic-rule")) {
      box.previousElementSibling.hidden = !count;
    }
    if (!count) return;
    const table = document.createElement("table");
    table.className = "clinic-doctors";
    let row = null;
    for (let n = 0; n < count; n++) {
      const i = idx[n];
      if (n % 2 === 0) { row = document.createElement("tr"); table.appendChild(row); }
      const cell = document.createElement("td");
      if (cols[0][i] || cols[1][i]) {
        const first = document.createElement("div");
        if (cols[0][i]) {
          const n = document.createElement("span");
          n.className = "clinic-doctor";
          n.textContent = cols[0][i];
          first.appendChild(n);
        }
        if (cols[1][i]) {
          const q = document.createElement("span");
          q.className = "clinic-qual";
          q.textContent = (cols[0][i] ? ", " : "") + cols[1][i];
          first.appendChild(q);
        }
        cell.appendChild(first);
      }
      if (cols[2][i]) {
        const r = document.createElement("div");
        r.className = "clinic-reg";
        r.textContent = "Reg. No: " + cols[2][i];
        cell.appendChild(r);
      }
      row.appendChild(cell);
      if (n === count - 1 && n % 2 === 0) row.appendChild(document.createElement("td"));   // an odd last row keeps two cells
    }
    box.appendChild(table);
  }

  // The sheet header shows the doctor who prints on this prescription: its author.
  function showAuthor(a) {
    renderDoctorLines(el("cDoctor"), a.doctor_name || a.name, a.qualifications, a.reg_no);
  }

  // Re-applied from app.js refreshPrintButton(), which runs after every setWorking/setPrinting: those
  // re-enable the mic and Save, so view-only must win again each time.
  function enforce() {
    const banner = el("viewOnlyBanner");
    if (banner) {
      banner.hidden = !locked();
      banner.textContent = viewOnly ? viewOnly + "'s prescription: view only"      // a colleague's past one: the colleague banner
        : pastDay !== null ? "Prescription from " + ((window.Dates && Dates.date(pastDay)) || pastDay) + ": view and reprint only" : "";
    }
    if (!locked()) return;
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
    const ready = el("grounding");                  // "…You can Save." cannot apply to a sheet that cannot be saved
    if (ready) ready.hidden = true;
  }

  // Leave view-only (New patient, or opening a prescription you may edit). Outside view-only nothing on the
  // sheet was locked, so single-database mode leaves every button exactly as app.js has it.
  function clear() {
    const was = locked();
    viewOnly = null;
    pastDay = null;
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
    if (doc && doc.past) { pastDay = String(doc.visit_date || ""); enforce(); }   // the server refuses a past re-save; locked in both modes
    const a = doc && doc.author;
    if (!a) return;                                   // single-database mode: no author data
    showAuthor(a);
    ownHeader = true;                                 // a later Profile save must not swap these for the viewer's
    if (doc.can_edit === false) viewOnly = a.name || "Another doctor";
    enforce();
  }

  function isViewOnly() { return locked(); }
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

  // A sheet opened on its own day and saved after midnight: the server refused the re-save (409 "past prescription").
  function lockPast(day) { pastDay = String(day || ""); enforce(); }

  return { renderDoctorLines, onOpen, clear, enforce, lockPast, isViewOnly, viewOnlyAuthor, keepsOwnHeader, todayQuery, authorLabel };
})();
