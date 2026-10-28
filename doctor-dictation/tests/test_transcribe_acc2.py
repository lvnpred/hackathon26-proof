import pytest
from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api import stt as route_mod
from doctor_dictation.api.app import create_app
from doctor_dictation.api.spoken import learn_spoken_terms
from doctor_dictation.config import override_settings
from doctor_dictation.providers.stt.base import Transcript

class Recorder:
    name = "recorder"
    available = staticmethod(lambda: True)
    calls = []

    async def transcribe(self, audio, filename, hints=()):
        self.calls.append({"audio": audio, "filename": filename, "hints": hints})
        return Transcript(text="hello", engine="recorder")

@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "acc2.db"))
    rec, trims = Recorder(), []
    rec.calls = []
    monkeypatch.setattr(route_mod, "make_stt", lambda settings: rec)
    monkeypatch.setattr(route_mod, "trim_silence", lambda audio, name: trims.append(name) or b"TRIMMED")
    with TestClient(create_app()) as client:
        yield client, rec, trims, monkeypatch

def _post(client):
    return client.post("/api/transcribe", files={"audio": ("note.webm", b"RAWBYTES", "audio/webm")})

def test_flags_off_means_no_hints_and_untouched_audio(env):
    client, rec, trims, mp = env
    override_settings(mp, stt_use_hints=False, stt_trim_silence=False)
    assert _post(client).status_code == 200
    assert rec.calls == [{"audio": b"RAWBYTES", "filename": "note.webm", "hints": ()}]
    assert trims == []

def test_hints_on_sends_doctors_medicines_first_then_lexicon(env):
    client, rec, _, mp = env
    conn = dbmod.get_conn()
    dbmod.migrate(conn)
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "40 / M", None))
    for names in (["Tamsulosin", "Tamsulosin", "Paracetamol"], ["Tamsulosin"]):      # a document counts a name once
        form = {"rx": [{"name": n} for n in names]}
        doc = dbmod.save_document(conn, eid, "sha", form, finalized_at="2026-10-13T00:00:00Z")
        learn_spoken_terms(conn, form, doc, None)
    conn.close()
    override_settings(mp, stt_use_hints=True, stt_hint_limit=12)
    assert _post(client).status_code == 200
    hints = list(rec.calls[0]["hints"])
    assert hints[:2] == ["Tamsulosin", "Paracetamol"]
    assert len(hints) == 12 and len({h.lower() for h in hints}) == 12
    assert rec.calls[0]["audio"] == b"RAWBYTES"

def test_hints_on_survives_a_database_error(env):
    client, rec, _, mp = env
    override_settings(mp, stt_use_hints=True, stt_hint_limit=5)
    mp.setattr(route_mod.spoken_db, "doctor_hint_terms", lambda conn, doctor_id, today: 1 / 0)
    assert _post(client).status_code == 200
    assert len(rec.calls[0]["hints"]) == 5            # lexicon names only

def test_trim_on_sends_trimmed_bytes_with_ogg_name_and_failsoft_keeps_original(env):
    client, rec, trims, mp = env
    override_settings(mp, stt_trim_silence=True)
    assert _post(client).status_code == 200
    assert trims == ["note.webm"]
    assert (rec.calls[0]["audio"], rec.calls[0]["filename"], rec.calls[0]["hints"]) == (b"TRIMMED", "note.ogg", ())
    mp.setattr(route_mod, "trim_silence", lambda audio, name: audio)     # fail-soft: same object back
    assert _post(client).status_code == 200
    assert (rec.calls[1]["audio"], rec.calls[1]["filename"]) == (b"RAWBYTES", "note.webm")
