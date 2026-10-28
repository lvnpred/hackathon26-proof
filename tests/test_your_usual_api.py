"""Plan SH-B6: POST /api/v1/spoken/usual offers the doctor's own usual rows for a diagnosis. Offline."""
import json
import logging
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api import stt as api_stt
from doctor_dictation.api import your_usual as yu_api
from doctor_dictation.api.app import create_app
from doctor_dictation.db import spoken as sdb
from doctor_dictation.providers.stt.base import Transcript

H = {"X-DD-Client": "1"}
DOLO = {"form": "Tab.", "name": "Dolo", "strength": "650 mg", "dose": "1-0-1", "timing": "After food", "duration": "5 days"}
OTHER = {"form": "Tab.", "name": "Cetirizine", "strength": "10 mg", "dose": "0-0-1", "timing": "At bedtime", "duration": "3 days"}
ZORB = {"form": "Tab.", "name": "Zorbexin", "strength": "5 mg", "dose": "1-0-0", "timing": "", "duration": "7 days"}


class Recorder:
    async def transcribe(self, audio, filename, hints=()):
        return Transcript(text="hello", engine="recorder")


def _fake_pdf(structured, meta, out_path, layout=None):
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(b"%PDF-fake")
    return Path(out_path)


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))                       # never the real dev database
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", _fake_pdf)
    monkeypatch.setattr(api_stt, "make_stt", lambda settings: Recorder())
    with TestClient(create_app()) as c:
        yield c


def _save(c, diagnosis, rows, document_id=None):
    rows = [{**r, "status": "verified"} for r in rows]
    body = {"structured": {"patientName": "Asha Verma", "ageSex": "40 / F", "diagnosis": diagnosis, "rx": rows},
            "confirmed_rows": list(range(len(rows))), **({"document_id": document_id} if document_id else {})}
    r = c.post("/api/v1/documents", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def ask(c, *lines):
    return c.post("/api/v1/spoken/usual", json={"diagnosis": list(lines)}, headers=H)


def test_two_saves_offer_the_usual_row_and_one_does_not(app_client):
    c = app_client
    _save(c, ["Fever"], [DOLO])
    assert ask(c, "Fever").json() == {"groups": []}
    _save(c, ["Fever"], [DOLO])
    item = ask(c, "fever.").json()["groups"][0]["items"][0]
    assert {k: item[k] for k in ("form", "name", "strength", "dose", "timing", "duration", "count")} == {
        "form": "Tab.", "name": "Dolo", "strength": "650 mg", "dose": "1-0-1", "timing": "After food",
        "duration": "5 days", "count": 2}
    assert "generic" in item


def test_lines_keep_their_index_and_a_medicine_shows_once(app_client):
    c = app_client
    for _ in range(2):
        _save(c, ["Fever", "Myalgia"], [DOLO])
    groups = ask(c, "", "Myalgia", "Fever").json()["groups"]
    assert [g["line"] for g in groups] == [1] and [i["name"] for i in groups[0]["items"]] == ["Dolo"]


def test_a_resave_that_drops_the_medicine_removes_the_suggestion(app_client):
    c = app_client
    _save(c, ["Fever"], [DOLO])
    doc = _save(c, ["Fever"], [DOLO])
    assert ask(c, "Fever").json()["groups"]
    _save(c, ["Fever"], [OTHER], document_id=doc)
    assert ask(c, "Fever").json() == {"groups": []}


def test_a_name_the_clinic_removed_or_hid_is_never_offered(app_client, monkeypatch):
    c = app_client
    for _ in range(2):
        _save(c, ["Fever"], [DOLO, ZORB])
    names = lambda: [i["name"] for g in ask(c, "Fever").json()["groups"] for i in g["items"]]   # noqa: E731
    assert sorted(names()) == ["Dolo", "Zorbexin"]
    with monkeypatch.context() as m:
        m.setattr(yu_api, "is_blocked", lambda n: n == "Dolo")                              # (b) the overlay hid it
        assert names() == ["Zorbexin"]
    entry = next(e for e in c.get("/api/v1/formulary").json()["items"] if e["name"] == "Zorbexin")
    assert c.delete(f"/api/v1/formulary/{entry['id']}", headers=H).status_code == 200      # (c) the clinic removed it
    assert names() == ["Dolo"]
    with dbmod.get_conn() as conn:                                                          # (a) the doctor's term removed
        conn.execute("UPDATE spoken_terms SET removed_at = '2026-01-01' WHERE term_key = 'dolo'")
    assert names() == []


def test_only_the_signed_in_doctor_counts_and_the_body_cannot_choose_one(app_client):
    c = app_client
    for _ in range(2):
        _save(c, ["Fever"], [DOLO])
    with dbmod.get_conn() as conn:
        conn.execute("UPDATE spoken_terms SET doctor_id = 7")
        conn.execute("UPDATE term_links SET doctor_id = 7")
    assert ask(c, "Fever").json() == {"groups": []}                                         # single mode is doctor 0
    r = c.post("/api/v1/spoken/usual", json={"diagnosis": ["Fever"], "doctor_id": 7}, headers=H)
    assert r.status_code == 200 and r.json() == {"groups": []}


def test_bad_bodies_answer_400(app_client):
    c = app_client
    for body in [{}, {"diagnosis": "Fever"}, {"diagnosis": ["a"] * 11}, {"diagnosis": ["a" * 201]}, {"diagnosis": [7]}]:
        assert c.post("/api/v1/spoken/usual", json=body, headers=H).status_code == 400
    assert ask(c).json() == {"groups": []} and ask(c, "Hb").json() == {"groups": []}   # no line, or a line under 3 letters


def test_a_database_error_answers_503_and_logs_no_diagnosis(app_client, monkeypatch, caplog):
    def boom(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(sdb, "diagnosis_medicine_links", boom)
    with caplog.at_level(logging.DEBUG):
        r = ask(app_client, "Benign prostatic hyperplasia")
    assert r.status_code == 503 and r.json() == {"error": "try again"}
    assert "prostatic" not in caplog.text and "prostatic" not in json.dumps(r.json())
