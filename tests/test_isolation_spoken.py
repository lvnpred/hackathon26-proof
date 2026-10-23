"""A doctor's spoken terms stay with that doctor in that clinic (plan SH-H1). Offline; the seeded two-clinic world."""
from doctor_dictation import admin
from doctor_dictation.api import stt as api_stt
from doctor_dictation.config import override_settings
from isolation_fixtures import A, B, H, sql, user_id, world  # noqa: F401

DOLO = {"form": "Tab.", "name": "Dolo", "strength": "650 mg", "dose": "1-0-1", "status": "verified"}

def test_a_doctors_spoken_terms_reach_only_that_doctors_hints(world, monkeypatch):
    for patient in ("Asha Verma", "Lakshmi Narayan"):
        body = {"structured": {"patientName": patient, "ageSex": "40 / F", "opNo": "", "rx": [dict(DOLO)]},
                "confirmed_rows": []}
        assert world.rao.post("/api/v1/documents", json=body, headers=H).status_code == 200
    override_settings(monkeypatch, stt_use_hints=True)
    real, seen = api_stt.build_hints, {}
    for who in ("rao", "mehta", "iyer"):
        monkeypatch.setattr(api_stt, "build_hints", lambda top, limit, who=who: seen.setdefault(who, real(top, limit)))
        r = getattr(world, who).post("/api/transcribe", files={"audio": ("a.webm", b"x" * 64, "audio/webm")}, headers=H)
        assert r.status_code == 200, r.text
    assert seen["rao"][0] == "Dolo 650" and "Dolo 650" not in seen["mehta"] + seen["iyer"]
    rows = sql(A, "SELECT doctor_id, uses FROM spoken_terms WHERE term_key = 'dolo'")
    assert [tuple(r) for r in rows] == [(user_id(world, "dr.rao"), 2)]
    assert sql(B, "SELECT COUNT(*) FROM spoken_terms WHERE term_key = 'dolo'")[0][0] == 0

def test_the_backfill_credits_each_author_in_their_own_clinic(world, capsys):
    for t in ("spoken_term_docs", "spoken_term_strengths", "spoken_terms"):
        sql(A, f"DELETE FROM {t}")                                            # as before H1: documents, no terms
    before_b = [tuple(r) for r in sql(B, "SELECT * FROM spoken_terms ORDER BY id")]
    assert admin.main(["backfill-spoken-terms"]) == 0
    assert capsys.readouterr().out.splitlines() == ["iyer: 2 documents read, 0 new term uses",
                                                    "rao: 3 documents read, 5 new term uses"]
    rao, mehta = user_id(world, "dr.rao"), user_id(world, "dr.mehta")
    assert {tuple(r) for r in sql(A, "SELECT doctor_id, term_key FROM spoken_terms")} == {
        (rao, "paracetamol"), (rao, "amlodipine"), (rao, "telmisartan"), (mehta, "cetirizine"), (mehta, "montelukast")}
    assert [tuple(r) for r in sql(B, "SELECT * FROM spoken_terms ORDER BY id")] == before_b
