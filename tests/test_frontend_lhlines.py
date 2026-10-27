"""Letterhead review lines (PQ-b task 4): the plan/payload rules and the DOM render/collect of frontend/lhlines.js run
under node with a tiny fake DOM. Skipped when node is missing."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"

FAKE = r"""
globalThis.window = globalThis;
class El {
  constructor(t) { this.tag = t; this.children = []; this._t = ""; this.attrs = {}; this.dataset = {}; this.hidden = false;
    this.className = ""; this.value = ""; this.disabled = false; this.checked = false; this.L = {}; }
  get textContent() { return this._t + this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this.children = []; this._t = String(v); }
  appendChild(c) { this.children.push(c); return c; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  addEventListener(t, f) { (this.L[t] = this.L[t] || []).push(f); }
  flip(on) { this.checked = on; (this.L.change || []).forEach((f) => f()); }
  all(tag) { return this.children.flatMap((c) => [c].concat(c.all(tag))).filter((n) => !tag || n.tag === tag); }
}
const ids = {};
["lhLinesBox", "lhLines", "lhDupes", "lhSkipped", "lhLeftOut"].forEach((i) => { ids[i] = new El("div"); });
document = { getElementById: (i) => ids[i], createElement: (t) => new El(t), createTextNode: (t) => { const e = new El("#t"); e._t = t; return e; } };
const LH = require(process.argv[1]);
"""


def node_run(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = FAKE + "console.log(JSON.stringify((() => {" + body + "})()))"
    out = subprocess.run([node, "-e", script, str(FRONT / "lhlines.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def node_plan(view):
    return node_run(f"return LH.plan({json.dumps(view)});")


VIEW = {"layout": {"header": [{"type": "text", "field": "phone"}, {"type": "text", "text": "Name: Age:"},
                              {"type": "text", "text": "Dr. X"}], "footer": [{"type": "text", "text": "Visit After"}],
                   "skipped_labels": ["Date:", "Sex"]},
        "fill_in": [{"section": "header", "index": 1, "text": "Name: Age:"}, {"section": "footer", "index": 0, "text": "Visit After"}],
        "warnings": [{"section": "header", "index": 2, "text": "Dr. X"}],
        "duplicates": [{"field": "phone", "header": [0], "footer": [1]}]}


def test_plan_pre_ticks_fill_in_lines_and_marks_warnings():
    view = dict(VIEW, duplicates=[])
    rows = node_plan(view)["rows"]
    assert [(r["section"], r["index"], r["remove"], r["label"], r["warn"]) for r in rows] == [
        ("header", 1, True, True, False), ("header", 2, False, False, True), ("footer", 0, True, True, False)]


def test_a_duplicate_starts_as_both():                                   # owner Q5
    view = {"layout": {"header": [], "footer": []}, "fill_in": [], "warnings": [],
            "duplicates": [{"field": "phone", "header": [0], "footer": [1]}]}
    assert node_plan(view)["dupes"] == [{"field": "phone", "header": [0], "footer": [1], "where": "both"}]


def test_plan_lists_the_skipped_labels_and_survives_a_bare_view():
    assert node_plan(VIEW)["skipped"] == ["Date:", "Sex"]
    assert node_plan({}) == {"rows": [], "dupes": [], "skipped": []}


def test_payload_turns_ticks_and_empty_text_into_removals_and_sends_the_choice():
    rows = ('[{section:"header",index:1,text:"Name:",remove:true},{section:"header",index:2,text:"  ",remove:false},'
            '{section:"footer",index:0,text:" Open daily ",remove:false}]')
    both = node_run(f'return LH.payload({rows}, {{phone:"both"}});')
    assert both == {"lines": [{"section": "header", "index": 1, "remove": True}, {"section": "header", "index": 2, "remove": True},
                             {"section": "footer", "index": 0, "text": "Open daily"}],
                    "keep": [{"field": "phone", "where": "both"}], "include": []}
    assert "missing" not in both
    assert node_run(f'return LH.payload({rows}, {{phone:"header"}}).keep;') == [{"field": "phone", "where": "header"}]
    assert node_run("return LH.payload([], {});") == {"lines": [], "keep": [], "include": []}


def test_render_then_collect_round_trip_with_labels_pre_ticked_and_both_selected():
    got = node_run(f"""
      const box = ids.lhLinesBox; LH.render(box, {json.dumps(VIEW)}, {{labels: {{phone: "Phone"}}}});
      const rows = ids.lhLines.children.map((r) => r.all("input"));
      const first = LH.collect(box);
      const dupe = ids.lhDupes.children[0];
      dupe.all("input").filter((r) => r.value === "footer")[0].checked = true;
      dupe.all("input").filter((r) => r.value === "both")[0].checked = false;
      return {{first, second: LH.collect(box), disabled: rows.map((r) => r[0].disabled),
               legend: dupe.children[0].textContent, skipped: ids.lhSkipped.textContent, hiddenSkipped: ids.lhSkipped.hidden,
               boxHidden: box.hidden, radios: dupe.all("input").map((r) => [r.value, r.name]),
               why: ids.lhLines.children.map((r) => r.all("p").length)}};""")
    assert got["first"] == {"lines": [{"section": "header", "index": 1, "remove": True, "text": "Name: Age:"},
                                      {"section": "header", "index": 2, "text": "Dr. X"},
                                      {"section": "footer", "index": 0, "remove": True, "text": "Visit After"}],
                            "keep": [{"field": "phone", "where": "both"}], "include": []}
    assert got["second"]["keep"] == [{"field": "phone", "where": "footer"}]
    assert got["disabled"] == [True, False, True] and got["why"] == [1, 0, 1]
    assert got["legend"] == "Phone prints at the top and at the bottom. Keep it:"
    assert got["radios"] == [["header", "lhDupe_phone"], ["footer", "lhDupe_phone"], ["both", "lhDupe_phone"]]
    assert got["skipped"] == "Left out as blank labels from the paper pad: Date:; Sex" and got["hiddenSkipped"] is False
    assert got["boxHidden"] is False


def test_unticking_a_label_enables_its_line_and_a_rerender_keeps_it_unticked():
    got = node_run(f"""
      const box = ids.lhLinesBox; LH.render(box, {json.dumps(VIEW)}, {{}});
      const tick = ids.lhLines.children[0].all("input")[1];
      tick.flip(false);
      const enabled = !ids.lhLines.children[0].all("input")[0].disabled;
      const kept = LH.unticked(box);
      LH.render(box, {json.dumps(VIEW)}, {{unticked: kept}});
      return {{enabled, kept, again: ids.lhLines.children.map((r) => r.all("input")[1].checked)}};""")
    assert got == {"enabled": True, "kept": ["Name: Age:"], "again": [False, False, True]}


def test_labels_and_text_are_set_as_text_not_markup_and_the_inputs_are_labelled():
    evil = {"layout": {"header": [{"type": "text", "text": "<img src=x onerror=alert(1)>"}], "footer": []},
            "fill_in": [], "warnings": [], "duplicates": []}
    got = node_run(f"""
      LH.render(ids.lhLinesBox, {json.dumps(evil)}, {{}});
      const row = ids.lhLines.children[0];
      return {{text: row.all("input")[0].value, tags: row.all().map((n) => n.tag),
               labels: row.all("label").map((l) => l.textContent), boxHidden: ids.lhLinesBox.hidden}};""")
    assert got["text"] == "<img src=x onerror=alert(1)>" and "img" not in got["tags"]
    assert got["labels"][0].startswith("Top line 1") and got["labels"][1] == " Remove this line" and got["boxHidden"] is False


def test_an_empty_view_hides_the_box_and_collects_nothing():
    got = node_run("""
      LH.render(ids.lhLinesBox, {layout: {header: [], footer: []}}, {});
      return {hidden: ids.lhLinesBox.hidden, out: LH.collect(ids.lhLinesBox), none: LH.collect(new (ids.lhLines.constructor)("div"))};""")
    assert got == {"hidden": True, "out": {"lines": [], "keep": [], "include": []},
                   "none": {"lines": [], "keep": [], "include": []}}


def test_each_remove_tick_names_its_line():
    got = node_run(f"""
      LH.render(ids.lhLinesBox, {json.dumps(VIEW)}, {{}});
      return ids.lhLines.children.map((r) => r.all("input")[1].attrs["aria-label"]);""")
    assert got == ["Remove this line (top line 1)", "Remove this line (top line 2)", "Remove this line (bottom line 1)"]


LEFT = {"layout": {"header": [], "footer": [], "skipped_labels": ["Date:"],
                   "left_out": [{"section": "header", "index": 1, "block": {"type": "text", "text": "Name: M F Age: Date:"}},
                                {"section": "footer", "index": 0, "block": {"type": "text", "text": "<b>x</b>"}}]},
        "fill_in": [], "warnings": [], "duplicates": []}


def test_left_out_maps_text_blocks_and_ignores_anything_else():
    one = node_run(f"return LH.leftOut({json.dumps(LEFT)});")
    assert one == [{"n": 0, "section": "header", "text": "Name: M F Age: Date:"}, {"n": 1, "section": "footer", "text": "<b>x</b>"}]
    assert node_run("return [LH.leftOut({}), LH.leftOut(null), LH.leftOut({layout: {left_out: 5}})];") == [[], [], []]
    img = {"layout": {"left_out": [{"section": "header", "index": 0, "block": {"type": "logo"}}, None]}}
    assert node_run(f"return LH.leftOut({json.dumps(img)});") == []


def test_ticking_a_left_out_line_sends_its_position_and_an_untouched_page_sends_none():
    got = node_run(f"""
      const box = ids.lhLinesBox; LH.render(box, {json.dumps(LEFT)}, {{}});
      const untouched = LH.collect(box).include;
      const ticks = ids.lhLeftOut.all("input"); ticks[1].checked = true;
      return {{untouched, ticked: LH.collect(box).include, heading: ids.lhLeftOut.children[0].textContent,
               rows: ids.lhLeftOut.children.length - 1, hidden: ids.lhLeftOut.hidden, boxHidden: box.hidden,
               sentence: ids.lhSkipped.textContent, sentenceHidden: ids.lhSkipped.hidden}};""")
    assert got == {"untouched": [], "ticked": [1], "heading": "Left out \u2013 the prescription fills these in",
                   "rows": 2, "hidden": False, "boxHidden": False, "sentence": "", "sentenceHidden": True}


def test_left_out_text_is_text_and_each_tick_names_its_line():
    got = node_run(f"""
      LH.render(ids.lhLinesBox, {json.dumps(LEFT)}, {{}});
      const rows = ids.lhLeftOut.children.slice(1);
      return {{tags: ids.lhLeftOut.all().map((n) => n.tag), texts: rows.map((r) => r.children[0].textContent),
               aria: ids.lhLeftOut.all("input").map((i) => i.attrs["aria-label"]),
               label: rows[0].all("label")[0].textContent, ticked: ids.lhLeftOut.all("input").map((i) => i.checked)}};""")
    assert "b" not in got["tags"] and got["texts"] == ["Name: M F Age: Date:", "<b>x</b>"]
    assert got["aria"] == ["Include on the print: Name: M F Age: Date:", "Include on the print: <b>x</b>"]
    assert got["label"] == " Include on the print" and got["ticked"] == [False, False]


def test_a_view_with_only_skipped_labels_keeps_the_old_sentence_and_an_empty_group():
    got = node_run("""
      LH.render(ids.lhLinesBox, {layout: {header: [], footer: [], skipped_labels: ["Date:"]}}, {});
      return {sentence: ids.lhSkipped.textContent, group: ids.lhLeftOut.children.length, hidden: ids.lhLeftOut.hidden,
              include: LH.collect(ids.lhLinesBox).include};""")
    assert got == {"sentence": "Left out as blank labels from the paper pad: Date:", "group": 0, "hidden": True, "include": []}


def test_a_ticked_include_survives_the_rerender_and_the_next_save_does_not_remove_it():
    lay = {"header": [{"type": "text", "text": "Dr. A"}, {"type": "text", "text": "Name: M F Age: Date:"}], "footer": []}
    v1 = {"layout": {"header": lay["header"][:1], "footer": [], "left_out": [{"section": "header", "index": 1, "block": lay["header"][1]}]},
          "fill_in": [], "duplicates": []}
    v2 = {"layout": lay, "fill_in": [{"section": "header", "index": 1, "text": "Name: M F Age: Date:"}], "duplicates": []}
    got = node_run(f"""
      const box = ids.lhLinesBox; LH.render(box, {json.dumps(v1)}, {{}});
      box._lh.left[0].box.flip(true);
      const first = LH.collect(box).include;
      LH.render(box, {json.dumps(v2)}, {{unticked: LH.unticked(box)}});   // the re-render after the save
      return {{first, again: LH.collect(box)}};""")
    assert got["first"] == [0]
    assert got["again"]["lines"] == [{"section": "header", "index": 0, "text": "Dr. A"},
                                      {"section": "header", "index": 1, "text": "Name: M F Age: Date:"}]
    assert got["again"]["include"] == []
