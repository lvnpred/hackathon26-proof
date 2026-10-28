"""Plan I2-c fix round H: a row the doctor confirmed carries no "[unverified: confirm with doctor]" on paper. Save keeps the Instructions
text exactly as the page sent it (it never re-adds the marker for a confirmed row) and the 409 gate still stops unconfirmed rows. Offline."""
import json

from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation import db as dbmod
from doctor_dictation.config import override_settings
from doctor_dictation.pdf import build_sheet_html

MARK = "[unverified: confirm with doctor]"


def _client(tmp_path, monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "m.db"))
    conn = dbmod.get_conn()
    dbmod.migrate(conn)
    conn.close()
    return TestClient(M.app)


def _save(client, rows, confirmed):
    return client.post("/api/v1/documents", json={"structured": {"patientName": "Anita", "opNo": "OP-9", "rx": rows}, "confirmed_rows": confirmed})


def _stored(tmp_path, doc):
    conn = dbmod.get_conn(tmp_path / "m.db")
    try:
        return json.loads(dbmod.get_document(conn, doc)["structured_json"])
    finally:
        conn.close()


def test_a_confirmed_row_is_saved_and_printed_without_the_marker_whatever_its_status(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    rows = [{"name": "Zyloprim", "status": "unknown-medicine", "instructions": "after food"},
            {"name": "Prednisolone", "status": "lookalike-check", "instructions": "", "lexicon_match": "Prednisolone"},
            {"name": "Allopurinol", "status": "unverified-name", "instructions": "mine"}]
    r = _save(client, rows, [0, 1, 2])
    assert r.status_code == 200, r.text
    got = _stored(tmp_path, r.json()["document_id"])["rx"]
    assert [x["instructions"] for x in got] == ["after food", "", "mine"]                    # nothing re-added at Save
    assert [x["status"] for x in got] == ["unknown-medicine", "lookalike-check", "unverified-name"]
    assert MARK not in build_sheet_html(_stored(tmp_path, r.json()["document_id"]), {"date": "2026-10-01"})   # nor on paper


def test_an_unconfirmed_row_cannot_be_saved_with_or_without_the_marker(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    for text in ("after food", "after food " + MARK):
        r = _save(client, [{"name": "Zyloprim", "status": "unknown-medicine", "instructions": text}], [])
        assert r.status_code == 409 and r.json()["block"][0]["name"] == "Zyloprim"


def test_a_marker_the_page_kept_is_stripped_at_save_because_the_gate_passed(tmp_path, monkeypatch):
    # was "what the page sends is stored": final-fix I1 (belt and braces) strips the exact marker from every row that reaches Save
    client = _client(tmp_path, monkeypatch)
    r = _save(client, [{"name": "Zyloprim", "status": "unknown-medicine", "instructions": "x " + MARK}], [0])
    assert _stored(tmp_path, r.json()["document_id"])["rx"][0]["instructions"] == "x"


def test_a_confirmed_row_is_stored_as_confirmed_so_a_reopen_does_not_ask_again(tmp_path, monkeypatch):
    # owner, 2026-10-20: a reopened prescription showed "Confirm as is" on rows confirmed before Save
    client = _client(tmp_path, monkeypatch)
    rows = [{"dose": "SOS", "status": "unverified-name"},                                  # no name or strength: Save drops it
            {"name": "Adopiline", "status": "unknown-medicine"},
            {"name": "Crocin", "strength": "500 mg", "status": "verified", "doctor_confirmed": True}]
    r = _save(client, rows, [0, 1])
    assert r.status_code == 200, r.text
    got = _stored(tmp_path, r.json()["document_id"])["rx"]
    assert [(x["name"], x.get("doctor_confirmed")) for x in got] == [("Adopiline", True), ("Crocin", None)]


def test_a_flag_the_page_sends_never_confirms_a_row_by_itself(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = _save(client, [{"name": "Zyloprim", "status": "unknown-medicine", "doctor_confirmed": True}], [])
    assert r.status_code == 409
