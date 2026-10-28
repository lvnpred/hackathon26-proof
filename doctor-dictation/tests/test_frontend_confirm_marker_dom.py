"""Plan I2-c fix round H (page): once the doctor confirms the name, the "[unverified: confirm with doctor]" text leaves the Instructions cell."""
from test_frontend_rxspell import _node
from test_frontend_rxspell_dom import _run

MARK = "[unverified: confirm with doctor]"


def test_strip_marker_removes_exactly_that_text_and_its_separator():
    got = _node('["after food [unverified: confirm with doctor]", "[unverified: confirm with doctor]", "a [unverified: confirm with doctor] b", "x [unverified strength: confirm with doctor]",'
                ' "keep  two spaces", "", null, "[Unverified: confirm with doctor]", "x [unverified: confirm with doctor] [unverified: confirm with doctor]"].map(RxState.stripMarker)')
    assert got == ["after food", "", "a b", "x", "keep  two spaces", "", "", "[Unverified: confirm with doctor]", "x"]


def test_use_this_and_did_you_mean_remove_the_marker_only_when_the_name_is_confirmed_and_undo_brings_it_back():
    r = _run("""
      const instr = (t) => cell(t, "instructions").textContent;
      const a = mkRow("h1", "unknown-medicine", { name: "Zyloprim", instructions: "mine" });
      await openPanel(a); await useTyped("Prednisolone");
      await reply({ name: "Prednisolone", status: "verified", lexicon_match: "Prednisolone", instructions: "mine @M@" });
      const yes = [confirmed.has("h1"), instr(a)];
      const b = mkRow("h2", "unknown-medicine", { name: "Zyloprim" });
      await openPanel(b); await useTyped("Zzqxwv");
      await reply({ name: "Zzqxwv", status: "unknown-medicine", instructions: "@M@" });             // a name nothing knows stays open: the marker stays
      const stay = [confirmed.has("h2"), instr(b)];
      const c = mkRow("h3", "unknown-medicine", { name: "Citrizene" }, { did_you_mean: "Cetirizine", did_you_mean_generic: "Cetirizine" });
      click(c.querySelector('[data-action="dym"]')); await reply({ name: "Cetirizine", status: "unverified-name", lexicon_match: "Cetirizine", instructions: "@M@" });
      const dym = [confirmed.has("h3"), instr(c)];
      RxView.restore(undos[0].rec);
      console.log(JSON.stringify({ yes, stay, dym, undo: [cell(a, "name").textContent, instr(a), confirmed.has("h1")] }));""".replace("@M@", MARK))
    assert r["yes"] == [True, "mine"] and r["stay"] == [False, MARK] and r["dym"] == [True, ""]
    assert r["undo"] == ["Zyloprim", "mine", False]


def test_strip_marker_removes_either_grounding_marker_from_a_row():
    r = _run("""
      const t = mkRow("h4", "unknown-medicine", { name: "Zyloprim", instructions: "x @M@" }), u = mkRow("h5", "unverified-strength", { name: "Amlodipine", instructions: "y [unverified strength: confirm with doctor]" });
      const changed = [RxView.stripMarker(t), RxView.stripMarker(t), RxView.stripMarker(u)];
      console.log(JSON.stringify({ changed, t: cell(t, "instructions").textContent, u: cell(u, "instructions").textContent }));""".replace("@M@", MARK))
    assert r == {"changed": [True, False, True], "t": "x", "u": "y"}


def test_the_confirm_button_handler_strips_the_marker_only_when_it_confirms():
    from pathlib import Path
    app = (Path(__file__).resolve().parents[1] / "frontend" / "app.js").read_text(encoding="utf-8")
    handler = app.split('[data-action="confirm"]')[1].split("function refreshBlockPanel")[0]
    assert "state.confirmed.delete(rowid);" in handler and "if (RxView.stripMarker(tr)) markDirty();" in handler
    assert handler.index("state.confirmed.add(rowid)") < handler.index("RxView.stripMarker(tr)") < handler.index("renderCheck(tr)")
    assert handler.index("state.confirmed.delete(rowid)") < handler.index("else {")                      # Reopen (delete) never strips or re-adds


SMARK = "[unverified strength: confirm with doctor]"


def test_a_chip_tap_strips_the_strength_marker_but_a_dose_check_chip_does_not_and_free_text_stays():
    r = _run("""
      const instr = (t) => cell(t, "instructions").textContent;
      const a = mkRow("c1", "unverified-strength", { name: "Amlodipine", strength: "15 mg", instructions: "after food @S@" }, { strength_options: ["5 mg", "10 mg"] });
      click(a.querySelector('[data-action="chip"]'));
      const tapped = [confirmed.has("c1"), instr(a), cell(a, "strength").textContent];
      const d = mkRow("c2", "dose-check", { name: "Metformin", strength: "500 mg", instructions: "x @S@" }, { dose_note: "3000 mg a day", strength_options: ["500 mg", "850 mg"] });
      click(d.querySelectorAll('[data-action="chip"]')[1]);
      const dose = [confirmed.has("c2"), instr(d)];
      const f = mkRow("c3", "unverified-strength", { name: "Amlodipine", strength: "15 mg", instructions: "I am unverified, confirm with doctor [ok]" }, { strength_options: ["5 mg"] });
      click(f.querySelector('[data-action="chip"]'));
      console.log(JSON.stringify({ tapped, dose, free: instr(f) }));""".replace("@S@", SMARK))
    assert r["tapped"][0] is True and r["tapped"][1] == "after food" and r["tapped"][2] in ("5 mg", "10 mg")
    assert r["dose"] == [False, "x " + SMARK]                                  # a dose chip does not confirm: nothing is stripped
    assert r["free"] == "I am unverified, confirm with doctor [ok]"            # only the exact marker goes


def test_the_page_changed_hook_runs_after_a_chip_strips_so_the_edit_is_saved():
    r = _run("""
      let changes = 0; RxView.init({ body: tbody, saveBtn: { textContent: "", disabled: false }, confirmed: () => confirmed, working: () => false, changed() { changes++; }, hasSheet: () => true,
        transcript: () => "", ageSex: () => "", post: () => new Promise(() => {}), notify() {}, snapshot: () => ({}), pushUndo() {} });
      const a = mkRow("c4", "unverified-strength", { name: "Amlodipine", strength: "15 mg", instructions: "@S@" }, { strength_options: ["5 mg"] });
      click(a.querySelector('[data-action="chip"]'));
      console.log(JSON.stringify({ changes, instr: cell(a, "instructions").textContent }));""".replace("@S@", SMARK))
    assert r == {"changes": 1, "instr": ""}


def test_the_row_buttons_name_themselves_with_their_visible_text_first():
    r = _run("""
      const u = mkRow("l1", "unknown-medicine", { name: "Citrizene" }), v = mkRow("l2", "unverified-name", { name: "Zyloprim" });
      const lab = (tr, a) => tr.querySelector('[data-action="' + a + '"]');
      console.log(JSON.stringify({ spell: [lab(u, "spell").attrs["aria-label"], lab(u, "spell").textContent], confirm: [lab(v, "confirm").attrs["aria-label"], lab(v, "confirm").textContent] }));""")
    assert r["spell"] == ["Spell it: Citrizene", "Spell it"] and r["confirm"] == ["Confirm as is: Zyloprim", "Confirm as is"]
    assert r["spell"][0].startswith(r["spell"][1]) and r["confirm"][0].startswith(r["confirm"][1])      # label in name: the visible words lead
