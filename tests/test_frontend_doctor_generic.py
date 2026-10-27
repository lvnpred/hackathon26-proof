"""Page row rules for a doctor-entered generic (plan g, task 6): rxstate.js and rxview.js under node, app.js as text."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def _run(expr, *files):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = "globalThis.window = globalThis; process.argv.slice(1).forEach(require); console.log(JSON.stringify(" + expr + "))"
    out = subprocess.run([node, "-e", script, *[str(FRONT / f) for f in files]], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _state(expr):
    return _run(expr, "rxstate.js")


def _view_node(expr):
    return _run(expr, "rxstate.js", "rxview.js")


def test_pending_doctor_generic_turns_a_matched_row_into_confirm_generic():
    r = _state("""RxState.rowState({status: "verified", generic_pending: true, generic: "A + B"}, {})""")
    assert (r["state"], r["label"], r["canSpell"], r["needsYou"]) == ("confirm", "Confirm generic", True, True)
    assert r["reason"] == "You entered the generic A + B. Confirm the row before saving."
    assert _state("""RxState.rowState({status: "verified", source: "clinic", generic_pending: true}, {}).state""") == "confirm"
    assert _state("""RxState.rowState({status: "verified", generic_pending: true}, {confirmed: true}).state""") == "you"
    assert _state("""RxState.rowState({status: "dose-check", generic_pending: true, dose_note: "n"}, {}).state""") == "dose"
    assert _state("""RxState.rowState({status: "verified", generic_pending: "yes"}, {}).state""") == "ok"


def test_a_row_that_needs_you_for_another_reason_names_its_pending_generic_too():   # final review I1
    r = _state("""RxState.rowState({status: "unknown-medicine", name: "Zerodol-P", generic_pending: true, generic: "A + B"}, {})""")
    assert (r["state"], r["label"]) == ("confirm", "Confirm medicine")
    assert r["reason"] == '"Zerodol-P" is not in the medicine list. The generic A + B was entered for it.'
    r = _state("""RxState.rowState({status: "dose-check", generic_pending: true, generic: "A", dose_note: "n"}, {})""")
    assert r["reason"] == "n The generic A was entered for it."
    plain = _state("""RxState.rowState({status: "unknown-medicine", name: "Zerodol-P", generic: "A + B"}, {}).reason""")
    assert plain == '"Zerodol-P" is not in the medicine list.'
    assert _state("""RxState.metaOf({generic_listed: "Paracetamol"}).generic_listed""") == "Paracetamol"


def test_a_name_edit_drops_every_generic_field():
    m = _state("""RxState.afterEdit(RxState.metaOf({generic: "A", generic_source: "doctor", generic_pending: true,
                   generic_suggestion: "S", generic_suggestion_unknown: ["S"]}), "name")""")
    assert (m["generic"], m["generic_source"], m["generic_pending"], m["generic_suggestion"], m["generic_suggestion_unknown"]) == ("", "", False, "", [])
    assert (m["generic_listed"], m["remember_generic"]) == ("", False)


def test_a_non_name_edit_keeps_the_doctor_generic():
    m = _state("""RxState.afterEdit(RxState.metaOf({generic: "A", generic_source: "doctor", generic_pending: true}), "dose")""")
    assert (m["generic"], m["generic_source"], m["generic_pending"]) == ("A", "doctor", True)


def test_metaof_defaults_missing_generic_keys():
    m = _state("""RxState.metaOf({status: "verified"})""")
    assert (m["generic_suggestion"], m["generic_suggestion_unknown"], m["generic_pending"]) == ("", [], False)
    m = _state("""RxState.metaOf({generic_suggestion: 5, generic_suggestion_unknown: "x", generic_pending: "true"})""")
    assert (m["generic_suggestion"], m["generic_suggestion_unknown"], m["generic_pending"]) == ("5", [], False)


def test_wire_sends_a_doctor_generic_and_a_suggestion_only():
    r = _view_node("""(() => { const a = {}, b = {}; RxView.attach(a, {generic: "A + B", generic_source: "doctor", generic_pending: true});
                       RxView.attach(b, {generic: "Pantoprazole", generic_source: "lexicon", generic_suggestion: "S"});
                       return [RxView.wire(a), RxView.wire(b)]; })()""")
    assert r[0] == {"heard": "", "lookalike": "", "generic": "A + B", "generic_source": "doctor", "generic_pending": True}
    assert list(r[0])[:2] == ["heard", "lookalike"]
    assert r[1] == {"heard": "", "lookalike": "", "generic_suggestion": "S"}


_FAKE = """(() => {
  const cell = (t) => ({ textContent: t });
  const mk = (id, name, meta, status) => ({ dataset: { rowid: id, status }, _rx: { meta: RxState.metaOf(meta), how: "" },
    querySelector: (q) => { const m = /data-col="(\\w+)"/.exec(q); return m && m[1] === "name" ? cell(name) : null; } });
  const confirmed = new Set(["r3"]);
  document = { getElementById: () => ({ children: [1] }), querySelector: () => null, fonts: null, documentElement: { style: { setProperty() {} } } };
  RxView.init({ body: { addEventListener() {}, querySelectorAll: () => [] }, confirmed: () => confirmed });
  const rows = [mk("r1", "Pan", { generic: "A", generic_source: "doctor", generic_pending: true }, "verified"),
                mk("r2", "Pan", {}, "verified"), mk("r3", "Pan", { generic_pending: true }, "verified"), mk("r4", "", {}, "")];
  return rows.map((tr) => RxView.needsYou(tr)).concat([RxView.blockReason(rows[2], { generic: "invalid" }), RxView.blockReason(rows[0], { generic: "invalid" })]);
})()"""


def test_needs_you_and_block_reason_follow_the_row_state():
    r = _view_node(_FAKE)
    assert r[:4] == [True, False, False, False]
    assert r[4] == "The generic you entered was not accepted. Edit it or clear it."
    assert "You entered the generic A" in r[5]


def test_open_rows_and_the_block_panel_use_the_same_predicate_as_the_bar():
    app = _read("app.js")
    assert "RxView.needsYou(tr)" in app.split("function openRows()")[1].split("}")[0]
    panel = app.split("function refreshBlockPanel()")[1].split("\n}")[0]
    assert "RxView.blockStands(tr, b)" in panel and "RxView.blockReason(rowTr, b)" in panel   # a confirmed row blocked on its generic stays listed (task 7: while it stands)
    assert "if (needsYou(tr)) needs++" in _read("rxview.js")


def test_pins_are_bumped():
    html = _read("index.html")
    assert re.search(r"rxstate\.js\?v=13\b", html) and re.search(r"rxview\.js\?v=18\b", html) and re.search(r"app\.js\?v=55\b", html)
