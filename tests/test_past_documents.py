"""Past prescriptions are view and reprint only (UI-A Task 1). Offline; the clinic day is frozen with monkeypatch.

A document's visit day is the clinic-zone day of its created_at (fixed at first save). A re-save of a document from an
earlier day is refused (409, nothing written); today's re-save is unchanged. GET adds ``past`` so the page can lock.
"""
import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api import visit

H = {"X-DD-Client": "1"}
TODAY = date(2026, 10, 21)
YESTERDAY_UTC = "2026-10-20T06:00:00Z"      # 11:30 IST on the 20th
TODAY_UTC = "2026-10-21T06:00:00Z"          # 11:30 IST on the 21st
FORM = {"patientName": "Asha", "opNo": "OP-7", "rx": [{"name": "Dolo 650", "status": "verified"}]}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "past.db"))
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    monkeypatch.setattr(visit, "today", lambda now=None: TODAY)

    def fake(structured, meta, out_path, layout=None):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)
    from doctor_dictation.api.app import create_app
    with TestClient(create_app()) as c:
        yield c


def _doc(created_at):
    conn = dbmod.get_conn()
    try:
        eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "Asha", "30 / F", "OP-7"), op_no="OP-7",
                                     status="finalized")
        return dbmod.save_document(conn, eid, "sha", FORM, created_at=created_at, finalized_at=created_at)
    finally:
        conn.close()


def _row(doc_id):
    conn = dbmod.get_conn()
    try:
        return dict(dbmod.get_document(conn, doc_id))
    finally:
        conn.close()


def _resave(c, doc_id, name="Asha"):
    return c.post("/api/v1/documents", headers=H, json={
        "structured": {**FORM, "patientName": name}, "confirmed_rows": [], "document_id": doc_id})


def test_a_resave_of_yesterdays_prescription_is_refused_and_nothing_is_written(client):
    doc = _doc(YESTERDAY_UTC)
    before = _row(doc)
    r = _resave(client, doc, name="Changed")
    assert r.status_code == 409
    j = r.json()
    assert j["error"] == "past prescription"
    assert j["hint"] == ("This prescription is from 20 Oct 2026. Past prescriptions are view and reprint only; "
                         "start a new visit to change the treatment.")
    assert _row(doc) == before
    assert json.loads(_row(doc)["structured_json"])["patientName"] == "Asha"


def test_the_past_refusal_comes_before_the_unverified_medicines_gate(client):
    doc = _doc(YESTERDAY_UTC)
    r = client.post("/api/v1/documents", headers=H, json={
        "structured": {**FORM, "rx": [{"name": "Zzzq", "status": "unverified-name"}]}, "confirmed_rows": [], "document_id": doc})
    assert r.status_code == 409 and r.json()["error"] == "past prescription"


def test_a_resave_of_todays_prescription_still_works(client):
    doc = _doc(TODAY_UTC)
    r = _resave(client, doc, name="Asha B")
    assert r.status_code == 200, r.text
    assert r.json()["document_id"] == doc
    assert json.loads(_row(doc)["structured_json"])["patientName"] == "Asha B"


def test_get_document_says_whether_it_is_past(client):
    old, new = _doc(YESTERDAY_UTC), _doc(TODAY_UTC)
    assert client.get(f"/api/v1/documents/{old}").json()["past"] is True
    assert client.get(f"/api/v1/documents/{new}").json()["past"] is False


def test_an_unreadable_visit_day_is_not_past(client):
    doc = _doc(TODAY_UTC)
    conn = dbmod.get_conn()
    conn.execute("UPDATE documents SET created_at = 'garbage' WHERE id = ?", (doc,))
    conn.commit()
    conn.close()
    assert client.get(f"/api/v1/documents/{doc}").json()["past"] is False
