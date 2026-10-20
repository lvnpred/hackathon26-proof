import json

from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.config import override_settings
from doctor_dictation.core.correction import changed_rx_rows


def _rx(*names):
    return {"rx": [{"name": n, "dose": "1-0-0"} for n in names]}


def test_nothing_named_nothing_changed():
    assert changed_rx_rows(_rx("Dolo 650", "Zyloric"), {}, _rx("Dolo 650", "Zyloric")) == []


def test_named_row_is_changed():
    assert changed_rx_rows(_rx("Dolo 650", "Zyloric"), {"rx": [{"name": "zyloric "}]}, _rx("Dolo 650", "Zyloric")) == [1]


def test_appended_new_medicine_is_changed():
    assert changed_rx_rows(_rx("Dolo 650"), {"rx": [{"name": "Cetirizine"}]}, _rx("Dolo 650", "Cetirizine")) == [1]


def test_removed_row_shifts_indexes_and_nothing_else_changes():
    # current is the PRE-ops form, as format.py passes it; Pantoprazole was removed by apply_ops
    assert changed_rx_rows(_rx("Pantoprazole", "Dolo 650", "Zyloric"), {}, _rx("Dolo 650", "Zyloric")) == []


def test_renamed_row_is_changed_via_extra_named():
    assert changed_rx_rows(_rx("Cephixime", "Dolo 650"), {}, _rx("Cefixime", "Dolo 650"), extra_named={"cefixime"}) == [0]


def test_a_named_duplicate_marks_every_row_of_that_name():
    assert changed_rx_rows(_rx("Amlodipine", "Dolo 650", "Amlodipine"), {"rx": [{"name": "Amlodipine"}]},
                           _rx("Amlodipine", "Dolo 650", "Amlodipine")) == [0, 2]


def test_echoed_row_counts_as_changed():
    assert changed_rx_rows(_rx("Dolo 650"), {"rx": [{"name": "Dolo 650"}]}, _rx("Dolo 650")) == [0]


def test_a_name_validation_changed_has_no_prior_and_is_changed():
    assert changed_rx_rows(_rx("dolo"), {}, _rx("Dolo 650")) == [0]


def test_cannot_pair_means_every_row_changed():
    assert changed_rx_rows({"rx": "garbage"}, {}, _rx("A1", "B1")) == [0, 1]
    assert changed_rx_rows({}, {}, {"rx": None}) == []
    assert changed_rx_rows(_rx("A1"), {}, {"rx": ["x", {"name": "A1", "dose": "1-0-0"}]}) == [0]


def test_inputs_are_not_mutated():
    cur, out = _rx("A1"), _rx("A1")
    snap = (repr(cur), repr(out))
    changed_rx_rows(cur, {"rx": [{"name": "A1"}]}, out)
    assert (repr(cur), repr(out)) == snap


# ---- POST /api/v1/correct returns changed_rows ----

def _client(monkeypatch):
    """Keys cleared -> the rules/offline path."""
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    return TestClient(M.app)


def _stub_llm(monkeypatch, patch):
    """Serve `patch` as the next chat completion (no network)."""
    class Resp:
        status_code = 200
        text = "ok"

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(patch)}}]}

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, **kw):
            return Resp()

    monkeypatch.setattr("httpx.AsyncClient", Client)
    override_settings(monkeypatch, openai_api_key="k", llm_provider="openai")


CUR = [{"form": "Tab.", "name": "Pantoprazole", "strength": "40 mg", "dose": "1-0-0", "instructions": "", "status": "verified", "lexicon_match": "Pantoprazole"},
       {"form": "Tab.", "name": "Paracetamol", "strength": "650 mg", "dose": "SOS", "instructions": "", "status": "verified", "lexicon_match": "Paracetamol"},
       {"form": "Tab.", "name": "Tamsulosin", "strength": "0.4 mg", "dose": "0-0-1", "instructions": "", "status": "verified", "lexicon_match": "Tamsulosin"}]


def _correct(transcript, current=None):
    return TestClient(M.app).post("/api/v1/correct", json={"transcript": transcript, "current_form": {"rx": CUR if current is None else current}}).json()


def test_offline_empty_correction_changes_no_row(monkeypatch):
    j = _client(monkeypatch).post("/api/v1/correct", json={"transcript": "", "current_form": {"rx": CUR}}).json()
    assert j["changed_rows"] == []


def test_dose_change_reports_only_that_row(monkeypatch):
    _stub_llm(monkeypatch, {"rx": [{"name": "Paracetamol", "dose": "1-0-1"}]})
    j = _correct("paracetamol twice daily")
    assert [r["name"] for r in j["structured"]["rx"]] == ["Pantoprazole", "Paracetamol", "Tamsulosin"]
    assert j["changed_rows"] == [1]


def test_remove_above_and_append_shift_indexes(monkeypatch):
    _stub_llm(monkeypatch, {"remove": {"rx": ["Pantoprazole"]}, "rx": [{"name": "Cetirizine", "strength": "10 mg", "dose": "0-0-1"}]})
    j = _correct("remove pantoprazole add cetirizine")
    assert [r["name"] for r in j["structured"]["rx"]] == ["Paracetamol", "Tamsulosin", "Cetirizine"]
    assert j["changed_rows"] == [2]


def test_spoken_rename_reports_the_renamed_row(monkeypatch):
    _stub_llm(monkeypatch, {"replace": {"rx": [{"from": "Tamsulosin", "to": "Silodosin"}]}})
    j = _correct("not tamsulosin, silodosin")
    assert j["structured"]["rx"][2]["name"] == "Silodosin" and j["changed_rows"] == [2]


def test_untouched_row_clinical_fields_come_back_identical(monkeypatch):
    _stub_llm(monkeypatch, {"rx": [{"name": "Paracetamol", "dose": "1-0-1"}]})
    j = _correct("paracetamol twice daily")
    keys = ("form", "name", "strength", "dose", "instructions", "status")
    for i in (0, 2):
        assert {k: j["structured"]["rx"][i].get(k, "") for k in keys} == {k: CUR[i][k] for k in keys}


def test_missing_current_form_gives_empty_changed_rows(monkeypatch):
    j = _client(monkeypatch).post("/api/v1/correct", json={"transcript": ""}).json()
    assert j["structured"]["rx"] == [] and j["changed_rows"] == []


def test_failed_llm_call_returns_valid_response_and_no_changed_rows(monkeypatch):
    """A failed extraction merges nothing, so the form is returned as sent and no row changed."""
    _stub_llm(monkeypatch, {})

    async def boom(*a, **k):
        raise RuntimeError("llm down")

    monkeypatch.setattr("doctor_dictation.api.format.extract_correction", boom)
    j = _correct("paracetamol twice daily")
    assert j["engine"].startswith("rules-after-error")
    assert [r["name"] for r in j["structured"]["rx"]] == ["Pantoprazole", "Paracetamol", "Tamsulosin"]
    assert j["changed_rows"] == []


def test_unit_clinical_field_rewrite_marks_paired_row_changed():
    cur = {"rx": [{"name": "A1", "dose": "", "timing": "After food"}, {"name": "B1", "dose": "BD"}, {"name": "C1", "timing": "After food"}]}
    out = {"rx": [{"name": "A1", "dose": "1-0-0", "timing": "After food"}, {"name": "B1", "dose": "1-0-1"}, {"name": "C1", "timing": " after  Food"}]}
    assert changed_rx_rows(cur, {}, out) == [0, 1]


def test_failed_llm_rows_rewritten_by_validation_are_changed(monkeypatch):
    rows = [dict(CUR[1], dose=""), dict(CUR[0], dose="BD", timing="After food"), dict(CUR[2], timing="After food")]
    _stub_llm(monkeypatch, {})

    async def boom(*a, **k):
        raise RuntimeError("llm down")

    monkeypatch.setattr("doctor_dictation.api.format.extract_correction", boom)
    j = _correct("anything", rows)
    out = j["structured"]["rx"]
    expect = [i for i, (o, r) in enumerate(zip(out, rows))
              if any(" ".join(str(o.get(f) or "").split()).casefold() != " ".join(str(r.get(f) or "").split()).casefold()
                     for f in ("form", "name", "strength", "dose", "timing", "duration"))]
    assert j["changed_rows"] == expect
    assert {0, 1} <= set(j["changed_rows"]) and 2 not in j["changed_rows"]
