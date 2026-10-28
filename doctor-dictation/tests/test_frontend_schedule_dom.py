"""Plan I2-d Task 4: the schedule badge is screen-only text, information only. Node fake DOM (tests/test_frontend_rxspell_dom.py)."""
import re
from pathlib import Path

from test_frontend_rxspell_dom import _run

ROOT = Path(__file__).resolve().parents[1]
TITLE = "Schedule {} medicine (Drugs and Cosmetics Rules). Information only: nothing on this row changes."


def test_the_schedule_badge_is_screen_only_text_and_a_name_edit_clears_it():
    r = _run("""
      const a = mkRow("s1", "verified", { name: "Crocin" }, { generic: "Paracetamol", schedule: "H1" });
      const b = mkRow("s2", "verified", { name: "Cetirizine" }, { generic: "Cetirizine", schedule: "" });
      const badge = (tr) => tr.querySelectorAll(".rx-sched").map((n) => [n.textContent, n.className, n.attrs.title]);
      const before = [badge(a), badge(b), a.dataset.rxstate];
      RxView.onEdit(a, cell(a, "name")); RxView.renderRow(a);
      console.log(JSON.stringify({ before, after: badge(a) }));""")
    assert r["before"] == [[["Schedule H1", "rx-extra rx-sched no-print", TITLE.format("H1")]], [], "ok"]
    assert r["after"] == []                                                     # a hand-edited name: the old badge is stale


def test_each_mark_reads_as_words_on_a_brand_row_and_a_generic_row_and_nothing_else_does():
    r = _run("""
      const text = (tr) => tr.querySelectorAll(".rx-sched").map((n) => n.textContent);
      const rows = {
        brandH: mkRow("1", "verified", { name: "Crocin" }, { generic: "Paracetamol", schedule: "H" }),
        genericH1: mkRow("2", "verified", { name: "Ondansetron" }, { generic: "Ondansetron", schedule: "H1" }),
        brandX: mkRow("3", "verified", { name: "Pred" }, { generic: "Prednisolone", schedule: "X" }),
        none: mkRow("4", "verified", { name: "Crocin" }, { generic: "Paracetamol", schedule: "" }),
        absent: mkRow("5", "verified", { name: "Crocin" }, { generic: "Paracetamol" }),          // an older row, no field
        unknown: mkRow("6", "verified", { name: "Crocin" }, { generic: "Paracetamol", schedule: "Q" }),
        lower: mkRow("7", "verified", { name: "Crocin" }, { generic: "Paracetamol", schedule: "h" }),
        blank: mkRow("8", "verified", {}, { generic: "Paracetamol", schedule: "H" }),             // nothing typed
        notStr: mkRow("9", "verified", { name: "Crocin" }, { generic: "Paracetamol", schedule: { x: 1 } }),
        noGeneric: mkRow("10", "unknown-medicine", { name: "Zzqxwv" }, { schedule: "H" }),
      };
      const out = {}; Object.keys(rows).forEach((k) => { out[k] = text(rows[k]); });
      console.log(JSON.stringify(out));""")
    assert r == {"brandH": ["Schedule H"], "genericH1": ["Schedule H1"], "brandX": ["Schedule X"], "none": [], "absent": [],
                 "unknown": [], "lower": [], "blank": [], "notStr": [], "noGeneric": ["Schedule H"]}


def test_the_badge_sits_with_the_generic_and_a_rerender_keeps_exactly_one():
    r = _run("""
      const tr = mkRow("t1", "verified", { form: "Tab.", name: "cetirizine", strength: "10 mg" }, { generic: "Cetirizine", schedule: "H" });
      const med = tr.querySelector("td"); ["form", "name", "strength"].forEach((c) => med.appendChild(cell(tr, c)));
      RxView.renderRow(tr);
      const order = () => med.children.map((c) => c.dataset.col || c.className);
      const first = order(); RxView.renderRow(tr); RxView.renderRow(tr);
      const brand = mkRow("t2", "verified", { name: "Crocin" }, { generic: "Paracetamol", schedule: "H" });
      console.log(JSON.stringify({ first, again: order(), brand: brand.querySelector("td").children.map((c) => c.className) }));""")
    want = ["form", "name", "rx-extra rx-gen-tag no-print", "rx-extra rx-sched no-print", "strength"]
    assert r["first"] == want and r["again"] == want
    assert r["brand"][:2] == ["rx-genbox", "rx-extra rx-sched no-print"]                   # a brand row: after its generic line


def test_hostile_text_is_inserted_as_text_never_as_markup_and_never_makes_a_badge():
    r = _run("""
      const bad = ['<img src=x onerror=alert(1)>', 'H" onmouseover="x', "H1<script>", "Schedule H", "H ", "javascript:1"];
      const out = bad.map((s, i) => { const tr = mkRow("h" + i, "verified", { name: "Crocin" }, { generic: "Paracetamol", schedule: s });
        return tr.querySelectorAll(".rx-sched").length; });
      console.log(JSON.stringify(out));""")
    assert r == [0] * 6                                            # only H, H1 and X exist; anything else is no badge at all
    js = (ROOT / "frontend" / "rxview.js").read_text(encoding="utf-8")
    assert ".innerHTML" not in js and "insertAdjacentHTML" not in js     # text insertion only


def test_a_schedule_is_information_only_state_save_gate_and_confirmed_set_do_not_move():
    r = _run("""
      const states = (sched) => ["verified", "unverified-strength", "lookalike-check", "unknown-medicine", "dose-check", "unverified-name"].map((st, i) => {
        const tr = mkRow(sched + st, st, { name: "Prednisolone", strength: "5 mg" }, { generic: "Prednisolone", schedule: sched, strength_options: ["5 mg"] });
        const s = RxState.rowState({ status: st, name: "Prednisolone", strength: "5 mg", generic: "Prednisolone", schedule: sched, strength_options: ["5 mg"] }, {});
        return [st, tr.dataset.rxstate, s.state, s.reason, s.canConfirm, s.canSpell, s.needsYou, tr.querySelectorAll('[data-action]').map((b) => b.dataset.action).join()];
      });
      const x = states("X"), none = states("");
      const sum = (rows) => JSON.stringify(RxState.summary({ total: rows.length, needs: rows.filter((q) => q[6]).length, checking: 0 }));
      console.log(JSON.stringify({ same: JSON.stringify(x) === JSON.stringify(none), sum: sum(x) === sum(none), confirmed: confirmed.size,
        clicks: posts.length, meta: RxState.metaOf({ schedule: "X" }).schedule }));""")
    assert r == {"same": True, "sum": True, "confirmed": 0, "clicks": 0, "meta": "X"}


def test_restoring_an_undone_row_brings_its_badge_back_and_an_old_snapshot_has_none():
    r = _run("""
      const tr = mkRow("u1", "verified", { name: "Crocin" }, { generic: "Paracetamol", schedule: "H" });
      const snap = RxView.meta(tr);
      RxView.onEdit(tr, cell(tr, "name")); RxView.renderRow(tr);
      const edited = tr.querySelectorAll(".rx-sched").length;
      RxView.restore({ rowid: "u1", wasConfirmed: false, data: { status: "verified", lexicon_match: "Paracetamol", name: "Crocin", instructions: "", ...snap } });
      const back = tr.querySelectorAll(".rx-sched").map((n) => n.textContent);
      const old = mkRow("u2", "verified", { name: "Crocin" }, { generic: "Paracetamol" });          // a row saved before the field existed
      RxView.restore({ rowid: "u2", wasConfirmed: false, data: { status: "verified", lexicon_match: "Paracetamol", name: "Crocin", instructions: "" } });
      console.log(JSON.stringify({ edited, snap: snap.schedule, back, old: old.querySelectorAll(".rx-sched").length, wire: Object.keys(RxView.wire(tr)) }));""")
    assert r == {"edited": 0, "snap": "H", "back": ["Schedule H"], "old": 0, "wire": ["heard", "lookalike"]}   # the server recomputes the mark; none is sent back


def _lum(hexcolour):
    c = [int(hexcolour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contrast(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_the_badge_style_is_readable_not_colour_only_and_cannot_be_mistaken_for_a_state():
    css = (ROOT / "frontend" / "rx.css").read_text(encoding="utf-8")
    rule = re.search(r"^\.rx-sched\s*\{([^}]*)\}", css, re.M).group(1)
    colour, bg = (re.search(rf"(?<![-\w]){k}:\s*(#[0-9a-fA-F]{{6}})", rule).group(1) for k in ("color", "background"))
    for ground in (bg, "#ffffff", "#fffbf0"):                               # its own tint, a plain row, a dose row
        assert _contrast(colour, ground) >= 4.5, (colour, ground)
    assert "border" in rule and int(re.search(r"font-size:\s*(\d+)px", rule).group(1)) >= 11
    states = {m.group(1) for m in re.finditer(r"--c:(#[0-9a-fA-F]{6})", css)}      # the row-state colours (ok, dose, confirm, known, you)
    assert colour.lower() not in {s.lower() for s in states}                      # a mark never wears a state's colour
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "rx-sched" not in html                                               # built by script only; no placeholder markup


def test_the_printed_prescription_is_identical_with_and_without_a_schedule():
    """Q10: no schedule mark on paper. The PDF never reads the field; the browser print hides the badge (.no-print)."""
    from doctor_dictation.pdf.sheet import build_sheet_html
    base = {"form": "Tab.", "name": "Crocin", "strength": "500 mg", "dose": "1-0-1", "timing": "After food", "duration": "5 days",
            "instructions": "", "generic": "Paracetamol"}
    meta = {"patientName": "Anita Rao", "date": "2026-10-17"}
    plain = build_sheet_html({"rx": [base]}, meta)
    for mark in ("H", "H1", "X", "<b>X</b>"):
        marked = build_sheet_html({"rx": [{**base, "schedule": mark}]}, meta)
        assert marked == plain and "Schedule" not in marked and "rx-sched" not in marked
    css = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")
    assert re.search(r"@media print\s*\{.*?\.no-print[^{]*\{[^}]*display:\s*none\s*!important", css, re.S)   # the class the badge wears is hidden when printing


def test_the_served_files_carry_the_cache_pins_of_this_change():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    pin = lambda name: int(re.search(re.escape(name) + r"\?v=(\d+)", html).group(1))    # noqa: E731
    assert pin("rx.css") >= 7 and pin("rxstate.js") >= 6 and pin("rxview.js") >= 7        # the badge changed these three files
