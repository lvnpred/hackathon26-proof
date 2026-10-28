"""Plan SH-H4: the patient's earlier terms lift correction hints to tier 3. Offline, single-database mode."""
import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api import patientctx
from doctor_dictation.api import stt as api_stt
from doctor_dictation.api.app import create_app
from doctor_dictation.api.spoken import learn_spoken_terms
from doctor_dictation.config import override_settings
from doctor_dictation.core import spoken
from doctor_dictation.core.patientctx import match_patient
from doctor_dictation.db import spoken as sdb
from doctor_dictation.providers.stt.base import Transcript
from doctor_dictation.scope import Scope, use_scope

K = spoken.key
T = ["2026-10-0%dT09:00:00Z" % d for d in range(1, 10)]
AUDIO = {"audio": ("note.webm", b"RAWBYTES", "audio/webm")}
SURESH = {"name": "Suresh Babu", "age_sex": "40 / M", "op_no": ""}


def fresh():
    conn = dbmod.get_conn()                    # the autouse temp DB_PATH (tests/conftest.py)
    dbmod.migrate(conn)
    return conn


def visit(conn, pid, when, meds=(), tests=(), doctor=None, finalized=True, learn=False):
    eid = dbmod.create_encounter(conn, pid, doctor_id=doctor, status="finalized")
    form = {"patientName": "", "ageSex": "", "opNo": "", "diagnosis": [],
            "rx": [{"form": "Tab.", "name": m, "strength": "", "status": "verified"} for m in meds],
            "investigations": [{"text": t, "canonical": "", "status": "", "source": "dictated"} for t in tests]}
    did = dbmod.save_document(conn, eid, f"sha-{pid}-{when}", form, finalized_at=when if finalized else None, created_at=when)
    if learn:
        learn_spoken_terms(conn, form, did, doctor)          # H1's save hook fills spoken_terms
    return did


def test_patient_term_keys_reads_the_last_three_finalized_visits_of_this_doctor():
    conn = fresh()
    a, b = dbmod.create_user(conn, "dr.a", "x"), dbmod.create_user(conn, "dr.b", "x")
    pid = dbmod.create_patient(conn, "Suresh Babu", "40 / M", "OP 5")
    visit(conn, pid, T[0], ["Amoxicillin"], doctor=a)                       # 4th of a's visits: outside the window
    visit(conn, pid, T[1], ["Montelukast"], ["Serum creatinine"], doctor=a)
    visit(conn, pid, T[2], ["Cetirizine"], doctor=a)
    visit(conn, pid, T[3], ["Doxycycline"], doctor=a, finalized=False)     # never finalized: never counts
    visit(conn, pid, T[4], ["Azithromycin"], doctor=b)                      # another doctor's visit
    visit(conn, pid, T[5], ["Pantoprazole", "Montelukast"], doctor=a)
    odd = dbmod.create_patient(conn, "Gopal Das", "62 / M", None)
    visit(conn, odd, T[6], ["Telmisartan"])
    dbmod.save_document(conn, dbmod.create_encounter(conn, odd, status="finalized"), "sha-bad", "not json",
                        finalized_at=T[7], created_at=T[7])
    assert sdb.patient_term_keys(conn, pid, a) == {K("Montelukast"), K("Serum creatinine"), K("Cetirizine"), K("Pantoprazole")}
    assert sdb.patient_term_keys(conn, pid, a, visits=1) == {K("Pantoprazole"), K("Montelukast")}
    assert sdb.patient_term_keys(conn, pid, b) == {K("Azithromycin")}
    assert sdb.patient_term_keys(conn, pid, 0) == {K("Azithromycin"), K("Pantoprazole"), K("Montelukast"), K("Cetirizine")}
    assert sdb.patient_term_keys(conn, odd, 0) == {K("Telmisartan")}        # a malformed document adds nothing
    assert sdb.patient_term_keys(conn, 999, 0) == sdb.patient_term_keys(conn, (), 0) == set()
    again = dbmod.create_patient(conn, "Suresh Babu", "40 / M", None)       # his row from a save without an OP
    visit(conn, again, T[8], ["Levocetirizine"], doctor=a)
    assert sdb.patient_term_keys(conn, (pid, again), a) == {K("Levocetirizine"), K("Pantoprazole"), K("Montelukast"), K("Cetirizine")}
    conn.close()


def test_candidates_are_this_doctors_patients_or_everyone_in_single_database_mode():
    conn = fresh()
    a, b = dbmod.create_user(conn, "dr.a", "x"), dbmod.create_user(conn, "dr.b", "x")
    mine = dbmod.create_patient(conn, "Suresh Babu", "40 / M", "OP 5")
    theirs = dbmod.create_patient(conn, "Suresh Babu", "40 / M", "OP 6")
    nobody = dbmod.create_patient(conn, "Gopal Das", "", None)               # no encounter yet
    for _ in range(2):
        dbmod.create_encounter(conn, mine, doctor_id=a)                      # two visits, one candidate
    dbmod.create_encounter(conn, theirs, doctor_id=b)
    assert [r["id"] for r in sdb.patient_candidates(conn, a)] == [mine]
    assert [r["id"] for r in sdb.patient_candidates(conn, 0)] == [mine, theirs, nobody]
    assert sdb.patient_candidates(conn, a)[0].keys() == ["id", "name", "age_sex", "op_no"]
    assert match_patient("", "Suresh Babu", "40 / M", sdb.patient_candidates(conn, a)) == (mine,)
    assert match_patient("OP 6", "", "", sdb.patient_candidates(conn, a)) == ()      # another doctor's OP
    assert match_patient("", "Suresh Babu", "40 / M", sdb.patient_candidates(conn, 0)) == (mine, theirs)   # one person
    conn.close()


class Recorder:                                      # the speech provider: records the hints it was sent
    name, available = "recorder", staticmethod(lambda: True)

    def __init__(self):
        self.calls = []

    async def transcribe(self, audio, filename, hints=()):
        self.calls.append(list(hints))
        return Transcript(text="tab montelukast", engine="recorder")


def tier3(context):
    return {t.key for t in api_stt._doctor_terms(context) if t.tier == 3}


def test_a_correction_recording_hints_this_patients_earlier_medicines_first(monkeypatch):
    conn = fresh()
    suresh, gopal = dbmod.create_patient(conn, "Suresh Babu", "40 / M", "OP 5"), dbmod.create_patient(conn, "Gopal Das", "62 / M", "OP 6")
    for when in T[:3]:
        visit(conn, gopal, when, ["Pantoprazole"], learn=True)               # the doctor's most-used medicine
    visit(conn, suresh, T[3], ["Montelukast", "Cetirizine"], learn=True)
    conn.close()
    rec = Recorder()
    monkeypatch.setattr(api_stt, "make_stt", lambda settings: rec)
    override_settings(monkeypatch, stt_use_hints=True, stt_trim_silence=False, stt_hint_limit=12)
    ctx = {"diagnosis": [], "patient": {**SURESH, "name": "suresh  babu"}}
    with TestClient(create_app()) as client:
        plain = client.post("/api/transcribe", files=AUDIO)                  # a first dictation: no context
        hinted = client.post("/api/transcribe", files=AUDIO, data={"context": json.dumps(ctx)})
    assert plain.status_code == hinted.status_code == 200 and plain.json() == hinted.json()
    first, second = rec.calls
    assert first[0] == "Pantoprazole"
    assert set(second[:2]) == {"Montelukast", "Cetirizine"} and second[2] == "Pantoprazole"
    assert not [h for h in first + second if "suresh" in h.casefold() or "babu" in h.casefold()]    # S2


def test_tier_three_needs_exactly_one_person_named_in_the_context():
    conn = fresh()
    suresh = dbmod.create_patient(conn, "Suresh Babu", "40 / M", "OP 5")
    visit(conn, dbmod.create_patient(conn, "Gopal Das", "62 / M", "OP 6"), T[0], ["Pantoprazole"], learn=True)
    visit(conn, suresh, T[1], ["Montelukast", "Cetirizine"], learn=True)
    mine = {K("Montelukast"), K("Cetirizine")}
    assert tier3({"patient": SURESH}) == tier3({"patient": {**SURESH, "name": "", "op_no": "OP 5"}}) == mine
    assert tier3(None) == tier3({"diagnosis": []}) == tier3({"patient": "Suresh Babu"}) == set()
    assert tier3({"patient": {**SURESH, "age_sex": "43 / M"}}) == tier3({"patient": {**SURESH, "name": "Suresh Baabu"}}) == set()
    again = dbmod.create_patient(conn, "Suresh Babu", "40 / M", None)            # his row from a save without an OP
    visit(conn, again, T[2], ["Levocetirizine"], learn=True)
    both = mine | {K("Levocetirizine")}
    assert tier3({"patient": SURESH}) == tier3({"patient": {**SURESH, "name": "", "op_no": "OP 5"}}) == both   # one person
    dbmod.create_patient(conn, "Suresh Babu", "60 / M", None)                     # another man, twenty years older
    assert tier3({"patient": {**SURESH, "age_sex": ""}}) == set()                 # two people: nobody
    assert tier3({"patient": SURESH}) == both                                     # the dictated age tells them apart
    assert {t.key for t in api_stt._doctor_terms({"patient": SURESH})} >= mine | {K("Pantoprazole")}   # none lost
    conn.close()


def test_patient_context_fails_soft_and_takes_the_doctor_from_the_scope(monkeypatch):
    conn = fresh()
    visit(conn, dbmod.create_patient(conn, "Suresh Babu", "40 / M", "OP 5"), T[0], ["Montelukast"], learn=True)
    conn.close()

    def broken(conn, doctor_id):
        raise sqlite3.OperationalError("disk I/O error")
    monkeypatch.setattr(sdb, "patient_candidates", broken)
    terms = api_stt._doctor_terms({"patient": SURESH})
    assert terms and not [t for t in terms if t.tier == 3]                        # hints without the patient, never none
    assert patientctx.doctor_id() == 0
    with use_scope(Scope("rao", user_id=7)):
        assert patientctx.doctor_id() == 7
    with use_scope(Scope("rao", user_id=None)):
        assert patientctx.doctor_id() is None
    assert patientctx.clean_patient({"name": "x" * 300, "age_sex": 45, "op_no": "OP 5"}) == \
        {"name": "x" * 200, "age_sex": "", "op_no": "OP 5"}
    assert patientctx.clean_patient({"name": " ", "age_sex": "", "op_no": ""}) is None
    assert patientctx.clean_patient("Suresh Babu") is None


def test_the_page_puts_the_sheets_patient_in_the_correction_context():
    js = (Path(__file__).resolve().parents[1] / "frontend" / "app.js").read_text(encoding="utf-8")
    body = js.split("function patientContext()", 1)[1].split("\n}", 1)[0]
    assert all(f'$("{i}")' in body for i in ("pName", "pAge", "pOp"))
    assert "patient: patientContext()" in js
