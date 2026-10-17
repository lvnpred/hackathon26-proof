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
    assert got == ["The check took too long and was stopped.", "The medicine check is not available right now.", "Could not reach the server.",
                   "The server answered 422.", "The server answered 400 (row.instructions is longer than 600 characters)."]


def test_a_server_fault_never_shows_a_raw_status_or_server_text_but_a_client_error_keeps_its_message():
    got = _node('[500, 502, 503, 599].map((s) => RxState.errorText({status: s, message: "Traceback: secret"})).concat('
                '[RxState.errorText({status: 499, message: "gone"}), RxState.errorText({status: 404, message: "Not found"}), RxState.errorText({status: 400, message: "row is not an object"})])')
    assert got[:4] == ["The medicine check is not available right now."] * 4
    assert got[4:] == ["The server answered 499 (gone).", "The server answered 404 (Not found).", "The server answered 400 (row is not an object)."]


def test_the_row_follows_the_spell_it_contract_through_the_modal():
    raw = _read("rxview.js")
    js = _code("rxview.js")
    for token in ('"/api/v1/rx/check-row"', "SpellModal.open(", "age_sex: ", "transcript: ", 'setAttribute("aria-expanded"', "Checking this medicine...",
                  "The row is unchanged.", "r.req !== tok", 'H.pushUndo({ type: "respell"', "H.transcript()", "H.ageSex()", 'setAttribute("aria-haspopup", "dialog")'):
        assert token in js, token
    assert "innerHTML" not in raw and "Sounds like" not in raw and "rx-spell" not in raw and "paneWidth" not in raw and "r.panel" not in js   # the inline panel is gone
    assert "bound !== H.body" in js and js.count('H.body.addEventListener("click", onClick)') == 1 and "keydown" not in js   # keys belong to the dialog now
    assert "return { init, attach, renderRow, sync, onEdit, meta, wire, reasonFor, restore, isBlank, stripMarker };" in js


def test_the_page_hands_over_the_spell_hooks_and_undo_restores_the_row():
    app = _code("app.js")
    for token in ("RxView.restore(r)", "post: postJson, snapshot: snapshotRow, pushUndo: setUndo", "transcript: () => state.transcript", 'ageSex: () => text($("pAge"))'):
        assert token in app, token
    branch = app.split('r.type === "respell"')[1].split("} else {")[0]
    assert "refreshBlockPanel()" in branch and "updateGrounding()" in branch and branch.index("RxView.restore(r)") < branch.index("updateGrounding()")
    html = _read("index.html")
    assert int(re.search(r"rxstate\.js\?v=(\d+)", html).group(1)) >= 4 and int(re.search(r"rxview\.js\?v=(\d+)", html).group(1)) >= 4 and int(re.search(r"rx\.css\?v=(\d+)", html).group(1)) >= 4 and int(re.search(r"suglist\.js\?v=(\d+)", html).group(1)) >= 2 and int(re.search(r"app\.js\?v=(\d+)", html).group(1)) >= 33 and int(re.search(r"spellmodal\.js\?v=(\d+)", html).group(1)) >= 1
    css = _read("rx.css")
    assert ".rx-spin { animation:none; }" in css and "--rx-focus" not in css
    assert "outline:3px solid var(--accent)" in css.split(".spell-item:focus-visible")[1].split("\n")[0]    # the focus ring is the accent


def test_the_spell_modal_fits_a_phone_and_its_targets_are_44px():
    css = re.sub(r"/\*.*?\*/", "", _read("rx.css"), flags=re.S)
    flat = re.sub(r"\s+", " ", css)
    for rule in ("dialog.spell-dlg { width:min(560px, calc(100vw - 32px)); max-height:calc(100vh - 2rem); overflow:hidden; }",
                 "dialog.spell-dlg[open] { display:flex; flex-direction:column; }",
                 "@supports (height:100dvh) { dialog.spell-dlg { max-height:calc(100dvh - 2rem); } }",
                 ".spell-item { min-height:44px; width:100%;", ".spell-line { display:flex; flex-wrap:wrap; gap:8px; }"):
        assert rule in flat, rule
    wrap = re.search(r"\.spell-wrap \{([^}]*)\}", flat).group(1)                        # the list scrolls, the buttons stay in view
    lst = re.search(r"\.spell-list \{([^}]*)\}", flat).group(1)
    assert "min-height:0" in wrap and "flex:1 1 auto" in wrap and "flex-direction:column" in wrap
    assert "overflow-y:auto" in lst and "min-height:0" in lst and "flex:1 1 auto" in lst
    assert re.search(r"\.spell-wrap \.panel-actions \{[^}]*flex:none", flat) and re.search(r"\.spell-pager \{[^}]*flex:none", flat)
    assert "dialog.spell-dlg { display" not in flat                                         # an unscoped display would show the closed dialog
    assert "rx-spell-box" not in css and "--rx-pane" not in css and "rx-spell" not in css and all("animation" not in ln for ln in css.splitlines() if "spell" in ln)
    assert len(_read("rx.css").splitlines()) < 500
