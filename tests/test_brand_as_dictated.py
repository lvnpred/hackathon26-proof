"""I1-b: a dictated brand stays as dictated; the generic is kept for checks (offline)."""
import subprocess
import sys

import pytest

import doctor_dictation.core.determinism as D
import doctor_dictation.core.repair as R


# ---- Task 1: pure move ----
def test_old_import_paths_still_work():
    for n in ("build_repair_message", "loop_should_continue", "open_issues", "MAX_CANDIDATE_ROWS",
              "_UNKNOWN_ISSUE_RE", "UNKNOWN_MEDICINE_TEXT", "FORMAT_LLM_CAP", "RX_VERIFIED"):
        assert getattr(D, n) is getattr(R, n), n
    assert D.build_repair_message.__module__ == "doctor_dictation.core.repair"


@pytest.mark.parametrize("first", ["repair", "determinism"])
def test_no_circular_import_either_order(first):
    other = "determinism" if first == "repair" else "repair"
    code = f"import doctor_dictation.core.{first}, doctor_dictation.core.{other}"
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr


# ---- Task 2: surface forms in correct_drugs ----
from doctor_dictation.core.determinism import correct_drugs
from doctor_dictation.core.surface import ambiguous_names, surface_map

COMBI = [  # one brand, two generics (a combination product)
    {"canonical": "Paracetamol", "aliases": ["paracetamol"], "brands": ["Combiflam"], "strengths": ["500 mg"]},
    {"canonical": "Ibuprofen", "aliases": ["ibuprofen"], "brands": ["Combiflam"], "strengths": ["400 mg"]},
]
# Lexicon names correct_drugs never rewrote correctly (measured before this plan, still unfixed).
KNOWN_UNFIXED = {"artemether+lumefantrine", "coenzymeq10", "coq10", "imipenem+cilastatin",
                 "iron sucrose injection", "levodopa+carbidopa", "piperacillin+tazobactam",
                 "sacubitril+valsartan"}


@pytest.mark.parametrize("text,want", [
    ("crocin twice daily", "Crocin twice daily"),              # brand spelling, not Paracetamol
    ("Neo-Mercazole 5 mg", "Neo-Mercazole 5 mg"),              # hyphenated brand
    ("tablet emset 4 mg", "tablet Emset 4 mg"),                # brand that is also an alias
    ("tab zylorik 100", "tab Zyloric 100"),                    # misspelled brand: fixed, still a brand
    ("zy loric 100", "Zyloric 100"),                           # split brand
    ("neo mercazole 5 mg", "Neo-Mercazole 5 mg"),
    ("tablet tam sulosin 0.4 mg", "tablet Tamsulosin 0.4 mg"),  # generics still normalise
    ("have paracetmol twice a day", "have Paracetamol twice a day"),
    ("tablet azithro 500 mg", "tablet Azithromycin 500 mg"),
    ("syrup Potassium Magnesium Citrate 15 ml and tab Zyloric 100 and Co-Amoxiclav 625",
     "syrup Potassium Magnesium Citrate 15 ml and tab Zyloric 100 and Co-Amoxiclav 625"),
])
def test_correct_drugs_brand_as_dictated_generic_normalised(text, want):
    assert correct_drugs(text) == want


def test_every_lexicon_name_round_trips():
    smap, _amb = D._maps()
    bad = {k for k, v in smap.items()
           if correct_drugs(k) != v and not (len(k) < 5 and correct_drugs(k) == k)}
    assert bad <= KNOWN_UNFIXED, sorted(bad - KNOWN_UNFIXED)


def test_lookups_still_return_the_generic():
    assert D._alias_map()["zyloric"] == "Allopurinol"
    assert D._canonical_lookup("Zyloric") == "Allopurinol"
    assert D._canonical_lookup("zylorik") == "Allopurinol"


def test_surface_map_unit():
    entries = [{"canonical": "Atenolol", "aliases": ["atenolol", "tenormin"], "brands": ["Tenormin"]}]
    assert surface_map(entries, {"atenolol": "Atenolol", "tenormin": "Atenolol"}) == \
        {"atenolol": "Atenolol", "tenormin": "Tenormin"}
    assert ambiguous_names(COMBI) == {"combiflam": ("Ibuprofen", "Paracetamol")}
    assert "combiflam" not in surface_map(COMBI, {"combiflam": "Ibuprofen"})


# ---- Task 3: generic field, ambiguous brands, preserve, ops, rules path ----
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.determinism import ground_rx, normalize_transcript, validate_structured
from doctor_dictation.core.fallback import fallback_format
from doctor_dictation.core.ops import apply_ops
from test_determinism import _rx, _stub_llm


def _row(name, strength="", transcript=""):
    rows, _w = validate_structured({"rx": [_rx(name, strength=strength)]}, transcript)
    return rows["rx"][0]


def test_brand_row_keeps_brand_and_carries_generic():
    row = _row("Zyloric", "100 mg", "tab zyloric 100 mg once daily")
    assert (row["name"], row["status"]) == ("Zyloric", "verified")
    assert (row["lexicon_match"], row["generic"]) == ("Allopurinol", "Allopurinol")
    assert _row("Allopurinol", "100 mg", "allopurinol 100 mg")["generic"] == ""
    assert _row("paracetamol", "", "paracetamol")["generic"] == ""            # case only
    assert _row("Medalpha")["generic"] == ""
    rows, _issues = ground_rx([{"name": "Zyloric"}, {"name": ""}], "zyloric")
    assert [r["generic"] for r in rows] == ["Allopurinol", ""]
    assert _row("Zyloric", "77 mg", "zyloric 77 mg")["status"] == "unverified-strength"   # checked via the generic


def test_a_brand_two_generics_claim_is_not_guessed(monkeypatch):
    monkeypatch.setattr(D, "_lexicon_cache", COMBI)
    assert correct_drugs("tab combiflam 500") == "tab combiflam 500"
    for typed in ("Combiflam", "Combiflm"):                                   # exact and near spelling
        row = _row(typed, "", f"tab {typed.lower()} twice daily")
        assert (row["status"], row["lexicon_match"], row["generic"]) == ("unverified-name", "", "")
    _rows, issues = ground_rx([{"name": "Combiflam"}], "combiflam")
    assert "Ibuprofen, Paracetamol" in issues[0]
    assert _row("Paracetamol", "500 mg", "paracetamol 500 mg")["status"] == "verified"


def test_preserve_restores_generic_with_the_status():
    prior = {"name": "Zyloric", "status": "verified", "lexicon_match": "Allopurinol",
             "generic": "Allopurinol", "instructions": ""}
    cur = {"rx": [prior, {"name": "Dolo", "instructions": ""}]}          # Dolo: no status at all
    fresh = {"status": "x", "lexicon_match": "x", "instructions": "", "generic": "STALE"}
    rows = preserve_untouched_rx_status(cur, {}, {"rx": [dict(fresh, name="Zyloric"),
                                                         dict(fresh, name="Dolo")]})["rx"]
    assert rows[0]["generic"] == "Allopurinol"
    assert "generic" not in rows[1] and "status" not in rows[1]


def test_replace_op_drops_the_old_generic():
    cur = {"rx": [{"name": "Zyloric", "status": "verified", "lexicon_match": "Allopurinol",
                   "generic": "Allopurinol", "instructions": ""}]}
    new, _rest, _notes, _t = apply_ops(cur, {"replace": {"rx": [{"from": "Zyloric", "to": "Febuxostat"}]}})
    assert "generic" not in new["rx"][0] and "status" not in new["rx"][0]


def test_rules_path_keeps_a_brand_dictated_without_a_strength():
    rows = fallback_format(normalize_transcript("fever have calpol twice a day"))["rx"]
    assert [(r["name"], r["dose"]) for r in rows] == [("Calpol", "1-0-1")]


# ---- Task 4: end to end ----
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.core.determinism import _FORMAT_CACHE


def test_format_keeps_the_brand_in_prompt_and_row(monkeypatch):
    _FORMAT_CACHE.clear()
    calls = _stub_llm(monkeypatch, [{"rx": [_rx("Zyloric", strength="100 mg")]}])
    r = TestClient(M.app).post("/api/format", json={"transcript": "tab zylorik 100 mg once daily"})
    assert r.status_code == 200, r.text
    j = r.json()
    prompt = calls["messages"][0][-1]["content"]
    assert "Zyloric" in prompt and "Allopurinol" not in prompt
    row = j["structured"]["rx"][0]
    assert (row["name"], row["status"], row["lexicon_match"], row["generic"]) == \
        ("Zyloric", "verified", "Allopurinol", "Allopurinol")
    assert "exactly as dictated, including brand names" in calls["messages"][0][0]["content"]  # system prompt


def test_a_model_that_swaps_the_brand_for_the_generic_is_flagged_not_trusted():
    row = _row("Allopurinol", "100 mg", "tab Zyloric 100 mg once daily")
    assert (row["status"], row["lexicon_match"]) == ("unverified-name", "Allopurinol")


# ---- Final review fixes ----
import copy
import json

from doctor_dictation import db as dbmod
from doctor_dictation.config import override_settings
import doctor_dictation.core.correction as C
from doctor_dictation.core.correction import CORRECTION_INSTRUCTION, merge_form
from test_correction_ops import _post

_READ_RX = ("form", "name", "strength", "dose", "timing", "duration", "instructions", "status",
            "lexicon_match")  # the fields frontend/app.js readRx sends back: never `generic`


def _read_rx(row):
    return {k: row.get(k, "") for k in _READ_RX}


def _cur(*rows):  # (name, lexicon_match) pairs as verified rows
    return {"rx": [{"form": "Tab.", "name": n, "strength": "100 mg", "dose": "1-0-0",
                    "instructions": "", "status": "verified", "lexicon_match": m} for n, m in rows]}


# Finding 1: a brand and its generic are the same medicine in a correction.
@pytest.mark.parametrize("rows,said,target", [
    ((("Zyloric", "Allopurinol"),), "Allopurinol", "Zyloric"),      # brand row, generic dictated
    ((("Allopurinol", "Allopurinol"),), "Zyloric", "Allopurinol"),  # generic row, brand dictated
])
def test_correction_naming_the_other_name_updates_the_same_row(rows, said, target):
    cur = _cur(*rows)
    patch, notes, unsure = C.match_by_generic(cur, {"rx": [{"name": said, "strength": "300 mg"}]})
    assert patch["rx"] == [{"name": target, "strength": "300 mg"}] and unsure == set()
    assert notes == [f"'{said}' matched the existing row '{target}' (same medicine)."]
    out = merge_form(cur, patch)["rx"]
    assert [(r["name"], r["strength"]) for r in out] == [(target, "300 mg")]


def test_correction_does_not_guess_between_two_rows_of_one_generic():
    cur = _cur(("Telma", "Telmisartan"), ("Tazloc", "Telmisartan"))
    patch, notes, unsure = C.match_by_generic(cur, {"rx": [{"name": "Telmisartan", "strength": "80 mg"}]})
    assert patch["rx"] == [{"name": "Telmisartan", "strength": "80 mg"}]   # left alone: added as new
    assert len(notes) == 1 and "Telma, Tazloc" in notes[0]
    assert unsure == {"telmisartan"}                                       # the route blocks it (M3)


def test_correction_exact_name_wins_over_the_generic():
    cur = _cur(("Zyloric", "Allopurinol"), ("Allopurinol", "Allopurinol"))
    patch, notes, _unsure = C.match_by_generic(cur, {"rx": [{"name": "allopurinol", "dose": "1-0-1"}]})
    assert patch["rx"] == [{"name": "allopurinol", "dose": "1-0-1"}] and notes == []


def test_ops_remove_and_replace_by_generic_find_the_brand_row():
    cur = _cur(("Zyloric", "Allopurinol"), ("Telma", "Telmisartan"))
    new, _rest, notes, _t = apply_ops(cur, {"remove": {"rx": ["allopurinol"]}})
    assert [r["name"] for r in new["rx"]] == ["Telma"] and notes == ["Removed Zyloric."]
    new, _rest, notes, _t = apply_ops(cur, {"replace": {"rx": [{"from": "Allopurinol", "to": "Febuxostat"}]}})
    assert [r["name"] for r in new["rx"]] == ["Febuxostat", "Telma"] and notes == ["Renamed Zyloric to Febuxostat."]
    two = _cur(("Telma", "Telmisartan"), ("Tazloc", "Telmisartan"))
    new, _rest, notes, _t = apply_ops(two, {"remove": {"rx": ["telmisartan"]}})
    assert new == two and notes[0].startswith("Several rows match telmisartan")


def test_correct_route_generic_patch_changes_the_brand_row(monkeypatch):
    cur = _cur(("Zyloric", "Allopurinol"))
    j = _post(monkeypatch, {"rx": [{"name": "Allopurinol", "strength": "300 mg"}]}, copy.deepcopy(cur),
              transcript="change allopurinol to 300 mg")
    rows = j["structured"]["rx"]
    assert [(r["name"], r["strength"], r["status"], r["generic"]) for r in rows] == \
        [("Zyloric", "300 mg", "verified", "Allopurinol")]
    assert "'Allopurinol' matched the existing row 'Zyloric' (same medicine)." in j["warnings"]
    assert "same medicine" in CORRECTION_INSTRUCTION.split("\n2.")[0]   # rule 1 says so


# Round 2, I1: only an exact lexicon name links two rows; a fuzzy neighbour is another drug.
@pytest.mark.parametrize("row,said", [(("Zovirax", "Acyclovir"), "Famciclovir"),
                                      (("Theophylline", "Theophylline"), "Etophylline")])
def test_a_different_drug_never_merges_into_a_row(row, said):
    cur = _cur(row)
    patch, notes, unsure = C.match_by_generic(cur, {"rx": [{"name": said, "strength": "250 mg"}]})
    assert (patch["rx"], notes, unsure) == ([{"name": said, "strength": "250 mg"}], [], set())
    assert [r["name"] for r in merge_form(cur, patch)["rx"]] == [row[0], said]


@pytest.mark.parametrize("rows,ref", [
    ((("Zovirax", "Acyclovir"), ("Telma", "Telmisartan")), "famciclovir"),   # fuzzy: another drug
    ((("Levoflox", "Levofloxacin"), ("Levocet", "Levocetirizine")), "levo"),  # short: several drugs
    ((("Ketorol", "Ketorolac"), ("Nizral", "Ketoconazole")), "keto"),
    ((("R-Cin", "Rifampicin"), ("Rifagut", "Rifaximin")), "rifa"),
    ((("Pantocid", "Pantoprazole"), ("Telma", "Telmisartan")), "pan"),
])
def test_ops_never_find_a_row_by_a_fuzzy_or_short_name(rows, ref):
    cur = _cur(*rows)
    for ops in ({"remove": {"rx": [ref]}}, {"replace": {"rx": [{"from": ref, "to": "Cetirizine"}]}}):
        new, _rest, notes, _t = apply_ops(cur, ops)
        assert new == cur and notes == [f"Could not find {ref} on the prescription; nothing was "
                                        "changed. Use the x button."]


# Round 2, M3: a generic two current rows share is appended, but must be confirmed.
def test_correct_route_blocks_a_generic_it_could_not_place(monkeypatch):
    from doctor_dictation.core.safety import screen_unverified
    cur = _cur(("Telma", "Telmisartan"), ("Tazloc", "Telmisartan"))
    j = _post(monkeypatch, {"rx": [{"name": "Telmisartan", "strength": "80 mg"}]}, copy.deepcopy(cur),
              transcript="change telmisartan to 80 mg")
    assert [(r["name"], r["status"]) for r in j["structured"]["rx"]] == \
        [("Telma", "verified"), ("Tazloc", "verified"), ("Telmisartan", "unverified-name")]
    assert screen_unverified(j["structured"], []) == \
        [{"index": 2, "name": "Telmisartan", "status": "unverified-name"}]
    assert any("could be any of Telma, Tazloc" in w for w in j["warnings"])


# Findings 2 and 5: the rules path keeps a brand with a digit, in its own spelling.
@pytest.mark.parametrize("text,want", [
    ("cap alpha d3 0.25 mcg once daily", [("Alpha D3", "0.25 mcg", "1-0-0")]),
    ("cap moxikind-cv 625 mg twice daily", [("Moxikind-CV", "625 mg", "1-0-1")]),
    # a bare number is still never part of a name, so a later row keeps its own dose
    ("tab zyloric 100 mg twice daily for 5 days tab telma 40 mg once daily",
     [("Zyloric", "100 mg", "1-0-1"), ("Telma", "40 mg", "1-0-0")]),
    ("tab zyloric 100 mg 1-0-1 for 5-7 days tab telma 40 mg once daily",
     [("Zyloric", "100 mg", "1-0-1"), ("Telma", "40 mg", "1-0-0")]),
    ("cap doxy-1 100 mg twice daily", [("Doxy-1", "100 mg", "1-0-1")]),       # round 2, M1
    ("syrup ston-1 15 ml twice daily", [("Ston-1", "15 ml", "1-0-1")]),
])
def test_rules_path_keeps_brand_spelling_and_digits(text, want):
    rows = fallback_format(normalize_transcript(text))["rx"]
    assert [(r["name"], r["strength"], r["dose"]) for r in rows] == want


@pytest.mark.parametrize("text,want", [
    ("tab b12 500 mcg once daily", ("Tab.", "B12")),      # was name "Tab B12"
    ("inj d3 600000 iu once a week", ("Inj.", "D3")),     # was form "Tab.", name "Inj D3"
])
def test_rules_path_form_word_is_not_part_of_a_short_name(text, want):
    rows = fallback_format(normalize_transcript(text))["rx"]
    assert [(r["form"], r["name"]) for r in rows] == [want]


def test_rules_path_keeps_a_short_alias_as_dictated():
    norm = normalize_transcript("tab amlo 5 mg once daily")
    rows, _w = validate_structured(fallback_format(norm), norm)
    assert [(r["name"], r["status"]) for r in rows["rx"]] == [("Amlo", "verified")]   # not Amlodipine


def test_rules_path_never_renames_a_short_alias():
    bad = []
    for k in sorted(k for k in D._alias_map() if len(k) < 5):
        rows = fallback_format(normalize_transcript(f"tab {k} 5 mg once daily"))["rx"]
        if [r["name"].lower() for r in rows] != [k]:
            bad.append((k, [r["name"] for r in rows]))
    assert bad == []


# Finding 3: a name two generics claim is never fuzzed into a neighbouring drug.
def _lexicon_plus(generic, brand):
    lex = copy.deepcopy(D.load_lexicon())
    next(e for e in lex if e["canonical"] == generic)["brands"].append(brand)
    return lex


def test_an_ambiguous_brand_stays_as_dictated(monkeypatch):
    monkeypatch.setattr(D, "_lexicon_cache", _lexicon_plus("Paracetamol", "Acivir"))
    assert D._maps()[1] == {"acivir": ("Acyclovir", "Paracetamol")}
    assert correct_drugs("tab acivir 500 mg") == "tab acivir 500 mg"      # was "tab Valcivir 500 mg"
    assert correct_drugs("tab valcivir 500 mg") == "tab Valcivir 500 mg"  # its neighbour is untouched
    row = _row("acivir", "500 mg", "tab acivir 500 mg")
    assert (row["status"], row["lexicon_match"], row["generic"]) == ("unverified-name", "", "")


@pytest.mark.parametrize("text", ["tab neo-mercazole 5 mg", "tab Neo Mercazole 5 mg"])
def test_no_word_of_an_ambiguous_phrase_is_rewritten(monkeypatch, text):
    monkeypatch.setattr(D, "_lexicon_cache", _lexicon_plus("Omeprazole", "Neo-Mercazole"))
    assert correct_drugs(text) == text                                   # was "tab neo-Omeprazole 5 mg"


def test_the_split_pass_does_not_guess_an_ambiguous_name(monkeypatch):
    lex = COMBI + [{"canonical": "Flamtide", "aliases": ["flamtide", "combi-flam"], "brands": []}]
    monkeypatch.setattr(D, "_lexicon_cache", lex)                          # same letters as Combiflam
    assert correct_drugs("tab combi flam 500") == "tab combi flam 500"


# Finding 4: `generic` depends on the name only; the client never sends it back.
def test_preserve_recomputes_generic_the_client_did_not_send():
    cur = {"rx": [_read_rx({"name": "Zyloric", "status": "verified", "lexicon_match": "Allopurinol"}),
                  _read_rx({"name": "Allopurinol", "status": "verified", "lexicon_match": "Allopurinol"})]}
    fresh = {"status": "x", "lexicon_match": "x", "instructions": "", "generic": "STALE"}
    rows = preserve_untouched_rx_status(cur, {}, {"rx": [dict(fresh, name="Zyloric"),
                                                         dict(fresh, name="Allopurinol")]})["rx"]
    assert [(r["lexicon_match"], r["generic"]) for r in rows] == [("Allopurinol", "Allopurinol"),
                                                                 ("Allopurinol", "")]


def test_preserve_drops_generic_when_the_name_was_hand_edited():
    # Round 2, M2: the UI renamed Zyloric to Febuxostat but kept data-lexicon = Allopurinol.
    cur = {"rx": [_read_rx({"name": "Febuxostat", "status": "", "lexicon_match": "Allopurinol"})]}
    fresh = {"name": "Febuxostat", "status": "x", "lexicon_match": "x", "instructions": "",
             "generic": "STALE"}
    rows = preserve_untouched_rx_status(cur, {}, {"rx": [fresh]})["rx"]
    assert (rows[0]["lexicon_match"], rows[0]["generic"]) == ("Allopurinol", "")


def test_generic_survives_an_offline_correction_round_trip(monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    _FORMAT_CACHE.clear()
    client = TestClient(M.app)
    j = client.post("/api/format", json={
        "transcript": "tab zyloric 100 mg once daily and tab telma 40 mg once daily"}).json()
    rows = j["structured"]["rx"]
    assert [(r["name"], r["status"], r["generic"]) for r in rows] == \
        [("Zyloric", "verified", "Allopurinol"), ("Telma", "verified", "Telmisartan")]
    form = dict(j["structured"], rx=[_read_rx(r) for r in rows])
    out = client.post("/api/v1/correct", json={"transcript": "", "current_form": form}).json()
    assert [(r["status"], r["generic"]) for r in out["structured"]["rx"]] == \
        [("verified", "Allopurinol"), ("verified", "Telmisartan")]


def test_save_keeps_generic_for_a_row_the_client_sent_without_it(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "save.db"))
    conn = dbmod.get_conn(tmp_path / "save.db")
    dbmod.migrate(conn)
    row = _read_rx({"form": "Tab.", "name": "Zyloric", "strength": "100 mg", "dose": "1-0-0",
                    "status": "verified", "lexicon_match": "Allopurinol"})
    r = TestClient(M.app).post("/api/v1/documents", json={
        "structured": {"patientName": "Anita", "opNo": "OP-31", "rx": [row]}, "confirmed_rows": []})
    assert r.status_code == 200, r.text
    saved = json.loads(dbmod.get_document(conn, r.json()["document_id"])["structured_json"])["rx"][0]
    assert (saved["name"], saved["status"], saved["generic"]) == ("Zyloric", "verified", "Allopurinol")
    conn.close()


# Task 5: a short alias (under five letters) never reaches a row through the same-medicine fallback.
def _merged(cur, row):
    patch, _notes, _unsure = C.match_by_generic(cur, {"rx": [row]})
    return merge_form(cur, patch)["rx"]


def test_short_alias_keto_is_a_new_row_not_an_overwrite():
    cur = _cur(("Ketorol", "Ketorolac"), ("Nizral", "Ketoconazole"))
    cur["rx"][0]["strength"], cur["rx"][1]["strength"] = "10 mg", "200 mg"
    out = _merged(cur, {"name": "Keto", "strength": "10 mg", "dose": "SOS"})
    assert [r["name"] for r in out] == ["Ketorol", "Nizral", "Keto"]
    assert (out[1]["strength"], out[1]["status"]) == ("200 mg", "verified")


def test_short_alias_levo_is_a_new_row_not_an_overwrite():
    cur = _cur(("Levoflox", "Levofloxacin"))
    cur["rx"][0]["strength"] = "500 mg"
    out = _merged(cur, {"name": "Levo", "strength": "5 mg", "dose": "0-0-1"})
    assert [(r["name"], r["strength"]) for r in out] == [("Levoflox", "500 mg"), ("Levo", "5 mg")]


def test_long_name_same_medicine_fallback_still_updates_the_row():
    out = _merged(_cur(("Zyloric", "Allopurinol")), {"name": "Allopurinol", "strength": "300 mg"})
    assert [(r["name"], r["strength"]) for r in out] == [("Zyloric", "300 mg")]


def test_exact_short_name_still_matches_its_row():
    out = _merged(_cur(("Keto", "Ketoconazole")), {"name": "Keto", "strength": "20 mg"})
    assert [(r["name"], r["strength"]) for r in out] == [("Keto", "20 mg")]
