"""SH-B4: context breaks near-ties among clinic names in the Spell it list only (S1); Did you mean is untouched."""
from datetime import date

import pytest

from doctor_dictation.core import formulary as F
from doctor_dictation.core import rowcheck

TODAY = date(2026, 10, 17)


@pytest.fixture(autouse=True)
def _no_layer_leaks():
    F.activate(F.ClinicLayer())
    yield
    F.activate(F.ClinicLayer())


def _db_row(name, count):
    return {"id": 0, "name": name, "generic": None, "confirm_count": count, "first_seen_at": "2026-10-17T00:00:00Z",
            "last_seen_at": "2026-10-17T00:00:00Z", "added_by": None}


def test_context_moves_a_clinic_name_inside_the_band_only(frozen_lexicon):
    F.activate(F.ranked_layer([_db_row("Dolvexa", 2), _db_row("Dolvexi", 30), _db_row("Dolmexa", 500)], TODAY))
    plain = [o["name"] for o in rowcheck.options({"name": "Dolvex", "lexicon_match": ""})[0]]
    assert plain == ["Dolvexi", "Dolvexa", "Dolmexa"]                       # I1-r1 usage order, unchanged
    got = [o["name"] for o in rowcheck.options({"name": "Dolvex", "lexicon_match": ""}, prefer=frozenset({"dolvexa"}))[0]]
    assert got == ["Dolvexa", "Dolvexi", "Dolmexa"]


def test_tie_break_preference_never_crosses_the_band_or_moves_a_lexicon_name():
    scored = [("Lexo", 0.95, False), ("Clina", 0.94, True), ("Clinb", 0.92, True), ("Far", 0.919, True)]
    pref = lambda n: n in {"Clinb", "Far", "Lexo"}                          # noqa: E731
    assert F.tie_break(scored, lambda n: 0.0, pref) == ["Lexo", "Clinb", "Clina", "Far"]   # Far is 0.031 behind: stays
    assert F.tie_break(scored, lambda n: 0.0) == F.tie_break(scored, lambda n: 0.0, None) == ["Lexo", "Clina", "Clinb", "Far"]


def test_options_without_prefer_are_byte_identical_and_did_you_mean_is_untouched(frozen_lexicon):
    rowcheck._clear_dym_cache()
    row = {"name": "Citrizene", "lexicon_match": ""}
    before = rowcheck.did_you_mean("Citrizene", rowcheck.D_UNKNOWN)
    assert rowcheck.options(row) == rowcheck.options(row, prefer=frozenset())
    rowcheck.options(row, prefer=frozenset({"cetirizine"}))
    assert rowcheck.did_you_mean("Citrizene", rowcheck.D_UNKNOWN) == before    # Spell it context never reaches Did you mean
    assert len(rowcheck._DYM_CACHE) == 1                                       # only did_you_mean's own entry
