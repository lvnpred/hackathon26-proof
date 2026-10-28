"""Plan I2-c: SugList paging and the list, the one component behind the inline Did you mean and the Spell it modal."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"
FAKE = """class N { constructor(t) { this.tagName = t.toUpperCase(); this.children = []; this._t = ""; this.className = ""; this.dataset = {}; this.attrs = {}; }
  get textContent() { return this._t + this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this.children = []; this._t = String(v); }
  appendChild(c) { this.children.push(c); return c; } append(...k) { k.forEach((c) => this.appendChild(c)); } setAttribute(k, v) { this.attrs[k] = String(v); } }
globalThis.document = { createElement: (t) => new N(t) };"""


def _node(expr):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    js = "globalThis.window = globalThis;" + FAKE + "require(process.argv[1]); console.log(JSON.stringify(" + expr + "))"
    out = subprocess.run([node, "-e", js, str(FRONT / "suglist.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_paging_labels_and_bounds():
    got = _node("""(() => { const mk = (n) => Array.from({ length: n }, (_, i) => ({ name: "N" + (i + 1) }));
      const p = (n, i, t) => { const r = SugList.page(mk(n), i, t); return [r.label, r.items.map((s) => s.name).join(","), r.hasPrev, r.hasNext, r.index]; };
      return [p(0, 0, 0), p(3, 0, 3), p(20, 0, 20), p(20, 2, 20), p(20, 9, 20), p(20, -1, 20), p(40, 0, 60), SugList.PAGE]; })()""")
    assert got[0] == ["No close names found. Type the name.", "", False, False, 0]
    assert got[1] == ["Showing 1-3 of 3", "N1,N2,N3", False, False, 0]
    assert got[2] == ["Showing 1-8 of 20", "N1,N2,N3,N4,N5,N6,N7,N8", False, True, 0]
    assert got[3] == ["Showing 17-20 of 20", "N17,N18,N19,N20", True, False, 2]
    assert got[4] == got[3] and got[5] == got[2]                                   # out of range: clamped
    assert got[6][0] == "Showing 1-8 of 40 (60 found: type more letters to narrow them)" and got[7] == 8


def test_page_edges_one_page_exactly_eight_nine_a_hundred_and_a_shrinking_list():
    got = _node("""(() => { const mk = (n) => Array.from({ length: n }, (_, i) => ({ name: "N" + (i + 1) }));
      const r = (n, i, t) => { const x = SugList.page(mk(n), i, t == null ? n : t); return [x.label, x.items.length, x.pages, x.index, x.from, x.to, x.hasPrev, x.hasNext]; };
      const grow = SugList.page(mk(20), 2, 20), shrunk = SugList.page(mk(5), grow.index, 5);       // the page was 3, the list shrank to 5
      return [r(8, 0), r(9, 0), r(9, 1), r(100, 12), r(100, 13), r(100, 0, 100), r(0, 5), r(1, "2"), r(20, "abc"), r(20, 1.9), r(20, NaN),
              [shrunk.label, shrunk.index, shrunk.hasPrev, shrunk.hasNext], SugList.page(mk(8), 0, 8).items.length]; })()""")
    assert got[0] == ["Showing 1-8 of 8", 8, 1, 0, 1, 8, False, False]
    assert got[1] == ["Showing 1-8 of 9", 8, 2, 0, 1, 8, False, True]
    assert got[2] == ["Showing 9-9 of 9", 1, 2, 1, 9, 9, True, False]
    assert got[3] == ["Showing 97-100 of 100", 4, 13, 12, 97, 100, True, False]
    assert got[4] == got[3]                                                         # page 13 of 13 is the last: clamped
    assert got[5][0] == "Showing 1-8 of 100" and got[5][2] == 13
    assert got[6] == ["No close names found. Type the name.", 0, 1, 0, 0, 0, False, False]
    assert got[7] == ["Showing 1-1 of 1", 1, 1, 0, 1, 1, False, False]             # "2" clamps to the only page
    assert got[8][3] == 0 and got[9][3] == 1 and got[10][3] == 0                    # junk -> 0; 1.9 floors to 1; NaN -> 0
    assert got[11] == ["Showing 1-5 of 5", 0, False, False] and got[12] == 8       # a shrinking list clamps to page 1


def test_the_list_is_text_only_with_a_generic_and_a_reason_per_name():
    got = _node("""(() => { const box = document.createElement("div");
      SugList.list(box, [{ name: "Crocin", generic: "Paracetamol", reason: "sounds" }, { name: "<img src=x onerror=1>", generic: "", reason: "clinic" },
                         { name: "Prednisolone", generic: "Prednisolone", reason: "lookalike" }]);
      return box.children.map((b) => [b.dataset.action, b.dataset.value, b.className, b.children.map((c) => [c.className, c.textContent])]); })()""")
    assert got[0] == ["pick", "Crocin", "rx-act sug spell-item", [["sug-name", "Crocin"], ["sug-gen", "generic: Paracetamol"], ["sug-why", "sounds like"]]]
    assert got[1][1] == "<img src=x onerror=1>" and got[1][3] == [["sug-name", "<img src=x onerror=1>"], ["sug-why", "your clinic uses it"]]
    assert got[2][3] == [["sug-name", "Prednisolone"], ["sug-why", "looks alike: a different medicine"]]


def test_the_list_rebuilds_in_place_labels_hold_the_visible_text_and_no_markup_is_parsed():
    got = _node("""(() => { const box = document.createElement("div"); box.textContent = "old";
      SugList.list(box, [{ name: "A", generic: "", reason: "sounds" }]); const first = box.children.length;
      const hostile = "<b onmouseover=1>x</b>";
      SugList.list(box, [{ name: hostile, generic: "G<i>", reason: "sounds" }, { name: "B", generic: "", reason: "matched" }], { cls: "x" });
      const b = box.children[0];
      return [first, box.children.length, box._t, b.attrs["aria-label"], b.className, b.children[1].textContent, box.children[1].children[1].textContent,
              b.children.every((c) => c.children.length === 0), box.children[0].children[0].textContent.includes(hostile)]; })()""")
    assert got[0] == 1 and got[1] == 2 and got[2] == ""                              # the old content is cleared, not appended to
    assert got[3] == "<b onmouseover=1>x</b>: use for this row" and got[4] == "rx-act sug x"
    assert got[5] == "generic: G<i>" and got[6] == "in the medicine list" and got[7] is True and got[8] is True
    assert "innerHTML" not in (FRONT / "suglist.js").read_text(encoding="utf-8")
