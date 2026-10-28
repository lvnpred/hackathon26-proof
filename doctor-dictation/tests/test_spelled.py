"""Spelled words win over the words heard before them (core/spelled.py; owner rule H2, 2026-10-22): a cue word
("spelled") replaces silently, a replacement made only because the words sounded alike is offered back with an Undo."""
import copy

import pytest
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.api.format import SYSTEM_PROMPT
from doctor_dictation.core import spelled
from doctor_dictation.core.correction_prompt import CORRECTION_INSTRUCTION
from doctor_dictation.core.determinism import _FORMAT_CACHE, ground_rx, normalize_transcript
from doctor_dictation.core.promptrules import SPELLED_RULE
from test_correction_ops import _post, _row
from test_determinism import _rx, _stub_llm


def _apply(text):
    return spelled.apply(text)


def test_a_cue_word_replaces_the_spoken_words():
    text, found = _apply("tablet Cello dial, spelled S-I-L-O-D-A-L, 8 mg at bedtime")
    assert text == "tablet Silodal, 8 mg at bedtime"
    assert found == [{"spelled": "Silodal", "heard": "Cello dial", "why": "cue"}]
    assert _apply("tablet Urimax, that is U R I M A X, at bedtime")[0] == "tablet Urimax, at bedtime"


def test_without_a_cue_words_that_sound_alike_are_replaced():
    assert _apply("tablet Cello dial S-I-L-O-D-A-L 8 mg") == (
        "tablet Silodal 8 mg", [{"spelled": "Silodal", "heard": "Cello dial", "why": "alike"}])
    assert _apply("tablet Feb you stat F-E-B-U-X-T-A-T 40 mg")[0] == "tablet Febuxtat 40 mg"


def test_words_that_do_not_sound_alike_stay_and_the_letters_are_only_joined():
    text, found = _apply("pain abdomen S-I-L-O-D-A-L 8 mg")
    assert text == "pain abdomen Silodal 8 mg" and found == [{"spelled": "Silodal", "heard": "", "why": ""}]


@pytest.mark.parametrize("letters", ["S-I-L-O-D-A-L", "S I L O D A L", "S, I, L, O, D, A, L", "S. I. L. O. D. A. L", "s-i-l-o-d-a-l"])
def test_every_way_of_writing_the_letters_gives_one_word(letters):
    assert _apply(f"tablet {letters} 8 mg")[0] == "tablet Silodal 8 mg"


@pytest.mark.parametrize("text", ["advised U S G abdomen and K F T", "tablet Dolo 650 S O S for fever",
                                  "Hepatitis B, C, D negative", "tablet Zerodol P twice daily", "B P 140/90"])
def test_short_letter_runs_with_nothing_to_replace_stay_as_dictated(text):
    assert _apply(text) == (text, [])


def test_a_replacement_never_reaches_past_a_form_word_a_number_or_a_full_stop():
    assert _apply("tablet Pan 40 and tablet Cello dial S-I-L-O-D-A-L 8 mg")[0] == "tablet Pan 40 and tablet Silodal 8 mg"
    assert _apply("fever for 3 days. Cello dial S-I-L-O-D-A-L.")[0] == "fever for 3 days. Silodal."
    assert _apply("tablet, spelled S-I-L-O-D-A-L, 8 mg")[0] == "tablet Silodal, 8 mg"


def test_the_cleanup_keeps_a_spelled_brand_but_still_corrects_a_spoken_one():
    assert normalize_transcript("tablet Tamsulin, spelling T-A-M-S-U-L-I-N, 0.4 mg") == "tablet Tamsulin, 0.4 mg"
    assert normalize_transcript("tablet Tamsulin 0.4 mg") == "tablet Tamsulosin 0.4 mg"     # unchanged behaviour


def test_a_spelled_name_is_grounded_with_nothing_for_the_repair_loop():
    raw = "tablet Cello dial S-I-L-O-D-A-L 8 mg at bedtime"
    rows, issues = ground_rx([{"name": "Silodal", "strength": ""}], normalize_transcript(raw), raw)
    assert rows[0]["status"] == "verified" and issues == []


def test_only_rows_replaced_because_they_sounded_alike_are_tagged_and_the_input_is_not_changed():
    rows = [{"name": "Silodal"}, {"name": "Urimax"}, {"name": "Pan"}]
    found = [{"spelled": "Silodal", "heard": "Cello dial", "why": "alike"},
             {"spelled": "Urimax", "heard": "Uri max", "why": "cue"}]
    out = spelled.tag_rows(rows, found)
    assert [r.get("spelled_heard") for r in out] == ["Cello dial", None, None]
    assert "spelled_heard" not in rows[0]
    assert spelled.tag_rows(rows, [{"spelled": "Silodal", "heard": "Silodal", "why": "alike"}]) == rows   # nothing to undo


def test_both_prompts_tell_the_model_the_spelled_word_wins():
    assert SPELLED_RULE in SYSTEM_PROMPT and SPELLED_RULE in CORRECTION_INSTRUCTION


def test_format_offers_the_heard_words_back_on_the_row_and_the_cache_stays_untagged(monkeypatch):
    _FORMAT_CACHE.clear()
    calls = _stub_llm(monkeypatch, [{"rx": [_rx("Silodal", strength="8 mg")]}])
    c = TestClient(M.app)
    body = {"transcript": "tablet Cello dial S-I-L-O-D-A-L 8 mg at bedtime"}
    first, again = c.post("/api/format", json=body).json(), c.post("/api/format", json=body).json()
    assert calls["n"] == 1 and first["grounding"]["rounds"] == 0 and again["cached"] is True
    assert first["normalized_transcript"] == "tablet Silodal 8 mg at bedtime"
    assert first["structured"]["rx"][0]["spelled_heard"] == again["structured"]["rx"][0]["spelled_heard"] == "Cello dial"
    assert all("spelled_heard" not in r for hit in _FORMAT_CACHE.values() for r in hit["structured"]["rx"])


def test_format_asks_nothing_when_the_doctor_said_spelled(monkeypatch):
    _FORMAT_CACHE.clear()
    _stub_llm(monkeypatch, [{"rx": [_rx("Silodal", strength="8 mg")]}])
    j = TestClient(M.app).post("/api/format", json={"transcript": "tablet Cello dial, spelled S-I-L-O-D-A-L, 8 mg"}).json()
    assert "spelled_heard" not in j["structured"]["rx"][0]


def test_a_correction_keeps_the_undo_on_untouched_rows_and_tags_a_new_spelled_row(monkeypatch):
    current = {"rx": [_row("Silodal", strength="8 mg", status="verified", lexicon_match="Silodosin", spelled_heard="Cello dial"),
                      _row("Pantoprazole", status="verified", lexicon_match="Pantoprazole")]}
    j = _post(monkeypatch, {"rx": [_row("Febuxtat", strength="40 mg")]}, copy.deepcopy(current),
              transcript="add tablet Feb you stat F-E-B-U-X-T-A-T 40 mg")
    rows = {r["name"]: r for r in j["structured"]["rx"]}
    assert rows["Silodal"]["spelled_heard"] == "Cello dial" and rows["Febuxtat"]["spelled_heard"] == "Feb you stat"
    assert not rows["Pantoprazole"].get("spelled_heard")


def test_a_spoken_rename_drops_the_undo():
    from doctor_dictation.core.ops import _regrounded
    assert "spelled_heard" not in _regrounded({**_row("Silodal"), "spelled_heard": "Cello dial"}, "Tamsulosin")


@pytest.mark.parametrize("said, written", [
    ("patient Anu, A-N-U, 30 female", "patient Anu, 30 female"),                 # a short name is not an abbreviation
    ("patient anu A-N-U", "patient Anu"),                                         # after a name label: a name
    ("Mrs Anu A-N-U", "Mrs Anu"),
    ("patient Sri Devi S-R-I-D-E-V-I, 52 female", "patient Sridevi, 52 female"),
    ("diagnosis ureteric calculus, spelled C-A-L-C-U-L-U-S", "diagnosis ureteric calculus"),   # prose keeps its case
    ("c/o dysuria D-Y-S-U-R-I-A for 3 days", "c/o dysuria for 3 days"),
    ("tablet cello dial S-I-L-O-D-A-L 8 mg", "tablet Silodal 8 mg"),              # after a form: a name
    ("tablet P-A-N 40", "tablet Pan 40"),
    ("advised, spelled U-S-G, abdomen", "advised USG, abdomen"),                 # nothing to replace: an abbreviation
])
def test_the_spelled_word_takes_the_casing_of_what_it_replaces(said, written):
    assert _apply(said)[0] == written


def test_label_words_are_never_replaced():
    assert _apply("patient name R-A-M, 40 male")[0] == "patient name Ram, 40 male"   # "name" sounds a bit like "Ram"
    assert _apply("diagnosis B-P-H")[0] == "diagnosis B-P-H"                         # 3 letters, nothing to replace
