"""dose-check inside grounding: ranking, the new row fields, preserve_untouched, the routes and /api/health."""
import copy
import json

from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.config import override_settings
from doctor_dictation.core import determinism, dosing
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.determinism import validate_structured
from doctor_dictation.core.fallback import fallback_format
from dosing_fixtures import FIXTURE, _e, use_fixture

TEXT = "paracetamol 650 mg three times daily, prednisolone 10 mg syrup once daily"
NOTE = "1950 mg a day; usual adult maximum 1500 mg"

def _row(age="45 / M", transcript=TEXT, **row):
    base = {"form": "Tab.", "name": "Paracetamol", "strength": "650 mg", "dose": "1-1-1", "duration": "3 days"}
    out, warnings = validate_structured({"ageSex": age, "rx": [{**base, **row}]}, transcript)
    return out["rx"][0], warnings

def test_above_max_is_dose_check_ranked_by_contract_and_age_aware(monkeypatch, tmp_path, frozen_lexicon):
    use_fixture(monkeypatch, tmp_path)
    row, warnings = _row()                                                     # 650 x 3 = 1950 > 1500
    assert (row["status"], row["lexicon_match"], row["dose_note"]) == ("dose-check", "Paracetamol", NOTE)
    assert (row["strength_options"], row["usual_strength"]) == (["650 mg", "500 mg", "1 g"], "650 mg")
    assert row["instructions"] == "" and warnings == []
    assert [_row(strength="500 mg")[0]["status"], _row(age="8 / F")[0]["status"]] == ["verified"] * 2
    assert _row(strength="1 g")[0]["status"] == "unverified-strength"          # a higher-ranked status wins
    assert _row(transcript="no medicines")[0]["status"] == "unverified-name"
    assert _row(name="Zzqxwv")[0]["status"] == "unknown-medicine"
    kw, _ = validate_structured({"ageSex": "8 / F", "rx": [{"name": "Paracetamol", "strength": "650 mg", "dose": "1-1-1"}]},
                                TEXT, age_sex="45 / M")                        # the keyword overrides the form
    assert kw["rx"][0]["status"] == "dose-check"

def test_hook_ranking_form_mismatch_and_fields_on_unknown_rows(monkeypatch, tmp_path):
    use_fixture(monkeypatch, tmp_path)
    hook = lambda status, strength="650 mg", dose="1-1-1": dosing.ground_extra(          # noqa: E731
        status, "Paracetamol", "Tab.", strength, dose, "45 / M")[0]
    assert [hook(s) for s in ("unverified-name", "unverified-strength", "unknown-medicine")] == [
        "unverified-name", "unverified-strength", "unknown-medicine"]
    assert (hook("lookalike-check"), hook("lookalike-check", "500 mg", "1-0-0")) == ("dose-check", "lookalike-check")
    row, _ = _row(name="Prednisolone", form="Inj.", strength="10 mg", dose="1-0-0")
    assert (row["status"], row["dose_note"]) == ("dose-check", "Inj. is not a usual form of Prednisolone (usual: Tab., Syr.)")
    assert _row(name="Zzqxwv")[0]["strength_options"] == []

def _page_row(**over):
    """A row as the page's readRx sends it back: visible fields plus status and lexicon_match, nothing derived."""
    row = {"form": "Tab.", "name": "Paracetamol", "strength": "650 mg", "dose": "1-1-1", "timing": "", "duration": "3 days",
           "instructions": "", "status": "dose-check", "lexicon_match": "Paracetamol"}
    return {**row, **over}

def _keep(rows, age="45 / M"):
    form = {"ageSex": age, "rx": rows}
    validated, _ = validate_structured(form, "")
    return preserve_untouched_rx_status(form, {}, validated)["rx"]

def test_preserve_untouched_recomputes_the_dose_note_from_the_page_shaped_row(monkeypatch, tmp_path):
    use_fixture(monkeypatch, tmp_path)
    ok = _page_row(name="Prednisolone", strength="10 mg", dose="1-0-0", status="verified", lexicon_match="Prednisolone")
    out = _keep([_page_row(), ok])
    assert [(r["status"], r["dose_note"]) for r in out] == [("dose-check", NOTE), ("verified", "")]
    assert _keep([_page_row(form="Inj.", strength="500 mg", dose="1-0-0")])[0]["dose_note"] == \
        "Inj. is not a usual form of Paracetamol (usual: Tab., Syr.)"
    assert _keep([_page_row()], age="8 / F")[0]["dose_note"] == ""                # no note recomputed, none prior

def test_preserve_untouched_falls_back_to_the_prior_note_and_never_stamps_a_status_less_row(monkeypatch, tmp_path):
    use_fixture(monkeypatch, tmp_path)
    assert _keep([_page_row(strength="500 mg", dose_note="from before")])[0]["dose_note"] == "from before"
    row = _keep([{k: v for k, v in _page_row().items() if k not in ("status", "lexicon_match")}])[0]
    assert "status" not in row and "dose_note" not in row

def _ref(monkeypatch, tmp_path, forms):
    data = copy.deepcopy(FIXTURE)
    data["entries"].append(_e("Ceftriaxone", ["250 mg", "500 mg", "1 g"], forms, "1 g", 2000))   # the lexicon lists Inj.
    use_fixture(monkeypatch, tmp_path, data)

def test_an_echoed_tab_does_not_swap_an_overdose_note_for_a_form_note(monkeypatch, tmp_path):
    _ref(monkeypatch, tmp_path, ["Inj."])                                        # cap 2000; the page echoes the default Tab.
    over = _page_row(name="Ceftriaxone", lexicon_match="Ceftriaxone", strength="1 g")          # 3 x 1 g = 3000
    assert _keep([over])[0]["dose_note"] == "3000 mg a day; usual adult maximum 2000 mg"
    fine = _page_row(name="Ceftriaxone", lexicon_match="Ceftriaxone", strength="250 mg", dose="1-0-0")
    assert _keep([fine])[0]["dose_note"] == "Tab. is not a usual form of Ceftriaxone (usual: Inj.)"

def _said(text):
    form = fallback_format(f"patient Rahul Sharma 45 year old male. {text}")
    return form["rx"][0]["form"], validate_structured(form, text)[0]["rx"][0]

def test_no_form_word_spoken_leaves_the_form_empty_and_is_never_a_form_mismatch(monkeypatch, tmp_path):
    _ref(monkeypatch, tmp_path, ["Tab.", "Inj."])
    raw, row = _said("ceftriaxone 250 mg once daily")
    assert (raw, row["form"], row["dose_note"]) == ("", "", "")                # no form spoken: none printed
    assert fallback_format("have paracetamol twice a day")["rx"][0]["form"] == ""

def test_explicit_wrong_form_against_a_full_reference_is_dose_check(monkeypatch, tmp_path):
    _ref(monkeypatch, tmp_path, ["Tab.", "Inj."])                                # a superset of the lexicon's [Inj.]
    raw, row = _said("syrup ceftriaxone 250 mg once daily")
    assert (raw, row["status"], row["dose_note"]) == ("Syr.", "dose-check",
                                                      "Syr. is not a usual form of Ceftriaxone (usual: Tab., Inj.)")
    assert _said("injection ceftriaxone 250 mg once daily")[1]["dose_note"] == ""
    assert _said("tablet ceftriaxone 250 mg once daily")[1]["dose_note"] == ""

def test_a_reference_missing_a_lexicon_form_skips_the_form_check_but_not_the_dose_check(monkeypatch, tmp_path):
    _ref(monkeypatch, tmp_path, ["Tab."])                                        # lacks Inj., which the lexicon lists
    assert _said("syrup ceftriaxone 250 mg once daily")[1]["dose_note"] == ""
    assert _said("injection ceftriaxone 250 mg once daily")[1]["dose_note"] == ""
    assert _said("injection ceftriaxone 1 g thrice daily")[1]["dose_note"] == "3000 mg a day; usual adult maximum 2000 mg"

def test_an_explicit_tab_against_an_inj_only_entry_is_dose_check(monkeypatch, tmp_path):
    _ref(monkeypatch, tmp_path, ["Inj."])
    row = validate_structured({"ageSex": "45 / M", "rx": [{"form": "Tab.", "name": "Ceftriaxone", "strength": "250 mg",
                                                           "dose": "1-0-0"}]}, "ceftriaxone")[0]["rx"][0]
    assert (row["status"], row["dose_note"]) == ("dose-check", "Tab. is not a usual form of Ceftriaxone (usual: Inj.)")

def test_a_drug_whose_lexicon_forms_are_none_of_the_four_is_never_form_checked(monkeypatch, tmp_path):
    data = copy.deepcopy(FIXTURE)
    data["entries"].append(_e("Betamethasone", ["1 mg"], ["Tab."], "1 mg", 10))     # the lexicon lists Cream, Oint.
    use_fixture(monkeypatch, tmp_path, data)
    assert dosing.check_dose("Betamethasone", "1 mg", "1-0-0", "45 / M", "Syr.").state == "in-range"

def test_routes_end_to_end_and_health(monkeypatch, tmp_path):
    client = TestClient(M.app)
    assert client.get("/api/health").json()["dosing_version"] == "none"
    use_fixture(monkeypatch, tmp_path)
    assert client.get("/api/health").json()["dosing_version"] == "test-1"
    monkeypatch.setattr(determinism, "_FORMAT_CACHE", {})
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    said = "patient Rahul Sharma 45 year old male. tablet paracetamol 650 mg thrice daily for 3 days"
    row = client.post("/api/format", json={"transcript": said}).json()["structured"]["rx"][0]
    assert (row["status"], row["dose_note"]) == ("dose-check", NOTE)
    monkeypatch.setenv("ALLOW_STUB_PROVIDERS", "1")
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps({"rx": [{"name": "Paracetamol", "strength": "650 mg", "dose": "1-1-1"}]}))
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True)
    form = {"ageSex": "45 / M", "rx": [{"form": "Tab.", "name": "Paracetamol", "strength": "500 mg", "dose": "1-0-0"}]}
    body = {"transcript": "make paracetamol 650 mg thrice daily", "current_form": form}
    assert client.post("/api/v1/correct", json=body).json()["structured"]["rx"][0]["status"] == "dose-check"

def _stub(monkeypatch, patch):
    monkeypatch.setenv("ALLOW_STUB_PROVIDERS", "1")
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(patch))
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True)

def test_correct_keeps_an_untouched_rows_dose_note_when_the_page_sends_only_visible_fields(monkeypatch, tmp_path):
    use_fixture(monkeypatch, tmp_path)
    _stub(monkeypatch, {"rx": [{"name": "Metformin", "strength": "850 mg"}]})
    metformin = _page_row(name="Metformin", strength="500 mg", dose="1-0-1", status="verified", lexicon_match="Metformin")
    form = {"ageSex": "45 / M", "rx": [_page_row(), metformin]}
    body = {"transcript": "make metformin 850 mg", "current_form": form}
    rows = TestClient(M.app).post("/api/v1/correct", json=body).json()["structured"]["rx"]
    assert [(r["name"], r["status"], r["dose_note"]) for r in rows] == [
        ("Paracetamol", "dose-check", NOTE), ("Metformin", "verified", "")]

def test_save_keeps_the_dose_note_in_the_stored_document(monkeypatch, tmp_path):
    from doctor_dictation import db as dbmod
    from doctor_dictation.api.app import create_app
    use_fixture(monkeypatch, tmp_path)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "api.db"))
    body = {"structured": {"patientName": "Anita", "opNo": "OP-1", "ageSex": "45 / M", "rx": [_page_row()]},
            "confirmed_rows": [0]}
    with TestClient(create_app()) as c:
        r = c.post("/api/v1/documents", json=body, headers={"X-DD-Client": "1"})
        assert r.status_code == 200, r.text
        conn = dbmod.get_conn()
        try:
            stored = json.loads(dbmod.get_document(conn, r.json()["document_id"])["structured_json"])
        finally:
            conn.close()
    assert (stored["rx"][0]["status"], stored["rx"][0]["dose_note"]) == ("dose-check", NOTE)
