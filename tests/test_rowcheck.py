"""core/rowcheck.py: one row grounded the same way /api/format grounds it. Offline, pure."""
import pytest

from doctor_dictation.core import lasa, rowcheck
from doctor_dictation.core.determinism import normalize_transcript, validate_structured
from dosing_fixtures import FIXTURE, _e, use_fixture

RAW = "patient on tablet prednisone 10 mg twice daily after meals for 5 days, paracetamol 650 mg thrice daily"
NORM = normalize_transcript(RAW)
ROW = {"form": "Tab.", "name": "Prednisone", "strength": "10 mg", "dose": "1-0-1", "timing": "", "duration": "5 days"}
FIELDS = {"form", "name", "strength", "dose", "timing", "duration", "instructions", "status", "lexicon_match",
          "strength_options", "usual_strength", "dose_note", "heard", "lookalike", "generic"}


def test_ground_one_has_every_field_and_never_trusts_a_name_nobody_said():
    got = rowcheck.ground_one(ROW, RAW, NORM)
    assert FIELDS <= set(got) and (got["status"], got["lexicon_match"]) == ("lookalike-check", "Prednisone")   # curated pair (I1-a)
    for transcript in ("", "tablet metformin 500 mg"):
        typed = rowcheck.ground_one(ROW, transcript, transcript)
        assert (typed["status"], typed["lexicon_match"]) == ("unverified-name", "Prednisone")
    assert rowcheck.ground_one({"name": "Zzqxwv"}, "", "")["status"] == "unknown-medicine"


def test_suggestions_put_candidates_first_then_twins_without_duplicates(monkeypatch):
    monkeypatch.setattr(lasa, "twins", lambda c: ["Prednisolone", "Predni-twin"] if c == "Prednisone" else [])
    got = rowcheck.suggestions({"name": "Prednisone", "lexicon_match": "Prednisone"})
    assert got == ["Prednisone", "Prednisolone", "Predni-twin"]
    assert rowcheck.suggestions({"name": "Zzqxwv", "lexicon_match": ""}) == []
    monkeypatch.setattr(lasa, "twins", lambda c: [f"Twin{i}" for i in range(9)])
    assert len(rowcheck.suggestions({"name": "Prednisone", "lexicon_match": "Prednisone"})) == rowcheck.SUGGESTION_LIMIT


def test_ground_one_refuses_a_row_with_nothing_in_it():
    for row in ({}, {"name": " ", "strength": ""}):
        with pytest.raises(ValueError):
            rowcheck.ground_one(row, RAW, NORM)
    assert rowcheck.ground_with_notes({}, RAW, NORM, index=3) == (
        None, ["rx[3] ?: unknown dose '' -> '1-0-0'", "rx[3]: dropped empty row"])   # the dose block runs before the drop
    assert rowcheck.ground_with_notes({"dose": "1-0-0"}, RAW, NORM, index=3) == (None, ["rx[3]: dropped empty row"])


def test_only_an_explicit_wrong_form_is_a_form_mismatch(monkeypatch, tmp_path):
    use_fixture(monkeypatch, tmp_path, {**FIXTURE, "entries": [_e("Amikacin", ["250 mg", "500 mg"], ["Inj."], "500 mg", 1500)]})
    text = "amikacin 500 mg once daily"                  # Amikacin is Inj.-only; a missing or unknown form stays empty
    base = {"name": "Amikacin", "strength": "500 mg", "dose": "1-0-0", "duration": "5 days"}
    wrong = rowcheck.ground_one({**base, "form": "Tab."}, text, text, "45 / M")
    assert (wrong["status"], wrong["dose_note"]) == ("dose-check", "Tab. is not a usual form of Amikacin (usual: Inj.)")
    assert rowcheck.ground_one({**base, "form": "Inj."}, text, text, "45 / M")["status"] == "verified"
    for form, shown in (({}, ""), ({"form": ""}, ""), ({"form": "empty"}, ""), ({"form": "Tablet"}, "Tab.")):
        got = rowcheck.ground_one({**base, **form}, text, text, "45 / M")
        assert (got["status"], got["form"], got["dose_note"]) == ("verified", shown, "")   # never a form mismatch


def test_a_form_given_as_dictated_is_still_checked(monkeypatch, tmp_path):
    use_fixture(monkeypatch, tmp_path, {**FIXTURE, "entries": [_e("Amikacin", ["250 mg", "500 mg"], ["Inj."], "500 mg", 1500)]})
    got = rowcheck.ground_one({"name": "Amikacin", "strength": "500 mg", "dose": "1-0-0", "form": "Tab."}, "amikacin 500 mg", "amikacin 500 mg", "45 / M")
    assert got["status"] == "dose-check"


PARITY_ROWS = [
    ROW,
    {"name": "Paracetamol", "strength": "650 mg", "dose": "1-1-1", "form": "Tab.", "duration": "3 days"},
    {"name": "Zzqxwv", "strength": "5 mg", "dose": "1-0-0"},
    {"name": "Prednisolone", "strength": "10 mg", "dose": "1-0-0", "form": "Inj."},
    {"name": "Prednisolone", "strength": "10 mg", "dose": "1-0-0", "form": "Tablet"},
    {"name": "Prednisolone", "strength": "10 mg", "dose": "1-0-0"},
    {"name": "Paracetamol", "strength": "999 mg", "dose": "1-0-0"},
    {"name": "Crocin", "strength": "650 mg", "dose": "1-0-0"},
    {"name": "Metformin", "strength": "500 mg", "dose": "1-0-1", "timing": "after food"},
    {"name": "Metformin", "strength": "500 mg", "dose": "twice daily", "timing": "before bedtime"},
    {"name": "Metformin", "strength": "500 mg", "dose": "9-9-9", "timing": "whenever"},
    {"name": "Metformin", "strength": "500 mg", "dose": "", "timing": "as needed with food"},
    {"name": "Paracetamol", "strength": "650 mg", "dose": "1-0-0", "instructions": "x [unverified: confirm with doctor]"},
    {"name": "Prednisolone.", "strength": "", "dose": "1-0-0", "duration": "five days"},
    {"name": "", "strength": "10 mg", "dose": "1-0-0"},
    {"name": "Prednisone", "strength": "20 mg", "dose": "bogus"},
    {"name": "Paracetamol", "strength": "650 mg", "dose": "1-1-1", "form": "Syr."},
    {"name": "Tab Prednisone", "strength": "10 mg", "dose": "1-0-0", "form": ""},
    {"name": "Metformin", "strength": "500 mg", "dose": "1-0-1", "duration": "2 weeks"},
    {"name": "Paracetamol", "strength": "650 mg", "dose": "1-1-1", "form": "Tab.", "timing": "after meals"},
    {},
    {"name": " ", "strength": ""},
    {"dose": "1-0-0"},
    {"name": "", "strength": "", "dose": "nonsense", "form": "Inj."},
]


@pytest.mark.parametrize("age", ["45 / M", "", "10 / F"])
@pytest.mark.parametrize("item", PARITY_ROWS, ids=range(len(PARITY_ROWS)))
def test_ground_with_notes_matches_validate_structured_row_for_row(item, age, monkeypatch, tmp_path):
    use_fixture(monkeypatch, tmp_path)
    validated, warnings = validate_structured({"ageSex": age, "rx": [item]}, NORM, raw_transcript=RAW)
    got, notes = rowcheck.ground_with_notes(item, RAW, NORM, age, 0)
    assert notes == warnings
    assert got == (validated["rx"][0] if validated["rx"] else None)


def test_ground_one_and_validate_structured_give_identical_rows(monkeypatch, tmp_path):
    use_fixture(monkeypatch, tmp_path)                                         # so one row is a dose-check
    seen, real = [], rowcheck.ground_with_notes
    monkeypatch.setattr(rowcheck, "ground_with_notes", lambda *a, **k: seen.append(a) or real(*a, **k))
    rows = [ROW, {**ROW, "dose": "twice a week", "timing": "after meals", "duration": "for 5 days"},
            {"name": "Paracetamol", "strength": "650 mg", "dose": "1-1-1"}, {"name": "Zzqxwv"},
            {"name": "Metformin", "strength": "500 mg"}, {"name": "Amlodipine", "strength": "7 mg"},
            {"form": "Syringe", "name": "Prednisone.", "strength": " 10 mg ", "instructions": "with milk"}]
    for row in rows:
        seen.clear()
        validated, warnings = validate_structured({"ageSex": "45 / M", "rx": [row]}, NORM, raw_transcript=RAW)
        assert len(seen) == 1, "validate_structured must ground each row through rowcheck"
        assert rowcheck.ground_one(row, RAW, NORM, "45 / M") == validated["rx"][0], row
        assert rowcheck.ground_with_notes(row, RAW, NORM, "45 / M")[1] == warnings, row
    assert rowcheck.ground_one(rows[2], RAW, NORM, "45 / M")["status"] == "dose-check"


def test_form_words_map_whole_words_only():
    ok = {"tab": "Tab.", "Tabs": "Tab.", "Tablet": "Tab.", "TABLETS": "Tab.", " tab. ": "Tab.", "Tab.": "Tab.",
          "cap": "Cap.", "caps": "Cap.", "Capsule": "Cap.", "capsules": "Cap.", "Cap.": "Cap.",
          "syr": "Syr.", "Syrup": "Syr.", "syrups": "Syr.", "inj": "Inj.", "Injection": "Inj.", "injections": "Inj."}
    for word, shown in ok.items():
        assert rowcheck._coerce_form(word) == shown, word
    for word in ("Syringe", "capsicum", "capsule-shaped", "tablet-like", "inject", "", None, "empty"):
        assert rowcheck._coerce_form(word) == "", word
