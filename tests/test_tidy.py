"""PQ-d Task 6: cross-section duplicate cleanup (core/tidy.py), run on format and correct, never on Save."""
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.core.determinism import _FORMAT_CACHE
from doctor_dictation.core.tidy import tidy_sections
from test_determinism import _stub_llm


def _s(**kw):
    base = {"patientName": "", "complaints": [], "diagnosis": [], "rx": [],
            "vitals": dict.fromkeys(("bp", "pulse", "weight", "spo2", "temp"), "")}
    return {**base, **kw}


def test_drops_a_complaint_equal_to_a_diagnosis():                      # spec 5, cause 1 (document 11)
    s = _s(complaints=["Headaches.", "Fever with chills"], diagnosis=["headaches", "Fever"])
    w = tidy_sections(s)
    assert s["complaints"] == ["Fever with chills"] and s["diagnosis"] == ["headaches", "Fever"]   # Review Focus 2
    assert w == ['complaints: dropped "Headaches.", the same as a diagnosis']


def test_strips_a_leading_demographics_clause():                        # spec 5, cause 2
    s = _s(patientName="Rahul Sharma", ageSex="45 / M", complaints=["78 yr old male, c/o fever for 3 days", "Rahul Sharma, 45 / M: cough",
                                                   "45-year-old female with knee pain", "65 yrs M c/o giddiness", "78 yr old male.",
                                                   "45M with chest pain", "45 M, chest pain", "45-F; cough", "50 y/o, asthma", "65 yrs old, BP 140/90"])
    w = tidy_sections(s)
    assert s["complaints"] == ["C/o fever for 3 days", "Cough", "Knee pain", "C/o giddiness", "Chest pain", "Chest pain", "Cough", "Asthma"]
    assert s["vitals"]["bp"] == "140/90"
    assert w[0] == "complaints[0]: removed the patient's details from the start (they print in the patient line)"


def test_leaves_numbers_that_are_not_a_leading_age():                  # Review Focus 3
    keep = ["3 m cough", "2 m history of fever", "5 m long ulcer", "45 M with chest pain", "5 years, cough", "2 years, knee pain", "5 mm calculus, right side", "3 days fever", "Fever in a 78 yr old male, since 2 days", "45 years history of smoking"]
    s = _s(complaints=list(keep))
    assert tidy_sections(s) == [] and s["complaints"] == keep


def test_moves_a_vitals_only_line_unless_it_conflicts():
    s = _s(complaints=["BP 140/90, pulse 88", "Fever"]); s["vitals"]["pulse"] = "88/min"
    w = tidy_sections(s)
    assert s["complaints"] == ["Fever"] and s["vitals"]["bp"] == "140/90" and s["vitals"]["pulse"] == "88/min"
    assert w == ["complaints[0]: moved to vitals"]
    s = _s(complaints=["BP 150/100"]); s["vitals"]["bp"] = "140/90"
    assert tidy_sections(s) == [] and s["complaints"] == ["BP 150/100"] and s["vitals"]["bp"] == "140/90"


def test_fields_limits_the_scope():
    s = _s(complaints=["78 yr old male, cough"], diagnosis=["78 yr old male, bronchitis"])
    tidy_sections(s, ("diagnosis",))
    assert s["complaints"] == ["78 yr old male, cough"] and s["diagnosis"] == ["Bronchitis"]


def test_rx_rows_and_odd_shapes_are_untouched():
    rx = [{"name": "Headaches"}]
    s = _s(complaints="not a list", diagnosis=None, rx=rx)
    assert tidy_sections(s) == [] and s["rx"] is rx and s["complaints"] == "not a list"
    assert tidy_sections({}) == []


def test_format_and_correct_routes_tidy(monkeypatch):
    _FORMAT_CACHE.clear()
    _stub_llm(monkeypatch, [{"complaints": ["Headache", "78 yr old male, c/o fever"], "diagnosis": ["headache"], "rx": []}])
    j = TestClient(M.app).post("/api/format", json={"transcript": "tidy route unique headache fever seventy eight"}).json()
    assert j["structured"]["complaints"] == ["C/o fever"]
    assert 'complaints: dropped "Headache", the same as a diagnosis' in j["warnings"]
    assert any(w.startswith("complaints[1]: removed the patient's details") for w in j["warnings"])
    _stub_llm(monkeypatch, [{"diagnosis": ["Cough"]}])
    form = {"complaints": ["Cough", "78 yr old male, fever"], "diagnosis": ["Fever"], "rx": []}
    j = TestClient(M.app).post("/api/v1/correct", json={"transcript": "diagnosis is cough", "current_form": form}).json()
    assert j["structured"]["complaints"] == ["Cough", "78 yr old male, fever"]   # only diagnosis was replaced: complaints untouched
    assert not any("dropped" in w for w in j["warnings"])
    _stub_llm(monkeypatch, [{"complaints": ["Fever", "78 yr old male, cough"]}])
    j = TestClient(M.app).post("/api/v1/correct", json={"transcript": "complaints are fever and cough", "current_form": form}).json()
    assert j["structured"]["complaints"] == ["Cough"]            # replaced field: dedupe and strip apply
    assert 'complaints: dropped "Fever", the same as a diagnosis' in j["warnings"]
