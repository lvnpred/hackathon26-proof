"""Investigation items on the sheet (plan PQ-h, task 9): frontend/ixlist.js runs under node on a tiny fake DOM (tree, class
selectors, events, a post the test controls). Covers the chips, read-back, edit-to-lookup, Keep, Remember, delete/undo, the
409 marking and the index rule (blanks dropped exactly as the server's coerce_items drops them)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from doctor_dictation.core import investigations

FRONT = Path(__file__).resolve().parents[1] / "frontend"

_DOM = r"""
class El {
  constructor(tag) { this.tagName = String(tag).toUpperCase(); this.children = []; this.parentNode = null; this.dataset = {}; this.attrs = {}; this.className = "";
    this._t = ""; this.hidden = false; this.disabled = false; this.handlers = {}; this.value = ""; this.checked = false; }
  get classList() { const c = this, list = () => c.className.split(/\s+/).filter(Boolean);
    return { contains: (n) => list().includes(n), add: (n) => { if (!list().includes(n)) c.className = list().concat(n).join(" "); },
      remove: (n) => { c.className = list().filter((x) => x !== n).join(" "); } }; }
  get textContent() { return this._t + this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this.children.forEach((c) => { c.parentNode = null; }); this.children = []; this._t = String(v); }
  get nextSibling() { const p = this.parentNode; return p ? p.children[p.children.indexOf(this) + 1] || null : null; }
  get isConnected() { let n = this; while (n.parentNode) n = n.parentNode; return n === ROOT_EL; }
  appendChild(c) { if (c.parentNode) c.remove(); c.parentNode = this; this.children.push(c); return c; }
  append(...k) { k.forEach((c) => this.appendChild(c)); }
  insertBefore(c, ref) { if (c.parentNode) c.remove(); c.parentNode = this; const i = ref ? this.children.indexOf(ref) : -1; if (i < 0) this.children.push(c); else this.children.splice(i, 0, c); return c; }
  remove() { const p = this.parentNode; if (p) { p.children.splice(p.children.indexOf(this), 1); this.parentNode = null; } }
  after(n) { const p = this.parentNode; if (n.parentNode) n.remove(); n.parentNode = p; p.children.splice(p.children.indexOf(this) + 1, 0, n); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(t, f) { (this.handlers[t] = this.handlers[t] || []).push(f); }
  focus() { document.activeElement = this; }
  blur() { if (document.activeElement === this) document.activeElement = null; }
  dispatch(type, init) {
    let stop = false; const e = Object.assign({ type, target: this, defaultPrevented: false, preventDefault() { e.defaultPrevented = true; }, stopPropagation() { stop = true; } }, init || {});
    for (let n = this; n && !stop; n = n.parentNode) (n.handlers[type] || []).forEach((f) => f(e));
    return e;
  }
  matches(sel) {
    const m = /^([a-z]*)((?:\.[\w-]+)*)$/.exec(sel.trim());
    if (!m) throw new Error("selector " + sel);
    if (m[1] && m[1].toUpperCase() !== this.tagName) return false;
    return m[2].split(".").filter(Boolean).every((c) => this.classList.contains(c));
  }
  closest(sel) { for (let n = this; n; n = n.parentNode) if (n.matches && n.matches(sel)) return n; return null; }
  querySelectorAll(sel) { const out = []; const walk = (n) => n.children.forEach((c) => { if (c.matches(sel)) out.push(c); walk(c); }); walk(this); return out; }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}
const ROOT_EL = new El("html");
globalThis.document = { createElement: (t) => new El(t), activeElement: null };
const sheet = new El("div"); ROOT_EL.appendChild(sheet);
const ul = new El("ul"); ul.className = "ix-list"; sheet.appendChild(ul);
const posts = [], changes = [], removed = [], flags = { viewOnly: false, working: false };
globalThis.Authorship = { isViewOnly: () => flags.viewOnly };
IxList.init({ post: (url, body, ms) => new Promise((res, rej) => posts.push({ url, body, ms, res, rej })),
  onChange: () => changes.push(1), onRemove: (item, pos) => removed.push({ item, pos }), working: () => flags.working });
IxList.DEBOUNCE_MS = 5;
const tick = () => new Promise((r) => setTimeout(r, 0));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const items = () => ul.querySelectorAll("li.ix-item");
const q = (li, sel) => li.querySelector(sel);
const chips = () => items().map((li) => (q(li, ".ix-chip").hidden ? "" : q(li, ".ix-chip").textContent));
const type = (li, text) => { const s = q(li, ".ix-text"); s.textContent = text; s.dispatch("input"); };
const click = (b) => b.dispatch("click");
const tickBox = (li, on) => { const cb = q(li, ".ix-remember-cb"); cb.checked = on; cb.dispatch("change"); };
const fullName = (li, v) => { const i = q(li, ".ix-fullname-input"); i.value = v; i.dispatch("input"); };
const out = (o) => console.log(JSON.stringify(o));
"""

VERIFIED = {"text": "RFT", "canonical": "Renal Function Test", "status": "verified", "source": "dictated"}
NEW = {"text": "Uroflow at home", "canonical": "", "status": "new", "source": "dictated"}
RED = {"text": "MRI brain", "canonical": "MRI Brain", "status": "not-dictated", "source": "dictated"}
LEGACY = {"text": "CBC", "canonical": "", "status": "", "source": "dictated"}

# One table of print_text cases: IxList.printText and investigations.print_text must give the same line for each.
PRINT_CASES = [
    {"text": "RFT", "canonical": "Renal Function Test"},
    {"text": "renal function test", "canonical": "Renal Function Test"},
    {"text": "Uroflow at home", "canonical": ""},
    "CBC", "  CBC  ", None, 5, [],
    {"text": "  RFT ", "canonical": "  Renal Function Test  "},
    {"text": "Vit. D Level", "canonical": "Vit D level"},
    {"text": "LFT & RFT", "canonical": "LFT and RFT"},
    {"text": "USG-KUB", "canonical": "USG KUB"},
    {"text": "usg_kub", "canonical": "USG KUB"},
    {"text": "", "canonical": "Renal Function Test"},
    {"text": "RFT", "canonical": None},
    {"text": None, "canonical": "X"},
    {"text": "STRASSE test", "canonical": "straße test"},
    {"text": "Hb A1c", "canonical": "HbA1c"},
    {"text": "TSH", "canonical": "Thyroid Stimulating Hormone"},
]


def _run(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    full = "globalThis.window = globalThis; require(process.argv[1]);" + _DOM + \
        "(async () => {" + body + "})().catch((e) => { console.error(e.stack); process.exit(1); });"
    res = subprocess.run([node, "-e", full, str(FRONT / "ixlist.js")], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _js(v):
    return json.dumps(v)


def test_items_render_with_a_status_chip_and_read_back_unchanged():
    r = _run(f"""
      IxList.render(ul, [{_js(VERIFIED)}, {_js(NEW)}, {_js(RED)}, "CBC", "   ", {{"text": ""}}, null, 7]);
      out({{ chips: chips(), read: IxList.read(ul), status: items().map((li) => li.dataset.status), full: items().map((li) => q(li, ".ix-full").textContent),
        keep: items().map((li) => !q(li, ".ix-keep").hidden), add: ul.nextSibling.textContent, addCls: ul.nextSibling.className }});""")
    assert r["chips"] == ["In list", "New test", "Not dictated", ""]
    assert r["read"] == [VERIFIED, NEW, RED, LEGACY]
    assert r["status"] == ["verified", "new", "not-dictated", ""]
    assert r["full"] == [" (Renal Function Test)", "", "", ""]                # "MRI brain" and "MRI Brain" are one name
    assert r["keep"] == [False, False, True, False]                  # Keep on the red item only
    assert r["add"] == "+ Add test" and "no-print" in r["addCls"]


def test_a_legacy_saved_document_re_saves_unchanged_in_meaning():
    r = _run("""
      IxList.render(ul, ["CBC", "  Lipid   profile ", "RFT"]); const first = IxList.read(ul);
      IxList.render(ul, first); out({ first, second: IxList.read(ul), remember: IxList.rememberIndexes(ul) });""")
    want = [{"text": t, "canonical": "", "status": "", "source": "dictated"} for t in ("CBC", "Lipid profile", "RFT")]
    assert r["first"] == want and r["second"] == want and r["remember"] == []
    assert investigations.coerce_items(["CBC", "  Lipid   profile ", "RFT"]) == want     # what the server makes of the same list


def test_print_text_matches_the_server():
    r = _run(f"out({_js(PRINT_CASES)}.map((c) => IxList.printText(c)));")
    assert r == [investigations.print_text(c) for c in PRINT_CASES]


def test_key_matches_the_server():
    names = ["Vit. D Level", "LFT & RFT", "usg_kub", "  Hb-A1c ", "straße", "ÉCHO cardio", "T3/T4", ""]
    r = _run(f"out({_js(names)}.map((n) => IxList.key(n)));")
    assert r == [investigations.key(n) for n in names]


def test_editing_the_text_makes_it_the_doctors_and_asks_the_server():
    r = _run(f"""
      IxList.render(ul, [{_js(RED)}, {_js(NEW)}]);
      const li = items()[0];
      type(li, "R"); type(li, "RF"); type(li, "RFT");                 // three keystrokes inside the debounce: one question
      const before = {{ source: li.dataset.source, posts: posts.length, chip: chips()[0] }};
      await sleep(20);
      const first = posts.map((p) => [p.url, p.body]);
      type(li, "LFT"); await sleep(20);                               // a second question while the first is still out
      posts[1].res({{ canonical: "Liver Function Test", status: "verified" }}); await tick();
      posts[0].res({{ canonical: "Renal Function Test", status: "verified" }}); await tick();   // the stale answer is dropped
      out({{ before, first, posts: posts.length, read: IxList.read(ul)[0], chip: chips()[0], full: q(li, ".ix-full").textContent, changed: changes.length > 0 }});""")
    assert r["before"] == {"source": "doctor", "posts": 0, "chip": ""}
    assert r["first"] == [["/api/v1/investigations/lookup", {"text": "RFT"}]]
    assert r["posts"] == 2
    assert r["read"] == {"text": "LFT", "canonical": "Liver Function Test", "status": "verified", "source": "doctor"}
    assert r["chip"] == "In list" and r["full"] == " (Liver Function Test)" and r["changed"]


def test_a_failed_lookup_leaves_a_new_test_and_a_removed_item_takes_no_answer():
    r = _run(f"""
      IxList.render(ul, [{_js(NEW)}, {_js(LEGACY)}]);
      const [a, b] = items();
      type(a, "Uroflow"); await sleep(20); posts[0].rej(new Error("boom")); await tick();
      type(b, "ECG"); await sleep(20); IxList.remove(b); posts[1].res({{ canonical: "ECG", status: "verified" }}); await tick();
      out({{ a: IxList.read(ul)[0], left: items().length }});""")
    assert r == {"a": {"text": "Uroflow", "canonical": "", "status": "new", "source": "doctor"}, "left": 1}


def test_keep_clears_red_and_remember_reveals_full_name():
    r = _run(f"""
      IxList.render(ul, [{_js(VERIFIED)}, {_js({"text": "Uroflow", "canonical": "", "status": "not-dictated", "source": "dictated"})}, {_js(RED)}]);
      const [v, red, red2] = items();
      const rememberBefore = !q(red, ".ix-remember").hidden;
      click(q(red, ".ix-keep")); click(q(red2, ".ix-keep"));
      const after = {{ chips: chips(), src: [red.dataset.source, red2.dataset.source], keep: !q(red, ".ix-keep").hidden, verifiedHasRemember: !q(v, ".ix-remember").hidden }};
      const shown = !q(red, ".ix-remember").hidden, boxBefore = !q(red, ".ix-fullname").hidden;
      tickBox(red, true);
      const boxAfter = !q(red, ".ix-fullname").hidden;
      fullName(red, "  Uroflowmetry   study ");
      const ticked = {{ read: IxList.read(ul)[1], remember: IxList.rememberIndexes(ul), full: q(red, ".ix-full").textContent }};
      tickBox(red, false);
      out({{ rememberBefore, after, shown, boxBefore, boxAfter, ticked, unticked: {{ read: IxList.read(ul)[1], remember: IxList.rememberIndexes(ul), box: !q(red, ".ix-fullname").hidden }} }});""")
    assert r["rememberBefore"] is False
    assert r["after"] == {"chips": ["In list", "New test", "In list"], "src": ["doctor", "doctor"], "keep": False, "verifiedHasRemember": False}
    assert r["shown"] is True and r["boxBefore"] is False and r["boxAfter"] is True
    assert r["ticked"] == {"read": {"text": "Uroflow", "canonical": "Uroflowmetry study", "status": "new", "source": "doctor"},
                           "remember": [1], "full": " (Uroflowmetry study)"}
    assert r["unticked"] == {"read": {"text": "Uroflow", "canonical": "", "status": "new", "source": "doctor"}, "remember": [], "box": False}


def test_remember_indexes_skip_blank_items_like_the_server():
    r = _run(f"""
      IxList.render(ul, [{_js(NEW)}, {_js({**NEW, "text": "Sputum AFB"})}]);
      click(ul.nextSibling);                                          // "+ Add test": an empty doctor item, focused
      const added = items()[2], focused = document.activeElement === q(added, ".ix-text");
      const [a, b] = items();
      q(a, ".ix-text").textContent = "  \\u00a0 ";                    // emptied by hand: dropped from the save
      tickBox(b, true);
      out({{ focused, read: IxList.read(ul), remember: IxList.rememberIndexes(ul), count: items().length }});""")
    assert r["focused"] is True and r["count"] == 3
    assert r["read"] == [{**NEW, "text": "Sputum AFB"}]
    assert r["remember"] == [0]                                        # index into read(), not into the page's items
    assert investigations.coerce_items([{**NEW, "text": "    "}, {**NEW, "text": "Sputum AFB"}, {"text": ""}]) == r["read"]


def test_text_is_never_markup():
    r = _run("""
      IxList.render(ul, [{ text: "<img src=x onerror=alert(1)>", canonical: "<b>x</b>", status: "new", source: "dictated" }]);
      const li = items()[0], all = []; const walk = (n) => n.children.forEach((c) => { all.push(c.tagName); walk(c); }); walk(li);
      out({ text: q(li, ".ix-text").textContent, full: q(li, ".ix-full").textContent, tags: [...new Set(all)].sort() });""")
    assert r["text"] == "<img src=x onerror=alert(1)>" and r["full"] == " (<b>x</b>)"
    assert "IMG" not in r["tags"] and "B" not in r["tags"]
    js = (FRONT / "ixlist.js").read_text(encoding="utf-8")
    assert js.count("innerHTML") == 1 and len(re.findall(r"^\s*x\.innerHTML = X_ICON;\s*$", js, re.M)) == 1
    assert "insertAdjacentHTML" not in js and "outerHTML" not in js
    icon_decl = re.search(r"^\s*const X_ICON = (.*);$", js, re.M).group(1)
    assert re.fullmatch(r"'[^']*'", icon_decl) and "${" not in icon_decl and "+" not in icon_decl and "`" not in icon_decl


def test_the_text_takes_plain_text_only():
    r = _run(f"""
      IxList.render(ul, [{_js(NEW)}]);
      const s = q(items()[0], ".ix-text");
      const enter = s.dispatch("keydown", {{ key: "Enter" }}); s.focus();
      const para = s.dispatch("beforeinput", {{ inputType: "insertParagraph" }}), bold = s.dispatch("beforeinput", {{ inputType: "formatBold" }});
      const drop = s.dispatch("drop");
      out({{ editable: s.contentEditable, enter: enter.defaultPrevented, para: para.defaultPrevented, bold: bold.defaultPrevented, drop: drop.defaultPrevented,
        paste: !!(s.handlers.paste || []).length }});""")
    assert r == {"editable": "true", "enter": True, "para": True, "bold": True, "drop": True, "paste": True}


def test_delete_and_undo_put_the_test_back_with_its_state():
    r = _run(f"""
      IxList.render(ul, [{_js(VERIFIED)}, {_js(NEW)}, {_js(RED)}]);
      tickBox(items()[1], true); fullName(items()[1], "Uroflowmetry");
      const rec = IxList.remove(items()[1]);
      const mid = IxList.read(ul).map((i) => i.text);
      const li = IxList.insert(ul, removed[0].item, removed[0].pos);
      out({{ pos: rec.pos, hookPos: removed[0].pos, mid, read: IxList.read(ul), remember: IxList.rememberIndexes(ul), at: items().indexOf(li), x: q(li, ".x-btn").dataset.action }});""")
    assert r["pos"] == 1 and r["hookPos"] == 1 and r["mid"] == ["RFT", "MRI brain"]
    assert r["read"] == [VERIFIED, {**NEW, "canonical": "Uroflowmetry", "source": "doctor"}, RED]
    assert r["remember"] == [1] and r["at"] == 1 and r["x"] == "delete-ix"


def test_clicking_x_reaches_the_sheet_router_and_deletes_the_test():
    # app.js routes every x by a click listener on #sheet (data-action "delete-ix" -> IxList.remove): the x's own
    # click must bubble up to it.
    r = _run(f"""
      IxList.render(ul, [{_js(VERIFIED)}, {_js(NEW)}]);
      sheet.addEventListener("click", (e) => {{
        const b = e.target.closest(".x-btn");
        if (b && b.dataset.action === "delete-ix") IxList.remove(b.closest("li"));
      }});
      click(q(items()[0], ".x-btn"));
      out({{ read: IxList.read(ul).map((i) => i.text), hook: removed.length }});""")
    assert r == {"read": ["Uroflow at home"], "hook": 1}


def test_show_blocked_marks_the_named_items():
    r = _run(f"""
      IxList.render(ul, [{_js(VERIFIED)}, {_js(NEW)}, {_js({**RED, "status": ""})}, {_js(LEGACY)}]);
      const n = IxList.showBlocked(ul, [{{ index: 2, text: "MRI brain" }}]);
      const marked = items().map((li) => li.classList.contains("ix-blocked"));
      out({{ n, marked, chips: chips(), focus: document.activeElement === q(items()[2], ".ix-keep") }});""")
    assert r == {"n": 1, "marked": [False, False, True, False], "chips": ["In list", "New test", "Not dictated", ""], "focus": True}


def test_show_blocked_counts_indexes_after_blank_items_and_checks_the_text():
    r = _run(f"""
      IxList.render(ul, [{_js(VERIFIED)}, {_js(RED)}, {_js({**RED, "text": "CT chest"})}]);
      q(items()[0], ".ix-text").textContent = "   ";                  // a blank item before the red ones: the server never saw it
      const n = IxList.showBlocked(ul, [{{ index: 0, text: "MRI brain" }}, {{ index: 5, text: "CT chest" }}, {{ index: 0, text: "Not on the sheet" }}]);
      out({{ n, marked: items().map((li) => li.classList.contains("ix-blocked")) }});""")
    assert r == {"n": 2, "marked": [False, True, True]}


def test_view_only_locks_the_text_and_every_control_refuses():
    r = _run(f"""
      flags.viewOnly = true;
      IxList.render(ul, [{_js(RED)}, {_js(NEW)}]);
      const [li, nw] = items(), n0 = posts.length, c0 = changes.length;
      click(q(li, ".ix-keep")); tickBox(nw, true); fullName(nw, "Uroflowmetry"); click(ul.nextSibling); type(li, "CT"); await sleep(20);
      out({{ ro: [q(li, ".ix-text").contentEditable, q(li, ".ix-text").dataset.ro], x: q(li, ".x-btn").disabled, count: items().length,
        posts: posts.length - n0, changes: changes.length - c0, remember: IxList.rememberIndexes(ul), chips: chips(),
        read: IxList.read(ul).map((i) => [i.canonical, i.status, i.source]) }});""")
    assert r["ro"] == ["false", "1"] and r["x"] is True and r["count"] == 2           # what Authorship.enforce does; clear() undoes it
    assert r["posts"] == 0 and r["changes"] == 0 and r["remember"] == []
    assert r["chips"] == ["Not dictated", "New test"]
    assert r["read"] == [["MRI Brain", "not-dictated", "dictated"], ["", "new", "dictated"]]
    css = re.sub(r"/\*.*?\*/", "", (FRONT / "ixlist.css").read_text(encoding="utf-8"), flags=re.S)
    rule = next(ln for ln in css.splitlines() if ln.startswith("#sheet.view-only"))
    for sel in (".ix-act", ".ix-add", ".ix-keep", ".ix-remember", ".ix-fullname", "ul.ix-list .x-btn"):
        assert "#sheet.view-only " + sel in rule
    assert "display:none" in rule


def test_a_colleagues_prescription_then_your_own_is_fully_editable():
    # openDocument renders (app.js) before Authorship.onOpen clears view-only: the own document is drawn while it is set.
    r = _run(f"""
      flags.viewOnly = true; IxList.render(ul, [{_js(RED)}]);
      IxList.render(ul, [{_js(RED)}, {_js(NEW)}]);
      flags.viewOnly = false;                                         // Authorship.clear(): data-ro spans and x buttons unlock
      sheet.querySelectorAll("span").forEach((n) => {{ if (n.dataset.ro === "1") {{ n.contentEditable = "true"; delete n.dataset.ro; }} }});
      sheet.querySelectorAll("button").forEach((b) => {{ if (b.classList.contains("x-btn")) b.disabled = false; }});
      const [li, nw] = items();
      const shape = {{ editable: q(li, ".ix-text").contentEditable, keep: !q(li, ".ix-keep").hidden, x: !q(li, ".x-btn").disabled,
        remember: !q(nw, ".ix-remember").hidden, add: !ul.nextSibling.hidden && !ul.nextSibling.disabled }};
      click(q(li, ".ix-keep")); tickBox(nw, true);
      click(ul.nextSibling);
      out({{ shape, chips: chips(), remember: IxList.rememberIndexes(ul), count: items().length }});""")
    assert r["shape"] == {"editable": "true", "keep": True, "x": True, "remember": True, "add": True}
    assert r["chips"] == ["In list", "New test", ""] and r["remember"] == [1] and r["count"] == 3


def test_add_test_stops_at_the_servers_list_limit():
    r = _run(f"""
      IxList.render(ul, Array.from({{ length: 11 }}, (_, i) => "Test " + i));
      const add = ul.nextSibling, at11 = [add.disabled, add.getAttribute("title") || ""];
      click(add); const at12 = [add.disabled, add.getAttribute("title") || "", items().length];
      click(add); const still = items().length;
      IxList.remove(items()[0]); const after = [add.disabled, add.getAttribute("title") || ""];
      IxList.insert(ul, removed[0].item, removed[0].pos); const back = add.disabled;
      IxList.render(ul, Array.from({{ length: 14 }}, (_, i) => "T" + i));
      out({{ at11, at12, still, after, back, rendered: add.disabled }});""")
    assert r["at11"] == [False, ""] and r["at12"] == [True, "At most 12 tests", 12] and r["still"] == 12
    assert r["after"] == [False, ""] and r["back"] is True and r["rendered"] is True


def test_untick_after_undo_restores_the_canonical_and_source():
    r = _run(f"""
      IxList.render(ul, [{_js(NEW)}]);
      const li = items()[0]; tickBox(li, true); fullName(li, "Uroflowmetry");
      IxList.remove(li); const back = IxList.insert(ul, removed[0].item, removed[0].pos);
      const ticked = IxList.read(ul)[0]; tickBox(back, false);
      out({{ ticked, unticked: IxList.read(ul)[0], remember: IxList.rememberIndexes(ul) }});""")
    assert r["ticked"] == {**NEW, "canonical": "Uroflowmetry", "source": "doctor"}
    assert r["unticked"] == NEW and r["remember"] == []


def test_blocked_message_words_medicines_tests_or_both():
    r = _run("out([IxList.blockedMessage(0, 1), IxList.blockedMessage(0, 2), IxList.blockedMessage(1, 0), IxList.blockedMessage(2, 1)]);")
    assert r[0] == "Save blocked: 1 test was not heard in the dictation. Keep it or remove it, then Save again."
    assert r[1] == "Save blocked: 2 tests were not heard in the dictation. Keep them or remove them, then Save again."
    assert r[2] == "Save blocked: 1 medicine needs a check. Resolve them in the sheet (the list below jumps to each one), then Save again."
    assert r[3] == ("Save blocked: 2 medicines need a check, and 1 test was not heard in the dictation. Resolve the medicines (the list "
                    "below jumps to each one), keep or remove the test, then Save again.")


def test_app_js_hooks():
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    assert 'base.investigations = IxList.read($("pIx"));' in app
    assert 'remember_investigations: IxList.rememberIndexes($("pIx"))' in app and "      remember_investigations,\n" in app
    assert 'IxList.render($("pIx"), s.investigations);' in app and 'renderList($("pIx")' not in app and 'readList("pIx")' not in app
    assert 'b.dataset.action === "delete-ix") IxList.remove(b.closest("li"))' in app
    assert 'r.type === "ix"' in app and 'IxList.insert($("pIx"), r.item, r.pos)' in app
    assert 'setUndo({ type: "ix", item, pos }' in app
    branch = app.split("e.status === 409")[1].split("} else {")[0]
    assert 'IxList.showBlocked($("pIx"), ix)' in branch and "IxList.blockedMessage(n, ix.length)" in branch


def test_index_html_pins():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert html.index("rx.css?v=10") < html.index("ixlist.css?v=3")
    assert html.index("ixlist.js?v=4") < html.index("app.js?v=61")
    assert '<ul id="pIx" class="ix-list"></ul>' in html and not re.search(r'id="pIx"[^>]*editable-list', html)
    assert len((FRONT / "ixlist.js").read_text(encoding="utf-8").splitlines()) < 300
