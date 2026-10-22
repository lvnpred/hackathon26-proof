"""The Undo on a row whose name the doctor spelled over words that only sounded like it (core/spelled.py). The rules in
frontend/rxstate.js run under node; the wiring in rxview.js is checked as text, like the other frontend tests."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def _node(expr):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = "globalThis.window = globalThis; require(process.argv[1]); console.log(JSON.stringify(" + expr + "))"
    out = subprocess.run([node, "-e", script, str(FRONT / "rxstate.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _undo(row, confirmed=False):
    return _node(f"RxState.rowState({json.dumps(row)},{{confirmed:{json.dumps(confirmed)}}}).spelledUndo")


def test_a_spelled_row_offers_the_heard_words_back_in_every_state():
    row = {"status": "verified", "name": "Silodal", "spelled_heard": "Cello dial"}
    assert _undo(row) == {"heard": "Cello dial"}
    assert _undo({**row, "status": "unknown-medicine"}) == {"heard": "Cello dial"}
    assert _undo(row, confirmed=True) == {"heard": "Cello dial"}


def test_no_undo_without_heard_words_or_when_they_are_the_name():
    assert _undo({"status": "verified", "name": "Silodal"}) is None
    assert _undo({"status": "verified", "name": "Silodal", "spelled_heard": " silodal "}) is None
    assert _undo({"status": "verified", "name": "Silodal", "spelled_heard": ["Cello dial"]}) is None   # not a string


def test_the_heard_words_are_kept_as_row_meta_and_a_name_edit_drops_them():
    got = _node('[RxState.metaOf({spelled_heard: "Cello dial"}).spelled_heard,'
                ' RxState.afterEdit(RxState.metaOf({spelled_heard: "Cello dial"}), "name").spelled_heard,'
                ' RxState.afterEdit(RxState.metaOf({spelled_heard: "Cello dial"}), "dose").spelled_heard]')
    assert got == ["Cello dial", "", "Cello dial"]


def test_the_undo_button_checks_the_heard_words_like_a_typed_name():
    js = _read("rxview.js")
    assert '"spelled-undo", \'Heard "\' + h + \'" · Undo\'' in js and "b.dataset.value = h" in js
    assert 'a === "dym" || a === "spelled-undo") useName(tr, b.dataset.value)' in js
    assert '[data-action="spelled-undo"]' in js.split("function sync()")[1].split("function bodyFor")[0]   # dead while busy
    assert js.index("st.spelledUndo") < js.index('"Confirm as is"')


def test_the_page_sends_the_heard_words_back_so_a_correction_keeps_the_undo():
    wire = _read("rxview.js").split("const wire = (tr) => {")[1].split("return w;")[0]
    assert "if (s(m.spelled_heard)) w.spelled_heard = m.spelled_heard;" in wire


def test_the_changed_scripts_are_re_fetched():
    html = _read("index.html")
    assert "rxstate.js?v=12" in html and "rxview.js?v=15" in html
