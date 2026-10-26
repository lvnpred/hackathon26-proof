"""Diagnosis links stay with the doctor and the clinic that saved them (plan SH-H3). Offline; the seeded two-clinic world."""
import json

from doctor_dictation.api import stt as api_stt
from doctor_dictation.config import override_settings
from isolation_fixtures import A, B, H, fingerprint, save_body, sql, user_id, world  # noqa: F401

CTX = json.dumps({"diagnosis": ["Acute pharyngitis"], "patient": {"name": "Asha Verma", "age_sex": "40 / F", "op_no": ""}})


def save(client, patient, diagnosis):
    body = save_body(patient, medicine="Dolo")
    body["structured"]["rx"][0]["strength"] = "650 mg"
    body["structured"]["diagnosis"] = [diagnosis]
    body["confirmed_rows"] = [0]
    r = client.post("/api/v1/documents", json=body, headers=H)
    assert r.status_code == 200, r.text


def test_diagnosis_links_lift_only_the_saving_doctors_hints_in_their_own_clinic(world, monkeypatch):
    before_b = fingerprint(B)
    for patient in ("Asha Verma", "Lakshmi Narayan"):
        save(world.rao, patient, "Acute pharyngitis")
        save(world.mehta, "Ravi Kulkarni", "Fever")                     # same clinic, same drug, another diagnosis
    assert fingerprint(B) == before_b                       # the seeded links in B are in the fingerprint
    rows = [tuple(r) for r in sql(A, "SELECT doctor_id, diagnosis_key, count FROM term_links "
                                 "WHERE diagnosis_key IN ('acute pharyngitis', 'fever') ORDER BY diagnosis_key")]
    assert rows == [(user_id(world, "dr.rao"), "acute pharyngitis", 2), (user_id(world, "dr.mehta"), "fever", 2)]
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, stt_chain=("stub",),
                      stt_use_hints=True, stt_trim_silence=False)
    real, seen = api_stt.build_hints, {}
    for who in ("rao", "mehta", "iyer"):
        monkeypatch.setattr(api_stt, "build_hints", lambda terms, limit, who=who: (seen.setdefault(who, list(terms)), real(terms, limit))[1])
        r = getattr(world, who).post("/api/transcribe", data={"context": CTX},
                                     files={"audio": ("a.webm", b"x" * 64, "audio/webm")}, headers=H)
        assert r.status_code == 200, r.text
    tiers = {who: {t.phrase: t.tier for t in terms} for who, terms in seen.items()}
    lifted = {who: sorted(p for p, t in by.items() if t == 2) for who, by in tiers.items()}   # the seeded drugs sit at other tiers
    assert lifted == {"rao": ["Dolo 650"], "mehta": [], "iyer": []}
    assert tiers["mehta"]["Dolo 650"] == 0 and "Dolo 650" not in tiers["iyer"]
