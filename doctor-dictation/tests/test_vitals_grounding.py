"""PQ-d final fix wave: a dictated vital is never deleted, an invented vital is never kept."""
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.core.determinism import _FORMAT_CACHE
from doctor_dictation.core.fallback import fallback_format
from doctor_dictation.core.tidy import tidy_sections
from doctor_dictation.core.vitals import VITAL_KEYS, ground, vitals_all_stored

EMPTY = dict.fromkeys(VITAL_KEYS, "")


def _s(**kw):
    return {"patientName": "", "ageSex": "", "complaints": [], "diagnosis": [], "rx": [], "vitals": dict(EMPTY), **kw}


# Item 1: a vitals-only sentence moves to vitals only when every vital it names was stored.
def test_vitals_all_stored():
    assert vitals_all_stored("BP 140/90") and vitals_all_stored("BP 140/90, pulse 88")
    for t in ("SpO2 45%.", "Pulse 300.", "BP 280/130", "BP 140/90, pulse 300", "fever", ""):
        assert not vitals_all_stored(t), t


def test_tidy_keeps_an_out_of_range_vital_in_complaints():
    for t in ("SpO2 45%.", "Pulse 300.", "BP 280/130"):
        s = _s(complaints=[t, "Breathless since morning"])
        w = tidy_sections(s)
        assert s["complaints"] == [t, "Breathless since morning"] and s["vitals"] == EMPTY and w == [], t
    s = _s(complaints=["BP 140/90", "Fever"])
    assert tidy_sections(s) == ["complaints[0]: moved to vitals"] and s["vitals"]["bp"] == "140/90"


def test_fallback_keeps_an_out_of_range_vital_in_complaints():
    out = fallback_format("SpO2 45%. Breathless since morning.")
    assert any("45" in c for c in out["complaints"]) and out["vitals"]["spo2"] == ""
    assert fallback_format("BP 140/90")["vitals"]["bp"] == "140/90"


def test_fallback_no_longer_imports_private_patterns():
    import inspect
    import doctor_dictation.core.fallback as F
    assert "_PATTERNS" not in inspect.getsource(F)


# Item 2: grounding.
def test_ground_blanks_a_value_whose_numbers_were_not_dictated():
    v, w = ground({"bp": "120/80", "pulse": "72/min", "weight": "", "spo2": "", "temp": ""}, "fever for 2 days")
    assert v == EMPTY and len(w) == 2 and all("not in the dictation" in x for x in w)
    v, w = ground({"bp": "140/90", "pulse": "72/min", "temp": "98.6 F", "spo2": "98%", "weight": "72 kg"},
                  "bp 140 by 90", "pulse 72, temp 98.6, saturation 98 percent")
    assert v == {"bp": "140/90", "pulse": "72/min", "temp": "98.6 F", "spo2": "98%", "weight": "72 kg"} and w == []
    v, w = ground({"bp": "140/80"}, "bp 140/90")
    assert v["bp"] == "" and w                                   # both numbers are needed
    v, w = ground({"pulse": "regular"}, "pulse regular")
    assert v["pulse"] == "" and w                                # no digits: never from the model path
    assert ground({"temp": "98.60"}, "temp 98.6")[0]["temp"] == "98.60"   # compared numerically


def _stub_format(monkeypatch, draft):
    from test_determinism import _stub_llm
    _FORMAT_CACHE.clear()
    _stub_llm(monkeypatch, [draft])


def test_format_route_drops_an_invented_vital(monkeypatch):
    _stub_format(monkeypatch, {"complaints": ["Fever for 2 days"], "vitals": {"bp": "120/80", "pulse": "72"}, "rx": []})
    j = TestClient(M.app).post("/api/format", json={"transcript": "grounding probe fever for 2 days"}).json()
    assert j["structured"]["vitals"] == EMPTY
    assert any(w.startswith("vitals.bp") for w in j["warnings"]) and any(w.startswith("vitals.pulse") for w in j["warnings"])


def test_format_route_keeps_a_dictated_vital(monkeypatch):
    _stub_format(monkeypatch, {"complaints": ["Fever"], "vitals": {"bp": "140/90", "pulse": "88"}, "rx": []})
    j = TestClient(M.app).post("/api/format", json={"transcript": "grounding probe BP 140 by 90, pulse 88, fever"}).json()
    assert j["structured"]["vitals"]["bp"] == "140/90" and j["structured"]["vitals"]["pulse"] == "88/min"
    _stub_format(monkeypatch, {"complaints": ["Fever"], "vitals": {"bp": "140/90"}, "rx": []})
    j = TestClient(M.app).post("/api/format", json={"transcript": "grounding probe BP one forty by ninety, fever"}).json()
    assert j["structured"]["vitals"]["bp"] == ""          # ruling: number words are not normalised; the doctor types it


def test_format_route_keeps_an_out_of_range_spo2_in_complaints(monkeypatch):
    _stub_format(monkeypatch, {"complaints": ["SpO2 45%.", "Breathless since morning"], "vitals": {}, "rx": []})
    j = TestClient(M.app).post("/api/format", json={"transcript": "grounding probe SpO2 45%. Breathless since morning."}).json()
    assert j["structured"]["complaints"][0] == "SpO2 45%." and j["structured"]["vitals"]["spo2"] == ""
    assert not any("moved to vitals" in w for w in j["warnings"])


def _correct(monkeypatch, patch, cur, transcript):
    from test_correction import _client, _stub_llm
    client = _client(monkeypatch)
    _stub_llm(monkeypatch, patch)
    return client.post("/api/v1/correct", json={"transcript": transcript, "current_form": cur}).json()


def test_correct_route_drops_an_invented_patch_vital(monkeypatch):
    cur = {"vitals": {"bp": "140/90", "pulse": "88 irregular"}, "rx": []}
    j = _correct(monkeypatch, {"vitals": {"bp": "130/80", "spo2": "97%"}}, cur, "BP is now 130 by 80")
    assert j["structured"]["vitals"] == {"bp": "130/80", "pulse": "88 irregular", "weight": "", "spo2": "", "temp": ""}
    assert any(w.startswith("vitals.spo2") for w in j["warnings"])     # the current side is the doctor's: not grounded


# Item 4: a rejected correction value is reported.
def test_correct_route_reports_a_rejected_vital(monkeypatch):
    cur = {"vitals": {"bp": "140/90"}, "rx": []}
    j = _correct(monkeypatch, {"vitals": {"bp": "280/140"}}, cur, "BP is now 280/140")
    assert j["structured"]["vitals"]["bp"] == "140/90"
    assert any(w.startswith("vitals.bp") and "kept" in w for w in j["warnings"])


# Item 3: bare m/f strips only when the number is the patient's age.
def test_bare_m_f_strips_only_the_patients_age():
    keep = ["3m, swelling over neck", "2 m, cough on and off", "6 f, catheter", "45M with chest pain"]
    s = _s(complaints=list(keep))
    assert tidy_sections(s) == [] and s["complaints"] == keep
    s = _s(ageSex="", complaints=["45 M, chest pain", "45-F; cough", "45/m: fever"])
    assert tidy_sections(s) == [] and s["complaints"] == ["45 M, chest pain", "45-F; cough", "45/m: fever"]
    s = _s(ageSex="45 / M", complaints=["45 M, chest pain", "45-F; cough", "45/m: fever", "3m, swelling over neck"])
    tidy_sections(s)
    assert s["complaints"] == ["Chest pain", "Cough", "Fever", "3m, swelling over neck"]
    s = _s(ageSex="", complaints=["45 year old male, chest pain", "50 y/o, asthma", "45 male, cough"])
    tidy_sections(s)
    assert s["complaints"] == ["Chest pain", "Asthma", "Cough"]               # word forms and age markers unchanged
