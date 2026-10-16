"""Spell it (I1-e3): the pure rules run under node; the wiring is checked as text. DOM behaviour (races, guards, undo) is run under node in
test_frontend_rxspell_dom.py; real layout and focus are the browser checklist."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def _strip_comments(js):
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$|(?<![:\"'\\])//[^\n]*", "", js)


def _code(name):
    return _strip_comments(_read(name))


def _node(expr):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = "globalThis.window = globalThis; require(process.argv[1]); console.log(JSON.stringify(" + expr + "))"
    out = subprocess.run([node, "-e", script, str(FRONT / "rxstate.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_spelling_settles_name_questions_only():
    got = _node('["verified","unverified-name","lookalike-check","unknown-medicine","dose-check","unverified-strength","","x"].map(RxState.afterSpell)')
    assert got == ["you", "you", "you", "stay", "stay", "stay", "stay", "stay"]


def test_typed_names_are_tidied_and_checked_before_any_request():
    assert _node('["p r e d n i s o l o n e","  Vitamin   D3 ","ab"].map(RxState.cleanTyped)') == ["prednisolone", "Vitamin D3", "ab"]
    nine = "Vitamin one two three four five six seven eight"
    eight = "Vitamin one two three four five six seven"
    got = _node("[" + ", ".join(json.dumps(s) for s in ["", "x", "<b>hi</b>", "a" * 61, nine, eight, "Prednisolone"]) + "].map(RxState.typedProblem)")
    assert got == ["Type a medicine name first.", "That is too short for a medicine name.", "Use letters and digits only.",
                   "That is too long for a medicine name (60 characters at most).",
                   "That is too many words for a medicine name (8 at most).", "", ""]


def test_a_failed_check_is_one_honest_sentence():
    got = _node('[RxState.errorText({aborted:true}), RxState.errorText({status:500,message:"boom"}), RxState.errorText(new TypeError("x")),'
                ' RxState.errorText({status:422,message:"Request failed (422)"}), RxState.errorText({status:400,message:"row.instructions is longer than 600 characters"})]')
    assert got == ["The check took too long and was stopped.", "The server answered 500 (boom).", "Could not reach the server.",
                   "The server answered 422.", "The server answered 400 (row.instructions is longer than 600 characters)."]


def test_the_pane_width_comes_from_the_element_that_scrolls_minus_its_padding():
    wide = '{sheetClient:777,sheetPadL:"16px",sheetPadR:"16px",tableClient:322,tablePadL:"0px",tablePadR:"0px",tableOverflowX:"%s",tableDisplay:"%s"}'
    got = _node("[" + ",".join("RxState.paneWidth(" + wide % a + ")" for a in [("visible", "table"), ("auto", "block"), ("auto", "table"), ("visible", "block")]) + ", RxState.paneWidth(), RxState.paneWidth({sheetClient:-5})]")
    assert got[0] == {"scroller": "sheet", "width": 745}                      # 777 - 32 padding
    assert got[1] == {"scroller": "table", "width": 322}                      # under 600px table.rx scrolls itself
    assert got[2]["scroller"] == "sheet" and got[3]["scroller"] == "sheet"    # both overflow:auto and display:block are needed
    assert got[4] == {"scroller": "sheet", "width": 0} and got[5]["width"] == 0   # never negative


def test_the_panel_follows_the_spell_it_contract():
    raw = _read("rxview.js")
    js = _code("rxview.js")
    for token in ('"/api/v1/rx/check-row"', "age_sex: ", "transcript: ", 'setAttribute("aria-expanded"', "Checking this medicine...",
                  "Say the letters (later)", "later.disabled = true", "e.stopPropagation()", 'e.key === "Escape"', "The row is unchanged.", "r.req !== tok",
                  'H.pushUndo({ type: "respell"', '"rx-spell-row no-print"', '"Did you mean"', "H.transcript()", "H.ageSex()"):
        assert token in js, token
    assert "innerHTML" not in raw and "Sounds like" not in raw
    assert "bound !== H.body" in js and js.count('H.body.addEventListener("keydown", onKey)') == 1 and js.count('H.body.addEventListener("click", onClick)') == 1
    assert "return { init, attach, renderRow, sync, onEdit, meta, wire, reasonFor, restore, isBlank };" in js


def test_the_page_hands_over_the_spell_hooks_and_undo_restores_the_row():
    app = _code("app.js")
    for token in ("RxView.restore(r)", "post: postJson, snapshot: snapshotRow, pushUndo: setUndo", "transcript: () => state.transcript", 'ageSex: () => text($("pAge"))'):
        assert token in app, token
    branch = app.split('r.type === "respell"')[1].split("} else {")[0]
    assert "refreshBlockPanel()" in branch and "updateGrounding()" in branch and branch.index("RxView.restore(r)") < branch.index("updateGrounding()")
    html = _read("index.html")
    assert re.search(r"rxstate\.js\?v=2\b", html) and re.search(r"rxview\.js\?v=2\b", html) and re.search(r"rx\.css\?v=2\b", html) and "app.js?v=28" in html
    css = _read("rx.css")
    assert "#sheet.view-only .rx-spell-row" in css and ".rx-spin { animation:none; }" in css
    assert "--rx-focus" not in css and "outline:3px solid var(--accent)" in css.split(".rx-spell-row input:focus-visible")[1].split("\n")[0]


def test_the_spell_panel_stays_in_the_visible_pane_and_its_buttons_wrap():
    css = re.sub(r"/\*.*?\*/", "", _read("rx.css"), flags=re.S)
    box = re.search(r"\.rx-spell-box\s*\{([^}]*)\}", css).group(1)
    assert "position:sticky" in box and "left:0" in box and "width:var(--rx-pane" in box and "max-width:100%" in box
    assert re.search(r"\.rx-sugs,\s*\.rx-spell-line\s*\{[^}]*flex-wrap:wrap", css)
    cellrule = re.search(r"(?m)^table\.rx \.rx-spell-row td\s*\{([^}]*)\}", css)           # must outrank styles.css "table.rx td { padding:6px }"
    assert cellrule and "padding:0" in cellrule.group(1)                                    # the padding moves to the box, so it lines up with the pane edge
    assert "border-left:0" in cellrule.group(1) and "border-right:0" in cellrule.group(1)  # no side border: the box is exactly the pane wide
    assert re.search(r"table\.rx td\s*\{[^}]*padding:\s*6px", re.sub(r"/\*.*?\*/", "", _read("styles.css"), flags=re.S))   # the rule we outrank still exists
    js = _code("rxview.js")
    assert 'setProperty("--rx-pane", w + "px")' in js and '$("sheet")' in js and 'querySelector("table.rx")' in js and "RxState.paneWidth({" in js
    assert "paneObs = new ResizeObserver(paneWidth)" in js and "paneObs.observe(s)" in js and "paneObs.observe(t)" in js and "window.ResizeObserver && !paneObs" in js
    assert js.count("paneWidth()") >= 3 and 'el("div", "rx-spell-box")' in js              # defined, called from topbarHeight (resize) and on open
    assert len(_read("rx.css").splitlines()) < 500
