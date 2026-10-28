from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.config import override_settings

FORM = {"patientName": "Suresh Babu", "ageSex": "40 / M", "opNo": "OP-20261026-002",
        "rx": [{"form": "Tab.", "name": "Pantoprazole", "strength": "40 mg", "dose": "1-0-0", "instructions": "",
                "status": "verified", "lexicon_match": "Pantoprazole"}]}


def _post(transcript):
    return TestClient(M.app).post("/api/v1/correct", json={"transcript": transcript, "current_form": FORM})


def test_offline_a_correction_naming_another_patient_reports_it_and_keeps_the_old_keys(monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    r = _post("Next patient Ravi Kumar, 45 years male, fever")
    j = r.json()
    assert r.status_code == 200
    assert j["other_patient"] == {"name": "Ravi Kumar", "op_no": ""}
    assert {"structured", "grounding", "engine", "prose_check", "warnings", "changed_rows"} <= set(j)


def test_an_ordinary_correction_reports_no_other_patient(monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    j = _post("add tab Dolo 650 twice daily").json()
    assert j["other_patient"] is None


def test_the_model_patch_name_is_checked_and_the_answer_still_carries_the_merge(monkeypatch):
    class Fake:
        name = "fake"
        model = "m"

        async def complete_json(self, messages):
            return {"patientName": "Ravi Kumar", "rx": [{"name": "Dolo 650"}]}, None

    monkeypatch.setattr("doctor_dictation.api.format.make_llm", lambda s: Fake())
    j = _post("fever, give Dolo 650").json()
    assert j["other_patient"] == {"name": "Ravi Kumar", "op_no": ""}
    assert j["structured"]["patientName"] == "Ravi Kumar"


def test_the_check_reads_the_raw_dictation_not_the_normalised_text(monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")

    async def rewrite(text):
        return "next patient tab ravikumar 45 years"

    monkeypatch.setattr("doctor_dictation.api.format._normalize", rewrite)
    assert _post("Next patient Ravi Kumar, 45 years male, fever").json()["other_patient"] == {"name": "Ravi Kumar", "op_no": ""}
