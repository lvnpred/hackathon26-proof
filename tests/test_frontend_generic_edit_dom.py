"""Plan g, task 7: the editable generic line, "Add generic", "AI suggests" and the Remember tick (frontend/genericedit.js).
Node fake DOM from tests/test_frontend_rxspell_dom.py; the Python validator is the reference for GenericEdit.problem."""
import json
import re
from pathlib import Path

from doctor_dictation.core import doctor_generic as G
from test_frontend_rxspell_dom import _run

FRONT = Path(__file__).resolve().parents[1] / "frontend"
LEX = '{generic: "Paracetamol", generic_source: "lexicon"}'
SUGG = '{combo_base: "Zerodol", generic_suggestion: "Aceclofenac + Paracetamol"}'


def test_typing_a_generic_marks_the_row_doctor_pending_and_unconfirmed():
    r = _run("""const tr = mkRow("g1", "verified", {name: "Crocin"}, @LEX@);
      tbody.addEventListener("input", () => { tr.dataset.status = ""; });      // what app.js's sheet listener would do to a cell edit
      confirmed.add("g1"); const s = tr.querySelector(".rx-gen-text"); s.textContent = "Paracetamol + Caffeine"; s.dispatch("input");
      console.log(JSON.stringify({m: RxView.wire(tr), c: confirmed.has("g1"), st: tr.dataset.rxstate, status: tr.dataset.status}));""".replace("@LEX@", LEX))
    assert r == {"m": {"heard": "", "lookalike": "", "generic": "Paracetamol + Caffeine", "generic_source": "doctor", "generic_pending": True},
                 "c": False, "st": "confirm", "status": "verified"}


def test_the_line_prints_its_span_is_plain_text_and_enter_blurs():
    r = _run("""const tr = mkRow("p1", "verified", {name: "Crocin"}, @LEX@);
      const line = tr.querySelector(".rx-gen"), s = tr.querySelector(".rx-gen-text");
      const shape = [line.textContent, line.className, s.contentEditable, tr.querySelector(".rx-genbox").classList.contains("rx-extra")];
      s.focus(); const k = s.dispatch("keydown", {key: "Enter"}), enter = [k.defaultPrevented, document.activeElement === s];
      document.execCommand = (cmd, ui, t) => { if (cmd !== "insertText") return false; inserted.push(t); s.textContent = t; s.dispatch("input"); return true; };
      const inserted = []; s.focus(); const pasted = s.dispatch("paste", {clipboardData: {getData: (t) => (t === "text/plain" ? "Aceclofenac\\n+ Paracetamol" : "<b>x</b>")}});
      const dropped = s.dispatch("drop");
      console.log(JSON.stringify({shape, enter, paste: pasted.defaultPrevented,
        text: [inserted, tr.querySelector(".rx-gen-text") === s, RxView.wire(tr).generic], drop: dropped.defaultPrevented}));""".replace("@LEX@", LEX))
    assert r["shape"] == ["generic: Paracetamol", "rx-sub rx-gen", "true", False]      # prints (no no-print), not an .rx-extra
    assert r["enter"] == [True, False] and r["drop"] is True
    assert r["paste"] is True and r["text"] == [["Aceclofenac + Paracetamol"], True, "Aceclofenac + Paracetamol"]   # one line of text, never markup


def test_a_focused_span_is_never_rebuilt_while_typing():
    r = _run("""const tr = mkRow("f1", "verified", {name: "Crocin"}, @LEX@);
      const s = tr.querySelector(".rx-gen-text"); s.focus(); s.textContent = "Ibuprofen"; s.dispatch("input");
      const same = tr.querySelector(".rx-gen-text") === s; RxView.renderRow(tr);
      console.log(JSON.stringify({same, again: tr.querySelector(".rx-gen-text") === s, tick: !!tr.querySelector(".rx-gen-remember"),
        pill: tr.querySelector(".rx-pill").textContent}));""".replace("@LEX@", LEX))
    assert r == {"same": True, "again": True, "tick": True, "pill": "Confirm generic"}


def test_emptying_a_doctor_generic_removes_it():
    r = _run("""const tr = mkRow("e1", "verified", {name: "Crocin"}, {generic: "Ibuprofen", generic_source: "doctor", generic_pending: true});
      const s = tr.querySelector(".rx-gen-text"); s.textContent = "  "; s.dispatch("input");
      const m = tr._rx.meta;
      console.log(JSON.stringify([m.generic, m.generic_source, m.generic_pending, RxView.wire(tr), tr.querySelectorAll(".rx-genbox").length]));""")
    assert r == ["", "", False, {"heard": "", "lookalike": ""}, 0]


def test_use_this_accepts_the_suggestion_and_type_my_own_opens_an_empty_box():
    r = _run("""const a = mkRow("s1", "unknown-medicine", {name: "Zerodol-SP"}, @SUGG@);
      const line = a.querySelector(".rx-sugg"), btns = line.querySelectorAll("button").map((b) => b.textContent);
      const text = line.querySelector(".rx-sugg-text").textContent, add = !!a.querySelector(".rx-add-gen");
      line.querySelectorAll("button")[0].dispatch("click");
      const used = [RxView.wire(a), document.activeElement === a.querySelector(".rx-state"), !!a.querySelector(".rx-sugg"), a.querySelector(".rx-gen").textContent];
      const b = mkRow("s2", "unknown-medicine", {name: "Zerodol-SP"}, @SUGG@);
      b.querySelector(".rx-sugg").querySelectorAll("button")[1].dispatch("click");
      const s = b.querySelector(".rx-gen-text"), own = [s.textContent, document.activeElement === s, !!b.querySelector(".rx-sugg"), b.querySelector(".rx-gen").className];
      s.blur();                                                                         // left empty: the suggestion comes back
      console.log(JSON.stringify({text, btns, add, used, own, back: !!b.querySelector(".rx-sugg") && !b.querySelector(".rx-gen-text")}));""".replace("@SUGG@", SUGG))
    assert r["text"] == "AI suggests: Aceclofenac + Paracetamol" and r["btns"] == ["Use this", "Type my own"] and r["add"] is False
    assert r["used"][0] == {"heard": "", "lookalike": "", "generic": "Aceclofenac + Paracetamol", "generic_source": "doctor", "generic_pending": True,
                            "generic_suggestion": "Aceclofenac + Paracetamol"}
    assert r["used"][1:] == [True, False, "generic: Aceclofenac + Paracetamol"]
    assert r["own"] == ["", True, False, "rx-sub rx-gen no-print"] and r["back"] is True


def test_add_generic_opens_an_empty_focused_box_on_a_combination_row():
    r = _run("""const c = mkRow("c1", "unknown-medicine", {name: "Zerodol-P"}, {combo_base: "Zerodol"});
      const b = c.querySelector(".rx-add-gen"); const shape = [b.tagName, b.textContent, b.className, b.attrs.title];
      b.dispatch("click"); const s = c.querySelector(".rx-gen-text");
      const opened = [s.textContent, document.activeElement === s, !c.querySelector(".rx-add-gen")];
      s.textContent = "Aceclofenac + Paracetamol"; s.dispatch("input");
      console.log(JSON.stringify({shape, opened, tick: !!c.querySelector(".rx-gen-remember"), gen: RxView.wire(c).generic}));""")
    assert r["shape"] == ["BUTTON", "Add generic", "rx-act mini no-print rx-add-gen", "A combination of Zerodol: add its generic"]
    assert r["opened"] == ["", True, True] and r["tick"] is False and r["gen"] == "Aceclofenac + Paracetamol"


def test_amber_when_a_component_is_unknown_and_the_suggestion_never_prints():
    r = _run("""const a = mkRow("a1", "unknown-medicine", {name: "Zerodol-SP"}, {generic_suggestion: "Aceclofenac + Serratiopeptidase",
        generic_suggestion_unknown: ["Serratiopeptidase"]});
      const p = mkRow("a2", "unknown-medicine", {name: "Zerodol-P"}, @SUGG@);
      const l = a.querySelector(".rx-sugg"), q = p.querySelector(".rx-sugg");
      console.log(JSON.stringify([l.className, l.attrs.title, q.className, q.attrs.title === undefined]));""".replace("@SUGG@", SUGG))
    assert r == ["rx-sugg no-print amber", "Not in the medicine list: Serratiopeptidase", "rx-sugg no-print", True]


def test_remember_tick_only_on_an_overridden_listed_generic():      # Q20
    r = _run("""const tr = mkRow("g1", "verified", {name: "Crocin"}, @LEX@), other = mkRow("g2", "verified", {name: "Dolo"}, @LEX@);
      const before = !!tr.querySelector(".rx-gen-remember");
      const s = tr.querySelector(".rx-gen-text"); s.textContent = "Paracetamol + Caffeine"; s.dispatch("input");
      const lab = tr.querySelector(".rx-remember"), cb = tr.querySelector(".rx-gen-remember");
      const shown = [lab.tagName, lab.className, lab.textContent, cb.type, cb.checked];
      const rows = [tr, other], first = GenericEdit.rememberIndexes(rows);
      tbody.addEventListener("input", () => { tr.dataset.status = ""; });
      cb.checked = true; cb.dispatch("input"); cb.dispatch("change");
      const ticked = GenericEdit.rememberIndexes(rows), reversed = GenericEdit.rememberIndexes([other, tr]);
      const c = mkRow("c1", "unknown-medicine", {name: "Zerodol-P"}, {combo_base: "Zerodol"});
      c.querySelector(".rx-add-gen").dispatch("click"); const cs = c.querySelector(".rx-gen-text"); cs.textContent = "Aceclofenac"; cs.dispatch("input");
      RxView.onEdit(tr, cell(tr, "name")); RxView.renderRow(tr);                         // a new name: the tick and the listed flag go
      console.log(JSON.stringify({before, shown, first, ticked, reversed, status: tr.dataset.status, combo: !!c.querySelector(".rx-gen-remember"),
        afterName: [GenericEdit.rememberIndexes([tr]), !!tr.querySelector(".rx-gen-remember")]}));""".replace("@LEX@", LEX))
    assert r["before"] is False and r["combo"] is False
    assert r["shown"] == ["LABEL", "rx-remember no-print", " Remember for this clinic", "checkbox", False]
    assert r["first"] == [] and r["ticked"] == [0] and r["reversed"] == [1] and r["status"] == "verified"
    assert r["afterName"] == [[], False]


def test_a_bad_generic_shows_its_problem_and_keeps_the_row_in_confirm():
    r = _run("""const tr = mkRow("b1", "verified", {name: "Crocin"}, @LEX@); confirmed.add("b1");
      const s = tr.querySelector(".rx-gen-text"); s.textContent = "Aceclofenac +"; s.dispatch("input");
      const bad = [tr.querySelector(".rx-note").textContent, tr.dataset.rxstate, !!tr.querySelector('[data-action="confirm"]'), confirmed.has("b1")];
      s.textContent = "Aceclofenac"; s.dispatch("input");
      console.log(JSON.stringify({bad, good: [tr.querySelector(".rx-note").textContent, !!tr.querySelector('[data-action="confirm"]')]}));""".replace("@LEX@", LEX))
    assert r["bad"] == [G.MESSAGES["parts"], "confirm", False, False]
    assert r["good"] == ["", True]


def test_the_refused_generic_entry_does_not_linger_once_the_generic_is_cleared_or_fixed():
    r = _run("""const mk = (id) => { const t = mkRow(id, "verified", {name: "Crocin"}, {generic: "A1", generic_source: "doctor"}); confirmed.add(id); RxView.renderRow(t); return t; };
      const b = {generic: "invalid"}, a = mk("i1"), f = mk("i2");
      const start = [RxView.blockStands(a, b), RxView.blockReason(a, b)];
      const s = a.querySelector(".rx-gen-text"); s.textContent = ""; s.dispatch("input");      // cleared: a matched row, nothing to resolve
      const cleared = RxView.blockStands(a, b);
      const t = f.querySelector(".rx-gen-text"); t.textContent = "Aceclofenac"; t.dispatch("input");
      const fixedOpen = [RxView.blockStands(f, b), RxView.blockReason(f, b)];
      confirmed.add("i2"); RxView.renderRow(f);
      console.log(JSON.stringify({start, cleared, fixedOpen, fixedConfirmed: RxView.blockStands(f, b), plain: RxView.blockStands(f, {})}));""")
    assert r["start"] == [True, "The generic you entered was not accepted. Edit it or clear it."]
    assert r["cleared"] is False
    assert r["fixedOpen"] == [True, "You entered the generic Aceclofenac. Confirm the row before saving."]
    assert r["fixedConfirmed"] is False and r["plain"] is False


def test_view_only_locks_the_line_and_every_control_refuses():
    # Task 9 fix round 1: the controls are always built (view-only can start or end after the render); a locked page gets
    # what Authorship.enforce does (data-ro), rx.css hides the buttons and the tick, and every handler refuses.
    r = _run("""globalThis.Authorship = { isViewOnly: () => true };
      const d = mkRow("v1", "verified", {name: "Crocin"}, {generic: "Ibuprofen", generic_source: "doctor", generic_listed: "Paracetamol"});
      const c = mkRow("v2", "unknown-medicine", {name: "Zerodol-P"}, {combo_base: "Zerodol"});
      const g = mkRow("v3", "unknown-medicine", {name: "Zerodol-SP"}, @SUGG@);
      const s = d.querySelector(".rx-gen-text"), labels = (t) => t.querySelectorAll("button").map((b) => b.textContent);
      const shape = {text: s.textContent, ce: [s.contentEditable, s.dataset.ro], tick: !!d.querySelector(".rx-gen-remember"),
        add: !!c.querySelector(".rx-add-gen"), sugg: g.querySelector(".rx-sugg-text").textContent, gb: labels(g.querySelector(".rx-sugg"))};
      const cb = d.querySelector(".rx-gen-remember"); cb.checked = true; cb.dispatch("change");
      c.querySelector(".rx-add-gen").dispatch("click");
      g.querySelector(".rx-sugg").querySelectorAll("button").forEach((b) => b.dispatch("click"));
      s.textContent = "Aspirin"; s.dispatch("input");
      console.log(JSON.stringify({shape, remember: d._rx.meta.remember_generic === true, open: !!c.querySelector(".rx-gen-text"),
        g: RxView.wire(g), d: [d._rx.meta.generic, d._rx.meta.generic_source]}));""".replace("@SUGG@", SUGG))
    assert r["shape"] == {"text": "Ibuprofen", "ce": ["false", "1"], "tick": True, "add": True,
                          "sugg": "AI suggests: Aceclofenac + Paracetamol", "gb": ["Use this", "Type my own"]}
    assert r["remember"] is False and r["open"] is False
    assert r["g"] == {"heard": "", "lookalike": "", "generic_suggestion": "Aceclofenac + Paracetamol"} and r["d"] == ["Ibuprofen", "doctor"]
    css = re.sub(r"/\*.*?\*/", "", (FRONT / "rx.css").read_text(encoding="utf-8"), flags=re.S)
    assert "#sheet.view-only .rx-remember, #sheet.view-only .rx-genbox button, #sheet.view-only .rx-sugg button { display:none; }" in css


def test_a_colleagues_prescription_then_your_own_has_a_working_generic_line():
    # openDocument renders before Authorship.onOpen clears view-only: your own rows are drawn while it is still set.
    r = _run("""globalThis.Authorship = { isViewOnly: () => true };
      const d = mkRow("o1", "verified", {name: "Crocin"}, @LEX@);
      const c = mkRow("o2", "unknown-medicine", {name: "Zerodol-P"}, {combo_base: "Zerodol"});
      const g = mkRow("o3", "unknown-medicine", {name: "Zerodol-SP"}, @SUGG@);
      globalThis.Authorship = { isViewOnly: () => false };                              // Authorship.clear(): data-ro spans unlock
      tbody.querySelectorAll("span").forEach((n) => { if (n.dataset.ro === "1") { n.contentEditable = "true"; delete n.dataset.ro; } });
      const s = d.querySelector(".rx-gen-text"), ce = s.contentEditable;
      s.textContent = "Paracetamol + Caffeine"; s.dispatch("input");
      c.querySelector(".rx-add-gen").dispatch("click");
      g.querySelector(".rx-sugg").querySelectorAll("button")[0].dispatch("click");
      console.log(JSON.stringify({ce, d: [d._rx.meta.generic, d._rx.meta.generic_source], open: !!c.querySelector(".rx-gen-text"),
        g: [g._rx.meta.generic, g._rx.meta.generic_source], tick: !!d.querySelector(".rx-gen-remember")}));""".replace("@LEX@", LEX).replace("@SUGG@", SUGG))
    assert r == {"ce": "true", "d": ["Paracetamol + Caffeine", "doctor"], "open": True,
                 "g": ["Aceclofenac + Paracetamol", "doctor"], "tick": True}


def test_view_only_that_starts_after_the_render_does_nothing():
    r = _run("""const c = mkRow("w1", "unknown-medicine", {name: "Zerodol-P"}, {combo_base: "Zerodol"});
      const g = mkRow("w2", "unknown-medicine", {name: "Zerodol-SP"}, @SUGG@);
      const d = mkRow("w3", "verified", {name: "Crocin"}, @LEX@);
      globalThis.Authorship = { isViewOnly: () => true };                               // app.js renders, then Authorship.onOpen locks the sheet
      c.querySelector(".rx-add-gen").dispatch("click");
      g.querySelector(".rx-sugg").querySelectorAll("button").forEach((b) => b.dispatch("click"));
      const s = d.querySelector(".rx-gen-text"); s.textContent = "Ibuprofen"; s.dispatch("input");
      console.log(JSON.stringify([!!c.querySelector(".rx-gen-text"), RxView.wire(g), !!g.querySelector(".rx-sugg"), RxView.wire(d), tr_meta(d)]));
      function tr_meta(t) { return [t._rx.meta.generic, t._rx.meta.generic_source]; }""".replace("@SUGG@", SUGG).replace("@LEX@", LEX))
    assert r == [False, {"heard": "", "lookalike": "", "generic_suggestion": "Aceclofenac + Paracetamol"}, True,
                 {"heard": "", "lookalike": ""}, ["Paracetamol", "lexicon"]]
    css = re.sub(r"/\*.*?\*/", "", (FRONT / "rx.css").read_text(encoding="utf-8"), flags=re.S)
    assert "#sheet.view-only .rx-genbox button, #sheet.view-only .rx-sugg button { display:none; }" in css
    auth = (FRONT / "authorship.js").read_text(encoding="utf-8")
    assert 'sheet.classList.add("view-only")' in auth and "[contenteditable=\"true\"]" in auth   # onOpen hides the buttons and locks the span


def test_an_emptied_listed_generic_comes_back_on_blur_so_the_screen_matches_the_print():
    r = _run("""const tr = mkRow("l1", "verified", {name: "Crocin"}, @LEX@);
      const s = tr.querySelector(".rx-gen-text"); s.focus(); s.textContent = ""; s.dispatch("input");
      const during = [tr._rx.meta.generic, tr._rx.meta.generic_source]; s.blur();
      console.log(JSON.stringify({during, after: tr.querySelector(".rx-gen-text").textContent, line: tr.querySelector(".rx-gen").textContent}));""".replace("@LEX@", LEX))
    assert r == {"during": ["Paracetamol", "lexicon"], "after": "Paracetamol", "line": "generic: Paracetamol"}


def test_clearing_a_doctor_override_restores_the_listed_generic():
    r = _run("""const tr = mkRow("o1", "verified", {name: "Crocin"}, @LEX@);
      const s = tr.querySelector(".rx-gen-text"); s.focus(); s.textContent = "Ibuprofen"; s.dispatch("input");
      tr.querySelector(".rx-gen-remember").checked = true; tr.querySelector(".rx-gen-remember").dispatch("change");
      const over = [RxView.wire(tr).generic_source, GenericEdit.rememberIndexes([tr])];
      s.textContent = ""; s.dispatch("input"); s.blur();
      const m = tr._rx.meta;
      console.log(JSON.stringify({over, m: [m.generic, m.generic_source, m.generic_pending, m.generic_listed, m.remember_generic],
        wire: RxView.wire(tr), shown: tr.querySelector(".rx-gen").textContent, tick: !!tr.querySelector(".rx-gen-remember"), st: tr.dataset.rxstate}));""".replace("@LEX@", LEX))
    assert r["over"] == ["doctor", [0]]
    assert r["m"] == ["Paracetamol", "lexicon", False, "", False]
    assert r["wire"] == {"heard": "", "lookalike": ""}                                     # the listed text is page only, never sent
    assert r["shown"] == "generic: Paracetamol" and r["tick"] is False and r["st"] == "ok"


def test_a_spoken_override_from_the_server_gets_the_tick_and_clearing_restores_the_listed_generic():   # final review M1
    r = _run("""const tr = mkRow("v1", "verified", {name: "Crocin"}, {generic: "Paracetamol + Caffeine", generic_source: "doctor",
        generic_pending: true, generic_listed: "Paracetamol"});
      const tick = !!tr.querySelector(".rx-gen-remember"), sent = RxView.wire(tr);
      const s = tr.querySelector(".rx-gen-text"); s.focus(); s.textContent = ""; s.dispatch("input"); s.blur();
      const m = tr._rx.meta;
      console.log(JSON.stringify({tick, sent, m: [m.generic, m.generic_source, m.generic_listed], shown: tr.querySelector(".rx-gen").textContent}));""")
    assert r["tick"] is True and "generic_listed" not in r["sent"]                         # read from the server, never sent back
    assert r["m"] == ["Paracetamol", "lexicon", ""] and r["shown"] == "generic: Paracetamol"


# Task 1's cases (tests/test_doctor_generic.py) plus the edge cases since, and Unicode text where JavaScript's defaults
# differ from Python's (\s, \d, \b, len, casefold).
CASES = ["", "Aceclofenac + ", "+ +", "x" * 161, "x" * 160, "<script>", "A1", " + ".join(f"Drug{c}" for c in "abcdefg"),
         "Aceclofenac+Paracetamol", "  aceclofenac   plus  paracetamol ", "Paracetamol + paracetamol", "Calcium Carbonate + Vitamin D3",
         "Plusfen", "plus", "Aceclofenac\t+\nParacetamol", "Vitamin B12", "Café", "5-Fluorouracil", "6-Mercaptopurine + Methotrexate",
         "5-1", "5Fluorouracil", "A + B + C", "Abc PLUS Def", "Abcplus Def", "Abc_plus Def", "Abc éplus Def", "Abc ٥plus Def",
         "٥-Fluorouracil", "\x1cAspirin\x1c", "Aspirin﻿", "\xa0Aspirin　", "Aspirin\x85+ Codeine",
         " + ".join(["Drugaa", "DRUGAA", "Drugbb", "Drugcc", "Drugdd", "Drugee", "Drugff"]), "ß" * 3 + " + " + "SS" * 3,
         "😀" * 81, "x" * 159 + "😀", "Aspirin (enteric) / Codeine, 5-mg's", "a.b.c", "-Abc", "Abc-", "12-34-Abc", "plus + Abc"]


def test_problem_mirrors_the_server_messages():                     # Review Focus 5
    r = _run("console.log(JSON.stringify(" + json.dumps(CASES) + ".map((x) => GenericEdit.problem(x)).concat([GenericEdit.problem(null), GenericEdit.problem(['x'])])));")
    want = [G.generic_problem(x) for x in CASES] + [G.generic_problem(None), G.generic_problem(["x"])]
    assert r == want
    assert r[CASES.index("\u0665-Fluorouracil")] == G.MESSAGES["chars"]                   # ASCII digits only, both sides
    assert set(want) >= set(G.MESSAGES.values()) | {""}                                    # every message is exercised


def test_the_page_loads_genericedit_between_rxview_and_app():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert html.index("rxview.js?v=18") < html.index("genericedit.js?v=3") < html.index("app.js?v=53") and "rx.css?v=10" in html
    js = (FRONT / "genericedit.js").read_text(encoding="utf-8")
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js and len(js.splitlines()) < 200
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    assert "remember_generics: GenericEdit.rememberIndexes(kept.map(k => k.tr))" in app and "      remember_generics,\n" in app
    css = re.sub(r"/\*.*?\*/", "", (FRONT / "rx.css").read_text(encoding="utf-8"), flags=re.S)
    assert ".rx-sugg.amber { color: var(--warn); background:#fff8e1; }" in css and "@media print { .rx-genbox .rx-gen-text { border:0; } }" in css
    assert re.search(r"\.rx-genbox \.rx-gen-text \{[^}]*dotted", css)
