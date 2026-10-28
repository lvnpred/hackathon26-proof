"""SH-B5: a hand edit keeps the words the doctor heard (or the dictated name) so the save can learn the pair. Rules in
frontend/rxstate.js run under node."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _node(expr):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = "globalThis.window = globalThis; require(process.argv[1]); console.log(JSON.stringify(" + expr + "))"
    out = subprocess.run([node, "-e", script, str(FRONT / "rxstate.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_a_name_edit_keeps_what_was_dictated_and_the_first_keystroke_wins():
    m = _node('RxState.afterEdit(RxState.afterEdit(RxState.metaOf({name: "Urimacks", heard: ""}), "name"), "name")')
    assert m["typed_heard"] == "Urimacks" and m["heard"] == "" and m["said"] == "Urimacks"


def test_the_heard_words_win_over_the_dictated_name_and_spelled_words_win_over_both():
    a, b = _node('[RxState.afterEdit(RxState.metaOf({name: "Dolo", heard: "dollo"}), "name").typed_heard,'
                 ' RxState.afterEdit(RxState.metaOf({name: "Silodal", heard: "silodel", spelled_heard: "Cello dial"}), "name").typed_heard]')
    assert (a, b) == ("dollo", "Cello dial")                               # Review Focus 5: still one source per row


def test_a_strength_edit_keeps_the_heard_words_but_never_the_name():
    a, b = _node('[RxState.afterEdit(RxState.metaOf({name: "Dolo", heard: "dollo"}), "strength").typed_heard,'
                 ' RxState.afterEdit(RxState.metaOf({name: "Dolo", heard: ""}), "strength").typed_heard]')
    assert (a, b) == ("dollo", "")


def test_a_new_hand_added_row_has_nothing_to_carry():
    assert _node('RxState.afterEdit(RxState.metaOf(null), "name").typed_heard') == ""
    assert _node('RxState.afterEdit(undefined, "name").typed_heard') == ""


def test_the_page_loads_the_new_rxstate():
    assert "rxstate.js?v=14" in (FRONT / "index.html").read_text(encoding="utf-8")
