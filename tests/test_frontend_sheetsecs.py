"""Plan C1 (task 5): frontend/sheetsecs.js under node on a tiny fake DOM. The sheet follows the section list: order, headings,
hidden blocks, added plain-text blocks and the read-back into structured.extra; plan() matches core.sections.layout."""
import json
import re
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from doctor_dictation.core import sections as core

FRONT = Path(__file__).resolve().parents[1] / "frontend"
FH = tuple(core.Section(s.key, s.heading, "", s.kind, s.order, s.key != "advice") for s in core.BUILT_INS) + (
    core.Section("family_history", "Family History", "Father diabetic", "text", 25, True),)
FH = tuple(sorted(FH, key=lambda s: s.order))
BUILT = ["complaints", "diagnosis", "investigations", "findings", "rx", "advice", "review"]

_DOM = r"""
class El {
  constructor(tag) { this.tagName = String(tag).toUpperCase(); this.children = []; this.parentNode = null; this.dataset = {}; this.className = ""; this._t = ""; this.hidden = false; }
  get textContent() { return this._t + this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this.children.forEach((c) => { c.parentNode = null; }); this.children = []; this._t = String(v); }
  appendChild(c) { if (c.parentNode) c.remove(); c.parentNode = this; this.children.push(c); return c; }
  insertBefore(c, ref) { if (c.parentNode) c.remove(); c.parentNode = this; const i = ref ? this.children.indexOf(ref) : -1; if (i < 0) this.children.push(c); else this.children.splice(i, 0, c); return c; }
  remove() { const p = this.parentNode; if (p) { p.children.splice(p.children.indexOf(this), 1); this.parentNode = null; } }
  cloneNode() { const c = new El(this.tagName); c._t = this._t; this.children.forEach((k) => c.appendChild(k.cloneNode())); return c; }
  matches(sel) {
    if (sel === "ul[data-extra]") return this.tagName === "UL" && this.dataset.extra !== undefined;
    if (sel[0] === ".") return this.className.split(/\s+/).includes(sel.slice(1));
    return this.tagName === sel.toUpperCase();
  }
  querySelectorAll(sel) { const out = []; const walk = (n) => n.children.forEach((c) => { if (c.matches(sel)) out.push(c); walk(c); }); walk(this); return out; }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}
const mk = (tag, cls) => { const e = new El(tag); if (cls) e.className = cls; return e; };
const body = mk("div"); const byId = { sheetBody: body };
for (const k of %(built)s) { const w = mk("div", "sec"); w.dataset.sec = k; w.appendChild(mk("div", "sec-title")).textContent = k.toUpperCase(); w.appendChild(mk("ul")); body.appendChild(w); }
const disc = mk("div", "disclaimer"); body.appendChild(disc);
globalThis.document = { getElementById: (id) => byId[id] || null, createElement: (t) => new El(t) };
globalThis.window = globalThis;
const rendered = [];
const renderList = (ul, vals) => { rendered.push([ul.dataset.extra, vals]); ul.children.slice().forEach((c) => c.remove()); (vals && vals.length ? vals : [""]).forEach((v) => { const li = mk("li"); li.textContent = v; ul.appendChild(li); }); };
const order = () => body.children.map((c) => c.dataset.sec || "disclaimer");
const wrap = (k) => body.children.find((c) => c.dataset.sec === k);
"""


def _run(body, sections=FH, fail=False):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    get = "() => Promise.reject(new Error('down'))" if fail else "() => Promise.resolve({ sections: %s })" % json.dumps([asdict(s) for s in sections])
    js = (_DOM % {"built": json.dumps(BUILT)} + "require(process.argv[1]); SheetSecs.init({ get: " + get + ", renderList });"
          + "(async () => {" + body + "})().catch((e) => { console.error(e.stack); process.exit(1); });")
    out = subprocess.run([node, "-e", js, str(FRONT / "sheetsecs.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_plan_matches_the_server_layout():
    forms = [{}, {"advice": ["Drink water"]}, {"extra": {"old_sec": {"heading": "Old", "lines": ["x"]}}},
             {"rx": [{"name": "Paracetamol"}], "review": " ", "extra": {"family_history": {"heading": "FH stored", "lines": ["a"]}}}]
    r = _run("await SheetSecs.load(); const sl = SheetSecs.list(); console.log(JSON.stringify(%s.map((f) => SheetSecs.plan(sl, f))));" % json.dumps(forms))
    assert r == [[list(t) for t in core.layout(FH, f)] for f in forms]


def test_render_orders_retitles_hides_and_adds_blocks():
    r = _run("""await SheetSecs.load();
      const s = { extra: { family_history: { heading: "Family History", lines: ["a"] } } };
      SheetSecs.render(s);
      const first = order(), hidden = wrap("advice").hidden, title = wrap("family_history").querySelector(".sec-title").textContent, got = rendered.slice();
      SheetSecs.render({ extra: { old_sec: { heading: "<b>x</b>", lines: ["y"] } } });
      const mid = order(), oldTitle = wrap("old_sec").querySelector(".sec-title"), oldKids = oldTitle.children.length, oldText = oldTitle.textContent;
      SheetSecs.render({});
      console.log(JSON.stringify({ first, hidden, title, got, mid, oldKids, oldText, after: order(), fhHidden: wrap("family_history").hidden, again: wrap("advice").hidden }));""")
    assert r["first"] == ["complaints", "diagnosis", "family_history", "investigations", "findings", "rx", "advice", "review", "disclaimer"]
    assert r["hidden"] is True and r["title"] == "Family History" and r["got"] == [["family_history", ["a"]]]
    assert "old_sec" in r["mid"] and r["oldText"] == "<b>x</b>" and r["oldKids"] == 0   # a heading is text, never markup
    assert "old_sec" not in r["after"] and "family_history" in r["after"] and r["fhHidden"] is False and r["again"] is True


def test_read_returns_only_sections_with_lines():
    sl = FH + (core.Section("habits", "Habits", "", "text", 26, True),)
    r = _run("""await SheetSecs.load(); SheetSecs.render({});
      const fh = wrap("family_history").querySelector("ul"); fh.children[0].textContent = "  Father diabetic ";
      const out = SheetSecs.read();
      console.log(JSON.stringify(out));""", sections=sl)
    assert r == {"family_history": {"heading": "Family History", "lines": ["Father diabetic"]}}
    r = _run("""await SheetSecs.load(); const before = order(); SheetSecs.render({ advice: ["x"] });
      console.log(JSON.stringify({ list: SheetSecs.list(), before, after: order(), hidden: body.children.some((c) => c.hidden) }));""", fail=True)
    assert r["list"] == [] and r["after"] == r["before"] == BUILT + ["disclaimer"] and r["hidden"] is False


def test_page_wiring_and_versions():
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    for line in ("SheetSecs.init({ get: (u) => fetch(u).then(safeJson), renderList });",
                 "SheetSecs.load().then(() => SheetSecs.render(state.structured ? readForm() : {})).catch(() => {}).finally(() => Cues.show());",
                 "SheetSecs.render(s);", "SheetSecs.render({});",
                 "SheetSecs.readBack(base);"):
        assert line in app
    assert re.findall(r'<div class="sec" data-sec="(\w+)">', html) == BUILT
    assert html.index("sheetsecs.js?v=2") < html.index("app.js?v=61") and "styles.css?v=17" in html
    assert "#sheet .sec-title { text-transform:uppercase; }" in (FRONT / "styles.css").read_text(encoding="utf-8")


def test_a_failed_list_load_keeps_the_stored_extra_on_save():
    r = _run("""await SheetSecs.load(); const extra = { old_sec: { heading: "Old", lines: ["kept"] } };
      SheetSecs.render({ extra }); const kept = SheetSecs.readBack({ extra, a: 1 });
      await (async () => { SheetSecs.init({ get: () => Promise.resolve({ sections: %s }) }); await SheetSecs.load(); })();
      SheetSecs.render({}); const cleared = SheetSecs.readBack({ extra, a: 1 });
      console.log(JSON.stringify({ kept, cleared }));""" % json.dumps([asdict(s) for s in FH]), fail=True)
    assert r["kept"] == {"extra": {"old_sec": {"heading": "Old", "lines": ["kept"]}}, "a": 1}
    assert r["cleared"] == {"a": 1}


def test_a_document_rendered_before_the_list_loads_keeps_its_extra():
    r = _run("""const extra = { family_history: { heading: "Family History", lines: ["kept"] } };
      let resolve; SheetSecs.init({ get: () => new Promise((res) => { resolve = res; }) });
      const doc = { extra, a: 1 }; const p = SheetSecs.load();
      SheetSecs.render(doc);                                          // list pending: nothing drawn yet
      await new Promise((r) => setTimeout(r, 0));
      resolve({ sections: %s }); await p;
      SheetSecs.render(SheetSecs.readBack(JSON.parse(JSON.stringify(doc))));   // the app's load callback: render(readForm())
      console.log(JSON.stringify({ back: SheetSecs.readBack({ a: 1 }), drawn: rendered, id: wrap("family_history").querySelector("ul").id }));""" % json.dumps([asdict(s) for s in FH]))
    assert r["drawn"] == [["family_history", ["kept"]]] and r["back"]["extra"]["family_history"]["lines"] == ["kept"]
    assert r["id"] == "pEx-family_history"                              # undo of a deleted line finds the list by id
