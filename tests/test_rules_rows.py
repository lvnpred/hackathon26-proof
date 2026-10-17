"""Fix batch 2: the rules-only medicine rows keep what was dictated (suffix, bare strength, duration) and never vanish silently."""
import pytest
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.core.determinism import _FORMAT_CACHE, normalize_transcript, validate_structured
from doctor_dictation.core.fallback import fallback_format, unparsed_notes


def _rows(text):
    return [(r["form"], r["name"], r["strength"], r["dose"], r["duration"]) for r in fallback_format(normalize_transcript(text))["rx"]]


@pytest.mark.parametrize("text,rows", [
    ("Tab Moxikind CV 625 twice a day for 5 days", [("Tab.", "Moxikind CV", "625", "1-0-1", "5 days")]),
    ("Tab Dolo 650 thrice a day for 3 days", [("Tab.", "Dolo", "650", "1-1-1", "3 days")]),
    ("Tab Paracetamol 500 SOS for 5 days", [("Tab.", "Paracetamol", "500", "SOS", "5 days")]),
    ("have paracetamol twice a day", [("", "Paracetamol", "", "1-0-1", "")]),           # nothing dictated, nothing added
    ("have paracetamol twice a day for 2 weeks", [("", "Paracetamol", "", "1-0-1", "2 weeks")]),
    ("Tab Crocin bd for 3 days", [("Tab.", "Crocin", "", "1-0-1", "3 days")]),            # "bd" is a frequency, not a suffix
    ("Tab Dolo XR 650 once daily", [("Tab.", "Dolo XR", "650", "1-0-0", "")]),
    ("Tab Paracetamol 650 mg twice daily for 3 days", [("Tab.", "Paracetamol", "650 mg", "1-0-1", "3 days")]),   # the unit branch is unchanged
])
def test_no_strength_branch_rows_keep_suffix_bare_strength_and_duration(text, rows):
    assert _rows(text) == rows


def test_a_combination_brand_is_not_confirmed_as_its_first_word_alone():
    norm = normalize_transcript("Tab Moxikind CV 625 twice a day for 5 days")
    out, _w = validate_structured(fallback_format(norm), norm)
    row = out["rx"][0]
    assert row["name"] == "Moxikind CV" and row["status"] != "verified", row


def test_a_bare_number_after_a_duration_word_is_not_a_strength():
    assert _rows("have paracetamol 2 days")[0][2] == ""


def test_an_unparsed_medicine_line_is_reported_with_the_dictated_words():
    text = normalize_transcript("fever since 2 days. Tab Montair LC 1 tab at bedtime for 1 month. tab Pantoprazole 40 mg once daily")
    rows = fallback_format(text)["rx"]
    assert [r["name"] for r in rows] == ["Pantoprazole"]
    assert unparsed_notes(text, rows) == ["A medicine line was not understood: Tab Montair LC 1 tab at bedtime for 1 month"]
    ok = normalize_transcript("tab Pantoprazole 40 mg once daily after food for 5 days, tab Dolo 650 mg SOS")
    assert unparsed_notes(ok, fallback_format(ok)["rx"]) == [] and unparsed_notes("", []) == []


def test_the_format_route_shows_the_unparsed_line_on_the_rules_path():
    _FORMAT_CACHE.clear()
    j = TestClient(M.app).post("/api/format", json={"transcript": "fever since 2 days. Tab Montair LC 1 tab at bedtime for 1 month"}).json()
    assert j["engine"].startswith("fallback-rules")
    assert "A medicine line was not understood: Tab Montair LC 1 tab at bedtime for 1 month" in j["warnings"]


def test_the_golden_dictations_raise_no_false_unparsed_note():
    import json
    from pathlib import Path
    for c in json.loads((Path(__file__).parent / "golden.json").read_text()):
        t = normalize_transcript(c["transcript"])
        assert unparsed_notes(t, fallback_format(t)["rx"]) == [], c["id"]


def test_the_error_fallback_path_also_reports_the_unparsed_line(monkeypatch):
    _FORMAT_CACHE.clear()

    class Broken:
        name, model = "x", "y"

        async def complete_json(self, messages):
            raise RuntimeError("down")
    monkeypatch.setattr("doctor_dictation.api.format.make_llm", lambda settings: Broken())
    j = TestClient(M.app).post("/api/format", json={"transcript": "Tab Montair LC 1 tab at bedtime for 1 month"}).json()
    assert j["engine"].startswith("fallback-after-error")
    assert "A medicine line was not understood: Tab Montair LC 1 tab at bedtime for 1 month" in j["warnings"]
