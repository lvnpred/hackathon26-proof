"""E2 and E3 (owner feedback batch): keyboard rhythm on a row awaiting a decision, and "Change name" on every medicine row.
frontend/rxview.js and rxstate.js run under node on the fake DOM of test_frontend_rxspell_dom.py."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from test_frontend_rxspell_dom import FRONT, _run

OPEN = 'const key = (target, k, mods) => tbody.dispatch("keydown", Object.assign({ target, key: k }, mods)); const confirmBtn = (tr) => tr.querySelector(\'button[data-action="confirm"]\');'


def _state(expr):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    out = subprocess.run([node, "-e", "globalThis.window = globalThis; require(process.argv[1]); console.log(JSON.stringify(" + expr + "))", str(FRONT / "rxstate.js")],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_after_spell_it_returns_a_row_that_still_needs_a_decision_focus_is_its_confirm_button():
    r = _run("""
      const tr = mkRow("1", "unknown-medicine", { name: "Zyloprim" });
      await openPanel(tr); await useTyped("Allopurinol");
      await reply({ name: "Allopurinol", status: "unknown-medicine", instructions: "" });
      const c = tr.querySelector('button[data-action="confirm"]');
      console.log(JSON.stringify({ onConfirm: !!c && document.activeElement === c, note: tr.querySelector(".rx-note").textContent }));""")
    assert r["onConfirm"] is True
    assert "still needs your decision" in r["note"]


def test_arrow_right_and_left_move_between_confirm_and_spell_it_and_tab_order_matches():
    r = _run(OPEN + """
      const tr = mkRow("1", "unknown-medicine", { name: "Zyloprim" });
      const acts = tr.querySelector(".rx-acts"), order = acts.children.map((b) => b.dataset.action);
      const c = confirmBtn(tr), s = spellBtn(tr), at = () => document.activeElement === c ? "confirm" : document.activeElement === s ? "spell" : "other";
      c.focus(); const out = [];
      const e1 = key(c, "ArrowRight"); out.push(at(), e1.defaultPrevented);
      key(s, "ArrowRight"); out.push(at());
      key(s, "ArrowLeft"); out.push(at());
      key(c, "ArrowLeft"); out.push(at());
      s.disabled = true; key(c, "ArrowRight"); out.push(at());
      console.log(JSON.stringify({ order, out }));""")
    assert r["order"] == ["confirm", "spell"]
    assert r["out"] == ["spell", True, "spell", "confirm", "confirm", "confirm"]


def test_arrow_keys_inside_a_medicine_cell_are_left_alone():
    r = _run(OPEN + """
      const tr = mkRow("1", "unknown-medicine", { name: "Zyloprim" });
      const c = confirmBtn(tr), n = cell(tr, "name"); c.focus();
      const e = key(n, "ArrowRight");
      console.log(JSON.stringify({ prevented: e.defaultPrevented, kept: document.activeElement === c }));""")
    assert r == {"prevented": False, "kept": True}


def test_arrow_keys_with_a_modifier_are_left_to_the_browser():
    r = _run(OPEN + """
      const tr = mkRow("1", "unknown-medicine", { name: "Zyloprim" });
      const c = confirmBtn(tr), s = spellBtn(tr); c.focus();
      const out = ["altKey", "ctrlKey", "metaKey", "shiftKey"].map((m) => {
        const e = key(s, "ArrowLeft", { [m]: true });
        return [e.defaultPrevented, document.activeElement === c];
      });
      console.log(JSON.stringify(out));""")
    assert r == [[False, True]] * 4


def test_a_settled_row_keeps_focus_on_its_state_after_a_name_change():
    r = _run("""
      const tr = mkRow("1", "unknown-medicine", { name: "Zyloprim" });
      await openPanel(tr); await useTyped("Allopurinol");
      await reply({ name: "Allopurinol", status: "verified", lexicon_match: "Allopurinol" });
      console.log(JSON.stringify(document.activeElement === tr.querySelector(".rx-state")));""")
    assert r is True


def test_every_state_offers_a_name_change_with_the_right_label():
    r = _state("""[
      RxState.rowState({status: "verified"}, {}), RxState.rowState({status: "verified", source: "clinic"}, {}),
      RxState.rowState({status: "unknown-medicine"}, {confirmed: true}), RxState.rowState({status: "dose-check", dose_note: "n"}, {}),
      RxState.rowState({status: "verified", generic_pending: true, generic: "A"}, {}), RxState.rowState({status: "unknown-medicine"}, {})
    ].map((s) => [s.canSpell, s.spellLabel])""")
    assert r == [[True, "Change name"]] * 5 + [[True, "Spell it"]]


def test_matched_row_shows_change_name_and_view_only_disables_it():
    r = _run("""
      const label = (tr) => { const b = spellBtn(tr); return b ? [b.textContent, b.disabled, b.attrs["aria-label"]] : null; };
      const m = mkRow("1", "verified", { name: "L-thyroxine" }), u = mkRow("2", "unknown-medicine", { name: "Zyloprim" }), b = mkRow("3", "", {});
      const out = [label(m), label(u), label(b)];
      window.Authorship = { isViewOnly: () => true }; RxView.renderRow(m);
      out.push(label(m)[1]);
      console.log(JSON.stringify(out));""")
    assert r == [["Change name", False, "Change name: L-thyroxine"], ["Spell it", False, "Spell it: Zyloprim"], None, True]


def test_changing_the_name_of_a_matched_row_rechecks_only_that_row():
    r = _run("""
      const run = async (id, status) => {
        const tr = mkRow(id, "verified", { name: "L-thyroxine", dose: "1-0-0" }); await openPanel(tr); await useTyped("Eltroxin");
        const body = posts[0].body.row;
        await reply({ name: "Eltroxin", status });
        return [body.name, body.dose, cell(tr, "name").textContent, confirmed.has(id), tr.dataset.rxstate, tr.querySelector(".rx-note").textContent];
      };
      console.log(JSON.stringify([await run("a", "verified"), await run("b", "unknown-medicine")]));""")
    assert r[0][:5] == ["Eltroxin", "1-0-0", "Eltroxin", True, "you"]
    assert r[1][:5] == ["Eltroxin", "1-0-0", "Eltroxin", False, "confirm"]
    assert "still needs your decision" in r[1][5]
