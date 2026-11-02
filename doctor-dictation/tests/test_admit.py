"""Save & admit to ward (DD -> Count Guard, spec §6.1, §7.1, §7.3, §7.4). Offline: the push is captured or blackholed.

Run:  .venv/bin/python -m pytest tests/test_admit.py -q
"""
import json
import time
from contextlib import closing
from pathlib import Path

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api import admit
from doctor_dictation.api.app import create_app
from test_users_routes import _signed_in, world  # noqa: F401

CG_FIXTURE = Path(__file__).resolve().parents[2] / "count-guard" / "backend" / "tests" / "fixtures" / "dd_admission.json"
SAVE = {"structured": {"patientName": "M. Fernandes (synthetic)", "ageSex": "52 F", "opNo": "OP-24-0042",
                       "diagnosis": ["Left inguinal hernia"],
                       "rx": [{"name": "Tamsulosin", "status": "verified"}]}}
ADMIT = {**SAVE, "admit": True, "admit_reason": "Hernia repair"}
_ORIGINAL_PUSH = admit.push                     # the `pushed` fixture replaces the module attribute; tests that send use this
UNVERIFIED = {"structured": {"patientName": "A", "rx": [{"name": "Zorbexx", "status": "unknown-medicine"}]},
              "admit": True, "admit_reason": "Hernia repair"}


def _fake_pdf(monkeypatch):
    def fake(structured, meta, out_path, layout=None):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)


@pytest.fixture()
def pushed(monkeypatch):
    sent = []
    monkeypatch.setattr(admit, "push", lambda payload, url, token, db: sent.append((payload, url, token, db)))
    return sent


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("CG_SYNC_TOKEN", raising=False)
    monkeypatch.setenv("COUNT_GUARD_URL", "http://cg.test:8200")
    _fake_pdf(monkeypatch)
    with TestClient(create_app()) as c:
        yield c


def _rows():
    with closing(dbmod.get_conn()) as c:
        return [dict(r) for r in c.execute("SELECT * FROM admissions ORDER BY document_id")]


def test_admit_save_records_admission_and_pushes(client, pushed):
    r = client.post("/api/v1/documents", json=ADMIT)
    assert r.status_code == 200, r.text
    assert len(pushed) == 1
    payload, url, token, db = pushed[0]
    expected = json.loads(CG_FIXTURE.read_text())
    assert set(expected) <= set(payload)
    assert payload["status"] == "admit" and payload["source"] == "doctor-dictation"
    assert payload["document_id"] == r.json()["document_id"] and payload["admit_reason"] == "Hernia repair"
    for key in expected["document"]["structured"]:
        assert key in payload["document"]["structured"], key
    assert "doctor_name" in payload["document"]["author"]
    with closing(dbmod.get_conn()) as c:
        stored = dbmod.get_document(c, payload["document_id"])["finalized_at"]
    assert payload["finalized_at"] == stored and time.strptime(stored, "%Y-%m-%dT%H:%M:%SZ")
    assert url == "http://cg.test:8200" and token == "" and Path(db) == dbmod.db_path()
    [row] = _rows()
    assert row["status"] == "admit" and row["reason"] == "Hernia repair" and row["admitted_at"]


def test_send_home_save_records_nothing(client, pushed):
    assert client.post("/api/v1/documents", json=SAVE).status_code == 200
    assert _rows() == [] and pushed == []


def test_admit_without_reason_is_422(client, pushed):
    for reason in ("", "   "):
        r = client.post("/api/v1/documents", json={**SAVE, "admit": True, "admit_reason": reason})
        assert r.status_code == 422 and r.json() == {"error": "admission reason required"}
    r = client.post("/api/v1/documents", json={**UNVERIFIED, "admit_reason": ""})
    assert r.status_code == 422                                        # before the verify gate
    assert pushed == []


def test_verify_gate_still_blocks_admit(client, pushed):
    r = client.post("/api/v1/documents", json=UNVERIFIED)
    assert r.status_code == 409
    assert _rows() == [] and pushed == []


def test_after_save_only_queues_push(client, monkeypatch):
    calls = []
    monkeypatch.setattr(admit.httpx, "post", lambda *a, **k: calls.append(a))
    doc_id = client.post("/api/v1/documents", json=SAVE).json()["document_id"]
    tasks = BackgroundTasks()
    admit.after_save(None, tasks, document_id=doc_id, admit=True, reason="Hernia repair", resave=False)
    assert len(tasks.tasks) == 1 and tasks.tasks[0].func is admit.push
    assert calls == []
    assert tasks.tasks[0].args[0]["status"] == "admit"


def test_push_to_blackholed_cg_is_fast_and_records_error(client, pushed):
    doc_id = client.post("/api/v1/documents", json=ADMIT).json()["document_id"]
    start = time.monotonic()
    assert _ORIGINAL_PUSH(pushed[0][0], "http://10.255.255.1:9", "", dbmod.db_path()) is None
    assert time.monotonic() - start < 1.5
    [row] = _rows()
    assert row["document_id"] == doc_id and row["last_error"] and row["pushed_at"] is None


def test_push_success_records_pushed_at(client, pushed, monkeypatch):
    doc_id = client.post("/api/v1/documents", json=ADMIT).json()["document_id"]
    seen = {}

    class Ok:
        status_code = 201

    def fake_post(url, json, headers, timeout):
        seen.update(url=url, headers=headers, timeout=timeout)
        return Ok()
    monkeypatch.setattr(admit.httpx, "post", fake_post)
    _ORIGINAL_PUSH(pushed[0][0], "http://cg.test:8200", "tok", dbmod.db_path())
    assert seen["url"] == "http://cg.test:8200/journey/intake" and seen["headers"] == {"X-CG-Sync-Token": "tok"}
    assert seen["timeout"].connect == 1.0 and seen["timeout"].read == 3.0
    [row] = _rows()
    assert row["document_id"] == doc_id and row["pushed_at"] and row["last_error"] is None


def test_admission_status_route(client, pushed, monkeypatch):
    monkeypatch.setenv("CG_SYNC_TOKEN", "secret-for-cg")
    doc_id = client.post("/api/v1/documents", json=ADMIT).json()["document_id"]
    r = client.get(f"/api/v1/documents/{doc_id}/admission")              # no token: the browser's own route
    assert r.status_code == 200
    assert r.json() == {"status": "admit", "pushed_at": None, "last_error": None}
    other = client.post("/api/v1/documents", json=SAVE).json()["document_id"]
    assert client.get(f"/api/v1/documents/{other}/admission").status_code == 404


def test_after_save_noop_in_multi_clinic(multi):
    tasks = BackgroundTasks()
    assert admit.after_save(None, tasks, document_id=1, admit=True, reason="x", resave=False) is None
    assert tasks.tasks == []


def test_resave_admitted_as_send_home_sets_status(client, pushed):
    doc_id = client.post("/api/v1/documents", json=ADMIT).json()["document_id"]
    r = client.post("/api/v1/documents", json={**SAVE, "document_id": doc_id})
    assert r.status_code == 200, r.text
    [row] = _rows()
    assert row["status"] == "send_home" and row["reason"] == "Hernia repair"
    assert [p[0]["status"] for p in pushed] == ["admit", "send_home"]


def test_resave_never_admitted_sends_nothing(client, pushed):
    doc_id = client.post("/api/v1/documents", json=SAVE).json()["document_id"]
    assert client.post("/api/v1/documents", json={**SAVE, "document_id": doc_id}).status_code == 200
    assert _rows() == [] and pushed == []


def test_admissions_since_lists_payloads(client, pushed):
    first = client.post("/api/v1/documents", json=ADMIT).json()["document_id"]
    client.post("/api/v1/documents", json=SAVE)                         # sent home: never listed
    j = client.get("/api/v1/admissions").json()
    assert [a["document_id"] for a in j["admissions"]] == [first]
    assert j["admissions"][0] == pushed[0][0]                          # the same body as the push
    assert client.get("/api/v1/admissions", params={"since": "2000-01-01T00:00:00Z"}).json()["admissions"]
    assert client.get("/api/v1/admissions", params={"since": "2999-01-01T00:00:00Z"}).json() == {"admissions": []}
    assert client.get("/api/v1/admissions", params={"since": "yesterday"}).status_code == 422


def test_admissions_token(client, pushed, monkeypatch):
    client.post("/api/v1/documents", json=ADMIT)
    monkeypatch.setenv("CG_SYNC_TOKEN", "secret-for-cg")
    assert client.get("/api/v1/admissions").status_code == 401
    assert client.get("/api/v1/admissions", headers={"X-CG-Sync-Token": "wrong"}).status_code == 401
    r = client.get("/api/v1/admissions", headers={"X-CG-Sync-Token": "secret-for-cg"})
    assert r.status_code == 200 and len(r.json()["admissions"]) == 1
    assert "secret-for-cg" not in r.text


def test_admissions_404_in_multi_clinic(world):
    with _signed_in("dr.rao") as (rao,):
        assert rao.get("/api/v1/admissions").status_code == 404


def test_admission_status_404_in_multi_clinic(world):
    with _signed_in("dr.rao") as (rao,):
        assert rao.get("/api/v1/documents/1/admission").status_code == 404
