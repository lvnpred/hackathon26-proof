"""RxState.carryRowids (PQ-c): which prior row id each row of a correction keeps. Pure rule, run under node."""
import json
import re
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


R = lambda *names: json.dumps([{"name": n} for n in names])


def carry(ids, prior, nxt, changed):
    return _node(f"RxState.carryRowids({json.dumps(ids)},{prior},{nxt},{changed})")


def test_nothing_changed_keeps_every_id():
    assert carry(["1", "2"], R("Dolo 650", "Zyloric"), R("Dolo 650", "Zyloric"), "[]") == ["1", "2"]


def test_a_changed_row_gets_a_fresh_id():
    assert carry(["1", "2"], R("Dolo 650", "Zyloric"), R("Dolo 650", "Zyloric"), "[1]") == ["1", None]


def test_confirmation_follows_the_medicine_when_a_row_above_is_removed():
    assert carry(["1", "2", "3"], R("Pantoprazole", "Dolo 650", "Zyloric"), R("Dolo 650", "Zyloric", "Cetirizine"), "[2]") == ["2", "3", None]


def test_reordered_rows_pair_by_name():
    assert carry(["1", "2"], R("A1", "B1"), R("B1", "A1"), "[]") == ["2", "1"]


def test_same_name_rows_pair_by_occurrence_and_a_changed_one_uses_its_slot():
    assert carry(["1", "2"], R("Amlodipine", "Amlodipine"), R("Amlodipine", "Amlodipine"), "[0]") == [None, "2"]


def test_name_case_and_outer_space_do_not_matter():
    assert carry(["7"], R("dolo 650"), R(" Dolo 650 "), "[]") == ["7"]


def test_a_new_name_not_reported_as_changed_still_gets_no_id():
    assert carry(["1"], R("A1"), R("A1", "Z9"), "[]") == ["1", None]


def test_bad_changed_rows_fall_back_to_clear_all():
    for bad in ("undefined", "null", '"1"', "[1.5]", "[-1]", "[2]", "[true]", '["0"]', "{}"):
        assert carry(["1", "2"], R("A1", "B1"), R("A1", "B1"), bad) == [None, None], bad


def test_garbage_rows_and_ids_are_safe():
    assert carry(["1"], R("A1"), "null", "[]") == []
    assert carry(["1"], "null", R("A1"), "[]") == [None]
    assert carry([None, 5], R("A1", "B1"), R("A1", "B1"), "[]") == [None, None]
    assert carry(["1", "2"], R("A1", "B1"), json.dumps(["x", {"name": "B1"}]), "[]") == [None, "2"]


def test_no_id_is_ever_returned_twice():
    got = carry(["1", "2", "3"], R("A1", "A1", "A1"), R("A1", "A1", "A1", "A1"), "[]")
    ids = [g for g in got if g]
    assert ids == ["1", "2", "3"] and len(set(ids)) == len(ids)


def test_duplicate_prior_ids_are_carried_once():
    assert carry(["1", "1"], R("A1", "B1"), R("A1", "B1"), "[]") == ["1", None]


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def _code(name):
    s = re.sub(r"/\*.*?\*/", "", _read(name), flags=re.S)
    return re.sub(r"(^|[\s;{}),])//[^\n]*", r"\1", s)


def _slice(src, start, end):
    a = src.index(start)
    return src[a:src.index(end, a)]


def test_apply_correction_keeps_unchanged_confirmations():
    body = _slice(_code("app.js"), "async function applyCorrection", "function retryLast")
    assert "serializeForm()" in body and "readForm()" not in body
    assert "RxState.carryRowids(" in body and "j.changed_rows" in body and "indexToRowid" in body
    assert "state.confirmed.clear()" not in body
    assert body.index("RxState.carryRowids(") < body.index("renderSheet(state.structured, carry)")


def test_render_passes_kept_row_ids_to_rxrow():
    src = _code("app.js")
    assert re.search(r"function renderRx\(rows, rowids\)", src) and re.search(r"function renderSheet\(s, rowids\)", src)
    assert "rxRow(r, i, rowids && rowids[i])" in _slice(src, "function renderRx", "function renderCheck")
    assert "renderRx(s.rx, rowids)" in _slice(src, "function renderSheet", "const stepCounts")


def test_other_paths_still_clear_all_confirmations():
    src = _code("app.js")
    for start, end in (("async function formatTranscript", "async function applyCorrection"), ("async function openDocument", "\n}\n")):
        assert "state.confirmed.clear()" in _slice(src, start, end)


def test_pins_are_bumped():
    html = _read("index.html")
    assert int(re.search(r"rxstate\.js\?v=(\d+)", html).group(1)) >= 9
    assert int(re.search(r"app\.js\?v=(\d+)", html).group(1)) >= 38


def test_kept_rows_keep_how_and_changed_rows_do_not():
    body = _slice(_code("app.js"), "async function applyCorrection", "function retryLast")
    a, b, c = body.index("const how = {}"), body.index("renderSheet(state.structured, carry)"), body.index("_rx.how = how[")
    assert a < b < c and "carry.includes(tr.dataset.rowid)" in body[a:b] and "renderCheck(tr)" in body[c:]
