"""core/dosing.py: strength chips and the daily-total check, against a synthetic reference. Offline."""
import pytest

from doctor_dictation.core import determinism, dosing
from doctor_dictation.core.determinism import ALLOWED_DOSES
from doctor_dictation.core.dosing import check_dose, strength_options
from dosing_fixtures import use_fixture

pytestmark = pytest.mark.usefixtures("frozen_lexicon")   # pins strengths of drugs.json v1.1.0 (plan I1-g simple, Task 3)

@pytest.fixture()
def ref(monkeypatch, tmp_path):
    use_fixture(monkeypatch, tmp_path)

def _state(*args, **kw):
    return check_dose(*args, **kw).state

def test_shipped_reference_is_empty_so_every_drug_is_cannot_check():
    assert dosing.dosing_version() == "none" and dosing._load()["entries"] == {}       # Delete this line when real data ships
    assert _state("Paracetamol", "500 mg", "1-1-1", "45 / M") == "cannot-check"
    assert strength_options("Paracetamol") == (["500 mg", "650 mg", "120 mg/5ml"], "")
    assert set(dosing.DAILY_UNITS) == set(ALLOWED_DOSES) - {"SOS"}

def test_in_range_at_max_and_above_max(ref):
    ok = check_dose("Paracetamol", "500 mg", "1-0-1", "45 / M")
    assert (ok.state, ok.daily_mg, ok.max_daily_mg, ok.note) == ("in-range", 1000.0, 1500.0, "")
    assert _state("Paracetamol", "500 mg", "1-1-1", "18 / M") == "in-range"            # exactly 1500, age 18
    assert _state("Digoxin", "0.25 mg", "1-1-1", "70 / F") == "in-range"               # 0.75: no float noise
    v = check_dose("Paracetamol", "650 mg", "1-1-1", "45 / M")
    assert (v.state, v.daily_mg, v.note) == ("above-max", 1950.0, "1950 mg a day; usual adult maximum 1500 mg")

@pytest.mark.parametrize("args", [
    ("Paracetamol", "650 mg", "SOS", "45 / M"), ("Paracetamol", "650 mg", "2-2-2-2", "45 / M"),
    ("Amlodipine", "10 mg", "1-1-1", "45 / M"),                                          # unreviewed: 30 > 10
    ("Metformin", "500 mg", "1-1-1", "45 / M"), ("", "500 mg", "1-1-1", "45 / M"),       # not in the reference
    ("Paracetamol", "650 mg", "1-1-1", "8 / F"), ("Paracetamol", "650 mg", "1-1-1", "17 / M"),
    ("Paracetamol", "650 mg", "1-1-1", "6 months"), ("Paracetamol", "650 mg", "1-1-1", ""),
    ("Paracetamol", "120 mg/5ml", "1-1-1", "45 / M"), ("Paracetamol", "100 IU", "1-1-1", "45 / M"),
])
def test_cannot_check_never_flags(ref, args):
    v = check_dose(*args)
    assert (v.state, v.note) == ("cannot-check", "")

def test_unit_conversion(ref):
    assert check_dose("Paracetamol", "1000 mg", "1-0-1", "45 / M").daily_mg == 2000.0
    assert _state("Paracetamol", "0.5 g", "1-1-1", "45 / M") == "in-range"                # 1500 mg
    assert check_dose("Digoxin", "250 mcg", "1-0-0", "45 / M").daily_mg == 0.25

def test_form_mismatch_flags_only_a_reviewed_entry_and_an_adult(ref):
    v = check_dose("Prednisolone", "10 mg", "1-0-0", "45 / M", form="Inj.")
    assert (v.state, v.note) == ("form-mismatch", "Inj. is not a usual form of Prednisolone (usual: Tab., Syr.)")
    assert _state("Prednisolone", "10 mg", "1-0-0", "45 / M", form="Tab.") == "in-range"
    assert _state("Prednisolone", "10 mg", "1-0-0", "45 / M") == "in-range"                # no form given
    assert _state("Amlodipine", "5 mg", "1-0-0", "45 / M", form="Syr.") == "cannot-check"
    assert _state("Prednisolone", "10 mg", "1-0-0", "8 / F", form="Inj.") == "cannot-check"

def test_strength_options_usual_first_else_the_lexicon_never_made_up(ref):
    assert strength_options("Paracetamol") == (["650 mg", "500 mg", "1 g"], "650 mg")
    assert strength_options("Metformin") == (["500 mg", "850 mg", "1000 mg"], "")
    assert strength_options("Not A Drug") == ([], "")

def test_an_unreadable_reference_is_reported_not_trusted(monkeypatch, tmp_path):
    (tmp_path / "dosing.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(dosing, "DOSING_PATH", tmp_path / "dosing.json")
    assert dosing.dosing_version() == "unreadable" and _state("Paracetamol", "650 mg", "1-1-1", "45 / M") == "cannot-check"

# ---- fix round 1: validation of the reference shape, age and strength parsing ----
import copy
import json
import logging

from doctor_dictation.core.dosing import age_years, ground_extra, parse_strength_mg
from dosing_fixtures import FIXTURE, _e

LEX_PARACETAMOL = ["500 mg", "650 mg", "120 mg/5ml"]

@pytest.mark.parametrize("text,want", [
    ("45 / M", 45), ("45Y/M", 45), ("45yrs", 45), ("17", 17), ("18", 18), ("45.5", 45), ("120", 120),
    ("121", None), ("130", None), ("", None), (None, None), ("Age 45", None), ("M/45", None),
    ("6 months", 0), ("3 weeks", 0), ("10 days", 0), ("0.5 yr", 0), ("45 years", 45), ("45 y", 45),
    ("24 mths", 0), ("36 mth", 0), ("18 mths", 0), ("24 m", None), ("30 min", None), ("2 wk", 0),
    ("1000", None), ("1000 / M", None),
])
def test_age_years_table(text, want):
    assert age_years(text) == want

@pytest.mark.parametrize("text,want", [
    ("5mg", 5), ("5 MG", 5), ("0.5 g", 500), ("250 mcg", "0.25"), ("5 µg", "0.005"),
    ("500 mg/5ml", None), ("5 ml", None), ("1,000 mg", None), ("½ mg", None), ("-5 mg", None),
    (".5 mg", None), ("1e3 mg", None), ("", None), (None, None), (650, None),
])
def test_parse_strength_mg_table(text, want):
    got = parse_strength_mg(text)
    assert got == (None if want is None else dosing.Decimal(str(want)))

def test_non_string_strength_is_cannot_check(ref):
    assert _state("Paracetamol", 650, "1-1-1", "45 / M") == "cannot-check"
    assert _state("Paracetamol", None, "1-1-1", "45 / M") == "cannot-check"

def test_ground_extra_ranks_and_fields(ref):
    st, f = ground_extra("verified", "Paracetamol", "", "650 mg", "1-1-1", "45 / M")
    assert st == "dose-check" and f == {"strength_options": ["650 mg", "500 mg", "1 g"],
                                       "usual_strength": "650 mg", "dose_note": "1950 mg a day; usual adult maximum 1500 mg"}
    assert ground_extra("lookalike-check", "Paracetamol", "", "650 mg", "1-1-1", "45 / M")[0] == "dose-check"
    st, f = ground_extra("unverified", "Paracetamol", "", "650 mg", "1-1-1", "45 / M")
    assert st == "unverified" and f["dose_note"] == ""
    st, f = ground_extra("verified", "Paracetamol", "", "500 mg", "1-0-1", "45 / M")
    assert st == "verified" and f["dose_note"] == ""
    st, f = ground_extra("verified", "", "", "500 mg", "1-0-1", "45 / M")
    assert st == "verified" and f["strength_options"] == []

def test_lexicon_fallback_is_case_insensitive():
    assert strength_options("paracetamol") == (LEX_PARACETAMOL, "")
    assert strength_options("") == ([], "") and strength_options(None) == ([], "")

def _bad(**over):
    e = _e("Paracetamol", ["500 mg"], ["Tab."], "500 mg", 1500)
    e.update(over)
    return e

_NAN, _INF = float("nan"), float("inf")
CORRUPT = {
    "nan cap": [_bad(adult={"usual": "500 mg", "max_daily_mg": _NAN})],
    "inf cap": [_bad(adult={"usual": "500 mg", "max_daily_mg": _INF})],
    "adult string": [_bad(adult="oops")],
    "adult list": [_bad(adult=[1])],
    "forms int": [_bad(forms=5)],
    "forms int items": [_bad(forms=[1, 2])],
    "forms string": [_bad(forms="Tab.")],
    "strengths int": [_bad(strengths=5)],
    "strengths string": [_bad(strengths="500 mg")],
    "strengths non-str": [_bad(strengths=[500, None])],
    "bool cap": [_bad(adult={"max_daily_mg": True})],
    "usual int": [_bad(adult={"usual": 5, "max_daily_mg": 1500})],
    "duplicate": [_bad(), _bad(canonical="PARACETAMOL", adult={"usual": "500 mg", "max_daily_mg": 99999})],
    "non-dict entry": [5, "x", None],
    "empty canonical": [_bad(canonical="")],
}

@pytest.mark.parametrize("name", list(CORRUPT))
def test_corrupt_reference_entries_are_dropped(monkeypatch, tmp_path, caplog, name):
    data = {"version": "t", "built_at": "", "entries": CORRUPT[name]}
    (tmp_path / "dosing.json").write_text(json.dumps(data), encoding="utf-8")   # json emits NaN/Infinity
    monkeypatch.setattr(dosing, "DOSING_PATH", tmp_path / "dosing.json")
    with caplog.at_level(logging.WARNING, logger=dosing.__name__):
        v = check_dose("Paracetamol", "500 mg", "1-1-1", "45 / M", form="Syr.")
        opts = strength_options("Paracetamol")
        gx = ground_extra("verified", "Paracetamol", "Syr.", "500 mg", "1-1-1", "45 / M")
    assert v.state == "cannot-check" and v.note == ""
    assert opts == (LEX_PARACETAMOL, "")                       # nothing from the dropped entry
    assert gx[0] == "verified" and gx[1]["dose_note"] == ""
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1

def test_one_bad_entry_does_not_hurt_a_good_one(monkeypatch, tmp_path, caplog):
    data = copy.deepcopy(FIXTURE)
    data["entries"].append(_bad(canonical="Warfarin", adult="oops"))
    (tmp_path / "dosing.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(dosing, "DOSING_PATH", tmp_path / "dosing.json")
    with caplog.at_level(logging.WARNING, logger=dosing.__name__):
        assert _state("Paracetamol", "650 mg", "1-1-1", "45 / M") == "above-max"
    msgs = [r.getMessage() for r in caplog.records]
    assert len(msgs) == 1 and "Warfarin" in msgs[0] and "1" in msgs[0]

def test_no_warning_when_nothing_dropped(ref, caplog):
    with caplog.at_level(logging.WARNING, logger=dosing.__name__):
        _state("Paracetamol", "650 mg", "1-1-1", "45 / M")
    assert not caplog.records

# ---- final fix round: unreadable reference robustness ----
def _ref_file(monkeypatch, tmp_path, text):
    (tmp_path / "dosing.json").write_text(text, encoding="utf-8")
    monkeypatch.setattr(dosing, "DOSING_PATH", tmp_path / "dosing.json")

def test_absurdly_nested_json_is_just_an_unreadable_reference(monkeypatch, tmp_path, caplog):
    _ref_file(monkeypatch, tmp_path, "[" * 100000 + "]" * 100000)
    with caplog.at_level(logging.WARNING, logger=dosing.__name__):
        assert dosing.dosing_version() == "unreadable"
        assert _state("Paracetamol", "650 mg", "1-1-1", "45 / M") == "cannot-check"
    _routes_still_work(monkeypatch, "unreadable")

def _routes_still_work(monkeypatch, version):
    """health and an OFFLINE /api/format (no API keys, so no network path exists) both answer 200."""
    from fastapi.testclient import TestClient

    import doctor_dictation.main as M
    from doctor_dictation.config import override_settings
    monkeypatch.setattr(determinism, "_FORMAT_CACHE", {})
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    c = TestClient(M.app)
    assert c.get("/api/health").json()["dosing_version"] == version
    r = c.post("/api/format", json={"transcript": "tablet paracetamol 650 mg thrice daily"})
    assert r.status_code == 200 and r.json()["engine"].startswith("fallback-rules+lexicon"), r.text

def test_a_401_digit_cap_drops_the_entry_and_nothing_crashes(monkeypatch, tmp_path, caplog):
    data = copy.deepcopy(FIXTURE)
    text = json.dumps(data).replace('"max_daily_mg": 1500', '"max_daily_mg": 1' + "0" * 400)
    assert "0" * 400 in text
    _ref_file(monkeypatch, tmp_path, text)
    with caplog.at_level(logging.WARNING, logger=dosing.__name__):
        assert _state("Paracetamol", "650 mg", "1-1-1", "45 / M") == "cannot-check"
    assert any("Paracetamol" in r.getMessage() for r in caplog.records)
    _routes_still_work(monkeypatch, "test-1")

def test_above_max_outranks_form_mismatch_and_a_form_mismatch_shows_when_the_dose_is_fine(monkeypatch, tmp_path):
    data = copy.deepcopy(FIXTURE)
    data["entries"].append(_e("Ceftriaxone", ["250 mg", "1 g"], ["Inj."], "1 g", 2000))   # the lexicon lists only Inj.
    use_fixture(monkeypatch, tmp_path, data)
    v = check_dose("Ceftriaxone", "1 g", "1-1-1", "45 / M", "Tab.")                      # 3000 > 2000 and the wrong form
    assert (v.state, v.note) == ("above-max", "3000 mg a day; usual adult maximum 2000 mg")
    v = check_dose("Ceftriaxone", "250 mg", "1-0-0", "45 / M", "Tab.")
    assert (v.state, v.note) == ("form-mismatch", "Tab. is not a usual form of Ceftriaxone (usual: Inj.)")

@pytest.mark.parametrize("how", ["truncated", "missing", "directory", "entries int", "no version", "not an object"])
def test_a_wholly_unreadable_reference_logs_one_warning(monkeypatch, tmp_path, caplog, how):
    if how == "missing":
        monkeypatch.setattr(dosing, "DOSING_PATH", tmp_path / "nope.json")
    elif how == "directory":
        monkeypatch.setattr(dosing, "DOSING_PATH", tmp_path)
    else:
        text = {"truncated": '{"version": "t", "entr', "entries int": '{"version": "t", "entries": 5}',
                "no version": '{"entries": []}', "not an object": "[1, 2]"}[how]
        _ref_file(monkeypatch, tmp_path, text)
    with caplog.at_level(logging.WARNING, logger=dosing.__name__):
        assert dosing.dosing_version() == "unreadable"
        dosing._load()
        dosing._load()
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "unreadable" in warnings[0].getMessage()

def test_the_shipped_empty_reference_logs_nothing(caplog):
    with caplog.at_level(logging.WARNING, logger=dosing.__name__):
        dosing._load()
    assert not caplog.records
