"""Ordinary-word denylist (plan I1-g simple, Task 1): correct_drugs never rewrites an everyday word. Offline."""
import ast
import copy
from pathlib import Path

from doctor_dictation.core import determinism as D
from doctor_dictation.core.commonwords import WORDS

TEXT = "Tab Paracetamol 650 mg twice daily after food"


def with_brands(**extra):
    lex = copy.deepcopy(D.load_lexicon())
    for e in lex:
        e["brands"] = [*e["brands"], *extra.get(e["canonical"], [])]
    return lex


def test_twice_daily_after_food_survives_brands_one_slip_from_its_words(monkeypatch):
    monkeypatch.setattr(D, "_lexicon_cache", with_brands(Cefadroxil=["Twicef"], Terbinafine=["Af-ter"]))
    assert D.normalize_transcript(TEXT) == TEXT
    assert D.normalize_transcript("tab twicef 500 mg") == "tab Twicef 500 mg"      # the brand itself still resolves


def test_two_ordinary_words_are_never_joined_into_a_brand(monkeypatch):
    monkeypatch.setattr(D, "_lexicon_cache", with_brands(Paracetamol=["Afterfood"]))
    assert D.normalize_transcript(TEXT) == TEXT
    assert D.normalize_transcript("tablet tam sulosin 0.4 mg") == "tablet Tamsulosin 0.4 mg"   # a real split still joins
    monkeypatch.setattr(D, "_lexicon_cache", with_brands(Paracetamol=["Takefen"]))
    assert D.normalize_transcript("tab take fen 650 mg") == "tab Takefen 650 mg"   # ONE ordinary word ("take") still joins


def test_no_single_word_lexicon_name_is_an_ordinary_word():
    assert {k for k in D._alias_map() if " " not in k} & WORDS == set()


def test_the_list_is_lower_case_words_and_holds_the_measured_cases():
    assert all(w == w.lower().strip() and w for w in WORDS) and len(WORDS) == 603
    assert {"twice", "after", "daily", "clear", "vitamin", "once", "care"} <= WORDS


def test_the_module_is_pure_data_and_the_two_blocks_are_unique():
    from doctor_dictation.core import commonwords as C
    tree = ast.parse(Path(C.__file__).read_text())
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert imports == []                                    # no import at all: no I/O, no stdlib, no state
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert calls <= {"frozenset"}                           # no open(), print(), exec(), etc.
    assert isinstance(C.WORDS, frozenset)
    for block in (C._EN, C._HI):
        words = block.split()
        assert len(words) == len(set(words))                # deduplicated inside each block
    assert not (set(C._EN.split()) & set(C._HI.split()))    # and across the two blocks
    assert len(C._EN.split()) + len(C._HI.split()) == len(C.WORDS) == 603


def test_a_normal_brand_is_still_written_as_dictated(monkeypatch):
    monkeypatch.setattr(D, "_lexicon_cache", with_brands(Paracetamol=["Dolotab"]))
    assert D.normalize_transcript("tab dolotab 650 mg twice daily") == "tab Dolotab 650 mg twice daily"
