// M2 page side: the "Adding to" banner, the forced-choice name check and the one-level Undo last dictation (a swap: Undo again returns).
// Text goes in with textContent only. app.js owns the flow; this module owns the pieces.
(function () {
const $ = (id) => document.getElementById(id);
const THIS = "this prescription";
let hooks = null;
let kept = null;

function bannerText(i) {
  return "Adding to: " + (i.name || THIS) + (i.op ? " · " + i.op : "") + (i.saved ? " (saved)" : " (not saved yet)");
}
function banner(info) {
  const el = $("addingBanner");
  if (!el) return;
  el.hidden = !info;
  el.textContent = info ? bannerText(info) : "";
}
function promptText(other, sheetName) {
  const sheet = sheetName || THIS;
  return { line: "This sounds like " + (other.name || other.op_no) + ", not " + sheet + ".", fresh: "Start new patient (Enter)", apply: "Apply to " + sheet };
}
let pending = null, bound = false;   // one prompt at a time; handlers are bound once and settle the pending promise
function settle(v) {
  if (!pending) return;
  const p = pending; pending = null;
  $("nameCheck").hidden = true;
  p.resolve(v);
}
function bindPrompt() {
  if (bound) return;
  bound = true;
  // Escape does nothing: a forced choice. Enter on the focused Apply button is that button's own click; Enter elsewhere means start new.
  $("nameCheck").addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    if (e.target && e.target.id === "nameCheckApply") return settle("apply");
    if (e.preventDefault) e.preventDefault();
    settle("new");
  });
  $("nameCheckNew").addEventListener("click", () => settle("new"));
  $("nameCheckApply").addEventListener("click", () => settle("apply"));
}
function ask(other, sheetName) {
  if (pending) return pending.promise;                  // an overlapping ask shares the open prompt
  bindPrompt();
  const t = promptText(other, sheetName);
  $("nameCheckText").textContent = t.line;
  $("nameCheckNew").textContent = t.fresh;
  $("nameCheckApply").textContent = t.apply;
  $("nameCheck").hidden = false;
  if (hooks) hooks.notify("Choose: start a new patient, or apply to " + (sheetName || THIS) + ".");
  pending = {};
  pending.promise = new Promise((resolve) => { pending.resolve = resolve; });
  $("nameCheckNew").focus();
  return pending.promise;
}
function keepIdentity(structured, current) {
  const out = JSON.parse(JSON.stringify(structured));
  ["patientName", "ageSex", "opNo"].forEach((k) => { out[k] = (current || {})[k]; });
  return out;
}
function keptNote(structured, current) {          // "Apply" kept the sheet's patient: say so only when the dictation named another
  const cur = current || {};
  const differs = ["patientName", "ageSex", "opNo"].some((k) => (structured || {})[k] && (structured || {})[k] !== cur[k]);
  return differs ? "Kept " + (cur.patientName || THIS) + "'s details. Say \"change the name to …\" to rename." : "";
}

function capture() {
  const s = hooks.state();
  if (!s.structured) return null;
  const ser = hooks.serialize();
  const how = {};
  [...hooks.rows()].forEach((tr) => { if (tr._rx && tr._rx.how) how[tr.dataset.rowid] = tr._rx.how; });
  return {
    structured: JSON.parse(JSON.stringify(ser.structured)), rowids: [...ser.indexToRowid], confirmed: [...s.confirmed], how,
    documentId: s.documentId, visitDate: s.visitDate, savedPatientName: s.savedPatientName,
    transcript: s.transcript, transcriptSha: s.transcriptSha, engine: s.engine,
  };
}
function setUndoVisible(on) { const el = $("undoDict"); if (el) el.hidden = !on; }
function keep(snap) { kept = snap; setUndoVisible(!!snap); }
function canUndo() { return !!kept; }
function clear() { kept = null; setUndoVisible(false); }

function undo() {
  if (!kept || hooks.working()) return;
  const s = hooks.state(), k = kept, now = capture();   // the newer sheet becomes the snapshot, so Undo again brings it back
  s.confirmed.clear();                                  // the confirmed set first, as undoDelete does, so "you chose" survives the render
  k.confirmed.forEach((id) => s.confirmed.add(id));
  s.documentId = k.documentId; s.visitDate = k.visitDate; s.savedPatientName = k.savedPatientName;
  s.transcript = k.transcript; s.transcriptSha = k.transcriptSha; s.engine = k.engine;
  s.structured = JSON.parse(JSON.stringify(k.structured));
  hooks.render(JSON.parse(JSON.stringify(k.structured)), k.rowids);
  [...hooks.rows()].forEach((tr) => {
    const how = k.how[tr.dataset.rowid];
    if (how) { tr._rx = tr._rx || {}; tr._rx.how = how; hooks.renderCheck(tr); }
  });
  s.dirty = true;                                       // never posts: the stored document changes only on the next Save
  hooks.restored();
  hooks.notify("Back to the sheet before your last dictation. Undo again to return. Save to keep it.");
  keep(now);
}

function init(h) {
  hooks = h;
  const b = $("undoDictBtn");
  if (b) b.addEventListener("click", undo);
}

window.DictGuard = { bannerText, banner, promptText, ask, keepIdentity, keptNote, init, capture, keep, canUndo, clear, undo };
})();
