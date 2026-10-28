"""Today scopes and per-doctor hints (M3 Task 3, spec 7.2 and 7.3). Offline."""
from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api import stt as stt_api
from doctor_dictation.api.spoken import learn_spoken_terms
from doctor_dictation.config import override_settings
from doctor_dictation.providers.stt.base import Transcript
from authorship_fixtures import H, SAVE, as_user, clinic_conn, legacy_document, save, team  # noqa: F401


def _names(rows):
    return [(r["patient_name"], r["doctor_name"]) for r in rows]


def _save_for(c, patient):
    return save(c, {**SAVE, "structured": {**SAVE["structured"], "patientName": patient, "opNo": ""}})


def test_today_defaults_to_my_prescriptions(team):
    c = as_user(team.client, team.rao)
    _save_for(c, "Asha")
    _save_for(as_user(c, team.mehta), "Bala")
    mine = as_user(c, team.rao).get("/api/v1/encounters/today")
    assert mine.status_code == 200
    assert _names(mine.json()) == [("Asha", "Dr. Rao")]
    assert c.get("/api/v1/encounters/today?scope=mine").json() == mine.json()


def test_whole_clinic_shows_every_prescription_with_its_authors_name(team):
    c = as_user(team.client, team.rao)
    _save_for(c, "Asha")
    _save_for(as_user(c, team.mehta), "Bala")
    legacy_document("Chitra")
    rows = c.get("/api/v1/encounters/today?scope=clinic").json()
    assert _names(rows) == [("Asha", "Dr. Rao"), ("Bala", "Dr. Mehta"), ("Chitra", "")]
    assert [r["author_id"] for r in rows] == [team.rao, team.mehta, None]


def test_today_rejects_an_unknown_scope(team):
    r = as_user(team.client, team.rao).get("/api/v1/encounters/today?scope=everyone")
    assert (r.status_code, r.json()) == (400, {"error": "scope must be mine or clinic"})


def test_repeated_scope_parameters_use_the_last_value(team):
    c = as_user(team.client, team.rao)
    _save_for(c, "Asha")
    _save_for(as_user(c, team.mehta), "Bala")
    as_user(c, team.rao)
    assert _names(c.get("/api/v1/encounters/today?scope=clinic&scope=mine").json()) == [("Asha", "Dr. Rao")]
    assert len(c.get("/api/v1/encounters/today?scope=mine&scope=clinic").json()) == 2


def test_single_mode_today_ignores_scope_and_keeps_the_old_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "single.db"))
    from doctor_dictation.api.app import create_app
    with TestClient(create_app()) as c:
        conn = dbmod.get_conn()
        eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "Asha", "", "OP-7"), op_no="OP-7")
        dbmod.save_document(conn, eid, "sha", {"rx": []})
        conn.close()
        for url in ("/api/v1/encounters/today", "/api/v1/encounters/today?scope=mine", "/api/v1/encounters/today?scope=clinic",
                    "/api/v1/encounters/today?scope=bogus"):
            rows = c.get(url).json()
            assert [r["patient_name"] for r in rows] == ["Asha"], url
            assert set(rows[0]) == {"document_id", "encounter_id", "patient_name", "op_no", "created_at"}


class _Recorder:
    name = "recorder"
    available = staticmethod(lambda: True)

    def __init__(self):
        self.hints = []

    async def transcribe(self, audio, filename, hints=()):
        self.hints.append(list(hints))
        return Transcript(text="hello", engine="recorder")


def test_hints_come_from_the_signed_in_doctors_own_prescriptions(team, monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(stt_api, "make_stt", lambda settings: rec)
    override_settings(monkeypatch, stt_use_hints=True, stt_trim_silence=False, stt_hint_limit=12)
    with clinic_conn() as conn:
        for author, names in ((team.rao, ["Tamsulosin", "Tamsulosin"]), (team.mehta, ["Paracetamol"])):
            eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "", None), doctor_id=author)
            form = {"rx": [{"name": n} for n in names]}
            doc = dbmod.save_document(conn, eid, "sha", form, finalized_at=dbmod._utcnow())
            learn_spoken_terms(conn, form, doc, author)
    audio = {"audio": ("note.webm", b"RAWBYTES", "audio/webm")}
    c = team.client
    assert as_user(c, team.mehta).post("/api/transcribe", files=audio, headers=H).status_code == 200
    assert as_user(c, team.rao).post("/api/transcribe", files=audio, headers=H).status_code == 200
    mehta_hints, rao_hints = rec.hints
    assert mehta_hints[0] == "Paracetamol"        # all prescriptions together would put Tamsulosin (2 uses) first
    assert rao_hints[0] == "Tamsulosin"
