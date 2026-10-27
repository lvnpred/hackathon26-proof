"""Plan C1: the stored form of added sections (structured["extra"]), the format draft and the cache key."""
import pytest
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.core.determinism import _FORMAT_CACHE, validate_structured
from doctor_dictation.core.sections import BUILT_INS, coerce_extra, fold, has_data, layout, parse, text_headings, unfold
from test_determinism import _stub_llm

FH = parse({"version": 1, "sections": [
    {"key": b.key, "heading": b.heading, "cue": "", "kind": b.kind, "order": b.order, "on": b.key != "advice"}
    for b in BUILT_INS] + [{"key": "family_history", "heading": "Family History", "cue": "", "kind": "text",
                            "order": 25, "on": True}]})
OLD = {"patientName": "Anita", "complaints": ["Fever"], "diagnosis": ["Viral"], "rx": [], "advice": ["Rest"], "review": "1 week"}


@pytest.fixture
def under_fh(monkeypatch):
    _FORMAT_CACHE.clear()
    monkeypatch.setattr("doctor_dictation.api.sections.sections_for", lambda clinic, doctor_id=None: FH)
    yield
    _FORMAT_CACHE.clear()


def test_an_old_form_validates_to_the_same_keys_without_extra():
    out = validate_structured(OLD, "")[0]
    assert "extra" not in out
    assert set(out) == {"patientName", "ageSex", "opNo", "diagnosis", "complaints", "findings", "investigations",
                        "rx", "advice", "review", "vitals"}


def test_coerce_extra_keeps_clean_entries_only():
    got = coerce_extra({"family_history": {"heading": " Family History ", "lines": [" a ", "", 3]},
                        "rx": {"heading": "R", "lines": ["x"]}, "Bad Key": {"lines": ["x"]},
                        "empty": {"lines": []}, "x_y": {"lines": ["q"]}}, limit=12)
    assert got == {"family_history": {"heading": "Family History", "lines": ["a", "3"]},
                   "x_y": {"heading": "X y", "lines": ["q"]}}
    assert coerce_extra("junk") == {}
    assert len(coerce_extra({"abc": {"lines": ["z" * 2500]}})["abc"]["lines"][0]) == 2000


def test_fold_unfold_round_trip_keeps_a_deleted_sections_heading():
    form = {"findings": [], "extra": {"old_sec": {"heading": "Old Sec", "lines": ["kept"]}}}
    flat, heads = unfold(form)
    assert flat["old_sec"] == ["kept"] and "extra" not in flat and heads == {"old_sec": "Old Sec"}
    assert fold({**flat, "family_history": ["x"]}, {**text_headings(FH), **heads})["extra"] == {
        "old_sec": {"heading": "Old Sec", "lines": ["kept"]},
        "family_history": {"heading": "Family History", "lines": ["x"]}}


def test_layout_shows_on_sections_and_off_or_deleted_ones_only_with_data():
    keys = [k for k, _, _ in layout(FH, {})]
    assert keys == ["complaints", "diagnosis", "family_history", "investigations", "findings", "rx", "review"]
    got = layout(FH, {"advice": ["Rest"], "extra": {"old_sec": {"heading": "Old", "lines": ["k"]}}})
    assert ("advice", "Dietary & General Advice", "list") in got and got[-1] == ("old_sec", "Old", "text")
    assert [k for k, _, _ in got].index("advice") == [k for k, _, _ in got].index("rx") + 1
    assert has_data({"rx": [{"name": ""}]}, "rx", "medication") is False
    assert has_data({"review": " "}, "review", "review") is False


def test_a_draft_files_added_lines_under_extra_and_blanks_off_sections(monkeypatch, under_fh):
    _stub_llm(monkeypatch, [{"complaints": ["Fever 3 days"], "family_history": ["Father diabetic"],
                             "advice": ["Rest"], "rx": []}])
    s = TestClient(M.app).post("/api/format", json={"transcript": "fever three days, father diabetic"}).json()["structured"]
    assert s["extra"] == {"family_history": {"heading": "Family History", "lines": ["Father diabetic"]}}
    assert s["advice"] == [] and "family_history" not in s


def test_the_format_cache_follows_the_section_list(monkeypatch):
    _FORMAT_CACHE.clear()
    c = TestClient(M.app)
    body = {"transcript": "fever three days"}
    use = lambda secs: monkeypatch.setattr("doctor_dictation.api.sections.sections_for",   # noqa: E731
                                           lambda clinic, doctor_id=None: secs)
    use(BUILT_INS)
    j = c.post("/api/format", json=body).json()
    assert j["cached"] is False and "extra" not in j["structured"]
    use(FH)
    assert c.post("/api/format", json=body).json()["cached"] is False
    assert c.post("/api/format", json=body).json()["cached"] is True
    _FORMAT_CACHE.clear()


def test_has_data_ignores_a_non_object_extra():
    for extra in (["x"], "x", 5, True):
        assert has_data({"extra": extra}, "family_history", "text") is False
        assert layout(FH, {"extra": extra})
