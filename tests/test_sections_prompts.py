"""Plan C1: the prompts learn the section list; corrections treat added sections like findings."""
import json
import pytest
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.api.format import PROMPT_SHA, SYSTEM_PROMPT
from doctor_dictation.core.correction import CORRECTION_INSTRUCTION, LIST_FIELDS, build_correction_messages, merge_form
from doctor_dictation.core.determinism import _FORMAT_CACHE, transcript_sha
from doctor_dictation.core.ops import apply_ops
from doctor_dictation.core.sections import BUILT_INS, signature as sections_signature, coerce_extra, correction_rule, format_rule, parse
from test_determinism import _stub_llm


def _list(cue="Father diabetic, mother hypertensive", heading="Family History"):
    return parse({"version": 1, "sections": [
        {"key": b.key, "heading": b.heading, "cue": "", "kind": b.kind, "order": b.order, "on": b.key != "advice"}
        for b in BUILT_INS] + [{"key": "family_history", "heading": heading, "cue": cue, "kind": "text",
                                "order": 25, "on": True}]})


FH = _list()
FORMAT_RULE = ('\n15. Added sections: also return each of these keys in the JSON object, a list of short sentences '
               'restating ONLY what the doctor dictated for it, [] if nothing was dictated, each item at most 400 '
               'characters: "family_history" (Family History, for example "Father diabetic, mother hypertensive").')
CORRECTION_RULE = ('\n17. Added list sections work like findings in rule 7, and "remove" and "replace" take their '
                   'keys too: "family_history" (Family History).')
CURRENT = {"complaints": ["Fever"], "advice": ["Rest"], "rx": [], "review": "",
           "extra": {"family_history": {"heading": "Family History", "lines": ["Father diabetic", "Mother hypertensive"]},
                     "old_sec": {"heading": "Old Sec", "lines": ["kept"]}}}


@pytest.fixture
def under_fh(monkeypatch):
    _FORMAT_CACHE.clear()
    monkeypatch.setattr("doctor_dictation.api.sections.sections_for", lambda clinic, doctor_id=None: FH)
    yield
    _FORMAT_CACHE.clear()


def _correct(monkeypatch, patch, form=CURRENT):
    calls = _stub_llm(monkeypatch, [patch])
    j = TestClient(M.app).post("/api/v1/correct", json={"transcript": "correction", "current_form": form}).json()
    return j, calls["messages"][0]


def test_the_default_list_leaves_both_prompts_unchanged():
    assert format_rule(BUILT_INS) == "" == correction_rule({})
    assert build_correction_messages("t", {})[0]["content"] == CORRECTION_INSTRUCTION
    assert transcript_sha(SYSTEM_PROMPT + format_rule(BUILT_INS))[:12] == PROMPT_SHA


def test_the_rules_name_each_added_key_with_heading_and_cue(monkeypatch, under_fh):
    assert format_rule(FH) == FORMAT_RULE
    assert correction_rule({"family_history": "Family History"}) == CORRECTION_RULE
    assert '"x" (X)' in correction_rule({"x": "X"}) and 'for example' not in format_rule(_list(cue=""))
    calls = _stub_llm(monkeypatch, [{"rx": []}])
    TestClient(M.app).post("/api/format", json={"transcript": "fever three days"})
    assert calls["messages"][0][0]["content"].endswith(FORMAT_RULE)


def test_editing_an_added_heading_or_cue_changes_the_format_cache_key(monkeypatch):
    _FORMAT_CACHE.clear()
    c = TestClient(M.app)
    seen = []
    for secs in (_list(), _list(heading="Family Hx"), _list(cue="Parents unwell")):
        monkeypatch.setattr("doctor_dictation.api.sections.sections_for", lambda clinic, doctor_id=None, s=secs: s)
        seen.append(c.post("/api/format", json={"transcript": "fever three days"}).json()["cached"])
    assert seen == [False, False, False]
    _FORMAT_CACHE.clear()


def test_a_correction_adds_removes_and_replaces_lines_of_an_added_section(monkeypatch, under_fh):
    j, msgs = _correct(monkeypatch, {"family_history": ["Brother asthmatic"]})
    assert j["structured"]["extra"]["family_history"]["lines"] == ["Father diabetic", "Mother hypertensive", "Brother asthmatic"]
    sent = json.loads(msgs[1]["content"])["current_form"]
    assert sent["family_history"] == ["Father diabetic", "Mother hypertensive"] and "extra" not in sent
    assert msgs[0]["content"].endswith(CORRECTION_RULE[:-1] + '; "old_sec" (Old Sec).')   # a stored section the list lost
    j, _ = _correct(monkeypatch, {"remove": {"family_history": ["Mother hypertensive"]}})
    assert j["structured"]["extra"]["family_history"]["lines"] == ["Father diabetic"]
    assert "Removed Mother hypertensive." in j["warnings"]
    j, _ = _correct(monkeypatch, {"replace": {"family_history": [{"from": "Father diabetic", "to": "Father diabetic since 2010"}]}})
    assert j["structured"]["extra"]["family_history"]["lines"] == ["Father diabetic since 2010", "Mother hypertensive"]


def test_a_correction_keeps_a_deleted_section_and_an_off_built_in(monkeypatch, under_fh):
    j, _ = _correct(monkeypatch, {"complaints": ["Cough"]})
    s = j["structured"]
    assert s["advice"] == ["Rest"] and s["extra"]["old_sec"] == {"heading": "Old Sec", "lines": ["kept"]}
    assert "Cough" in s["complaints"]


def test_merge_and_ops_default_to_todays_fields():
    assert merge_form({"family_history": ["a"]}, {"family_history": ["b"]}) == {"family_history": ["b"]}
    assert merge_form({"family_history": ["a"]}, {"family_history": ["b"]},
                      list_fields=LIST_FIELDS + ("family_history",)) == {"family_history": ["a", "b"]}
    op, fh = {"remove": {"family_history": ["asthma"]}}, ["asthma", "diabetes"]
    assert apply_ops({"family_history": fh}, op)[0]["family_history"] == fh
    assert apply_ops({"family_history": fh}, op, fields=("rx",) + LIST_FIELDS + ("family_history",))[0]["family_history"] == ["diabetes"]


def test_a_new_draft_leaves_an_off_or_unlisted_added_section_empty(monkeypatch, under_fh):
    _stub_llm(monkeypatch, [{"rx": [], "family_history": ["Father diabetic"], "social": ["Smoker"]}])
    s = TestClient(M.app).post("/api/format", json={"transcript": "x y"}).json()["structured"]
    assert s["extra"] == {"family_history": {"heading": "Family History", "lines": ["Father diabetic"]}}
    j = {"extra": {"social": {"heading": "Social", "lines": ["Smoker"]}, "family_history": {"lines": ["a"]}}}
    from doctor_dictation.api.format import _validate_draft
    import asyncio
    out = asyncio.run(_validate_draft(j, "x", "x", secs=parse({"version": 1, "sections": []})))[0]
    assert "extra" not in out


def test_coerce_extra_skips_null_lines():
    assert coerce_extra({"abc": {"lines": [None, "a", 3]}}) == {"abc": {"heading": "Abc", "lines": ["a", "3"]}}


def test_a_correction_never_trusts_an_extra_from_the_model(monkeypatch, under_fh):
    patch = {"extra": {"family_history": {"heading": "LLM Heading", "lines": ["a"]}, "social": {"heading": "Social", "lines": ["Smoker"]}},
             "remove": {"family_history": ["Mother hypertensive"]}}
    s = _correct(monkeypatch, patch)[0]["structured"]
    assert s["extra"]["family_history"] == {"heading": "Family History", "lines": ["Father diabetic"]}
    assert "social" not in s["extra"]


def test_a_correction_keeps_the_stored_heading_when_the_registry_heading_changes(monkeypatch):
    _FORMAT_CACHE.clear()
    monkeypatch.setattr("doctor_dictation.api.sections.sections_for", lambda clinic, doctor_id=None: _list(heading="Family Hx"))
    s = _correct(monkeypatch, {"family_history": ["Brother asthmatic"]})[0]["structured"]
    assert s["extra"]["family_history"]["heading"] == "Family History"
    assert s["extra"]["family_history"]["lines"][-1] == "Brother asthmatic"


def test_a_draft_ignores_the_models_extra_heading():
    import asyncio
    from doctor_dictation.api.format import _validate_draft
    d = {"extra": {"family_history": {"heading": "Totally Other", "lines": ["a"]}}}
    out = asyncio.run(_validate_draft(d, "x", "x", secs=FH))[0]
    assert "extra" not in out
    d = {"family_history": ["a"], "extra": {"family_history": {"heading": "Totally Other", "lines": ["b"]}}}
    out = asyncio.run(_validate_draft(d, "x", "x", secs=FH))[0]
    assert out["extra"] == {"family_history": {"heading": "Family History", "lines": ["a"]}}


def test_switching_advice_off_changes_the_cache_key_and_blanks_advice(monkeypatch):
    _FORMAT_CACHE.clear()
    _stub_llm(monkeypatch, [{"rx": [], "advice": ["Rest"]}, {"rx": [], "advice": ["Rest"]}])
    c = TestClient(M.app)
    seen = []
    advice_off = parse({"version": 1, "sections": [        # same keys and order as BUILT_INS; only advice's flag differs
        {"key": b.key, "heading": b.heading, "cue": "", "kind": b.kind, "order": b.order, "on": b.key != "advice"}
        for b in BUILT_INS]})
    assert sections_signature(advice_off) != sections_signature(BUILT_INS)
    for secs in (BUILT_INS, advice_off):
        monkeypatch.setattr("doctor_dictation.api.sections.sections_for", lambda clinic, doctor_id=None, s=secs: s)
        seen.append(c.post("/api/format", json={"transcript": "fever three days rest"}).json())
    assert [j["cached"] for j in seen] == [False, False]
    assert seen[0]["structured"]["advice"] == ["Rest"] and seen[1]["structured"]["advice"] == []
    _FORMAT_CACHE.clear()
