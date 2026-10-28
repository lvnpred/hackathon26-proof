"""Plan I2-a, page: the generic line (printable), the generic tag (screen only) and the one-tap Did you mean. Node fake DOM."""
from test_frontend_rxspell import _node
from test_frontend_rxspell_dom import _run

DYM = '{ did_you_mean: "Cetirizine", did_you_mean_generic: "Cetirizine" }'


def test_the_generic_line_prints_under_a_brand_and_a_generic_row_gets_a_screen_tag():
    r = _run("""
      const b = mkRow("g1", "verified", { form: "Tab.", name: "Crocin", strength: "500 mg" }, { generic: "Paracetamol" });
      const g = mkRow("g2", "verified", { name: "cetirizine" }, { generic: "Cetirizine" });
      const u = mkRow("g3", "unknown-medicine", { name: "Zzqxwv" }, {});
      const h = mkRow("g4", "verified", { name: "Evil" }, { generic: "<b>x</b>" });
      const e = mkRow("g5", "verified", {}, { generic: "Paracetamol" });                       // a blank row: nothing typed
      const pick = (tr, s) => tr.querySelectorAll(s).map((n) => [n.textContent, n.className]);
      console.log(JSON.stringify({ b: [pick(b, ".rx-gen"), pick(b, ".rx-gen-tag")], g: [pick(g, ".rx-gen"), pick(g, ".rx-gen-tag")],
        u: [pick(u, ".rx-gen"), pick(u, ".rx-gen-tag")], h: pick(h, ".rx-gen")[0][0], e: [pick(e, ".rx-gen"), pick(e, ".rx-gen-tag")] }));""")
    assert r["b"] == [[["generic: Paracetamol", "rx-sub rx-gen"]], []]                 # no no-print: the browser print shows it too (genericedit.js)
    assert r["g"] == [[], [["generic", "rx-extra rx-gen-tag no-print"]]]               # the same name, any case: a tag, no line
    assert r["u"] == [[], []] and r["h"] == "generic: <b>x</b>"                        # textContent: shown as text, never markup
    assert r["e"] == [[], []]                                                          # blank row: no line and no tag


def test_the_generic_tag_sits_directly_after_the_name_not_after_the_strength():
    r = _run("""
      const tr = mkRow("t1", "verified", { form: "Tab.", name: "cetirizine", strength: "10 mg" }, { generic: "Cetirizine" });
      const med = tr.querySelector("td"); ["form", "name", "strength"].forEach((c) => med.appendChild(cell(tr, c)));   // the real page keeps the three spans in td.med
      RxView.renderRow(tr);
      const order = () => med.children.map((c) => c.dataset.col || c.className);
      const first = order(); RxView.renderRow(tr);                                     // a re-render keeps one tag, in the same place
      console.log(JSON.stringify({ first, again: order() }));""")
    want = ["form", "name", "rx-extra rx-gen-tag no-print", "strength"]
    assert r["first"] == want and r["again"] == want


def test_did_you_mean_is_one_tap_through_the_spell_it_flow_and_answers_the_name_only():
    r = _run("""
      const tr = mkRow("d1", "unknown-medicine", { name: "Citrizene", strength: "10 mg", dose: "0-0-1" }, @DYM@);
      const idle = [cell(tr, "name").textContent, posts.length, confirmed.has("d1"), undos.length];   // shown, never applied by itself
      const b = tr.querySelector('[data-action="dym"]');
      const shown = [b.textContent, b.attrs["aria-label"]];
      click(b); const sent = posts[0].body.row, url = posts[0].url;
      await reply({ name: "Cetirizine", status: "unverified-name", lexicon_match: "Cetirizine", generic: "Cetirizine", instructions: "" });
      const pick = (t, s) => t.querySelectorAll(s).map((n) => n.textContent);
      const genAfter = [pick(tr, ".rx-gen"), pick(tr, ".rx-gen-tag")];               // a tap on a generic name: the tag, whatever the status
      const after = [cell(tr, "name").textContent, cell(tr, "dose").textContent, confirmed.has("d1"), tr._rx.how, undos.length, !!tr.querySelector('[data-action="dym"]')];
      const t2 = mkRow("d2", "unknown-medicine", { name: "Croissin" }, { did_you_mean: "Crocin", did_you_mean_generic: "Paracetamol" });
      const two = t2.querySelector('[data-action="dym"]').textContent;
      click(t2.querySelector('[data-action="dym"]')); const sent2 = posts[0].body.row.name; await reply({ name: "Crocin", status: "unknown-medicine", instructions: "" });
      const t5 = mkRow("d5", "unknown-medicine", { name: "Croissin" }, { did_you_mean: "Crocin", did_you_mean_generic: "Paracetamol" });
      click(t5.querySelector('[data-action="dym"]'));                                   // what check-row sends for a name nobody dictated
      await reply({ name: "Crocin", status: "unverified-name", lexicon_match: "Paracetamol", generic: "Paracetamol", instructions: "" });
      const brandAfter = [pick(t5, ".rx-gen"), pick(t5, ".rx-gen-tag"), confirmed.has("d5")];
      const t3 = mkRow("d3", "unknown-medicine", { name: "Citrizene" }, @DYM@);                       // the check fails: the row stays as it was
      const u0 = undos.length;
      click(t3.querySelector('[data-action="dym"]')); posts.shift().rej(Object.assign(new Error("boom"), { status: 500 })); await tick();
      const failed = [cell(t3, "name").textContent, confirmed.has("d3"), !!t3.querySelector('[data-action="dym"]'), t3._rx.note, undos.length - u0];
      const t4 = mkRow("d4", "unknown-medicine", { name: "Citrizene" }, @DYM@);                       // a hand edit while the check is pending wins
      click(t4.querySelector('[data-action="dym"]')); RxView.onEdit(t4, cell(t4, "name")); cell(t4, "name").textContent = "Citrizen";
      await reply({ name: "Cetirizine", status: "verified", lexicon_match: "Cetirizine", instructions: "" });
      const raced = [cell(t4, "name").textContent, confirmed.has("d4"), undos.length - u0];
      console.log(JSON.stringify({ genAfter, brandAfter, idle, shown, url, sent: [sent.name, sent.dose, sent.strength], after, two, sent2, open: [confirmed.has("d2"), t2._rx.note], failed, raced }));""".replace("@DYM@", DYM))
    assert r["idle"] == ["Citrizene", 0, False, 0]
    assert r["shown"] == ["Did you mean Cetirizine?", "Did you mean Cetirizine? Use it for this row"] and r["url"] == "/api/v1/rx/check-row"
    assert r["sent"] == ["Cetirizine", "0-0-1", "10 mg"] and r["two"] == "Did you mean Crocin?generic: Paracetamol"
    assert r["genAfter"] == [[], ["generic"]] and r["brandAfter"] == [["generic: Paracetamol"], [], True]
    assert r["sent2"] == "Crocin"                                                         # the suggested spelling goes, not its generic
    assert r["after"] == ["Cetirizine", "0-0-1", True, "spell", 1, False]               # confirmed before the render, Undo pushed
    assert r["open"] == [False, 'Name changed to "Crocin". It still needs your decision.']   # a name the list still does not know stays open
    assert r["failed"] == ["Citrizene", False, True, "The medicine check is not available right now. The row is unchanged.", 0]
    assert r["raced"] == ["Citrizen", False, 0]                                           # the late answer is dropped


def test_did_you_mean_is_off_when_confirmed_view_only_working_or_after_a_name_edit():
    r = _run("""
      const m = @DYM@, has = (tr) => !!tr.querySelector('[data-action="dym"]');
      const a = mkRow("e1", "unknown-medicine", { name: "Citrizene" }, m); confirmed.add("e1"); RxView.renderRow(a);
      const v = mkRow("e2", "unknown-medicine", { name: "Citrizene" }, m);
      globalThis.Authorship = { isViewOnly: () => true }; RxView.renderRow(v);
      const vo = v.querySelector('[data-action="dym"]').disabled; click(v.querySelector('[data-action="dym"]')); const voPosts = posts.length; RxView.sync(); const voSync = v.querySelector('[data-action="dym"]').disabled;
      globalThis.Authorship = undefined; flags.working = true; click(v.querySelector('[data-action="dym"]')); const busyPosts = posts.length; flags.working = false;
      const same = mkRow("e3", "unknown-medicine", { name: "cetirizine" }, m);
      const ed = mkRow("e4", "unknown-medicine", { name: "Citrizene" }, m); const before = has(ed); RxView.onEdit(ed, cell(ed, "name")); RxView.renderRow(ed);
      const w = mkRow("e5", "unknown-medicine", { name: "Citrizene" }, m), wb = w.querySelector('[data-action="dym"]');
      const idle = [wb.disabled, wb.attrs["aria-disabled"]];
      flags.working = true; RxView.sync(); const busy = [wb.disabled, wb.attrs["aria-disabled"]];
      flags.working = false; RxView.sync(); const back = [wb.disabled, wb.attrs["aria-disabled"]];
      flags.working = true; RxView.renderRow(w); const rendered = [w.querySelector('[data-action="dym"]').disabled]; flags.working = false;
      console.log(JSON.stringify([has(a), vo, voPosts, busyPosts, has(same), before, has(ed), idle, busy, back, rendered, voSync]));""".replace("@DYM@", DYM))
    assert r[:7] == [False, True, 0, 0, False, True, False]
    assert r[7:] == [[False, "false"], [True, "true"], [False, "false"], [True], True]       # disabled and aria-disabled follow state.working, and come back


def test_row_state_offers_did_you_mean_only_for_an_unknown_name_and_a_name_edit_clears_it():
    got = _node('[["unknown-medicine","Citrizene"],["unverified-name","Citrizene"],["verified","Citrizene"],["unknown-medicine","CETIRIZINE"]]'
                '.map(([s, n]) => RxState.rowState({status: s, name: n, did_you_mean: "Cetirizine", did_you_mean_generic: "Cetirizine"}, {}).didYouMean)'
                '.concat([RxState.afterEdit({did_you_mean: "X", did_you_mean_generic: "Y"}, "name"), RxState.afterEdit({did_you_mean: "X", did_you_mean_generic: "Y"}, "dose"),'
                ' RxState.metaOf({did_you_mean: "X", did_you_mean_generic: 5}), RxState.sameName(" Cetirizine", "cetirizine "),'
                ' RxState.rowState({status: "unknown-medicine", name: "Citrizene", did_you_mean: "Cetirizine"}, {confirmed: true}).didYouMean])')
    assert got[:4] == [{"name": "Cetirizine", "generic": "Cetirizine"}, None, None, None]
    assert (got[4]["did_you_mean"], got[4]["did_you_mean_generic"]) == ("", "") and got[5]["did_you_mean"] == "X"
    assert (got[6]["did_you_mean"], got[6]["did_you_mean_generic"]) == ("X", "5") and got[7] is True
    assert got[8] is None                                                                  # confirmed by the doctor: no suggestion left


def test_the_generic_styles_are_muted_the_pill_stacks_and_the_tag_stays_in_one_piece():
    import re
    from pathlib import Path
    css = re.sub(r"/\*.*?\*/", "", (Path(__file__).resolve().parents[1] / "frontend" / "rx.css").read_text(encoding="utf-8"), flags=re.S)
    rule = lambda sel: re.search(r"(?m)^" + re.escape(sel) + r"\s*\{([^}]*)\}", css).group(1)
    assert "color:var(--rx-muted)" in rule(".rx-gen") and "#0e5a6e" not in rule(".rx-gen")      # sub-text grey (5.8:1 or more on every row tint), not teal
    assert css.index(".rx-gen { color") < css.index("@media print { .rx-gen")                  # the print rule (#444) still wins
    pill = rule(".rx-act.sug")
    for want in ("flex-direction:column", "align-items:flex-start", "padding:6px 14px", "border-radius:14px", "min-height:44px", "max-width:100%"):
        assert want in pill, want
    tag = rule(".rx-gen-tag")
    assert "white-space:nowrap" in tag and "display:inline-block" in tag
    assert re.search(r"\.rx-gen-tag \+ \.cell::before\s*\{\s*content:\" \"", css)           # the space between name and strength survives the tag


def test_a_combination_row_shows_a_screen_only_add_generic_button_and_never_a_generic_line():
    r = _run("""
      const c = mkRow("c1", "unknown-medicine", { name: "Zerodol-P" }, { combo_base: "Zerodol" });
      const k = mkRow("c2", "verified", { name: "Crocin" }, { generic: "Paracetamol", generic_source: "lexicon" });
      const pick = (tr, s) => tr.querySelectorAll(s).map((n) => [n.textContent, n.className]);
      console.log(JSON.stringify({ c: [pick(c, ".rx-gen"), pick(c, ".rx-add-gen")], k: pick(k, ".rx-add-gen"),
        reason: RxView.reasonFor(c), title: c.querySelector(".rx-add-gen").attrs.title }));""")
    assert r["c"] == [[], [["Add generic", "rx-act mini no-print rx-add-gen"]]] and r["k"] == []     # plan g task 7: a button in the generic line
    assert r["reason"] == '"Zerodol-P" is a combination of Zerodol. Its generic is not in the medicine list.'
    assert r["title"] == "A combination of Zerodol: add its generic"


def test_the_script_pins_for_the_add_generic_tag():
    html = open("frontend/index.html").read()
    assert "rxstate.js?v=14" in html and "rxview.js?v=20" in html and "genericedit.js?v=3" in html
