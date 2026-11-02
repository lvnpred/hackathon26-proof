"""Your usual strip (plan SH-B6, Task 3). frontend/yourusual.js runs under node with a fake DOM, fake timers and recorded hooks."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"

_HARNESS = r"""
globalThis.window = globalThis;
const realSetTimeout = setTimeout;
const tick = () => new Promise((r) => realSetTimeout(r, 0));
let timers = [], tid = 0;                                   // fake timers: advance(ms) runs what is due
globalThis.setTimeout = (f, ms) => { timers.push({ id: ++tid, f, ms }); return tid; };
globalThis.clearTimeout = (id) => { timers = timers.filter((t) => t.id !== id); };
const advance = async (ms) => { const due = timers.filter((t) => t.ms <= ms); timers = timers.filter((t) => t.ms > ms); due.forEach((t) => t.f()); await tick(); await tick(); };
const mkEl = (tag) => { const h = {}; let text = ""; const e = { tag, className: "", hidden: false, disabled: false, children: [], attrs: {},
  setAttribute(k, v) { e.attrs[k] = v; }, appendChild(c) { e.children.push(c); return c; },
  get firstChild() { return e.children[0] || null; }, removeChild(c) { e.children = e.children.filter((x) => x !== c); },
  insertBefore(c, ref) { const i = e.children.indexOf(ref); e.children.splice(i < 0 ? e.children.length : i, 0, c); return c; },
  addEventListener(t, f) { (h[t] = h[t] || []).push(f); }, click() { (h.click || []).forEach((f) => f({})); } };
  Object.defineProperty(e, "textContent", { get: () => text, set: (v) => { text = v; e.children = []; } });
  return e; };
const find = (e, cls, out = []) => { e.children.forEach((c) => { if (c.className === cls) out.push(c); find(c, cls, out); }); return out; };
const box = mkEl("div"); box.hidden = true;
globalThis.document = { getElementById: (id) => (id === "usualRx" ? box : null), createElement: mkEl };
require(%(rxstate)s);
const posts = []; let answers = [];
const S = { diagnosis: ["BPH"], onSheet: [], viewOnly: false, working: false, hasSheet: true, seq: 1 }; const added = [];
const hooks = { post: (url, body, ms) => { posts.push({ url, body, ms }); const a = answers.shift(); return a.pending ? a.pending : a.reject ? Promise.reject(a.reject) : Promise.resolve(a.body); },
  diagnosis: () => S.diagnosis, onSheet: () => S.onSheet, ageSex: () => "60 / M", viewOnly: () => S.viewOnly, working: () => S.working,
  hasSheet: () => S.hasSheet, sheetSeq: () => S.seq, add: (r) => added.push(r) };
const it = (name, o = {}) => Object.assign({ form: "Tab.", name, strength: "0.4 mg", dose: "0-0-1", timing: "At bedtime", duration: "30 days", generic: "", count: 14 }, o);
const later = () => { let res, rej; const p = new Promise((a, b) => { res = a; rej = b; }); return { pending: p, res, rej }; };
const text = (e) => [e.textContent].concat(e.children.map(text)).join("");
"""


def _run(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    head = _HARNESS % {"rxstate": json.dumps(str(FRONT / "rxstate.js"))}
    script = head + f"const Y = require({json.dumps(str(FRONT / 'yourusual.js'))});" + "(async () => {" + body + "})().catch((e) => { console.error(e); process.exit(1); });"
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_label_and_phrase():
    r = _run("""const full = it("Urimax"), bare = it("Urimax", { timing: "", duration: "" });
      console.log(JSON.stringify([Y.labelOf(full), Y.labelOf(bare), Y.phraseOf(full)]));""")
    assert r == ["Tab Urimax 0.4 mg 0-0-1, at bedtime × 30 days", "Tab Urimax 0.4 mg 0-0-1", "Tab Urimax 0.4 mg 0-0-1 at bedtime 30 days"]


def test_shown_caps_lines_and_skips_what_is_on_the_sheet():
    r = _run("""const mk = (p) => [1, 2, 3, 4, 5].map((i) => it(p + i));
      const gs = [{ line: 1, items: mk("B") }, { line: 0, items: mk("A") }];
      const a = Y.shown(gs, ["BPH", "Fever"], []);
      const b = Y.shown([{ line: 0, items: [it("Urimax"), it("Other")] }], ["BPH"], [{ name: " urimax " }]);
      const c = Y.shown([{ line: 0, items: [it("Flomax", { generic: "Tamsulosin" })] }], ["BPH"], [{ name: "Tamsulosin", generic: "" }]);
      const d = Y.shown([{ line: 0, items: [it("Urimax")] }, { line: 1, items: [it("Other")] }], ["BPH", "Fever"], [{ name: "Urimax" }]);
      console.log(JSON.stringify([a.map((g) => [g.label, g.items.length]), b[0].items.map((i) => i.name), c, d.map((g) => g.label)]));""")
    assert r == [[["BPH", 3], ["Fever", 3]], ["Other"], [], ["Fever"]]


def test_refresh_posts_once_per_change_of_diagnosis():
    r = _run("""Y.init(hooks);
      answers = [{ body: { groups: [{ line: 0, items: [it("Urimax")] }] } }];
      Y.refresh(); Y.refresh(); await advance(499); const early = posts.length; await advance(500);
      const once = posts.map((p) => [p.url, p.body, p.ms]);
      Y.refresh(); await advance(500);
      console.log(JSON.stringify([early, once, posts.length, find(box, "usual-add").length, box.hidden]));""")
    assert r == [0, [["/api/v1/spoken/usual", {"diagnosis": ["BPH"]}, 30000]], 1, 1, False]


def test_hidden_when_view_only_working_or_no_sheet():
    r = _run("""Y.init(hooks); const out = [];
      for (const k of ["viewOnly", "working", "hasSheet"]) {
        const set = (blocked) => { S.viewOnly = false; S.working = false; S.hasSheet = true; S[k] = k === "hasSheet" ? !blocked : blocked; };
        answers = [{ body: { groups: [{ line: 0, items: [it("Urimax")] }] } }];
        set(false); Y.clear(); Y.refresh(); await advance(500);
        const shownOk = box.hidden === false, n = posts.length;
        set(true); Y.refresh(); await advance(500);
        out.push([k, shownOk, box.hidden, posts.length - n]);
      }
      console.log(JSON.stringify(out));""")
    assert r == [["viewOnly", True, True, 0], ["working", True, True, 0], ["hasSheet", True, True, 0]]


def test_a_stale_answer_is_dropped():
    r = _run("""Y.init(hooks); const a = later(), b = later(); answers = [a, b];
      S.diagnosis = ["BPH"]; Y.refresh(); await advance(500);
      S.diagnosis = ["Fever"]; Y.refresh(); await advance(500);
      b.res({ groups: [{ line: 0, items: [it("Paracetamol")] }] }); await tick();
      a.res({ groups: [{ line: 0, items: [it("Urimax")] }] }); await tick();
      console.log(JSON.stringify([posts.length, find(box, "usual-label").map(text), find(box, "usual-dx").map(text)]));""")
    assert r == [2, ["Tab Paracetamol 0.4 mg 0-0-1, at bedtime × 30 days"], ["Fever"]]


def _tap_setup(second):
    return f"""Y.init(hooks); const row = {{ form: "Tab.", name: "Urimax", strength: "0.4 mg", dose: "0-0-1", timing: "At bedtime", duration: "30 days", status: "matched" }};
      answers = [{{ body: {{ groups: [{{ line: 0, items: [it("Urimax")] }}] }} }}]; Y.refresh(); await advance(500);
      const c = later(); answers = [{second}];"""


def test_a_tap_checks_the_row_then_adds_the_grounded_row():
    r = _run(_tap_setup("{ body: { row } }") + """
      find(box, "usual-add")[0].click(); await tick(); await tick();
      console.log(JSON.stringify([posts[1], added.length, JSON.stringify(added[0]) === JSON.stringify(row),
        find(box, "usual-add")[0].attrs["aria-label"], find(box, "usual-count").map(text)]));""")
    assert r[0] == {"url": "/api/v1/rx/check-row", "ms": 30000, "body": {
        "row": {"form": "Tab.", "name": "Urimax", "strength": "0.4 mg", "dose": "0-0-1", "timing": "At bedtime", "duration": "30 days", "instructions": ""},
        "transcript": "Tab Urimax 0.4 mg 0-0-1 at bedtime 30 days", "age_sex": "60 / M"}}
    assert r[1:] == [1, True, "Add Tab Urimax 0.4 mg 0-0-1, at bedtime × 30 days", ["14 times"]]


def test_a_second_tap_while_checking_is_ignored():
    r = _run(_tap_setup("c") + """
      const b = find(box, "usual-add")[0]; b.click(); const dis = find(box, "usual-add")[0].disabled; b.click(); b.click();
      c.res({ row }); await tick(); await tick();
      console.log(JSON.stringify([posts.length, added.length, dis]));""")
    assert r == [2, 1, True]


def test_a_tap_answer_after_the_sheet_changed_adds_nothing():
    r = _run(_tap_setup("c") + """
      find(box, "usual-add")[0].click(); S.seq = 2; c.res({ row }); await tick(); await tick();
      const c2 = later(); answers = [c2]; S.seq = 1; Y.render(); find(box, "usual-add")[0].click(); S.viewOnly = true; c2.res({ row }); await tick(); await tick();
      console.log(JSON.stringify([posts.length, added.length]));""")
    assert r == [3, 0]


def test_a_failed_check_says_so_and_adds_nothing():
    r = _run(_tap_setup("{ reject: { status: 503, message: \"boom\" } }") + """
      find(box, "usual-add")[0].click(); await tick(); await tick();
      console.log(JSON.stringify([added.length, find(box, "usual-note").map(text), find(box, "usual-add")[0].disabled]));""")
    assert r == [0, ["Could not add Urimax. The medicine check is not available right now."], False]


def test_a_failed_lookup_hides_the_strip_quietly():
    r = _run("""Y.init(hooks); answers = [{ reject: { status: 503 } }];
      Y.refresh(); await advance(500);
      console.log(JSON.stringify([box.hidden, find(box, "usual-note").map(text).join("").length, text(box)]));""")
    assert r == [True, 0, ""]


def test_an_answer_after_the_diagnosis_was_cleared_paints_nothing():
    r = _run("""Y.init(hooks); const a = later(); answers = [a];
      S.diagnosis = ["BPH"]; Y.refresh(); await advance(500);
      S.diagnosis = []; Y.refresh(); await advance(500);
      a.res({ groups: [{ line: 0, items: [it("Urimax")] }] }); await tick();
      console.log(JSON.stringify([box.hidden, find(box, "usual-add").length]));""")
    assert r == [True, 0]


def test_an_answer_for_a_diagnosis_edited_back_to_the_cached_one_is_dropped():
    r = _run("""Y.init(hooks); const b = later(); answers = [{ body: { groups: [{ line: 0, items: [it("Urimax")] }] } }, b];
      S.diagnosis = ["BPH"]; Y.refresh(); await advance(500);
      S.diagnosis = ["BPH with LUTS"]; Y.refresh(); await advance(500);
      S.diagnosis = ["BPH"]; Y.refresh(); await advance(500);
      b.res({ groups: [{ line: 0, items: [it("Other")] }] }); await tick();
      console.log(JSON.stringify([find(box, "usual-label").map(text), find(box, "usual-dx").map(text)]));""")
    assert r == [["Tab Urimax 0.4 mg 0-0-1, at bedtime × 30 days"], ["BPH"]]


def test_a_throwing_add_is_not_reported_as_a_failed_check():
    r = _run(_tap_setup("{ body: { row } }") + """
      hooks.add = () => { throw new Error("page broke"); };
      let loud = 0; process.on("unhandledRejection", () => { loud++; });
      find(box, "usual-add")[0].click(); await tick(); await tick();
      console.log(JSON.stringify([find(box, "usual-note").map(text).join("").length, loud]));""")
    assert r == [0, 1]


def test_a_count_below_two_or_missing_is_not_shown():
    r = _run("""Y.init(hooks); answers = [{ body: { groups: [{ line: 0, items: [it("A", { count: undefined }), it("B", { count: 1 }), it("C", { count: 3 })] }] } }];
      Y.refresh(); await advance(500);
      console.log(JSON.stringify(find(box, "usual-count").map(text)));""")
    assert r == ["3 times"]


def _read(name):
    return (FRONT / name).read_text()


def test_the_page_loads_and_wires_the_strip():
    html, app = _read("index.html"), _read("app.js")
    assert 'id="usualRx"' in html and 'class="usual-rx no-print"' in html
    assert html.index('<tbody id="pRx">') < html.index('id="usualRx"') < html.index('data-sec="advice"')
    assert html.index("rxstate.js?v=") < html.index("yourusual.js?v=2") < html.index("app.js?v=62")
    assert "YourUsual.init(" in app and "function addRxRow(" in app
    for hook in ("YourUsual.refresh()", "YourUsual.render()", "YourUsual.clear()"):
        assert hook in app
    assert '<link rel="stylesheet" href="theme.css?v=9" />' in html


def test_a_new_sheet_never_shows_or_adds_the_previous_sheets_medicines():
    r = _run("""Y.init(hooks); const b = later(); answers = [{ body: { groups: [{ line: 0, items: [it("Urimax")] }] } }, b];
      Y.refresh(); await advance(500);
      const before = find(box, "usual-add").length;
      S.seq = 2; S.diagnosis = ["Fever"]; Y.render();                 // sheet B opened; its lookup is not back yet
      const during = [find(box, "usual-add").length, box.hidden];
      Y.refresh(); await advance(500); Y.render();
      b.res({ groups: [{ line: 0, items: [it("Paracetamol")] }] }); await tick();
      console.log(JSON.stringify([before, during, find(box, "usual-label").map(text), added.length]));""")
    assert r == [1, [0, True], ["Tab Paracetamol 0.4 mg 0-0-1, at bedtime × 30 days"], 0]


def test_a_lookup_answer_arriving_after_the_sheet_changed_paints_nothing():
    r = _run("""Y.init(hooks); const a = later(); answers = [a];
      Y.refresh(); await advance(500);
      S.seq = 2; S.working = true; Y.refresh(); await advance(500); S.working = false;   // the open starts: the blocked branch runs
      a.res({ groups: [{ line: 0, items: [it("Urimax")] }] }); await tick();
      console.log(JSON.stringify([box.hidden, find(box, "usual-add").length]));""")
    assert r == [True, 0]


def test_render_does_not_rebuild_an_unchanged_strip():
    r = _run("""Y.init(hooks); answers = [{ body: { groups: [{ line: 0, items: [it("Urimax")] }] } }];
      Y.refresh(); await advance(500);
      const b1 = find(box, "usual-add")[0]; Y.render(); Y.render();
      const same = find(box, "usual-add")[0] === b1;
      S.onSheet = [{ name: "Urimax" }]; Y.render();
      console.log(JSON.stringify([same, box.hidden, find(box, "usual-plus").length]));""")
    assert r == [True, True, 0]


def test_an_answer_that_lands_after_an_open_still_serves_the_same_diagnosis():
    r = _run("""Y.init(hooks); const a = later(); answers = [a, { body: { groups: [{ line: 0, items: [it("Urimax")] }] } }];
      S.diagnosis = ["BPH"]; Y.refresh(); await advance(500);
      S.seq = 2; S.diagnosis = ["BPH"]; Y.refresh(); Y.render(); await advance(500);
      a.res({ groups: [{ line: 0, items: [it("Urimax")] }] }); await tick();
      Y.refresh(); await advance(500); Y.render();
      console.log(JSON.stringify([posts.length, box.hidden, find(box, "usual-add").length]));""")
    assert r == [1, False, 1]


def test_an_answer_for_another_diagnosis_than_the_new_sheets_is_not_shown():
    r = _run("""Y.init(hooks); const a = later(); answers = [a];
      S.diagnosis = ["BPH"]; Y.refresh(); await advance(500);
      S.seq = 2; S.diagnosis = ["Fever"]; S.working = true; Y.render(); S.working = false;
      a.res({ groups: [{ line: 0, items: [it("Urimax")] }] }); await tick(); Y.render();
      console.log(JSON.stringify([box.hidden, find(box, "usual-add").length, added.length]));""")
    assert r == [True, 0, 0]
