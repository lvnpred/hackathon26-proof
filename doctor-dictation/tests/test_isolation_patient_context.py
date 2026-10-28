"""Plan SH-H4: a doctor never gets another clinic's or another doctor's patient terms. Offline; the two-clinic world."""
import json

from doctor_dictation.api import stt as api_stt
from doctor_dictation.config import override_settings
from doctor_dictation.core import spoken
from isolation_fixtures import H, world  # noqa: F401

AUDIO = {"audio": ("a.webm", b"x" * 64, "audio/webm")}
K = spoken.key


def save_rx(client, patient, *medicines):
    rx = [{"form": "Tab.", "name": m, "status": "verified"} for m in medicines]
    body = {"structured": {"patientName": patient, "ageSex": "40 / M", "opNo": "", "rx": rx}, "confirmed_rows": []}
    r = client.post("/api/v1/documents", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["op_no"]


def test_patient_terms_stay_with_the_doctor_and_the_clinic_that_wrote_them(world, monkeypatch):
    override_settings(monkeypatch, stt_use_hints=True)          # the world already stubs the LLM and the speech chain
    for who in ("rao", "mehta", "iyer"):
        save_rx(getattr(world, who), "Gopal Das", "Montelukast", "Azithromycin")    # all three use both
    op_a = save_rx(world.mehta, "Suresh Babu", "Montelukast")                      # clinic A, Dr. Mehta's patient
    save_rx(world.iyer, "Suresh Babu", "Azithromycin")                             # clinic B: same name, another person
    seen, real = [], api_stt._doctor_terms
    monkeypatch.setattr(api_stt, "_doctor_terms", lambda context=None: seen.append(real(context)) or seen[-1])

    def tier3(who, **patient):
        ctx = {"diagnosis": [], "patient": {"name": "", "age_sex": "", "op_no": "", **patient}}
        r = getattr(world, who).post("/api/transcribe", files=AUDIO, data={"context": json.dumps(ctx)}, headers=H)
        assert r.status_code == 200, r.text
        return {t.key for t in seen[-1] if t.tier == 3}
    named = {"name": "Suresh Babu", "age_sex": "40 / M"}
    assert tier3("mehta", **named) == tier3("mehta", op_no=op_a) == {K("Montelukast")}
    assert tier3("iyer", **named) == {K("Azithromycin")}
    assert tier3("rao", **named) == tier3("rao", op_no=op_a) == set()      # same clinic, another doctor's patient
    assert tier3("iyer", op_no=op_a) == set()                              # another clinic's OP number
