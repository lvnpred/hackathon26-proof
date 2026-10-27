"""Plan C1: the sections settings file, its strict loader and the single reader."""
import json

import pytest
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.api import sections as reader
from doctor_dictation.core import sections as S
from doctor_dictation.core.sections import BUILT_INS, KINDS, SectionsError, load_file, parse

HEADINGS = ["Chief Complaints & Brief History", "Diagnosis / Clinical Impression", "Investigations Advised", "Findings",
            "Rx (MEDICATIONS)", "Dietary & General Advice", "Review / Follow-up"]
ORDER = ["complaints", "diagnosis", "investigations", "findings", "rx", "advice", "review"]


def E(key, kind="text", **kw):
    return {"key": key, "heading": key.title(), "cue": "", "kind": kind, "order": 100, "on": True, **kw}


def doc(*entries, **kw):
    return {"version": 1, "sections": list(entries), **kw}


def test_the_shipped_file_parses_and_holds_every_built_in():
    assert {s.key for s in load_file()} >= set(KINDS)
    row = lambda s: (s.key, s.heading, s.kind, s.order, s.on)  # noqa: E731
    assert [row(s) for s in load_file()] == [row(s) for s in BUILT_INS]
    assert [s.key for s in BUILT_INS] == ORDER
    assert [s.heading for s in BUILT_INS] == HEADINGS
    assert [s.kind for s in BUILT_INS] == ["prose", "prose", "investigations", "prose", "medication", "list", "review"]


@pytest.mark.parametrize("data,match", [
    (doc(E("family"), E("family")), "duplicate"),
    (doc(E("family", heading="")), "heading"),
    (doc(E("family", heading="x" * 61)), "heading"),
    (doc(E("family", cue="x" * 121)), "cue"),
    (doc(E("family", on="yes")), "on"),
    (doc(E("family", order="1")), "order"),
    (doc(E("family"), version=2), "version"),
    (doc(E("family"), version=True), "version"),
    (doc(E("family"), version=1.0), "version"),
    ({"version": 1, "sections": {}}, "sections"),
    (doc(*[E(f"extra_{i}") for i in range(11)]), "too many"),
])
def test_bad_entries_name_what_is_wrong(data, match):
    with pytest.raises(SectionsError, match=match):
        parse(data)


@pytest.mark.parametrize("entry", [E("Family History"), E("rx2-"), E("x"), E("vitals"), E("extra"), E("remove"),
                                   E("replace"), E("review_date"), E("family_history", kind="prose"), E("rx", kind="text")])
def test_added_keys_must_be_new_slugs_of_kind_text(entry):
    with pytest.raises(SectionsError, match="key|reserved|kind"):
        parse(doc(entry))


def test_a_valid_added_key_is_kind_text():
    assert {s.key: s for s in parse(doc(E("family_history")))}["family_history"].kind == "text"


def test_order_off_and_missing_built_ins():
    keep = [b for b in ORDER if b != "advice"]
    entries = [E(k, kind=KINDS[k], heading=BUILT_INS[ORDER.index(k)].heading, order=10 * (ORDER.index(k) + 1),
                 on=k != "findings") for k in keep]
    entries.insert(2, E("family_history", order=25))
    secs = {s.key: s for s in parse(doc(*entries))}
    assert [s.key for s in parse(doc(*entries))] == ["complaints", "diagnosis", "family_history", "investigations",
                                                    "findings", "rx", "advice", "review"]
    assert secs["findings"].on is False
    assert secs["advice"].on is False and secs["advice"].heading == "Dietary & General Advice"
    assert [s.key for s in parse(doc(E("bb", order=5), E("aa", order=5)))][:2] == ["bb", "aa"]


@pytest.mark.parametrize("text", [json.dumps({"version": 1, "sections": [{"key": "rx"}, {"key": "rx"}]}), "{not json"])
def test_the_reader_falls_back_to_the_built_ins_when_the_file_is_broken(tmp_path, monkeypatch, caplog, text):
    bad = tmp_path / "sections.json"
    bad.write_text(text)
    monkeypatch.setattr(S, "DEFAULT_PATH", bad)
    reader._shipped.cache_clear()
    try:
        with caplog.at_level("WARNING"):
            assert reader.sections_for("a") == BUILT_INS
        assert len([r for r in caplog.records if "sections.json" in r.getMessage()]) == 1
    finally:
        monkeypatch.undo()
        reader._shipped.cache_clear()
    assert reader.sections_for("a") == reader.sections_for("b", 7) == load_file()


def test_the_route_lists_the_sections_in_order():
    r = TestClient(M.app).get("/api/v1/sections")
    assert r.status_code == 200
    body = r.json()
    assert [s["key"] for s in body["sections"]] == [s.key for s in load_file()]
    assert all(set(s) == {"key", "heading", "cue", "kind", "order", "on"} for s in body["sections"])
