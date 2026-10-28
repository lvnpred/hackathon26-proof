"""Plan C1 (task 6): frontend/cues.js under node on a tiny fake DOM. The cue panel lists the switched-on sections with their
cues while a first dictation records; the flags name each empty section as text; app.js wires both into the recording flow."""
import json
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from doctor_dictation.core import sections as core

FRONT = Path(__file__).resolve().parents[1] / "frontend"
CUES = {"complaints": "Fever with chills for 3 days, no vomiting"}
FH = tuple(core.Section(s.key, s.heading, CUES.get(s.key, ""), s.kind, s.order, s.key != "advice") for s in core.BUILT_INS) + (
    core.Section("family_history", "Family History", "Father diabetic", "text", 25, True),)
FH = tuple(sorted(FH, key=lambda s: s.order))
FAKE = """class El { constructor(id) { this.id = id; this.children = []; this._t = ""; this.hidden = true; }
  get textContent() { return this._t + this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this.children = []; this._t = String(v); }
  appendChild(c) { this.children.push(c); return c; } }
const els = {}; ["cuePanel", "cueList", "emptyFlags"].forEach((id) => { els[id] = new El(id); });
globalThis.document = { getElementById: (id) => els[id] || null, createElement: (t) => new El(t) }; globalThis.window = globalThis;
require(%r); require(%r);
const lines = (id) => els[id].children.map((c) => c.textContent);"""


def _run(body, list_):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    src = FAKE % (str(FRONT / "sheetsecs.js"), str(FRONT / "cues.js")) + "\nconst FH = " + json.dumps([asdict(s) for s in list_]) + ";\n" + body
    r = subprocess.run([node, "-e", src], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_the_panel_lists_switched_on_sections_with_their_cues():
    out = _run("""Cues.init({ list: () => FH }); Cues.show(); const a = [lines("cueList"), els.cuePanel.hidden];
Cues.hide(); const b = els.cuePanel.hidden; Cues.init({ list: () => [] }); Cues.show();
console.log(JSON.stringify([a, b, els.cuePanel.hidden]));""", FH)
    got, hidden_after, empty_hidden = out
    texts, shown = got
    # spec-driven (midnight task 3): each line is the cue alone; a section with no cue shows its heading
    assert texts[0] == "Fever with chills for 3 days, no vomiting"
    assert "Findings" in texts and "Father diabetic" in texts
    assert not any(t.startswith("Dietary") for t in texts) and shown is False
    assert hidden_after is True and empty_hidden is True      # hide() stays exported (unused by the app now)


def test_flags_name_each_empty_section_as_text():
    out = _run("""const s = {complaints: ["x"], rx: [{name: "Dolo"}], review: "1 week", extra: {family_history: {lines: ["a"]}}};
const heads = Cues.emptyHeadings(FH, s);
Cues.init({ list: () => [{key: "notes", heading: "<b>Notes</b>", cue: "", kind: "text", order: 1, on: true}] }); Cues.flagEmpty({});
const a = [lines("emptyFlags"), els.emptyFlags.hidden]; Cues.clearFlags();
console.log(JSON.stringify([heads, a, lines("emptyFlags"), els.emptyFlags.hidden]));""", FH)
    heads, (flags, hid), after, hid_after = out
    assert heads == ["Diagnosis / Clinical Impression", "Investigations Advised", "Findings"]
    assert flags == ["Nothing dictated for <b>Notes</b>"] and hid is False
    assert after == [] and hid_after is True


def test_app_js_wires_the_panel_into_the_recording_flow():
    js = (FRONT / "app.js").read_text()
    for line in ('Cues.init({ list: () => SheetSecs.list() });',
                 'Cues.clearFlags();'):
        assert line in js
    # spec-driven (midnight task 3): the panel shows once the section list loads and is no longer toggled by recording
    # spec-driven (round 2, M2): the panel shows from a finally, so a failed fetch or a render error cannot keep it hidden
    assert ".catch(() => {}).finally(() => Cues.show());" in js and js.count("Cues.show()") == 1 and "Cues.hide()" not in js
    assert js.count("Cues.flagEmpty(state.structured);") == 2
    reset = js[js.index("function resetSheet()"):]
    assert "Cues.clearFlags();" in reset.split("\n}\n")[0]
    html = (FRONT / "index.html").read_text()
    assert html.index("sheetsecs.js?v=") < html.index("cues.js?v=4") < html.index("app.js?v=")


def test_app_js_clears_the_flags_when_a_document_opens_or_an_undo_restores():
    js = (FRONT / "app.js").read_text()
    opened = js[js.index("async function openDocument("):]
    assert "DictGuard.clear(); Cues.clearFlags();" in opened.split("\n}\n")[0]
    assert "restored: () => { Cues.clearFlags();" in js


def test_cues_use_the_one_has_data_rule_of_the_sheet_and_the_server():
    forms = [{}, {"advice": ["x"]}, {"rx": [{"name": " "}]}, {"rx": [{"name": "Dolo"}], "review": " "}, {"review": "1 week"},
             {"extra": {"family_history": {"lines": ["a"]}}}, {"extra": {"family_history": {"lines": []}}}, {"extra": ["x"]}, {"extra": "x"}]
    out = _run("console.log(JSON.stringify(%s.map((f) => FH.map((x) => [SheetSecs.has(f, x.key, x.kind), Cues.emptyHeadings(FH, f).includes(x.heading)]))));"
               % json.dumps(forms), FH)
    for f, row in zip(forms, out):
        for x, (has, empty) in zip(FH, row):
            assert has == core.has_data(f, x.key, x.kind) and empty == (x.on and not has)


def test_a_cue_splits_at_its_first_colon_into_a_lead_span_and_a_rest_span():
    out = _run("""Cues.init({ list: () => [
  {key: "a", heading: "A", cue: "Complaints: fever: 3 days. History: diabetic", kind: "text", order: 1, on: true},
  {key: "b", heading: "Findings", cue: "", kind: "text", order: 2, on: true},
  {key: "c", heading: "C", cue: "no colon here", kind: "text", order: 3, on: true},
  {key: "d", heading: "D", cue: "<b>x</b>: y", kind: "text", order: 4, on: true}] });
Cues.show(); const spans = (li) => li.children.map((s) => [s.className, s.textContent]);
console.log(JSON.stringify(els.cueList.children.map(spans)));""", FH)
    a, b, c, d = out
    assert a == [["cue-lead", "Complaints:"], ["cue-rest", " fever: 3 days. History: diabetic"]]
    assert b == [["cue-lead", "Findings"], ["cue-rest", ""]]
    assert c == [["cue-lead", ""], ["cue-rest", "no colon here"]]
    # spec-driven (round 2, M3): only a word label splits, so "<b>x</b>:" is not a label; it stays text, never markup
    assert d == [["cue-lead", ""], ["cue-rest", "<b>x</b>: y"]]


def test_a_colon_inside_a_time_or_number_never_splits_the_cue():
    out = _run("""Cues.init({ list: () => [
  {key: "a", heading: "A", cue: "Tab. Dolo 650 at 8:30 pm", kind: "text", order: 1, on: true},
  {key: "b", heading: "B", cue: "Review (OPD) & labs: in 2 weeks at 10:00", kind: "text", order: 2, on: true},
  {key: "c", heading: "C", cue: "8:30 dose", kind: "text", order: 3, on: true},
  {key: "d", heading: "D", cue: "A very long label that is more than thirty chars: x", kind: "text", order: 4, on: true}] });
Cues.show(); console.log(JSON.stringify(els.cueList.children.map((li) => li.children.map((s) => s.textContent))));""", FH)
    assert out[0] == ["", "Tab. Dolo 650 at 8:30 pm"]
    assert out[1] == ["Review (OPD) & labs:", " in 2 weeks at 10:00"]
    assert out[2] == ["", "8:30 dose"]
    assert out[3] == ["", "A very long label that is more than thirty chars: x"]


def test_with_no_section_list_the_panel_falls_back_to_the_sheet_headings():
    out = _run("""const T = (t) => ({ textContent: t }); let asked = "";
document.querySelectorAll = (sel) => { asked = sel; return [T(" Findings "), T("Rx (MEDICATIONS)")]; };
Cues.init({ list: () => [] }); Cues.show();
console.log(JSON.stringify([asked, els.cueList.children.map((li) => li.textContent), els.cuePanel.hidden]));""", FH)
    asked, texts, hidden = out
    assert asked == "#sheetBody .sec:not([hidden]) > .sec-title"
    assert texts == ["Findings", "Rx (MEDICATIONS)"] and hidden is False
