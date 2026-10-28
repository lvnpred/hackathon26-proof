"""I1-a: look-alike guard, "heard" text and the new status (offline; the LLM is stubbed)."""
import json

import pytest

from doctor_dictation.core import lasa
from doctor_dictation.core.determinism import load_lexicon
from doctor_dictation.core.lasa import always_flag_names, heard_as, lookalike_flag, twins

CANONICALS = sorted({e["canonical"] for e in load_lexicon()})


# ---- Task 1: twins, the curated list, heard_as, the tiers ----
def test_twins_are_computed_symmetric_and_sorted():
    assert twins("Cefixime") == ["Cefotaxime", "Cefuroxime"]       # two twins, closest first
    assert twins("prednisone") == ["Prednisolone"]                  # input case does not matter
    assert twins("Paracetamol") == [] and twins("") == [] and twins("Nope") == []
    assert all(c in twins(t) for c in CANONICALS for t in twins(c))
    assert len({frozenset((a, b)) for a in CANONICALS for b in twins(a)}) >= 100   # 121 on v1.1.0


def test_curated_list_names_exist_and_is_marked_unreviewed():
    pairs = json.loads(lasa.PAIRS_PATH.read_text(encoding="utf-8"))["pairs"]
    low = {c.lower() for c in CANONICALS}
    assert len(pairs) == 8 and twins("Hydroxyzine")[0] == "Hydralazine"
    assert all(p["a"].lower() in low and p["b"].lower() in low and p["source"] and p["reviewed"] is False
               for p in pairs)


def test_unconditional_flags_stay_under_ten_percent_of_the_lexicon():
    flagged = [c for c in CANONICALS if lookalike_flag(c, c, "") or lookalike_flag(c, c, f"tablet {c} 10 mg")]
    assert set(flagged) == set(always_flag_names())                 # only the curated list flags
    assert len(flagged) / len(CANONICALS) <= 0.10, (len(flagged), len(CANONICALS))   # 16 of 444 today


@pytest.mark.parametrize("name,raw,want", [
    ("Tamsulosin", "tablet tam sulosin 0.4 mg", "tam sulosin"),
    ("Tamsulosin", "TABLET TAMSULOSIN 0.4", ""),                  # case only: same word
    ("Azithromycin", "tab azithro 500", "azithro"),               # alias of the same generic
    ("Zyloric", "tab Zylorik 100", "Zylorik"),                    # original case of the raw words
    ("Neo-Mercazole", "neo mercazole 5 mg", ""),                  # hyphen only: same words
    ("Tamsulosin", "tam sulosin and then Tamsulosin", ""),        # the exact word wins
    ("Tamsulosin", "", ""),
    ("Atorvastatin", "fever, rest advised", ""),
])
def test_heard_as(name, raw, want):
    assert heard_as(name, raw) == want


def test_clean_dictation_of_any_lexicon_name_has_no_heard_text():
    for e in load_lexicon():
        for n in [e["canonical"], *e.get("brands", [])]:
            assert heard_as(n, f"fever tablet {n} 10 mg once daily after food") == "", n


def test_computed_pairs_flag_only_on_evidence():
    A = "Atorvastatin"
    assert lookalike_flag(A, A, "tablet Atorvastatin 10 mg") == "" and lookalike_flag(A, A, "") == ""
    assert lookalike_flag(A, A, "tablet Atorvastatin 10 mg and tablet rosuvastatin 5 mg") == "Rosuvastatin"
    assert lookalike_flag("Rosuvastatin", "Rosuvastatin",
                          "tablet Atorvastatin 10 mg and tablet rosuvastatin 5 mg") == A     # both rows flag
    assert lookalike_flag(A, A, "tablet atorvastin 10 mg") in twins(A)                      # auto-corrected
    # "ferrous" is an alias of Ferrous Ascorbate and the first word of Ferrous Fumarate: not evidence
    assert lookalike_flag("Ferrous Fumarate", "Ferrous Fumarate", "tablet Ferrous Fumarate 10 mg") == ""
    both = "tablet Ferrous Fumarate 10 mg and tablet Ferrous Sulfate 5 mg"
    assert lookalike_flag("Ferrous Fumarate", "Ferrous Fumarate", both) == "Ferrous Sulfate"


def test_curated_pair_always_flags_even_with_no_transcript_and_any_case():
    assert lookalike_flag("Prednisone", "Prednisone", "") == "Prednisolone"
    assert lookalike_flag("prednisone", "PREDNISONE", "tablet PREDNISONE 5 mg") == "Prednisolone"
    assert lookalike_flag("Hydralazine", "Hydralazine", "") == "Hydroxyzine"


# ---- Task 2: the grounding hook ----
from doctor_dictation.core.determinism import ground_rx, validate_structured
from test_determinism import _rx, _stub_llm


def _row(name, strength="", normalized="", raw=""):
    out, _w = validate_structured({"rx": [_rx(name, strength=strength)]}, normalized, raw)
    return out["rx"][0]


def test_verified_curated_row_becomes_lookalike_check():
    row = _row("Prednisone", "10 mg", "tablet Prednisone 10 mg", "tablet Prednisone 10 mg")
    assert (row["status"], row["lookalike"], row["heard"]) == ("lookalike-check", "Prednisolone", "")
    assert row["lexicon_match"] == "Prednisone" and "[unverified" not in row["instructions"]
    assert _row("Prednisone", "10 mg", "tablet Prednisone 10 mg")["status"] == "lookalike-check"  # no raw


def test_grounding_order_strength_and_name_checks_come_first():
    assert _row("Prednisone", "7 mg", "prednisone 7 mg")["status"] == "unverified-strength"
    row = _row("Prednisone", "", "fever, rest advised")
    assert (row["status"], row["lookalike"]) == ("unverified-name", "")


def test_rows_without_twins_carry_empty_fields_and_heard_is_filled():
    row = _row("Tamsulosin", "0.4 mg", "tablet Tamsulosin 0.4 mg", "tablet tam sulosin 0.4 mg")
    assert (row["status"], row["heard"], row["lookalike"]) == ("verified", "tam sulosin", "")
    rows, issues = ground_rx([{"name": ""}, {"name": "Prednisone"}], "prednisone", "prednisone")
    assert [(r["heard"], r["lookalike"]) for r in rows] == [("", ""), ("", "Prednisolone")]
    assert rows[1]["status"] == "lookalike-check" and len(issues) == 1     # only the empty name
    from doctor_dictation.core.ops import _regrounded                      # a rename drops stale twin data
    renamed = _regrounded({**rows[1], "heard": "x"}, "Tamsulosin")
    assert not {"heard", "lookalike", "status"} & renamed.keys()


# ---- Task 3: plumbing from the endpoints ----
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.core.determinism import _FORMAT_CACHE
from test_correction_ops import _post


def test_lookalike_gives_the_repair_loop_nothing_to_fix(monkeypatch):
    _FORMAT_CACHE.clear()
    calls = _stub_llm(monkeypatch, [{"rx": [_rx("Prednisone", strength="10 mg")]}] * 3)
    j = TestClient(M.app).post("/api/format", json={"transcript": "tablet prednisone 10 mg once daily"}).json()
    assert calls["n"] == 1 and j["grounding"]["rounds"] == 0           # no LLM repair round
    assert j["structured"]["rx"][0]["status"] == "lookalike-check"
    assert j["grounding"]["open_issues"] == ["rx[0] 'Prednisone': lookalike-check"]


def test_format_cache_is_per_raw_wording(monkeypatch):
    _FORMAT_CACHE.clear()
    _stub_llm(monkeypatch, [{"rx": [_rx("Tamsulosin", strength="0.4 mg")]}] * 2)
    c = TestClient(M.app)
    a = c.post("/api/format", json={"transcript": "tablet tam sulosin 0.4 mg"}).json()
    b = c.post("/api/format", json={"transcript": "tablet Tamsulosin 0.4 mg"}).json()
    assert a["normalized_transcript"] == b["normalized_transcript"] and b["cached"] is False
    assert (a["structured"]["rx"][0]["heard"], b["structured"]["rx"][0]["heard"]) == ("tam sulosin", "")


def test_correct_route_passes_the_spoken_words(monkeypatch):
    j = _post(monkeypatch, {"rx": [_rx("Tamsulosin", strength="0.4 mg")]}, {"rx": []},
              transcript="add tam sulosin 0.4 mg")
    assert j["structured"]["rx"][0]["heard"] == "tam sulosin"


# ---- Task 4: save gate and save path ----
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.safety import screen_unverified


def test_save_gate_blocks_lookalike_until_the_doctor_confirms_it():
    form = {"rx": [{"name": "Prednisone", "status": "lookalike-check"},
                   {"name": "Tamsulosin", "status": "verified"}]}
    assert screen_unverified(form) == [{"index": 0, "name": "Prednisone", "status": "lookalike-check"}]
    assert screen_unverified(form, confirmed_rows=[0]) == []


def test_save_path_keeps_status_heard_and_lookalike():
    saved = {"rx": [dict(_rx("Prednisone"), status="lookalike-check", lexicon_match="Prednisone",
                         heard="predni sone", lookalike="Prednisolone", generic=""),
                    dict(_rx("Dolo"))]}
    validated, _w = validate_structured(saved, "")           # what persistence.py does on save
    rows = preserve_untouched_rx_status(saved, {}, validated)["rx"]
    assert (rows[0]["status"], rows[0]["heard"], rows[0]["lookalike"]) == \
        ("lookalike-check", "predni sone", "Prednisolone")
    assert all(k not in rows[1] for k in ("status", "heard", "lookalike", "generic"))


# ---- final-review fixes ----
from doctor_dictation.core.determinism import normalize_transcript


def _dictated(name, strength, raw):
    out, _w = validate_structured({"rx": [_rx(name, strength=strength)]}, normalize_transcript(raw), raw)
    return out["rx"][0]


def test_exact_alias_dictated_as_written_is_not_evidence():
    row = _dictated("Azithromycin", "500 mg", "tab azithro 500 mg once daily")
    assert (row["status"], row["heard"], row["lookalike"]) == ("verified", "azithro", "")
    assert _dictated("Pantoprazole", "40 mg", "tab panto 40 mg")["status"] == "verified"
    assert _dictated("Atorvastatin", "10 mg", "tablet atorvastin 10 mg")["status"] == "lookalike-check"
    assert _dictated("Fluoxetine", "20 mg", "tab dluoxetine 20 mg")["status"] == "lookalike-check"
    assert _dictated("Prednisone", "5 mg", "tab prednisone 5 mg")["status"] == "lookalike-check"


@pytest.fixture
def pairs_file(tmp_path, monkeypatch):
    def put(content):
        p = tmp_path / "lasa_pairs.json"
        if content is not None:
            p.write_text(content, encoding="utf-8")
        monkeypatch.setattr(lasa, "PAIRS_PATH", p)
        lasa._slot.clear()
    yield put
    lasa._slot.clear()


@pytest.mark.parametrize("content", ['{"pairs": null}', '{"pairs": 5}', "[]", "not json {", None])
def test_broken_pairs_file_switches_only_the_always_tier_off(pairs_file, caplog, content):
    pairs_file(content)
    with caplog.at_level("WARNING", logger=lasa.__name__):
        row = _row("Tamsulosin", "0.4 mg", "tablet Tamsulosin 0.4 mg", "tablet Tamsulosin 0.4 mg")
        assert always_flag_names() == frozenset() and twins("Prednisone") == ["Prednisolone"]
        _row("Prednisone", "5 mg", "tablet Prednisone 5 mg", "tablet Prednisone 5 mg")
    assert row["status"] == "verified"
    assert len([r for r in caplog.records if r.name == lasa.__name__]) == 1


def test_bad_entries_are_skipped_individually(pairs_file):
    pairs_file(json.dumps({"pairs": [{"a": "Prednisone", "b": "Prednisolone"}, 7, None, {"a": "x"},
                                     {"a": ["l"], "b": "Zzz"}]}))
    assert always_flag_names() == frozenset({"Prednisone", "Prednisolone"})


def test_common_word_alias_and_own_heard_words_are_no_twin_evidence():
    raw = "iron deficiency anaemia. tab ferrous sulfate 200 mg"
    assert _dictated("Ferrous Sulfate", "200 mg", raw)["status"] == "verified"
    for name, raw in [("Methylprednisolone", "tab methyl prednisolone 4 mg"),
                      ("Levocetirizine", "tab levo cetrizine 5 mg"),
                      ("Ferrous Fumarate", "tab iron fumarate 10 mg")]:
        row = _dictated(name, "", raw)
        assert row["lookalike"] == "" and row["status"] != "lookalike-check", (name, row["lookalike"])
