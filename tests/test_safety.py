"""Verify gate + Save (persist) + audit (Task 6).

The Save action must refuse to finalize while any Rx row is not ``verified``
unless the doctor explicitly confirmed that row; otherwise it records the
patient/encounter/document and an audit entry.

Offline: every test uses an isolated temp DB under pytest's ``tmp_path`` — the
real default DB (``doctor_dictation/data/app.db``) is never touched.

Run:  ./.venv-arm64/Scripts/python -m pytest tests/ -q
"""
import json
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation import db as dbmod
from doctor_dictation.core.safety import screen_unverified


def _client(monkeypatch):
    """TestClient pointed at a throwaway DB (mirrors tests/test_correction.py).

    The block path never touches the DB, but isolating DB_PATH keeps the test
    from ever opening ``doctor_dictation/data/app.db``.
    """
    import tempfile

    monkeypatch.setenv("DB_PATH", str(Path(tempfile.mkdtemp()) / "safety.db"))
    dbmod.init_db()
    return TestClient(M.app)


@pytest.fixture()
def client_db(tmp_path, monkeypatch):
    """Migrated connection to a throwaway DB; DB_PATH points at the same file.

    Mirrors the ``client`` fixture in tests/test_db.py for isolation, but yields
    a live connection so a test can inspect rows the endpoint wrote.
    """
    path = tmp_path / "safety.db"
    monkeypatch.setenv("DB_PATH", str(path))
    conn = dbmod.get_conn(path)
    dbmod.migrate(conn)
    yield conn
    conn.close()


def _use_renderer(monkeypatch, fn):
    fake = types.SimpleNamespace(render=fn)
    monkeypatch.setattr("doctor_dictation.pdf.renderer.get_renderer", lambda: fake)


def _client_after(client_db):
    """A TestClient for the temp DB the ``client_db`` fixture prepared."""
    return TestClient(M.app)


def _save_body(structured, document_id=None):
    """POST body for Save & Print; ``document_id`` is only included when set."""
    body = {"structured": structured, "confirmed_rows": []}
    if document_id is not None:
        body["document_id"] = document_id
    return body


def post_raw(client_db, structured, document_id=None):
    """POST /api/v1/documents against the temp DB; return the raw response."""
    return _client_after(client_db).post(
        "/api/v1/documents", json=_save_body(structured, document_id)
    )


def post_document(client_db, structured, document_id=None):
    """POST expecting 200; return the decoded body."""
    r = post_raw(client_db, structured, document_id)
    assert r.status_code == 200, r.text
    return r.json()


def count_documents(client_db):
    """Number of document rows currently stored."""
    return client_db.execute(
        "SELECT COUNT(*) AS n FROM documents"
    ).fetchone()["n"]


# --- screen_unverified (pure gate) -----------------------------------------

def test_screen_unverified_excludes_verified_and_confirmed():
    structured = {"rx": [
        {"name": "A", "status": "verified"},
        {"name": "B", "status": "unknown-medicine"},
        {"name": "C", "status": "unverified-name"},
    ]}
    assert screen_unverified(structured, []) == [
        {"index": 1, "name": "B", "status": "unknown-medicine"},
        {"index": 2, "name": "C", "status": "unverified-name"},
    ]
    # A doctor-confirmed row no longer blocks, even though it is not verified.
    assert screen_unverified(structured, [2]) == [
        {"index": 1, "name": "B", "status": "unknown-medicine"},
    ]
    assert screen_unverified({"rx": []}) == []


# --- POST /api/v1/documents -------------------------------------------------

def test_finalize_blocks_unverified(monkeypatch):
    c = _client(monkeypatch)
    r = c.post("/api/v1/documents", json={"structured": {"rx": [{"name": "Zzz", "status": "unknown-medicine"}]}, "confirmed_rows": []})
    assert r.status_code == 409 and r.json()["block"][0]["name"] == "Zzz"


def test_finalize_succeeds_when_all_verified(client_db):
    r = _client_after(client_db).post("/api/v1/documents", json={"structured": {"patientName": "Anita", "opNo": "OP-1", "rx": [{"name": "Tamsulosin", "status": "verified"}]}, "confirmed_rows": []})
    assert r.status_code == 200 and r.json()["encounter_id"]


def test_same_op_updates_same_patient(client_db):
    for _ in range(2):
        _client_after(client_db).post("/api/v1/documents", json={"structured": {"patientName": "Anita", "opNo": "OP-7", "rx": []}, "confirmed_rows": []})
    assert len(dbmod.list_patients(client_db)) == 1


def test_finalize_records_document_and_audit(client_db):
    r = _client_after(client_db).post("/api/v1/documents", json={
        "structured": {
            "patientName": "Anita",
            "ageSex": "45 / F",
            "opNo": "OP-9",
            "rx": [{"name": "Tamsulosin", "strength": "0.4 mg", "status": "verified"}],
        },
        "confirmed_rows": [],
        "engine": "test-engine",
        "transcript_sha256": "deadbeef",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"patient_id", "encounter_id", "document_id", "op_no"}
    doc = dbmod.get_document_by_sha(client_db, "deadbeef")
    assert doc["id"] == body["document_id"]
    assert doc["encounter_id"] == body["encounter_id"]
    assert doc["engine"] == "test-engine"
    assert doc["finalized_at"] and doc["finalized_at"].endswith("Z")
    # The doctor's verify state survives into the saved record (no re-grounding
    # against an absent transcript flips it to `unverified-name`).
    saved_rx = json.loads(doc["structured_json"])["rx"]
    assert saved_rx[0]["name"] == "Tamsulosin"
    assert saved_rx[0]["status"] == "verified"
    audit = client_db.execute(
        "SELECT * FROM audit_log WHERE entity = 'encounter' AND entity_id = ?",
        (str(body["encounter_id"]),),
    ).fetchone()
    assert audit is not None and audit["action"] == "finalize"


# --- PDF render wiring (Task 8; deterministic fake renderer) ----------------

def test_finalize_records_rendered_pdf_path(client_db, monkeypatch):
    """A successful render stores its path on the saved document."""
    def fake_render(html, out_path):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-fake")
        return Path(out_path)

    _use_renderer(monkeypatch, fake_render)
    r = _client_after(client_db).post("/api/v1/documents", json={
        "structured": {"patientName": "Anita", "opNo": "OP-11", "rx": []},
        "confirmed_rows": [],
        "transcript_sha256": "sha-pdf",
    })
    assert r.status_code == 200, r.text
    doc = dbmod.get_document_by_sha(client_db, "sha-pdf")
    assert doc["pdf_path"]
    assert doc["pdf_path"].endswith(f"encounter_{r.json()['encounter_id']}.pdf")
    assert Path(doc["pdf_path"]).read_bytes() == b"%PDF-fake"


def test_finalize_fails_soft_when_renderer_unavailable(client_db, monkeypatch):
    """A RuntimeError from the renderer never blocks Save; pdf_path stays None."""
    def boom(html, out_path):
        raise RuntimeError("PDF renderer unavailable: chromium not installed")

    _use_renderer(monkeypatch, boom)
    r = _client_after(client_db).post("/api/v1/documents", json={
        "structured": {"patientName": "Anita", "opNo": "OP-12", "rx": []},
        "confirmed_rows": [],
        "transcript_sha256": "sha-soft",
    })
    assert r.status_code == 200, r.text
    assert dbmod.get_document_by_sha(client_db, "sha-soft")["pdf_path"] is None


def test_finalize_fails_soft_on_non_runtimeerror_renderer_failure(client_db, monkeypatch):
    """Any renderer/storage failure (e.g. OSError from an unwritable dir) is
    fail-soft: Save still returns 200 with the document stored and pdf_path NULL."""
    def boom(html, out_path):
        raise OSError("cannot create directory: permission denied")

    _use_renderer(monkeypatch, boom)
    r = _client_after(client_db).post("/api/v1/documents", json={
        "structured": {"patientName": "Anita", "opNo": "OP-13", "rx": []},
        "confirmed_rows": [],
        "transcript_sha256": "sha-oserror",
    })
    assert r.status_code == 200, r.text
    doc = dbmod.get_document_by_sha(client_db, "sha-oserror")
    assert doc is not None and doc["pdf_path"] is None


def test_finalize_passes_current_profile_to_sheet(client_db, monkeypatch):
    """The sheet is built with the *current* clinic profile from the DB.

    A fake renderer captures the HTML handed to it; the profile saved just
    before Save must appear there (and therefore on the rendered PDF).
    """
    dbmod.save_profile(
        client_db, doctor_name="A. Rao", reg_no="12345", clinic_name="Meridian"
    )
    seen = {}

    def capture(html, out_path):
        seen["html"] = html
        raise RuntimeError("PDF renderer unavailable: chromium not installed")

    _use_renderer(monkeypatch, capture)
    r = _client_after(client_db).post("/api/v1/documents", json={
        "structured": {"patientName": "Anita", "opNo": "OP-P1", "rx": []},
        "confirmed_rows": [],
        "transcript_sha256": "sha-profile",
    })
    assert r.status_code == 200, r.text
    html = seen["html"]
    assert "A. Rao" in html and "12345" in html and "Meridian" in html


# --- Re-save (Task 4): update the existing document in place ----------------

def test_resave_updates_same_document(client_db):  # Review Focus #1
    """Re-saving a reopened document updates the same row (no duplicate)."""
    first = post_document(client_db, {
        "patientName": "Anita", "opNo": "OP-3",
        "rx": [{"name": "A", "status": "verified"}],
    })
    did = first["document_id"]
    second = post_document(client_db, {
        "patientName": "Anita", "opNo": "OP-3",
        "rx": [{"name": "B", "status": "verified"}],
    }, document_id=did)
    assert second["document_id"] == did
    assert count_documents(client_db) == 1
    # The form was overwritten in place, not appended as a new row.
    saved = json.loads(dbmod.get_document(client_db, did)["structured_json"])
    assert saved["rx"][0]["name"] == "B"


def test_resave_with_unverified_still_blocked(client_db):  # Review Focus #2
    """The verify gate runs before the update: an unverified row -> 409, no change."""
    first = post_document(client_db, {
        "patientName": "Anita", "opNo": "OP-4",
        "rx": [{"name": "A", "status": "verified"}],
    })
    did = first["document_id"]
    r = post_raw(client_db, {
        "patientName": "Anita", "opNo": "OP-4",
        "rx": [{"name": "B", "status": "unverified-name"}],
    }, document_id=did)
    assert r.status_code == 409
    assert r.json()["block"][0]["name"] == "B"
    # The stored document is untouched and no row was added.
    assert count_documents(client_db) == 1
    saved = json.loads(dbmod.get_document(client_db, did)["structured_json"])
    assert saved["rx"][0]["name"] == "A"


def test_resave_unknown_document_404(client_db):
    """A document_id that does not exist -> 404, and nothing is written."""
    r = post_raw(client_db, {
        "patientName": "Anita", "opNo": "OP-5", "rx": [],
    }, document_id=999999)
    assert r.status_code == 404
    assert count_documents(client_db) == 0


def test_resave_does_not_create_patient_row(client_db):
    """A re-save must not upsert a patient, even with a blank OP in the payload.

    ``upsert_patient`` always inserts when ``op_no`` is falsy, so calling it on
    re-save would leak an orphan patient on every save of a no-OP document.
    """
    first = post_document(client_db, {
        "patientName": "Anita", "opNo": "OP-6",
        "rx": [{"name": "A", "status": "verified"}],
    })
    did, p1 = first["document_id"], first["patient_id"]
    assert len(dbmod.list_patients(client_db)) == 1
    for _ in range(3):
        again = post_document(client_db, {
            "patientName": "Anita", "opNo": "",
            "rx": [{"name": "A", "status": "verified"}],
        }, document_id=did)
        assert again["patient_id"] == p1  # keeps the original encounter's patient
    assert len(dbmod.list_patients(client_db)) == 1
    assert count_documents(client_db) == 1


def test_resave_keeps_document_on_original_patient(client_db):
    """A re-save payload describing another patient never rebinds the document."""
    first = post_document(client_db, {
        "patientName": "Anita", "opNo": "OP-A",
        "rx": [{"name": "A", "status": "verified"}],
    })
    did, eid, p1 = first["document_id"], first["encounter_id"], first["patient_id"]
    second = post_document(client_db, {
        "patientName": "Bina", "opNo": "OP-B",
        "rx": [{"name": "B", "status": "verified"}],
    }, document_id=did)
    # The document stays on the original encounter/patient.
    assert second["encounter_id"] == eid
    assert second["patient_id"] == p1
    assert dbmod.get_encounter(client_db, eid)["patient_id"] == p1
    # No second patient row, and the original patient is not renamed.
    assert len(dbmod.list_patients(client_db)) == 1
    assert dbmod.get_patient(client_db, p1)["name"] == "Anita"
    # The extracted content is still updated in place.
    saved = json.loads(dbmod.get_document(client_db, did)["structured_json"])
    assert saved["rx"][0]["name"] == "B"
    assert count_documents(client_db) == 1


def test_resave_preserves_transcript_sha_and_created_at(client_db):
    """A re-save without a fresh transcript keeps the stored sha and created_at.

    ``transcript_sha`` is ``NOT NULL``; ``update_document`` uses
    ``COALESCE(?, transcript_sha)`` so a re-save with no new transcript hash
    keeps the original. ``created_at`` must not move either: "Today" membership
    is a function of the document's original creation timestamp.
    """
    client = _client_after(client_db)
    first = client.post("/api/v1/documents", json={
        "structured": {"patientName": "Anita", "opNo": "OP-SHA", "rx": []},
        "confirmed_rows": [],
        "transcript_sha256": "sha-keep",
    })
    assert first.status_code == 200, first.text
    did = first.json()["document_id"]
    before = dbmod.get_document(client_db, did)
    assert before["transcript_sha"] == "sha-keep"
    assert before["created_at"]

    # Re-save the reopened document with no transcript_sha256 in the payload.
    r = client.post("/api/v1/documents", json={
        "structured": {"patientName": "Anita", "opNo": "OP-SHA", "rx": []},
        "confirmed_rows": [],
        "document_id": did,
    })
    assert r.status_code == 200, r.text
    after = dbmod.get_document(client_db, did)
    assert after["transcript_sha"] == "sha-keep"  # COALESCE kept the old hash
    assert after["created_at"] == before["created_at"]  # Today membership stable
    assert count_documents(client_db) == 1


def test_app_shutdown_closes_the_pdf_renderer(client_db, monkeypatch):
    calls = []
    monkeypatch.setattr("doctor_dictation.api.app.close_renderer", lambda: calls.append(1))
    with TestClient(M.app):
        pass
    assert calls == [1]
