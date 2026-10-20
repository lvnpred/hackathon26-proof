"""merge_form: apply a spoken correction to the current form (pure, offline).

A correction changes ONLY what the doctor mentioned. Scalars/list fields are
left alone when the patch says nothing about them; rx rows are merged by
case-insensitive name. No network, no time, no randomness.

Run:  ./.venv-arm64/Scripts/python -m pytest tests/ -q
"""
import json

import doctor_dictation.main as M
from doctor_dictation.config import override_settings
from doctor_dictation.core.correction import CORRECTION_INSTRUCTION, extract_correction, merge_form, resolve_blank_names


def test_correction_replaces_named_rx_row_and_keeps_others():
    cur = {"rx": [{"name": "Tamsulosin", "strength": "0.4 mg", "dose": "0-0-1"},
                  {"name": "Paracetamol", "strength": "650 mg", "dose": "SOS"}]}
    out = merge_form(cur, {"rx": [{"name": "tamsulosin", "strength": "0.4 mg", "dose": "1-0-0"}]})
    assert [r["name"] for r in out["rx"]] == ["Tamsulosin", "Paracetamol"]
    assert out["rx"][0]["dose"] == "1-0-0"


def test_correction_adds_new_medicine():  # Review Focus #1
    cur = {"rx": [{"name": "Tamsulosin"}]}
    out = merge_form(cur, {"rx": [{"name": "Pantoprazole", "strength": "40 mg"}]})
    assert [r["name"] for r in out["rx"]] == ["Tamsulosin", "Pantoprazole"]


def test_empty_patch_leaves_form_unchanged():  # Review Focus #3
    cur = {"patientName": "Anita", "rx": [{"name": "Tamsulosin"}]}
    assert merge_form(cur, {}) == cur


def test_empty_scalar_does_not_clear():
    out = merge_form({"patientName": "Anita", "ageSex": "45 / F"}, {"patientName": ""})
    assert out["patientName"] == "Anita"


def test_non_empty_scalar_overwrites():
    out = merge_form({"patientName": "Anita", "ageSex": "45 / F"},
                     {"ageSex": "46 / F", "review": "after 1 week"})
    assert out["ageSex"] == "46 / F"
    assert out["review"] == "after 1 week"


def test_a_list_correction_adds_to_the_list_and_an_empty_list_keeps():
    # owner, 2026-10-20: a correction upserts a list section (adds what is new), never replaces it wholesale
    cur = {"diagnosis": ["Right flank pain"], "complaints": ["burning micturition"]}
    out = merge_form(cur, {"diagnosis": ["Renal calculus"], "complaints": []})
    assert out["diagnosis"] == ["Right flank pain", "Renal calculus"]
    assert out["complaints"] == ["burning micturition"]


def test_an_item_already_on_the_list_is_not_added_twice():
    cur = {"diagnosis": ["Restlessness", "Weird thinking"], "advice": ["Plenty of fluids."]}
    out = merge_form(cur, {"diagnosis": ["restlessness", "Sleeplessness", "Anaemia", "sleeplessness"], "advice": ["plenty of  fluids"]})
    assert out["diagnosis"] == ["Restlessness", "Weird thinking", "Sleeplessness", "Anaemia"]
    assert out["advice"] == ["Plenty of fluids."]


def test_merge_never_mutates_current():
    cur = {"patientName": "Anita",
           "rx": [{"name": "Tamsulosin", "dose": "0-0-1"}]}
    before = {"patientName": cur["patientName"], "rx": [dict(cur["rx"][0])]}
    merge_form(cur, {"patientName": "Bina",
                     "rx": [{"name": "tamsulosin", "dose": "1-0-0"}]})
    assert cur == before


def test_matching_row_keeps_fields_absent_from_patch():
    # A spoken correction changes only what she mentioned: a dose-only patch
    # must not wipe the existing strength.
    cur = {"rx": [{"name": "Tamsulosin", "strength": "0.4 mg", "dose": "0-0-1"}]}
    out = merge_form(cur, {"rx": [{"name": "tamsulosin", "dose": "1-0-0"}]})
    assert out["rx"][0]["dose"] == "1-0-0"
    assert out["rx"][0]["strength"] == "0.4 mg"


def test_patch_only_keeps_other_field_spelling_and_unmentioned_keys():
    cur = {"rx": [{"name": "Tamsulosin", "dose": "0-0-1"}],
           "advice": ["drink water"]}
    out = merge_form(cur, {"rx": [{"name": "Tamsulosin", "dose": "1-0-0"}]})
    assert out["rx"][0]["name"] == "Tamsulosin"
    assert out["rx"][0]["dose"] == "1-0-0"
    assert out["advice"] == ["drink water"]


# ---- Task 5: extract_correction + POST /api/v1/correct ----

def _client(monkeypatch):
    """Keys cleared -> the rules/offline path (mirrors tests/test_determinism.py)."""
    from fastapi.testclient import TestClient
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    return TestClient(M.app)


def _stub_llm(monkeypatch, patch):
    """Serve `patch` as the next chat completion; record every request body."""
    calls = {"n": 0, "messages": []}

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
            calls["n"] += 1
            calls["messages"].append(kw["json"]["messages"])
            return Resp()

    monkeypatch.setattr("httpx.AsyncClient", Client)
    override_settings(monkeypatch, openai_api_key="k", llm_provider="openai")
    return calls


def test_extract_correction_offline_returns_empty_patch():
    import asyncio
    patch = asyncio.run(extract_correction("change the dose", {"rx": [{"name": "Tamsulosin"}]}))
    assert patch == {}  # no LLM configured -> nothing to merge


def test_correct_endpoint_merges_offline(monkeypatch):
    client = _client(monkeypatch)  # keys cleared -> rules path
    cur = {"patientName": "Anita", "rx": [{"name": "Tamsulosin", "dose": "0-0-1"}]}
    j = client.post("/api/v1/correct", json={"transcript": "", "current_form": cur}).json()
    assert j["structured"]["rx"][0]["name"] == "Tamsulosin"  # empty correction never wipes
    assert j["structured"]["patientName"] == "Anita"
    assert "grounding" in j and "engine" in j


def test_correct_endpoint_llm_patch_merges_and_regrounds(monkeypatch):
    patch = {"rx": [{"name": "Paracetamol", "dose": "1-0-1", "timing": "After food"}]}
    calls = _stub_llm(monkeypatch, patch)
    cur = {"patientName": "Anita",
           "rx": [{"name": "Tamsulosin", "strength": "0.4 mg", "dose": "0-0-1"},
                  {"name": "Paracetamol", "strength": "650 mg", "dose": "SOS"}]}
    from fastapi.testclient import TestClient
    r = TestClient(M.app).post("/api/v1/correct", json={
        "transcript": "change Paracetamol to twice daily after food",
        "current_form": cur})
    assert r.status_code == 200, r.text
    j = r.json()
    assert calls["n"] == 1
    by_name = {row["name"]: row for row in j["structured"]["rx"]}
    assert by_name["Paracetamol"]["dose"] == "1-0-1"
    assert by_name["Paracetamol"]["timing"] == "After food"
    assert by_name["Paracetamol"]["strength"] == "650 mg"  # overlay keeps strength
    assert "Tamsulosin" in by_name                          # untouched row kept
    assert by_name["Paracetamol"]["status"] == "verified"  # pill recomputed
    # The model saw the current form plus the byte-identical instruction.
    system = calls["messages"][0][0]
    assert system["role"] == "system"
    assert "byte-identical" in system["content"]
    user = calls["messages"][0][1]["content"]
    assert "Paracetamol" in user and "Tamsulosin" in user


def test_correct_endpoint_missing_current_form_defaults_empty(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/api/v1/correct", json={"transcript": ""})
    assert r.status_code == 200, r.text
    assert r.json()["structured"]["rx"] == []


def test_correction_leaves_unmentioned_row_status_unchanged(monkeypatch):
    patch = {"rx": [{"name": "Paracetamol", "dose": "1-0-1"}]}
    _stub_llm(monkeypatch, patch)
    from fastapi.testclient import TestClient
    cur = {"rx": [
        {"form": "Tab.", "name": "Paracetamol", "strength": "650 mg", "dose": "SOS",
         "instructions": "", "status": "verified", "lexicon_match": "Paracetamol"},
        {"form": "Tab.", "name": "Tamsulosin", "strength": "0.4 mg", "dose": "0-0-1",
         "instructions": "", "status": "verified", "lexicon_match": "Tamsulosin"},
    ]}
    j = TestClient(M.app).post("/api/v1/correct", json={
        "transcript": "change Paracetamol to twice daily",
        "current_form": cur}).json()
    by_name = {row["name"]: row for row in j["structured"]["rx"]}
    # The named row is re-grounded...
    assert by_name["Paracetamol"]["status"] == "verified"
    # ...but the row the correction never mentions keeps its verification state.
    assert by_name["Tamsulosin"]["status"] == "verified"
    assert by_name["Tamsulosin"]["lexicon_match"] == "Tamsulosin"
    assert "[unverified" not in by_name["Tamsulosin"]["instructions"]


def test_correction_marker_does_not_accumulate(monkeypatch):
    patch = {"rx": [{"name": "Medalpha", "dose": "1-0-0"}]}
    _stub_llm(monkeypatch, patch)
    from fastapi.testclient import TestClient
    client = TestClient(M.app)
    cur = {"rx": [{"name": "Medalpha", "strength": "10 mg", "dose": "0-0-1",
                   "instructions": "[unverified: confirm with doctor]",
                   "status": "unknown-medicine", "lexicon_match": ""}]}
    body = {"transcript": "change Medalpha to once daily", "current_form": cur}
    first = client.post("/api/v1/correct", json=body).json()["structured"]
    second = client.post("/api/v1/correct", json={
        "transcript": body["transcript"], "current_form": first}).json()["structured"]
    assert second["rx"][0]["instructions"].count("[unverified") == 1


def test_empty_correction_adds_no_markers(monkeypatch):
    client = _client(monkeypatch)  # keys cleared -> empty patch
    cur = {"rx": [{"form": "Tab.", "name": "Tamsulosin", "strength": "0.4 mg",
                   "dose": "0-0-1", "timing": "", "duration": "",
                   "instructions": ""}]}
    row = client.post("/api/v1/correct", json={
        "transcript": "", "current_form": cur}).json()["structured"]["rx"][0]
    assert "[unverified" not in row["instructions"]
    assert row["name"] == "Tamsulosin"
    assert row["dose"] == "0-0-1"
    assert "status" not in row  # no verification state invented


def test_untouched_statusless_row_not_stamped(monkeypatch):
    patch = {"rx": [{"name": "Paracetamol", "dose": "1-0-1"}]}
    _stub_llm(monkeypatch, patch)
    from fastapi.testclient import TestClient
    cur = {"rx": [
        {"form": "Tab.", "name": "Paracetamol", "strength": "650 mg", "dose": "SOS",
         "timing": "", "duration": "", "instructions": ""},
        {"form": "Tab.", "name": "Tamsulosin", "strength": "0.4 mg", "dose": "0-0-1",
         "timing": "", "duration": "", "instructions": ""},
    ]}
    j = TestClient(M.app).post("/api/v1/correct", json={
        "transcript": "change Paracetamol to twice daily",
        "current_form": cur}).json()
    by_name = {row["name"]: row for row in j["structured"]["rx"]}
    assert "[unverified" not in by_name["Tamsulosin"]["instructions"]
    assert "status" not in by_name["Tamsulosin"]
    assert by_name["Paracetamol"]["status"] == "verified"  # named row re-grounded


# ---- B0 Task 1: nameless patch rows must never become ghost medicines ----

_ASCORIL = {"form": "Syr.", "name": "Ascoril", "strength": "", "dose": "1-0-1",
            "timing": "", "duration": "", "instructions": ""}


def test_resolve_fills_the_one_incomplete_medicine():
    cur = {"rx": [dict(_ASCORIL)]}
    patch = {"rx": [{"name": "", "strength": "5 ml", "duration": "7 days"}]}
    out, warnings = resolve_blank_names(cur, patch)
    assert out["rx"] == [{"name": "Ascoril", "strength": "5 ml", "duration": "7 days"}]
    assert warnings == []


def test_resolve_ambiguous_blank_name_row_is_dropped_with_warning():  # Review Focus #2
    cur = {"rx": [dict(_ASCORIL), dict(_ASCORIL, name="Zincovit")]}
    out, warnings = resolve_blank_names(cur, {"rx": [{"name": "", "duration": "7 days"}]})
    assert out["rx"] == []
    assert len(warnings) == 1
    assert "Could not tell which medicine" in warnings[0]
    assert "duration: 7 days" in warnings[0]


def test_resolve_never_overwrites_a_filled_field():  # Review Focus #1
    cur = {"rx": [dict(_ASCORIL, dose="1-1-1")]}
    out, warnings = resolve_blank_names(cur, {"rx": [{"name": "", "dose": "1-0-1"}]})
    assert out["rx"] == []
    assert len(warnings) == 1


def test_resolve_row_without_content_is_dropped_silently():
    out, warnings = resolve_blank_names({"rx": [dict(_ASCORIL)]},
                                        {"rx": [{"name": "", "strength": "  "}]})
    assert out["rx"] == []
    assert warnings == []


def test_resolve_passes_named_rows_through_untouched():
    named = {"name": "Paracetamol", "dose": "1-0-1"}
    out, warnings = resolve_blank_names({"rx": [dict(_ASCORIL)]},
                                        {"rx": [named, {"name": "", "strength": "5 ml"}]})
    assert out["rx"] == [named, {"name": "Ascoril", "strength": "5 ml"}]
    assert warnings == []


def test_resolve_row_without_name_key_and_non_string_values():  # Review Focus #3, #4
    cur = {"rx": [dict(_ASCORIL)]}
    out, _ = resolve_blank_names(cur, {"rx": [{"strength": 5, "duration": None}]})
    assert out["rx"] == [{"name": "Ascoril", "strength": "5"}]
    out, _ = resolve_blank_names(cur, {"rx": [{"name": None, "strength": "5 ml"}]})
    assert out["rx"] == [{"name": "Ascoril", "strength": "5 ml"}]


def test_resolve_never_mutates_its_inputs():
    cur = {"rx": [dict(_ASCORIL)]}
    patch = {"rx": [{"name": "", "strength": "5 ml"}], "review": "1 week"}
    before_cur, before_patch = json.dumps(cur), json.dumps(patch)
    resolve_blank_names(cur, patch)
    assert json.dumps(cur) == before_cur and json.dumps(patch) == before_patch


def test_merge_form_never_appends_a_nameless_row():
    cur = {"rx": [dict(_ASCORIL)]}
    out = merge_form(cur, {"rx": [{"name": "", "strength": "5 ml"}]})
    assert out["rx"] == cur["rx"]


# ---- B0 Task 2: the correction prompt has the same rules as the format prompt ----

def test_correction_prompt_carries_schema_and_rules():
    from doctor_dictation.core.correction import CORRECTION_INSTRUCTION as P
    assert "byte-identical" in P                # existing behaviour kept
    assert 'MUST include "name"' in P           # every rx row names its medicine
    for needle in ('"1-0-0"', '"1-0-1"', '"1-1-1"', '"0-0-1"', '"SOS"',
                   '"After food"', '"Before food"', '"At bedtime"', '"45 / M"'):
        assert needle in P, needle


# ---- B0 Task 3: /api/v1/correct applies resolve_blank_names ----

def _ascoril_form(**extra_rows):
    rows = [{"form": "Syr.", "name": "Ascoril", "strength": "", "dose": "1-0-1",
             "timing": "", "duration": "", "instructions": ""}]
    for name in extra_rows.get("more", []):
        rows.append(dict(rows[0], name=name))
    return {"rx": rows}


def test_correct_endpoint_blank_name_row_fills_the_one_incomplete_medicine(monkeypatch):
    _stub_llm(monkeypatch, {"rx": [{"name": "", "strength": "5 ml", "duration": "7 days"}]})
    from fastapi.testclient import TestClient
    j = TestClient(M.app).post("/api/v1/correct", json={
        "transcript": "strength is 5 ml for the Ascoril and the duration is 7 days",
        "current_form": _ascoril_form()}).json()
    rows = j["structured"]["rx"]
    assert [r["name"] for r in rows] == ["Ascoril"]  # no ghost row
    assert rows[0]["strength"] == "5 ml" and rows[0]["duration"] == "7 days"
    assert rows[0]["dose"] == "1-0-1"
    assert j["warnings"] == []


def test_correct_endpoint_ambiguous_blank_name_row_changes_nothing_and_warns(monkeypatch):
    _stub_llm(monkeypatch, {"rx": [{"name": "", "duration": "7 days"}]})
    from fastapi.testclient import TestClient
    j = TestClient(M.app).post("/api/v1/correct", json={
        "transcript": "duration is 7 days",
        "current_form": _ascoril_form(more=["Zincovit"])}).json()
    rows = j["structured"]["rx"]
    assert [r["name"] for r in rows] == ["Ascoril", "Zincovit"]
    assert all(r["duration"] == "" for r in rows)
    assert len(j["warnings"]) == 1 and "Could not tell which medicine" in j["warnings"][0]


def test_correct_endpoint_blank_name_fill_regrounds_the_filled_row(monkeypatch):
    _stub_llm(monkeypatch, {"rx": [{"name": "", "strength": "650 mg"}]})
    cur = {"rx": [{"form": "Tab.", "name": "Paracetamol", "strength": "", "dose": "1-1-1",
                   "timing": "After food", "duration": "5 days", "instructions": "",
                   "status": "unverified-strength", "lexicon_match": "Paracetamol"}]}
    from fastapi.testclient import TestClient
    j = TestClient(M.app).post("/api/v1/correct", json={
        "transcript": "strength is 650 mg for the Paracetamol",
        "current_form": cur}).json()
    row = j["structured"]["rx"][0]
    assert row["strength"] == "650 mg"
    assert row["status"] == "verified"  # the stale "unverified-strength" was not restored


def test_correct_endpoint_always_returns_a_warnings_list(monkeypatch):
    client = _client(monkeypatch)  # keys cleared -> rules path
    j = client.post("/api/v1/correct", json={"transcript": "", "current_form": {}}).json()
    assert j["warnings"] == []


# ---- B0 final-review fixes ----

def test_resolve_duplicate_named_rows_are_ambiguous():
    # Final review #1: merge resolves a name to the FIRST row, so a nameless fix aimed at the
    # second of two same-named rows would silently overwrite the first.
    cur = {"rx": [{"name": "Paracetamol", "strength": "650 mg", "duration": "3 days"},
                  {"name": "Paracetamol", "strength": "500 mg", "duration": ""}]}
    out, warnings = resolve_blank_names(cur, {"rx": [{"name": "", "duration": "5 days"}]})
    assert out["rx"] == []
    assert len(warnings) == 1 and "Could not tell which medicine" in warnings[0]


def test_resolve_warns_about_stated_fields_it_could_not_apply():
    # Final review #2: strength fills, but the already-filled dose is not silently dropped.
    cur = {"rx": [dict(_ASCORIL)]}
    out, warnings = resolve_blank_names(
        cur, {"rx": [{"name": "", "strength": "5 ml", "dose": "1-1-1"}]})
    assert out["rx"] == [{"name": "Ascoril", "strength": "5 ml"}]
    assert len(warnings) == 1
    assert "dose: 1-1-1" in warnings[0] and "Ascoril" in warnings[0]


def test_correction_prompt_allows_a_new_medicine():
    # Final review #5: "copy the name from the current form" must not block adding a medicine.
    from doctor_dictation.core.correction import CORRECTION_INSTRUCTION as P
    assert "NEW row" in P


def test_a_spoken_list_correction_adds_lines_and_checks_only_the_new_ones(monkeypatch):
    # owner, 2026-10-20: "update diagnosis as sleeplessness and anaemia" kept "Restlessness"; the model may echo the old line
    _stub_llm(monkeypatch, {"diagnosis": ["Restlessness", "Sleeplessness", "Anaemia 9.5"]})
    from fastapi.testclient import TestClient
    j = TestClient(M.app).post("/api/v1/correct", json={
        "transcript": "update diagnosis as sleeplessness and anaemia", "current_form": {"diagnosis": ["Restlessness"]}}).json()
    assert "structured" in j, j
    assert j["structured"]["diagnosis"] == ["Restlessness", "Sleeplessness", "Anaemia 9.5"]
    assert j["prose_check"] == [{"field": "diagnosis", "index": 2, "words": ["9.5"]}]   # "Restlessness" was not re-checked
    assert "ONLY the new items" in CORRECTION_INSTRUCTION
