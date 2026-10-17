"""Plan I2-d: the schedule mark reaches brand and generic rows from generics.json; information only. Offline."""
from pathlib import Path

import pytest

from doctor_dictation.core import generics, rowcheck
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.determinism import validate_structured
from doctor_dictation.core.safety import screen_unverified

FIX = Path(__file__).parent / "data" / "generics_fixture.json"
T = "tab crocin 500 mg sos, tab paracetamol 500 mg, tab prednisolone 5 mg, tab cetirizine 10 mg"

@pytest.fixture()
def fixture_list(monkeypatch):
    monkeypatch.setattr(generics, "GENERICS_PATH", FIX)
    generics.reset()
    yield
    generics.reset()

def _rows(names):
    s, _w = validate_structured({"rx": [{"form": "Tab.", "name": n} for n in names]}, T, T)
    return s

def test_the_schedule_reaches_brand_and_generic_rows_and_is_information_only(fixture_list, monkeypatch):
    s = _rows(["Crocin", "Paracetamol", "Prednisolone", "Cetirizine", "Zzqxwv"])
    assert [(r["name"], r["schedule"]) for r in s["rx"]] == [("Crocin", "H"), ("Paracetamol", "H"), ("Prednisolone", "X"), ("Cetirizine", ""), ("Zzqxwv", "")]
    with_marks = [(r["status"], r["instructions"]) for r in s["rx"]]
    monkeypatch.setattr(generics, "GENERICS_PATH", FIX.with_name("absent.json"))
    generics.reset()
    assert [(r["status"], r["instructions"]) for r in _rows(["Crocin", "Paracetamol", "Prednisolone", "Cetirizine", "Zzqxwv"])["rx"]] == with_marks
    assert screen_unverified(s, []) == [dict(index=i, name=r["name"], status=r["status"]) for i, r in enumerate(s["rx"]) if r["status"] != "verified"]
    assert [r["status"] for r in s["rx"]][:2] == ["verified", "verified"]                                # Crocin, Paracetamol (X row too: no block by mark)
    assert generics.generics_version() == "" and generics.RANK == {"H": 1, "H1": 2, "X": 3}

def test_the_schedule_is_recomputed_on_correct_and_save_and_follows_a_hand_edit(fixture_list):
    cur = {"rx": [{"name": "Crocin", "status": "verified", "lexicon_match": "Paracetamol", "instructions": ""},
                  {"name": "Febuxostat", "status": "", "lexicon_match": "Paracetamol", "instructions": ""}]}   # renamed by hand
    fresh = [dict(r, status="x", lexicon_match="x", schedule="STALE") for r in cur["rx"]]
    rows = preserve_untouched_rx_status(cur, {}, {"rx": fresh})["rx"]
    assert [r["schedule"] for r in rows] == ["H", ""]
    assert "schedule" in rowcheck.ground_one({"name": "Crocin"}, T, T)

def test_a_missing_or_broken_generics_file_means_no_schedule(monkeypatch, tmp_path):
    for content in (None, "{not json", '{"entries": "x"}', '{"entries": [{"lexicon": "Paracetamol", "lists": {"L": {"schedule": "Q"}}}]}'):
        path = tmp_path / "g.json"
        if content is not None:
            path.write_text(content, encoding="utf-8")
        monkeypatch.setattr(generics, "GENERICS_PATH", path if content is not None else tmp_path / "none.json")
        generics.reset()
        assert generics.schedule_of("Paracetamol") == "" and generics.schedule_of("") == ""
    generics.reset()


def test_reload_picks_up_a_changed_file_in_the_same_process(monkeypatch, tmp_path):
    f = tmp_path / "generics.json"
    f.write_text('{"entries": [{"generic": "Zorb", "lexicon": "Zorb", "lists": {"L": {"src": "a", "schedule": "H"}}}], "sources": [], "version": "0.1.0"}', encoding="utf-8")
    monkeypatch.setattr(generics, "GENERICS_PATH", f)
    generics.reset()
    try:
        assert (generics.schedule_of("Zorb"), generics.generics_version()) == ("H", "0.1.0")
        f.write_text(f.read_text(encoding="utf-8").replace('"H"', '"X"').replace("0.1.0", "0.2.0"), encoding="utf-8")
        assert generics.schedule_of("Zorb") == "H"                                  # still cached: a running server needs a restart or reload
        generics.reload()
        assert (generics.schedule_of("Zorb"), generics.generics_version()) == ("X", "0.2.0")
        f.unlink()
        generics.reload()
        assert generics.schedule_of("Zorb") == "" and generics.generics_version() == ""
    finally:
        generics.reset()
