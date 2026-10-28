"""Say it: /api/transcribe with mode=name returns the cleaned name next to the raw transcript. Offline."""
import json

from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api import stt as api_stt
from doctor_dictation.api.app import create_app
from doctor_dictation.api.spoken import learn_spoken_terms
from doctor_dictation.config import override_settings
from doctor_dictation.providers.stt.base import Transcript

AUDIO = {"audio": ("name.webm", b"RAWBYTES", "audio/webm")}


class Recorder:                                      # the speech provider: records the hints it was sent
    name, available = "recorder", staticmethod(lambda: True)

    def __init__(self):
        self.calls = []

    async def transcribe(self, audio, filename, hints=()):
        self.calls.append(list(hints))
        return Transcript(text="Eltroxin, E-L-T-R-O-X-I-N", engine="recorder")


def setup(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(api_stt, "make_stt", lambda settings: rec)
    override_settings(monkeypatch, stt_use_hints=True, stt_trim_silence=False, stt_hint_limit=12)
    return rec


def test_name_mode_returns_the_cleaned_name_and_keeps_the_raw_transcript(monkeypatch):
    setup(monkeypatch)
    with TestClient(create_app()) as client:
        r = client.post("/api/transcribe", files=AUDIO, data={"mode": "name"})
    j = r.json()
    assert r.status_code == 200 and j["name"] == "Eltroxin" and j["transcript"] == "Eltroxin, E-L-T-R-O-X-I-N"


def test_dictation_and_unknown_modes_keep_the_old_body(monkeypatch):
    setup(monkeypatch)
    with TestClient(create_app()) as client:
        plain = client.post("/api/transcribe", files=AUDIO)
        bogus = client.post("/api/transcribe", files=AUDIO, data={"mode": "bogus"})
    assert plain.status_code == bogus.status_code == 200
    assert "name" not in plain.json() and "name" not in bogus.json() and plain.json() == bogus.json()


def test_say_it_context_shapes_hints_and_never_reaches_the_engine_or_a_log(monkeypatch, capsys):
    conn = dbmod.get_conn()
    dbmod.migrate(conn)
    pid = dbmod.create_patient(conn, "Suresh Babu", "40 / M", "OP 5")
    eid = dbmod.create_encounter(conn, pid, doctor_id=None, status="finalized")
    form = {"patientName": "", "ageSex": "", "opNo": "", "diagnosis": [], "investigations": [],
            "rx": [{"form": "Tab.", "name": "Montelukast", "strength": "", "status": "verified"}]}
    did = dbmod.save_document(conn, eid, "sha-say-it", form, finalized_at="2026-10-01T09:00:00Z", created_at="2026-10-01T09:00:00Z")
    learn_spoken_terms(conn, form, did, None)
    conn.close()
    rec = setup(monkeypatch)
    ctx = {"diagnosis": [], "patient": {"name": "Suresh Babu", "age_sex": "40 / M", "op_no": ""}}
    with TestClient(create_app()) as client:
        r = client.post("/api/transcribe", files=AUDIO, data={"mode": "name", "context": json.dumps(ctx)})
    assert r.status_code == 200 and rec.calls[0][0] == "Montelukast"
    assert not [h for h in rec.calls[0] if "suresh" in h.casefold() or "babu" in h.casefold()]
    assert "Suresh" not in capsys.readouterr().out and "Suresh" not in r.text
