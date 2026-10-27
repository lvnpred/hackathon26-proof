"""Confirm moves to the next flagged row (owner request 2026-10-20): RxView.afterConfirm / focusFirst under node on a tiny fake DOM;
the app.js hooks are checked as text."""
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
globalThis.ResizeObserver = class { observe() {} };
globalThis.document = { getElementById: (id) => ids[id], createElement: (t) => new El(t), createElementNS: (ns, t) => new El(t), activeElement: null,
  querySelector: () => ({ offsetHeight: 10 }), documentElement: { style: { setProperty() {} } } };
globalThis.addEventListener = () => {};
globalThis.SpellModal = { isOpenFor: () => false, closeFor() {}, sweep() {} };
const tbody = new El("tbody"); ROOT_EL.appendChild(tbody);
const COLS = ["form", "name", "strength", "dose", "timing", "duration", "instructions"];
const confirmed = new Set(), save = new El("button");
function mkRow(id, status, name, meta) {
  const tr = new El("tr"); tr.dataset.index = id; tr.dataset.rowid = id; tr.dataset.status = status;
  const med = new El("td"); med.className = "med"; const chk = new El("td"); chk.className = "check"; tr.append(med, chk);
  COLS.forEach((c) => { const td = new El("td"); td.dataset.col = c; td.textContent = c === "name" ? name : ""; tr.appendChild(td); });
  tbody.appendChild(tr); RxView.attach(tr, Object.assign({ status }, meta || {})); RxView.renderRow(tr); return tr;
}
RxView.init({ body: tbody, saveBtn: save, confirmed: () => confirmed, working: () => false, changed() {}, hasSheet: () => true });
const ok = (tr) => { confirmed.add(tr.dataset.rowid); RxView.renderRow(tr); RxView.sync(); };
const at = () => { const a = document.activeElement; return a ? (a === save ? "save" : a.closest("tr").dataset.rowid + ":" + (a.dataset.action || "state")) : null; };
const rows3 = () => [mkRow("1", "unknown-medicine", "Zyloprim"), mkRow("2", "verified", "Crocin"), mkRow("3", "unknown-medicine", "Zerodol")];
const out = (v) => console.log(JSON.stringify(v));
"""


def _run(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    full = "globalThis.window = globalThis; require(process.argv[1]); require(process.argv[2]);" + _DOM + "(() => {" + body + "})();"
    out = subprocess.run([node, "-e", full, str(FRONT / "rxstate.js"), str(FRONT / "rxview.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_1_confirm_jumps_to_the_next_flagged_row_confirm_button_and_wraps():
    r = _run("""
      const [a] = rows3(); const seen = [];
      ok(a); RxView.afterConfirm(a); seen.push(at());          // below: row 3 (row 2 is fine and skipped)
      const d = mkRow("4", "unknown-medicine", "Other"); RxView.sync();
      ok(d); RxView.afterConfirm(d); seen.push(at());          // nothing below row 4: wraps up to row 3
      out(seen);""")
    assert r == ["3:confirm", "3:confirm"]


def test_2_a_row_with_no_confirm_button_gets_its_first_action_button():
    r = _run("""
      const a = mkRow("1", "unknown-medicine", "Zyloprim"), b = mkRow("2", "unknown-medicine", "Zerodol");
      b._rx.meta = Object.assign({}, b._rx.meta, { generic_pending: false });
      const spellOnly = b.querySelector('[data-action="confirm"]'); spellOnly.parentNode.children.splice(spellOnly.parentNode.children.indexOf(spellOnly), 1);   // no Confirm button on this row
      ok(a); RxView.afterConfirm(a); out(at());""")
    assert r == "2:spell"


def test_3_no_open_row_moves_focus_to_save():
    assert _run("const [a, b, c] = rows3(); ok(a); ok(c); RxView.afterConfirm(c); out(at());") == "save"


def test_4_a_new_sheet_focuses_the_first_flagged_row_and_steals_nothing_when_clean():
    r = _run("""
      const [a, b, c] = rows3(); RxView.focusFirst(); const first = at();
      document.activeElement = null; ok(a); ok(c); RxView.focusFirst(); out([first, at()]);""")
    assert r == ["1:confirm", None]


def test_4b_a_late_sheet_never_steals_focus_from_the_name_field_or_the_sheet():
    r = _run("""
      const sheet = new El("div"); ids.sheet = sheet; ROOT_EL.appendChild(sheet);
      const name = new El("input"); sheet.appendChild(name); const note = new El("span"); note.dataset.x = "1"; sheet.appendChild(note);
      rows3(); name.focus(); RxView.focusFirst(); const a = document.activeElement === name;
      note.focus(); RxView.focusFirst(); const b = document.activeElement === note;
      document.activeElement = null; RxView.focusFirst(); out([a, b, at()]);""")
    assert r == [True, True, "1:confirm"]


def test_5_nothing_else_moves_focus_renders_hand_edits_and_reopen_keep_the_old_rule():
    r = _run("""
      const [a, b, c] = rows3(); ok(a); document.activeElement = null;
      RxView.renderRow(a); RxView.renderRow(c); RxView.sync(); const plain = at();
      a.querySelector('[data-action="confirm"]').focus(); confirmed.delete("1"); RxView.renderRow(a);   // Reopen: the rebuilt button keeps focus (rxview.js rule)
      out([plain, at()]);""")
    assert r == [None, "1:confirm"]


def test_6_view_only_never_moves_focus():
    r = _run("""
      window.Authorship = { isViewOnly: () => true };
      const [a] = rows3(); ok(a); RxView.afterConfirm(a); const x = at(); RxView.focusFirst(); out([x, at()]);""")
    assert r == [None, None]


def test_7_no_open_row_but_a_red_test_focuses_its_keep_not_save():
    """Final review M3: a test the doctor never said blocks Save, so confirm-next goes to its Keep first."""
    r = _run("""
      const ul = new El("ul"); ul.id = "pIx"; ids.pIx = ul; ROOT_EL.appendChild(ul);
      const test = (status, source) => { const li = new El("li"); li.className = "ix-item"; li.dataset.status = status; li.dataset.source = source;
        const k = new El("button"); k.className = "ix-keep ix-act no-print"; k.hidden = status !== "not-dictated"; li.appendChild(k); ul.appendChild(li); return k; };
      test("verified", "dictated"); test("not-dictated", "doctor"); const red = test("not-dictated", "dictated");
      const [a, b, c] = rows3(); ok(a); ok(c); RxView.afterConfirm(c); const first = document.activeElement === red;
      ul.children[2].dataset.status = "verified"; red.hidden = true; ul.children[2].dataset.source = "doctor";   // kept
      document.activeElement = null; RxView.afterConfirm(c); out([first, at()]);""")
    assert r == [True, "save"]


def test_app_js_hooks_fire_only_after_a_confirm_and_when_a_sheet_appears():
    app, html = (FRONT / "app.js").read_text(encoding="utf-8"), (FRONT / "index.html").read_text(encoding="utf-8")
    assert "reopening = state.confirmed.has(rowid)" in app and "if (!reopening) RxView.afterConfirm(tr);" in app
    assert app.count("RxView.focusFirst();") == 3          # /api/format, opening a saved document, and a spoken correction
    corr = app.split("async function applyCorrection")[1].split("} catch")[0]
    assert "RxView.focusFirst();" in corr and corr.index("renderSheet(") < corr.index("RxView.focusFirst();")
    assert app.index("Authorship.onOpen(j);") < app.index("RxView.focusFirst();")     # view-only is known before the first focus
    assert "rxview.js?v=18" in html and "app.js?v=55" in html


def test_a_reopened_document_restores_the_saved_confirmations_and_the_waiting_row_is_marked():
    app, css = (FRONT / "app.js").read_text(encoding="utf-8"), (FRONT / "rx.css").read_text(encoding="utf-8")
    opened = app.split("state.confirmed.clear();")[1].split("Authorship.onOpen(j)")[0]   # openDocument: clear, then restore
    assert "renderSheet(state.structured, savedConfirmations(state.structured));" in opened
    fn = "function savedConfirmations(s)" + app.split("function savedConfirmations(s)")[1].split("\n}\n")[0] + "\n}\n"
    r = _run("let rowSeq = 0; const state = { confirmed: new Set() };\n" + fn +
             "const ids = savedConfirmations({ rx: [{ name: 'A', doctor_confirmed: true }, { name: 'B' }, { name: 'C', doctor_confirmed: 'yes' }] });"
             "out([ids, [...state.confirmed]]);")
    assert r == [["1", "2", "3"], ["1"]]                                   # only a true flag counts
    assert 'tr[data-rxstate]:has(.rx-act:focus)' in css and 'content:"Press Enter' in css
