""" "Today" query + load-a-document tests (Task 2).

Offline: every fixture uses an isolated temp DB via ``DB_PATH`` so the real
default DB (``doctor_dictation/data/app.db``) is never touched. Fixtures are defined
locally (not imported across test modules).

The boundary tests pin a fixed UTC+5:30 clock so "local midnight" straddles two
UTC days — a naive UTC-day filter would wrongly include the previous day's
23:50 document.

Run:  ./.venv-arm64/Scripts/python -m pytest tests/ -q
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod

# Fixed local zone (UTC+5:30) + anchor clock used by the boundary tests.
LOCAL_TZ = timezone(timedelta(hours=5, minutes=30))


def _local(year, month, day, hour, minute) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=LOCAL_TZ)


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient with DB_PATH pointed at an empty temp DB; lifespan runs init_db()."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "today_api.db"))
    from doctor_dictation.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def temp_db_with_two_docs(tmp_path, monkeypatch):
    """A migrated temp DB with one doc before local midnight and one after.

    Both save on UTC 2026-10-12 but fall on different *local* (UTC+5:30) days:
      * 2026-10-12 23:50 local  -> excluded from the 2026-10-13 local day
      * 2026-10-13 00:10 local  -> included
    """
    monkeypatch.setenv("DB_PATH", str(tmp_path / "today.db"))
    conn = dbmod.get_conn()
    dbmod.migrate(conn)
    old_patient = dbmod.create_patient(conn, "Old Patient", "50 / M", "OP-OLD")
    old_encounter = dbmod.create_encounter(conn, old_patient, op_no="OP-OLD")
    dbmod.save_document(
        conn,
        old_encounter,
        "sha-old",
        {"diagnosis": ["Old"]},
        created_at=_utc_iso(_local(2026, 10, 12, 23, 50)),
    )
    new_patient = dbmod.create_patient(conn, "Today Patient", "40 / F", "OP-NEW")
    new_encounter = dbmod.create_encounter(conn, new_patient, op_no="OP-NEW")
    dbmod.save_document(
        conn,
        new_encounter,
        "sha-new",
        {"diagnosis": ["New"]},
        created_at=_utc_iso(_local(2026, 10, 13, 0, 10)),
    )
    yield conn
    conn.close()


@pytest.fixture()
def client_with_today_doc(tmp_path, monkeypatch):
    """TestClient whose temp DB already holds one document saved "now" (today)."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "today_client.db"))
    from doctor_dictation.main import app

    with TestClient(app) as c:
        conn = dbmod.get_conn()
        try:
            pid = dbmod.create_patient(conn, "Asha", "30 / F", "OP-7")
            eid = dbmod.create_encounter(conn, pid, op_no="OP-7")
            dbmod.save_document(
                conn,
                eid,
                "sha-today",
                {"diagnosis": ["Fever"]},
                engine="fallback-rules",
            )
        finally:
            conn.close()
        yield c


# --- bounds ----------------------------------------------------------------

def test_today_bounds_straddle_local_midnight():
    # 03:00 local on a UTC+5:30 machine is the previous UTC day
    now = datetime(2026, 10, 13, 3, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    start, end = dbmod.local_day_bounds_utc(now)
    assert start.startswith("2026-10-12") and end.startswith("2026-10-13")
    assert start == "2026-10-12T18:30:00Z" and end == "2026-10-13T18:30:00Z"


# --- list_documents_between (Review Focus #4: local-midnight boundary) ------

def test_today_excludes_yesterday(temp_db_with_two_docs):
    """The doc saved 23:50 local (prev day) is out; the 00:10 local one is in."""
    bounds = dbmod.local_day_bounds_utc(_local(2026, 10, 13, 12, 0))
    rows = dbmod.list_documents_between(temp_db_with_two_docs, *bounds)
    assert len(rows) == 1
    row = rows[0]
    assert set(row.keys()) == {
        "document_id",
        "encounter_id",
        "patient_name",
        "op_no",
        "created_at",
    }
    assert row["patient_name"] == "Today Patient"
    assert row["op_no"] == "OP-NEW"
    assert row["created_at"] == _utc_iso(_local(2026, 10, 13, 0, 10))


# --- endpoints -------------------------------------------------------------

def test_today_endpoint_shape(client_with_today_doc):
    j = client_with_today_doc.get("/api/v1/encounters/today").json()
    assert set(j[0]) == {
        "document_id",
        "encounter_id",
        "patient_name",
        "op_no",
        "created_at",
    }
    assert j[0]["patient_name"] == "Asha"
    assert j[0]["op_no"] == "OP-7"


def test_today_endpoint_empty_is_empty_list(client):
    assert client.get("/api/v1/encounters/today").json() == []


def test_get_document_loads_structured(client_with_today_doc):
    doc = client_with_today_doc.get("/api/v1/encounters/today").json()[0]
    r = client_with_today_doc.get(f"/api/v1/documents/{doc['document_id']}")
    assert r.status_code == 200, r.text
    j = r.json()
    assert set(j) == {
        "document_id",
        "structured",
        "engine",
        "transcript_sha256",
        "created_at",
        "visit_date",      # I3: the clinic-zone day of created_at
    }
    assert j["document_id"] == doc["document_id"]
    assert j["structured"] == {"diagnosis": ["Fever"]}
    assert j["transcript_sha256"] == "sha-today"
    assert j["engine"] == "fallback-rules"
    assert j["created_at"].endswith("Z")


def test_get_document_404(client):
    assert client.get("/api/v1/documents/999999").status_code == 404
