"""Spell it (I1-e3), behaviour: frontend/rxview.js runs under node on a tiny fake DOM (tree, selectors, click and key events, a post the
test controls). Covers the race and guard rules the text checks in test_frontend_rxspell.py cannot."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"

_DOM = r"""
class El {
  constructor(tag) { this.tagName = String(tag).toUpperCase(); this.children = []; this.parentNode = null; this.dataset = {}; this.attrs = {}; this.className = ""; this._t = ""; this.hidden = false; this.disabled = false; this.handlers = {}; this.id = ""; this.value = ""; }
  get classList() { const c = this; return { contains: (n) => c.className.split(/\s+/).includes(n) }; }
  get textContent() { return this._t + this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this.children.forEach((c) => { c.parentNode = null; }); this.children = []; this._t = String(v); }
  get lastChild() { return this.children[this.children.length - 1] || null; }
  get nextSibling() { const p = this.parentNode; return p ? p.children[p.children.indexOf(this) + 1] || null : null; }
  get isConnected() { let n = this; while (n.parentNode) n = n.parentNode; return n === ROOT_EL; }
  appendChild(c) { if (c.parentNode) c.remove(); c.parentNode = this; this.children.push(c); return c; }
  append(...k) { k.forEach((c) => this.appendChild(c)); }
  remove() { const p = this.parentNode; if (p) { p.children.splice(p.children.indexOf(this), 1); this.parentNode = null; } }
  after(n) { const p = this.parentNode; if (n.parentNode) n.remove(); n.parentNode = p; p.children.splice(p.children.indexOf(this) + 1, 0, n); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(t, f) { (this.handlers[t] = this.handlers[t] || []).push(f); }
  focus() { document.activeElement = this; }
  blur() { if (document.activeElement === this) { document.activeElement = null; this.dispatch("blur"); } }
  dispatch(type, init) {                          // the event reaches this element, then bubbles up until stopPropagation
    let stop = false; const e = Object.assign({ type, target: this, defaultPrevented: false, preventDefault() { e.defaultPrevented = true; }, stopPropagation() { stop = true; } }, init || {});
    for (let n = this; n && !stop; n = n.parentNode) (n.handlers[type] || []).forEach((f) => f(e));
    return e;
  }
  matches(sel) {
    return sel.split(",").some((part) => {
      const m = /^([a-z]*)((?:\.[\w-]+|\[[\w-]+(?:="[^"]*")?\])*)$/.exec(part.trim());
      if (!m) throw new Error("selector " + part);
      if (m[1] && m[1].toUpperCase() !== this.tagName) return false;
      const re = /\.([\w-]+)|\[([\w-]+)(?:="([^"]*)")?\]/g; let x;
      while ((x = re.exec(m[2]))) {
        if (x[1]) { if (!this.classList.contains(x[1])) return false; continue; }
        const v = x[2].startsWith("data-") ? this.dataset[x[2].slice(5)] : this.attrs[x[2]];
        if (v === undefined || (x[3] !== undefined && v !== x[3])) return false;
      }
      return true;
    });
  }
  closest(sel) { for (let n = this; n; n = n.parentNode) if (n.matches && n.matches(sel)) return n; return null; }
  querySelectorAll(sel) { const out = []; const walk = (n) => n.children.forEach((c) => { if (c.matches(sel)) out.push(c); walk(c); }); walk(this); return out; }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}
const ROOT_EL = new El("html");
const ids = {}; ["rxBar", "rxTitle", "rxReady", "rxNeeds"].forEach((id) => { ids[id] = new El("div"); ROOT_EL.appendChild(ids[id]); });
globalThis.ResizeObserver = class { constructor(f) { this.f = f; } observe() {} };
globalThis.document = { getElementById: (id) => ids[id], createElement: (t) => new El(t), createElementNS: (ns, t) => new El(t), activeElement: null,
  querySelector: () => ({ offsetHeight: 10 }), documentElement: { style: { setProperty() {} } } };
globalThis.addEventListener = () => {};
const tbody = new El("tbody"); ROOT_EL.appendChild(tbody);
const COLS = ["form", "name", "strength", "dose", "timing", "duration", "instructions"];
const confirmed = new Set(), undos = [], posts = [], notes = [], flags = { working: false, transcript: "heard prednisone", ageSex: "46 / F" };
const tick = () => new Promise((r) => setTimeout(r, 0));
const click = (el) => tbody.handlers.click.forEach((f) => f({ target: el }));
const cell = (tr, c) => tr.querySelector('[data-col="' + c + '"]');
const spellBtn = (tr) => tr.querySelector('[data-action="spell"]');
function mkRow(id, status, cols, meta) {
  const tr = new El("tr"); tr.dataset.index = id; tr.dataset.rowid = id; tr.dataset.status = status;
  const med = new El("td"); med.className = "med"; const chk = new El("td"); chk.className = "check"; tr.append(med, chk);
  COLS.forEach((c) => { const td = new El("td"); td.dataset.col = c; td.textContent = (cols || {})[c] || ""; tr.appendChild(td); });
  tbody.appendChild(tr); RxView.attach(tr, Object.assign({ status }, meta || {})); RxView.renderRow(tr); return tr;
}
RxView.init({ body: tbody, saveBtn: { textContent: "", disabled: false }, confirmed: () => confirmed, working: () => flags.working, changed() {}, hasSheet: () => true,
  transcript: () => flags.transcript, ageSex: () => flags.ageSex,
  post: (url, body, ms, signal) => new Promise((res, rej) => { posts.push({ url, body, res, rej, signal }); }), notify: (m) => notes.push(m),
  snapshot: (tr) => { const rec = { status: tr.dataset.status || "", lexicon_match: tr.dataset.lexicon || "" }; COLS.forEach((c) => { rec[c] = cell(tr, c).textContent; }); return Object.assign(rec, RxView.meta(tr)); },
  pushUndo: (rec, msg) => undos.push({ rec, msg }) });
const dlg = new El("dialog"); dlg.open = false; dlg.showModal = function () { if (this.open) throw new Error("InvalidStateError"); this.open = true; }; dlg.close = function () { this.open = false; };
ROOT_EL.appendChild(dlg); ids.spellDlg = dlg;
[["spellTitle", "h2"], ["spellHint", "p"], ["spellInput", "input"], ["spellMic", "button"], ["spellMsg", "p"], ["spellInfo", "p"], ["spellList", "div"],
 ["spellPrev", "button"], ["spellPage", "p"], ["spellNext", "button"], ["spellClose", "button"], ["spellUse", "button"]]
  .forEach(([id, tag]) => { const n = new El(tag); n.id = id; n.value = ""; ids[id] = n; dlg.appendChild(n); });
const dkey = (k, target, shift) => (dlg.handlers.keydown || []).forEach((f) => f({ target: target || document.activeElement, key: k, shiftKey: !!shift, preventDefault() {} }));
const dclick = (el) => (dlg.handlers.click || []).forEach((f) => f({ target: el }));
const dtype = (text) => { ids.spellInput.value = text; (dlg.handlers.input || []).forEach((f) => f({ target: ids.spellInput })); };
const sleep = (ms) => new Promise((x) => setTimeout(x, ms));
const said = () => ids.spellMsg.textContent + ids.spellInfo.textContent;
flags.recording = false; flags.mic = "ok"; flags.audio = ["a1"]; const voice = [], gum = [];
class FakeRec { constructor() { this.state = "inactive"; this.mimeType = "audio/webm"; FakeRec.last = this; }
  start() { if (flags.startThrows) throw new Error("start failed"); this.state = "recording"; } stop() { this.state = "inactive"; flags.audio.forEach((d) => this.ondataavailable({ data: d })); this.onstop(); } }
const stream = { stopped: 0, getTracks: () => [{ stop() { stream.stopped++; } }] };
SpellModal.init({ dialog: dlg, working: () => flags.working, recording: () => flags.recording,
  viewOnly: () => !!(globalThis.Authorship && Authorship.isViewOnly()), voiceMs: 0, searchMs: 25,
  media: () => ({ getUserMedia: () => { gum.push(1); return flags.mic === "ok" ? Promise.resolve(stream) : Promise.reject({ name: flags.mic }); } }),
  Recorder: () => (flags.noRecorder ? undefined : FakeRec), transcribe: (blob) => new Promise((res, rej) => voice.push({ blob, res, rej })) });
const reply = async (row, sugs, opts, total) => { posts.shift().res({ row, suggestions: sugs || [], options: opts || (sugs || []).map((n) => ({ name: n, generic: "", reason: "sounds" })), total }); await tick(); };
const openPanel = async (tr) => { click(spellBtn(tr)); await reply({}, ["Allopurinol"]); };
const useTyped = async (text) => { ids.spellInput.value = text; dclick(ids.spellUse); await tick(); };
const panels = () => (dlg.open ? 1 : 0);
"""


def _run(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    full = ("globalThis.window = globalThis; require(process.argv[1]); require(process.argv[2]); require(process.argv[3]); require(process.argv[4]); require(process.argv[5]);" + _DOM
            + "(async () => {" + body + "})().catch((e) => { console.error(e.stack); process.exit(1); });")
    out = subprocess.run([node, "-e", full, str(FRONT / "rxstate.js"), str(FRONT / "suglist.js"), str(FRONT / "rxview.js"), str(FRONT / "genericedit.js"), str(FRONT / "spellmodal.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_undo_while_a_second_check_is_pending_drops_the_late_answer():
    r = _run("""
      const tr = mkRow("1", "unknown-medicine", { name: "Zyloprim", dose: "1-0-0" });
      await openPanel(tr); await useTyped("Allopurinol");
      await reply({ name: "Allopurinol", status: "unknown-medicine", instructions: "[unverified: confirm with doctor]", generic: "" });
      const first = undos.length;                                   // R1 pushed; the row still needs a name decision, so Spell it is still there
      await openPanel(tr); await useTyped("Prednisolone");          // R2 is now pending
      const pending = posts.length, checking = tr._rx.checking;
      RxView.restore(undos[0].rec);                                 // the Undo button
      posts.shift().res({ row: { name: "Prednisolone", status: "verified", instructions: "late", lexicon_match: "Prednisolone", generic: "late-generic" }, suggestions: [] });
      await tick();
      console.log(JSON.stringify({ first, pending, checking, name: cell(tr, "name").textContent, instr: cell(tr, "instructions").textContent, status: tr.dataset.status,
        lex: tr.dataset.lexicon || "", conf: confirmed.has("1"), generic: RxView.meta(tr).generic, undos: undos.length, spinner: !!tr.querySelector(".rx-checking"), panels: panels() }));""")
    assert r == {"first": 1, "pending": 1, "checking": True, "name": "Zyloprim", "instr": "", "status": "unknown-medicine", "lex": "", "conf": False,
                 "generic": "", "undos": 1, "spinner": False, "panels": 0}


def test_a_late_failure_after_undo_does_not_touch_the_restored_row():
    r = _run("""
      const tr = mkRow("1", "unknown-medicine", { name: "Zyloprim" });
      await openPanel(tr); await useTyped("Allopurinol");
      await reply({ name: "Allopurinol", status: "unknown-medicine", instructions: "" });
      await openPanel(tr); await useTyped("Prednisolone");
      RxView.restore(undos[0].rec);
      const err = new Error("boom"); err.status = 500; posts.shift().rej(err); await tick();
      console.log(JSON.stringify({ note: tr._rx.note, name: cell(tr, "name").textContent, spinner: !!tr.querySelector(".rx-checking") }));""")
    assert r == {"note": "", "name": "Zyloprim", "spinner": False}


def test_confirming_a_row_from_outside_closes_its_spell_panel():
    r = _run("""
      const tr = mkRow("2", "lookalike-check", { name: "Prednisone" });
      await openPanel(tr);
      const open = [panels(), spellBtn(tr).attrs["aria-expanded"]];
      RxView.renderRow(tr);                                          // an unrelated re-render keeps the panel
      const still = panels();
      confirmed.add("2"); RxView.renderRow(tr);                      // the Confirm button
      console.log(JSON.stringify({ open, still, after: panels(), spell: !!spellBtn(tr), held: SpellModal.isOpenFor("2") }));""")
    assert r == {"open": [1, "true"], "still": 1, "after": 0, "spell": False, "held": False}


def test_buttons_are_disabled_for_view_only_and_for_a_checking_row_and_dose_check_chips_do_not_confirm():
    r = _run("""
      const dis = (tr, a) => tr.querySelectorAll('[data-action="' + a + '"]').map((b) => b.disabled);
      const s = mkRow("3", "unverified-strength", { name: "Amlodipine", strength: "15 mg" }, { strength_options: ["5 mg", "10 mg"] });
      globalThis.Authorship = { isViewOnly: () => true }; RxView.renderRow(s);
      const viewOnly = [dis(s, "chip"), dis(s, "confirm")];
      globalThis.Authorship = undefined; RxView.renderRow(s);
      const open = [dis(s, "chip"), dis(s, "confirm")];
      s._rx.checking = true; RxView.renderRow(s);
      const checking = [dis(s, "chip"), dis(s, "confirm"), !!s.querySelector(".rx-checking")];
      s._rx.checking = false; RxView.renderRow(s);
      const n = mkRow("4", "unknown-medicine", { name: "Zyloprim" });
      globalThis.Authorship = { isViewOnly: () => true }; RxView.renderRow(n);
      const spell = dis(n, "spell"); click(spellBtn(n)); const noPanel = [panels(), posts.length];
      globalThis.Authorship = undefined;
      const ok = mkRow("5", "unverified-strength", { name: "Amlodipine", strength: "15 mg" }, { strength_options: ["5 mg", "10 mg"] });
      click(ok.querySelector('[data-action="chip"]'));
      const okTap = [cell(ok, "strength").textContent, confirmed.has("5"), RxView.meta(ok).how];
      const d = mkRow("6", "dose-check", { name: "Metformin", strength: "500 mg" }, { dose_note: "3000 mg a day", strength_options: ["500 mg", "850 mg"] });
      const before = RxView.meta(d).dose_note;
      click(d.querySelectorAll('[data-action="chip"]')[1]);
      console.log(JSON.stringify({ viewOnly, open, checking, spell, noPanel, okTap, before, dose: [cell(d, "strength").textContent, confirmed.has("6"), RxView.meta(d).how, RxView.meta(d).dose_note] }));""")
    assert r["viewOnly"] == [[True, True], [True]] and r["open"] == [[False, False], [False]]
    assert r["checking"] == [[True, True], [], True]                       # a checking row shows the spinner instead of Confirm
    assert r["spell"] == [True] and r["noPanel"] == [0, 0]
    assert r["okTap"][1:] == [True, "chip"] and r["okTap"][0] in ("5 mg", "10 mg")
    assert r["before"] == "3000 mg a day" and r["dose"] == ["850 mg", False, "chip-open", ""]


def test_use_this_confirms_a_name_answer_without_touching_dose_timing_or_duration():
    r = _run("""
      const tr = mkRow("7", "lookalike-check", { form: "Tab.", name: "Prednisone", strength: "5 mg", dose: "1-1-1", timing: "After food", duration: "5 days", instructions: "mine" });
      await openPanel(tr); await useTyped("p r e d n i s o l o n e");
      const sent = posts[0].body;
      await reply({ form: "Cap.", name: "Prednisolone", strength: "10 mg", dose: "1-0-0", timing: "", duration: "1 week", instructions: "mine [x]", status: "verified",
                    lexicon_match: "Prednisolone", generic: "", heard: "prednisone", lookalike: "Prednisone" });
      console.log(JSON.stringify({ sent, cols: COLS.map((c) => cell(tr, c).textContent), conf: confirmed.has("7"), how: tr._rx.how, reason: RxView.reasonFor(tr),
        shown: [tr.querySelector(".rx-reason").textContent, tr.dataset.rxstate],
        undo: undos[0].msg, back: undos[0].rec.data.name, panels: panels(), meta: [RxView.meta(tr).heard, RxView.meta(tr).lookalike] }));""")
    assert r["sent"]["row"]["name"] == "prednisolone" and r["sent"]["row"]["dose"] == "1-1-1"
    assert r["sent"]["transcript"] == "heard prednisone" and r["sent"]["age_sex"] == "46 / F"
    assert r["cols"] == ["Tab.", "Prednisolone", "5 mg", "1-1-1", "After food", "5 days", "mine [x]"]
    assert r["conf"] is True and r["how"] == "spell" and r["reason"] == "You chose this name."
    assert r["shown"] == ["You chose this name.", "you"]                    # what the row shows, so the confirm landed before the render
    assert r["undo"] == "Changed Prednisone to Prednisolone." and r["back"] == "Prednisone" and r["panels"] == 0 and r["meta"] == ["prednisone", "Prednisone"]


def test_answers_that_do_not_settle_the_name_leave_the_row_open():
    r = _run("""
      const out = [];
      for (const st of ["unknown-medicine", "dose-check", "unverified-strength"]) {
        const tr = mkRow("a" + st, "lookalike-check", { name: "Prednisone" });
        await openPanel(tr); await useTyped("Zyloprim"); await reply({ name: "Zyloprim", status: st, dose_note: "high" });
        out.push([st, confirmed.has("a" + st), tr._rx.note, tr.dataset.status]);
      }
      console.log(JSON.stringify(out));""")
    assert r == [[s, False, 'Name changed to "Zyloprim". It still needs your decision.', s] for s in ("unknown-medicine", "dose-check", "unverified-strength")]


def test_spell_is_refused_while_working_or_view_only_and_oversize_input_never_reaches_the_server():
    r = _run("""
      const tr = mkRow("8", "lookalike-check", { name: "Prednisone" });
      flags.working = true; click(spellBtn(tr)); const working = [panels(), posts.length]; flags.working = false;
      await openPanel(tr);
      globalThis.Authorship = { isViewOnly: () => true };
      const input = ids.spellInput; input.value = "Prednisolone";
      dkey("Enter", input); await tick(); const viewOnly = [posts.length, tr._rx.checking];
      globalThis.Authorship = undefined; flags.working = true;
      dkey("Enter", input); await tick(); const busyEnter = [posts.length, tr._rx.checking]; flags.working = false;
      const big = mkRow("9", "lookalike-check", { name: "x".repeat(70) });
      click(spellBtn(big)); const bigMsg = [posts.length, ids.spellMsg.textContent];
      flags.transcript = "t".repeat(20001); flags.ageSex = "a".repeat(41);
      const ok = mkRow("10", "lookalike-check", { name: "Prednisone" });
      click(spellBtn(ok)); const sent = posts[posts.length - 1].body;
      console.log(JSON.stringify({ working, viewOnly, busyEnter, bigMsg, sent: [sent.transcript, sent.age_sex, sent.row.name] }));""")
    assert r["working"] == [0, 0] and r["viewOnly"] == [0, False] and r["busyEnter"] == [0, False]
    assert r["bigMsg"] == [0, "That is too long for a medicine name (60 characters at most). You can still type the name."]
    assert r["sent"] == ["", "", "Prednisone"]


def test_a_hand_edit_during_a_pending_check_drops_the_answer_and_the_panel():
    r = _run("""
      const tr = mkRow("11", "lookalike-check", { name: "Prednisone" });
      await openPanel(tr); await useTyped("Prednisolone");
      const during = [tr._rx.checking, panels(), !!tr.querySelector(".rx-checking")];
      RxView.onEdit(tr, cell(tr, "dose")); RxView.renderRow(tr);
      await reply({ name: "Prednisolone", status: "verified" });
      console.log(JSON.stringify({ during, name: cell(tr, "name").textContent, checking: tr._rx.checking, panels: panels(), conf: confirmed.has("11"), undos: undos.length }));""")
    assert r == {"during": [True, 1, True], "name": "Prednisone", "checking": False, "panels": 0, "conf": False, "undos": 0}


def test_a_late_answer_for_a_deleted_row_never_confirms_it_even_after_undo():
    r = _run("""
      const out = {};
      const tr = mkRow("13", "lookalike-check", { name: "Prednisone" });
      await openPanel(tr); await useTyped("Prednisolone");
      tr.remove(); RxView.sync();                                               // the delete button (the page syncs after it)
      await reply({ name: "Prednisolone", status: "verified" });
      out.deleted = [confirmed.has("13"), undos.length, cell(tr, "name").textContent];
      const a = mkRow("14", "lookalike-check", { name: "Prednisone" });
      await openPanel(a); await useTyped("Prednisolone");
      a.remove(); RxView.sync(); const back = mkRow("14", "lookalike-check", { name: "Prednisone" });   // delete, then Undo: same id, new row
      await reply({ name: "Prednisolone", status: "verified" });
      out.undone = [confirmed.has("14"), undos.length, cell(back, "name").textContent, back.dataset.status, back._rx.checking];
      console.log(JSON.stringify(out));""")
    assert r == {"deleted": [False, 0, "Prednisone"], "undone": [False, 0, "Prednisone", "lookalike-check", False]}


def test_undo_of_a_spell_keeps_a_dose_edited_after_use_this():
    r = _run("""
      const tr = mkRow("15", "lookalike-check", { name: "Prednisone", dose: "1-1-1", timing: "After food", duration: "5 days", instructions: "mine" }, { heard: "prednisone", generic: "old-generic" });
      await openPanel(tr); await useTyped("Prednisolone");
      await reply({ name: "Prednisolone", instructions: "mine [x]", status: "verified", lexicon_match: "Prednisolone", generic: "new-generic", heard: "" });
      cell(tr, "dose").textContent = "2-0-0"; cell(tr, "timing").textContent = "Before food"; cell(tr, "duration").textContent = "9 days";   // hand edits
      confirmed.delete("15"); tr.dataset.status = ""; RxView.onEdit(tr, cell(tr, "dose")); RxView.renderRow(tr);
      RxView.restore(undos[0].rec);
      console.log(JSON.stringify({ cols: COLS.map((c) => cell(tr, c).textContent), status: tr.dataset.status, conf: confirmed.has("15"),
        meta: [RxView.meta(tr).heard, RxView.meta(tr).generic] }));""")
    assert r["cols"] == ["", "Prednisone", "", "2-0-0", "Before food", "9 days", "mine"]
    assert r["status"] == "lookalike-check" and r["conf"] is False and r["meta"] == ["prednisone", "old-generic"]


def test_a_chip_tap_on_a_view_only_row_changes_nothing():
    r = _run("""
      const s = mkRow("16", "unverified-strength", { name: "Amlodipine", strength: "15 mg" }, { strength_options: ["5 mg", "10 mg"] });
      globalThis.Authorship = { isViewOnly: () => true };
      click(s.querySelector('[data-action="chip"]'));
      console.log(JSON.stringify([cell(s, "strength").textContent, confirmed.has("16"), RxView.meta(s).how]));""")
    assert r == ["15 mg", False, ""]
