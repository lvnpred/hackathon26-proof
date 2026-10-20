"""core/overlay.py: the pure merge of a clinic's overlay rows onto the shipped lists (plan PQ-f, Task 2)."""
import copy

import pytest

from doctor_dictation.core import overlay as O
from doctor_dictation.core import surface

SHIPPED = [
    {"canonical": "Aceclofenac", "aliases": ["aceclofenac"], "brands": ["Zerodol"], "forms": ["Tab."], "strengths": ["100 mg"]},
    {"canonical": "Paracetamol", "aliases": ["paracetamol"], "brands": ["Crocin", "Dolo"], "forms": [], "strengths": ["650 mg"], "safety": True},
]
INV = [
    {"canonical": "CBC", "aliases": ["complete blood count"], "category": "Blood", "print": "CBC"},
    {"canonical": "LFT", "aliases": ["liver function test"], "category": "Blood", "print": "LFT", "safety": True},
]
COMBO = "Aceclofenac + Paracetamol"


def row(key, action, data, base_sha=""):
    return {"entry_key": key, "action": action, "data": data, "base_sha": base_sha}


def eff(rows, shipped=SHIPPED, kind="medicine"):
    return O.effective_entries(kind, shipped, rows)


def by_canon(entries, canon):
    return [e for e in entries if e["canonical"] == canon]


# --- effective_entries -----------------------------------------------------------------------------------------------

def test_no_rows_gives_the_shipped_entries_and_no_flags():
    assert O.effective_entries("medicine", SHIPPED, []) == (SHIPPED, [])


def test_add_appends_a_clinic_entry():
    e, f = eff([row("zerodol-p", "add", {"name": "Zerodol-P", "generic": COMBO})])
    assert e[-1] == {"canonical": COMBO, "brands": ["Zerodol-P"], "aliases": [], "forms": [], "strengths": [], "clinic": True}
    assert f == [] and e[:2] == SHIPPED


def test_add_whose_name_is_its_generic_has_no_brand():
    e, _ = eff([row("ibuprofen", "add", {"name": "Ibuprofen", "generic": "Ibuprofen"})])
    assert e[-1]["canonical"] == "Ibuprofen" and e[-1]["brands"] == []


def test_add_over_a_shipped_canonical_is_skipped():
    # Controller ruling 3 (review of Task 2) replaces the brief's "add over a shipped key replaces it": the add is a
    # conflict ("already on the list - edit it instead"), so the shipped entry and its brands stay.
    e, f = eff([row("aceclofenac", "add", {"name": "Aceclofenac", "generic": "Aceclofenac SR"})])
    assert e == SHIPPED and f == []


def test_edit_with_current_base_sha_has_no_flag():
    e, f = eff([row("aceclofenac", "edit", {"aliases": ["acf"]}, O.entry_sha(SHIPPED[0]))])
    assert e[0]["aliases"] == ["Acf"] and e[0]["strengths"] == ["100 mg"] and e[0]["brands"] == ["Zerodol"]
    assert f == []


def test_edit_with_stale_base_sha_keeps_the_clinic_edit_and_flags_it():
    e, f = eff([row("aceclofenac", "edit", {"aliases": ["acf"]}, "stale")])
    assert e[0]["aliases"] == ["Acf"]
    assert f == [{"entry_key": "aceclofenac", "reason": "shipped-changed"}]


def test_edit_can_change_the_generic():
    e, _ = eff([row("aceclofenac", "edit", {"generic": "Aceclofenac SR"}, O.entry_sha(SHIPPED[0]))])
    assert e[0]["canonical"] == "Aceclofenac SR" and e[0]["brands"] == ["Zerodol"]


def test_edit_of_an_entry_no_longer_shipped_is_appended_and_flagged():
    e, f = eff([row("ketorolac", "edit", {"generic": "Ketorolac", "brands": ["Toradol"]}, "old")])
    assert e[-1] == {"canonical": "Ketorolac", "brands": ["Toradol"], "aliases": [], "forms": [], "strengths": [], "clinic": True}
    assert f == [{"entry_key": "ketorolac", "reason": "shipped-changed"}]


def test_edit_of_a_gone_entry_without_a_generic_is_only_flagged():
    e, f = eff([row("ketorolac", "edit", {"aliases": ["ktr"]}, "old")])
    assert e == SHIPPED and f == [{"entry_key": "ketorolac", "reason": "shipped-changed"}]


def test_hide_drops_the_entry():
    e, f = eff([row("aceclofenac", "hide", {}, O.entry_sha(SHIPPED[0]))])
    assert [x["canonical"] for x in e] == ["Paracetamol"] and f == []
    _, f = eff([row("aceclofenac", "hide", {}, "stale")])
    assert f == [{"entry_key": "aceclofenac", "reason": "shipped-changed"}]


def test_hide_of_an_unknown_key_changes_nothing():
    assert eff([row("nothing", "hide", {})]) == (SHIPPED, [])


def test_a_safety_entry_wins_over_edit_and_hide():
    for r in (row("paracetamol", "edit", {"brands": ["Crocin"]}, O.entry_sha(SHIPPED[1])),
              row("paracetamol", "hide", {}, O.entry_sha(SHIPPED[1]))):
        e, f = eff([r])
        assert e[1] == SHIPPED[1] and len(e) == 2
        assert f == [{"entry_key": "paracetamol", "reason": "safety-override"}]


def test_add_takes_a_name_a_shipped_entry_claims():
    e, f = eff([row("zerodol", "add", {"name": "Zerodol", "generic": COMBO})])
    assert e[0]["brands"] == [] and e[-1]["brands"] == ["Zerodol"]
    assert "zerodol" not in surface.ambiguous_names(e) and f == []


def test_claims_match_space_hyphen_and_case_like_the_lookup():
    shipped = [{"canonical": "Aceclofenac", "aliases": [], "brands": ["Zerodol P"], "forms": [], "strengths": [],
                "generic_hidden": ["Zerodol P"]}]
    e, _ = eff([row("zerodol-p", "add", {"name": "ZERODOL-P", "generic": COMBO})], shipped)
    assert e[0]["brands"] == [] and e[0]["generic_hidden"] == [] and e[-1]["brands"] == ["Zerodol-P"]


def test_a_clinic_brand_under_another_generic_is_not_hidden_any_more():
    shipped = [{"canonical": "Ferrous", "aliases": [], "brands": ["Fefol", "Ferium"], "forms": [], "strengths": [],
                "generic_hidden": ["Fefol"]}]
    e, _ = eff([row("fefol", "add", {"name": "Fefol", "generic": "Ferrous + Folic acid"})], shipped)
    assert e[0]["brands"] == ["Ferium"] and e[0]["generic_hidden"] == []


def test_edit_drops_hidden_brands_it_no_longer_lists():
    shipped = [{"canonical": "Ferrous", "aliases": [], "brands": ["Fefol", "Ferium"], "forms": [], "strengths": [],
                "generic_hidden": ["Fefol"]}]
    e, _ = eff([row("ferrous", "edit", {"brands": ["Ferium"]}, O.entry_sha(shipped[0]))], shipped)
    assert e[0]["brands"] == ["Ferium"] and e[0]["generic_hidden"] == []


def test_a_brand_of_the_same_generic_is_not_stripped():
    e, _ = eff([row("mydol", "add", {"name": "Mydol", "generic": "Aceclofenac"})])
    assert e[0] == SHIPPED[0] and e[-1]["canonical"] == "Aceclofenac"


def test_add_of_a_name_a_safety_entry_claims_is_dropped_and_flagged():
    e, f = eff([row("dolo", "add", {"name": "Dolo", "generic": COMBO})])
    assert e == SHIPPED and not [x for x in e if x.get("clinic")]
    assert f == [{"entry_key": "dolo", "reason": "safety-override"}]


def test_edit_that_claims_a_safety_name_keeps_the_shipped_entry():
    e, f = eff([row("aceclofenac", "edit", {"brands": ["Zerodol", "Dolo"]}, O.entry_sha(SHIPPED[0]))])
    assert e == SHIPPED and f == [{"entry_key": "aceclofenac", "reason": "safety-override"}]


def test_a_name_that_is_another_generic_is_refused_and_skipped():
    r = row("mybrand", "add", {"name": "Mybrand", "generic": COMBO, "brands": ["Aceclofenac"]})
    assert eff([r]) == (SHIPPED, [])
    assert any("Aceclofenac" in m for m in O.conflicts("medicine", SHIPPED, [], r))


# --- ruling 1: one winner per claimed name ----------------------------------------------------------------------------

SHIPPED_NS = copy.deepcopy(SHIPPED[:1]) + [{**copy.deepcopy(SHIPPED[1]), "safety": False}]


def test_two_clinic_claims_on_one_name_the_greater_key_wins():
    rows = [row("aceclofenac", "edit", {"brands": ["Zerodol", "Crocin"]}, O.entry_sha(SHIPPED_NS[0])),
            row("crocin", "add", {"name": "Crocin", "generic": "Paracetamol + Caffeine"})]
    e, f = eff(rows, SHIPPED_NS)
    assert e[0]["brands"] == ["Zerodol"] and e[1]["brands"] == ["Dolo"] and e[-1]["brands"] == ["Crocin"]
    assert f == [] and "crocin" not in surface.ambiguous_names(e)


def test_two_clinic_edits_listing_one_new_brand_the_greater_key_wins():
    rows = [row("aceclofenac", "edit", {"brands": ["Zerodol", "Newbrand"]}, O.entry_sha(SHIPPED_NS[0])),
            row("paracetamol", "edit", {"brands": ["Crocin", "Dolo", "Newbrand"]}, O.entry_sha(SHIPPED_NS[1]))]
    e, _ = eff(rows, SHIPPED_NS)
    assert e[0]["brands"] == ["Zerodol"] and e[1]["brands"] == ["Crocin", "Dolo", "Newbrand"]


# --- ruling 2: a generic spelt like an existing one adopts its spelling ---------------------------------------------

def test_a_generic_in_another_case_adopts_the_listed_spelling():
    for g in ("paracetamol", "PARACETAMOL", "Paracetamol"):
        e, _ = eff([row("mydol", "add", {"name": "Mydol", "generic": g})])
        assert e[-1]["canonical"] == "Paracetamol" and surface.ambiguous_names(e) == {}
    e, _ = eff([row("aceclofenac", "edit", {"generic": "PARACETAMOL"}, O.entry_sha(SHIPPED[0]))])
    assert e[0]["canonical"] == "Paracetamol" and surface.ambiguous_names(e) == {}


# --- ruling 3: conflicts --------------------------------------------------------------------------------------------

def test_conflicts_generic_is_a_brand():
    r = row("mydol", "add", {"name": "Mydol", "generic": "Crocin"})
    assert O.conflicts("medicine", SHIPPED, [], r) == ["'Crocin' is a brand of Paracetamol \u2014 choose the generic"]
    assert eff([r]) == (SHIPPED, [])
    r = row("aceclofenac", "edit", {"generic": "Zerodol"}, O.entry_sha(SHIPPED[0]))
    assert O.conflicts("medicine", SHIPPED, [], r) == ["'Zerodol' is a brand of Aceclofenac \u2014 choose the generic"]
    clinic = row("zerodol-p", "add", {"name": "Zerodol-P", "generic": COMBO})
    r = row("mydol", "add", {"name": "Mydol", "generic": "Zerodol-P"})
    assert O.conflicts("medicine", SHIPPED, [clinic], r)
    # two clinic rows that conflict with each other (only possible if written around the API): the first key stays
    e, _ = eff([clinic, r])
    assert [x["canonical"] for x in e if x.get("clinic")] == ["Zerodol-P"] and surface.ambiguous_names(e) == {}


def test_conflicts_add_of_a_listed_generic():
    r = row("aceclofenac", "add", {"name": "Aceclofenac", "generic": "Aceclofenac"})
    assert O.conflicts("medicine", SHIPPED, [], r) == ["'Aceclofenac' is already on the list \u2014 edit it instead"]
    r = row("cbc", "add", {"name": "CBC"})
    assert O.conflicts("investigation", INV, [], r) == ["'CBC' is already on the list \u2014 edit it instead"]


def test_conflicts_add_key_must_be_the_name_key():
    r = row("other", "add", {"name": "Zerodol-P", "generic": COMBO})
    assert len(O.conflicts("medicine", SHIPPED, [], r)) == 1 and eff([r]) == (SHIPPED, [])
    assert O.conflicts("medicine", SHIPPED, [], row("zerodol-p", "add", {"name": "Zerodol-P", "generic": COMBO})) == []


def test_conflicts_name_is_another_generic():
    r = row("aceclofenac", "edit", {"aliases": ["Paracetamol"]}, O.entry_sha(SHIPPED[0]))
    assert len(O.conflicts("medicine", SHIPPED, [], r)) == 1
    assert O.conflicts("medicine", SHIPPED, [], row("aceclofenac", "edit", {"brands": ["Aceclofenac", "Zerodol"]})) == []


def test_conflicts_hide_of_an_unknown_key():
    assert O.conflicts("medicine", SHIPPED, [], row("nothing", "hide", {})) == ["There is no 'nothing' on the list to hide"]
    assert O.conflicts("medicine", SHIPPED, [], row("aceclofenac", "hide", {})) == []


def test_conflicts_reports_invalid_data():
    assert O.conflicts("medicine", SHIPPED, [], row("x", "add", {"name": "Xyzzy"})) == ["A new medicine needs its generic name."]


def test_conflicts_ignores_the_row_itself_in_rows():
    r = row("zerodol-p", "add", {"name": "Zerodol-P", "generic": COMBO})
    assert O.conflicts("medicine", SHIPPED, [r], r) == []


def test_conflicts_does_not_change_its_inputs():
    shipped, rows = copy.deepcopy(SHIPPED), [row("zerodol-p", "add", {"name": "zerodol-p", "generic": COMBO})]
    before = copy.deepcopy((shipped, rows))
    O.conflicts("medicine", shipped, rows, row("mydol", "add", {"name": "Mydol", "generic": "Crocin"}))
    assert (shipped, rows) == before


def test_invalid_rows_are_skipped():
    rows = [row("x", "add", {"name": "X"}), row("y", "add", {"name": "Yzz", "generic": "<b>x</b>"}),
            row("z", "delete", {}), row("w", "add", "not a dict"), {"entry_key": "v"}]
    assert eff(rows) == (SHIPPED, [])


def test_flags_are_sorted_and_one_per_key():
    rows = [row("zeta", "edit", {"generic": "Zetaine"}, "x"), row("aceclofenac", "edit", {"aliases": ["acfx"]}, "x"),
            row("dolo", "add", {"name": "Dolo", "generic": COMBO})]
    _, f = eff(rows)
    assert [x["entry_key"] for x in f] == ["aceclofenac", "dolo", "zeta"]


def test_output_is_deterministic_for_row_order():
    rows = [row("zerodol-p", "add", {"name": "Zerodol-P", "generic": COMBO}), row("aceclofenac", "edit", {"aliases": ["acf"]}, "x")]
    assert eff(rows) == eff(list(reversed(rows)))


def test_shipped_list_is_never_mutated():
    shipped = copy.deepcopy(SHIPPED) + [{"canonical": "Ferrous", "aliases": [], "brands": ["Fefol"], "forms": [],
                                         "strengths": [], "generic_hidden": ["Fefol"]}]
    before = copy.deepcopy(shipped)
    cases = [
        [row("zerodol-p", "add", {"name": "Zerodol-P", "generic": COMBO})],
        [row("zerodol", "add", {"name": "Zerodol", "generic": COMBO})],
        [row("fefol", "add", {"name": "Fefol", "generic": "Ferrous + Folic acid"})],
        [row("aceclofenac", "edit", {"aliases": ["acf"], "brands": ["Zerodol", "Hifenac"]}, "x")],
        [row("aceclofenac", "hide", {})],
        [row("paracetamol", "edit", {"brands": ["Crocin"]})],
        [row("dolo", "add", {"name": "Dolo", "generic": COMBO})],
        [row("aceclofenac", "add", {"name": "Aceclofenac", "generic": "Aceclofenac SR"})],
    ]
    for rows in cases:
        e, _ = eff(rows, shipped)
        for x in e:                        # a consumer that mutates its copy must not reach the shipped list either
            if not any(x is s for s in shipped):
                for v in x.values():
                    if isinstance(v, list):
                        v.append("MUTATED")
        assert shipped == before


def test_investigation_add_and_edit():
    e, f = eff([row("rft", "add", {"name": "RFT", "category": "Blood"})], INV, "investigation")
    assert e[-1] == {"canonical": "RFT", "aliases": [], "category": "Blood", "print": "", "clinic": True} and f == []
    e, f = eff([row("cbc", "edit", {"aliases": ["hemogram"], "print": "Complete blood count"}, O.entry_sha(INV[0]))],
               INV, "investigation")
    assert e[0] == {"canonical": "CBC", "aliases": ["hemogram"], "category": "Blood", "print": "Complete blood count"}
    assert f == []
    e, f = eff([row("lft", "hide", {})], INV, "investigation")
    assert e == INV and f == [{"entry_key": "lft", "reason": "safety-override"}]


def test_investigation_add_takes_an_alias():
    e, _ = eff([row("hemogram", "add", {"name": "Hemogram", "aliases": ["complete blood count"]})], INV, "investigation")
    assert e[0]["aliases"] == [] and e[-1]["aliases"] == ["complete blood count"]


# --- validate_data ---------------------------------------------------------------------------------------------------

def bad(*args, **kw):
    with pytest.raises(ValueError):
        O.validate_data(*args, **kw)


def test_validate_data_rules():
    # name: add, both kinds; clean_name non-empty
    assert O.validate_data("medicine", "add", {"name": "  zerodol  ", "generic": COMBO})["name"] == "Zerodol"
    bad("medicine", "add", {"name": "<x>", "generic": COMBO})
    bad("investigation", "add", {"name": ""})
    bad("medicine", "edit", {"name": "Zerodol"})
    # generic: medicine add required, medicine edit (clinic only)
    bad("medicine", "add", {"name": "Zerodol"})
    bad("medicine", "add", {"name": "Zerodol", "generic": "<b>x</b>"})
    bad("medicine", "add", {"name": "Zerodol", "generic": "Ab"})
    bad("medicine", "add", {"name": "Zerodol", "generic": "A" * 121})
    bad("medicine", "add", {"name": "Zerodol", "generic": "A,,,,,,"})
    bad("medicine", "add", {"name": "Zerodol", "generic": "Paracetamol 500 mg"})
    bad("medicine", "add", {"name": "Zerodol", "generic": "Cholecalciferol 60000 IU"})
    bad("medicine", "add", {"name": "Zerodol", "generic": "Povidone iodine 5%"})
    assert O.validate_data("medicine", "add", {"name": "Zerodol", "generic": "Vitamin B12"})["generic"] == "Vitamin B12"
    assert O.validate_data("medicine", "add", {"name": "Zerodol", "generic": "Iron (as  ferrous) 10%, B12"})["generic"] \
        == "Iron (as ferrous) 10%, B12"
    assert O.validate_data("medicine", "edit", {"generic": "Aceclofenac SR"}) == {"generic": "Aceclofenac SR"}
    bad("medicine", "edit", {"generic": "Aceclofenac SR"}, owner=True)
    bad("investigation", "add", {"name": "RFT", "generic": "Renal"})
    # aliases, brands: lists, caps, clean_name, de-duplicated; brands medicine only
    assert O.validate_data("medicine", "edit", {"aliases": ["acf", "ACF", " acf "]}) == {"aliases": ["Acf"]}
    bad("medicine", "edit", {"aliases": [f"Alias{chr(97 + i)}x" for i in range(21)]})
    assert len(O.validate_data("medicine", "edit", {"aliases": [f"Ali{chr(97 + i)}x" for i in range(20)]})["aliases"]) == 20
    bad("medicine", "edit", {"brands": [f"Brand{chr(97 + i % 26)}{chr(97 + i // 26)}" for i in range(41)]})
    bad("medicine", "edit", {"aliases": "acf"})
    bad("medicine", "edit", {"aliases": ["ok name", "<b>"]})
    bad("medicine", "edit", {"aliases": [1]})
    bad("investigation", "edit", {"brands": ["Xyz"]})
    # category, print: investigation only, caps, charset
    assert O.validate_data("investigation", "edit", {"category": "Blood", "print": "RFT"}) == {"category": "Blood", "print": "RFT"}
    bad("investigation", "edit", {"category": "B" * 41})
    bad("investigation", "edit", {"print": "P" * 31})
    bad("investigation", "edit", {"category": "<i>x"})
    bad("medicine", "edit", {"category": "Blood"})
    # safety: owner only, bool only
    bad("medicine", "edit", {"safety": True})
    assert O.validate_data("medicine", "edit", {"safety": True}, owner=True) == {"safety": True}
    bad("medicine", "edit", {"safety": 1}, owner=True)
    # other keys, hide with data, bad kind/action/shape
    bad("medicine", "edit", {"aliases": ["acf"], "forms": ["Tab."]})
    bad("medicine", "hide", {"name": "x"})
    assert O.validate_data("medicine", "hide", {}) == {} and O.validate_data("medicine", "hide", None) == {}
    bad("drug", "add", {"name": "Zerodol", "generic": COMBO})
    bad("medicine", "delete", {})
    bad("medicine", "edit", ["aliases"])
    bad("medicine", "edit", {})
    bad("medicine", "add", {"name": 5, "generic": COMBO})


def test_investigation_names_keep_their_case_medicine_names_are_tidied():
    assert O.validate_data("investigation", "add", {"name": " RFT ", "aliases": ["renal  profile"]}) == \
        {"name": "RFT", "aliases": ["renal profile"]}
    assert O.validate_data("medicine", "add", {"name": "DOLO", "generic": "Paracetamol"})["name"] == "Dolo"


def test_validate_data_has_no_numbers_so_1_and_1_0_cannot_differ():
    for v in (1, 1.0, True):
        bad("medicine", "edit", {"generic": v})
        bad("medicine", "edit", {"aliases": [v]})


def test_validate_data_does_not_change_its_input_and_is_idempotent():
    data = {"name": "zerodol-p", "generic": " Aceclofenac  + Paracetamol ", "aliases": ["zrp"]}
    before = copy.deepcopy(data)
    once = O.validate_data("medicine", "add", data)
    assert data == before and O.validate_data("medicine", "add", once) == once
    assert once == {"name": "Zerodol-P", "generic": COMBO, "aliases": ["Zrp"]}


def test_messages_are_readable():
    with pytest.raises(ValueError, match="generic"):
        O.validate_data("medicine", "add", {"name": "Zerodol"})


# --- entry_sha, entry_key_of -----------------------------------------------------------------------------------------

def test_entry_sha_ignores_key_order():
    assert O.entry_sha({"a": 1, "b": 2}) == O.entry_sha({"b": 2, "a": 1})
    assert O.entry_sha({"a": 1}) != O.entry_sha({"a": 2}) and len(O.entry_sha({})) == 64


def test_entry_key_of():
    assert O.entry_key_of({"canonical": "  Aceclofenac   SR "}) == "aceclofenac sr"
    assert O.KINDS == ("medicine", "investigation")


# --- the effective list keeps the lookups working (real shipped list) ------------------------------------------------

def test_effective_real_list_keeps_lookups_working(monkeypatch):
    from doctor_dictation.core import combo
    from doctor_dictation.core import determinism as D
    shipped = D.load_lexicon()
    before = copy.deepcopy(shipped)
    rows = [row("zerodol", "add", {"name": "Zerodol", "generic": COMBO}),
            row("calcimax", "add", {"name": "Calcimax", "generic": "Calcium Citrate + Vitamin D3"})]
    e, f = O.effective_entries("medicine", shipped, rows)
    assert shipped == before and f == []
    monkeypatch.setattr(D, "_lexicon_cache", e)
    assert D._exact_lookup("Zerodol") == COMBO and D._exact_lookup("Zerodol") == D._alias_map()["zerodol"]
    assert "zerodol" not in surface.ambiguous_names(e) and "calcimax" not in surface.ambiguous_names(e)
    assert combo.combo_suffix("Zerodol-P") == ("Zerodol", "P")
    assert surface.generic_fields("Zerodol", COMBO)["generic"] == COMBO
    assert not surface.generic_hidden("Calcimax", "Calcium Citrate + Vitamin D3")
    assert D._exact_lookup("Dolo") == "Paracetamol"


def _real(monkeypatch, rows):
    from doctor_dictation.core import determinism as D
    shipped = D.load_lexicon()
    before = copy.deepcopy(shipped)
    e, f = O.effective_entries("medicine", shipped, rows)
    assert shipped == before
    monkeypatch.setattr(D, "_lexicon_cache", e)
    return D, e, f


def test_probe_two_claims_on_crocin_real_list(monkeypatch):
    from doctor_dictation.core import determinism as D0
    acf = next(x for x in D0.load_lexicon() if x["canonical"] == "Aceclofenac")
    rows = [row("aceclofenac", "edit", {"brands": ["Zerodol", "Crocin"]}, O.entry_sha(acf)),
            row("crocin", "add", {"name": "Crocin", "generic": "Paracetamol + Caffeine"})]
    D, e, f = _real(monkeypatch, rows)
    assert D._exact_lookup("Crocin") == "Paracetamol + Caffeine" and "crocin" not in surface.ambiguous_names(e)
    assert D._exact_lookup("Zerodol") == "Aceclofenac" and f == []


def test_probe_lower_case_generic_real_list(monkeypatch):
    for g in ("paracetamol", "PARACETAMOL"):
        D, e, _ = _real(monkeypatch, [row("mydolx", "add", {"name": "Mydolx", "generic": g})])
        assert D._exact_lookup("Mydolx") == "Paracetamol" and surface.ambiguous_names(e) == surface.ambiguous_names(_shipped_file())


def _shipped_file():
    import json
    from doctor_dictation.core import determinism as D
    return json.loads(D.LEXICON_PATH.read_text(encoding="utf-8"))["entries"]


