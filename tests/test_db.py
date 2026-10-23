"""Persistence tests (P0-4): stdlib sqlite3 schema, migrations, repositories, API.

Offline: every test uses an isolated temp DB under pytest's ``tmp_path`` — the
real default DB (``doctor_dictation/data/app.db``) is never touched.

Run:  ./.venv-arm64/Scripts/python -m pytest tests/ -q
"""
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod


@pytest.fixture()
def conn(tmp_path):
    """A migrated connection to a throwaway temp DB."""
    c = dbmod.get_conn(tmp_path / "test.db")
    dbmod.migrate(c)
    yield c
    c.close()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient with DB_PATH pointed at a temp DB; lifespan runs init_db()."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "api.db"))
    from doctor_dictation.main import app

    with TestClient(app) as c:
        yield c


# --- schema / migrations ---------------------------------------------------

def test_db_module_resolves_to_package_init():
    """Regression: ``db`` must resolve to the package ``doctor_dictation/db/__init__.py``.

    ``doctor_dictation/db/`` is both the module and the migrations directory (P0-4).
    A rogue ``doctor_dictation/db.py`` module — or any stray module on ``sys.path`` — would
    shadow the package and break ``dbmod.get_conn()`` at startup. This pins the
    import to the real package ``__init__.py`` so the suite catches any future
    shadowing.
    """
    repo_root = Path(__file__).resolve().parents[1]
    expected = (repo_root / "doctor_dictation" / "db" / "__init__.py").resolve()
    resolved = Path(dbmod.__file__).resolve()
    assert resolved == expected, f"db resolved to {resolved}, expected {expected}"
    assert resolved.name == "__init__.py"
    assert resolved.parent.name == "db"
    # The package must still find the migrations next to it (not under doctor_dictation/data).
    assert Path(dbmod.MIGRATIONS_DIR).resolve() == resolved.parent / "migrations"
    assert (Path(dbmod.MIGRATIONS_DIR) / "001_init.sql").exists()
    # The default DB path must stay doctor_dictation/data/app.db (unchanged by the move).
    assert Path(dbmod.DEFAULT_DB_PATH).resolve() == (
        repo_root / "doctor_dictation" / "data" / "app.db"
    ).resolve()


def test_schema_tables_created(conn):
    names = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {
        "users",
        "patients",
        "encounters",
        "documents",
        "audit_log",
        "clinic_profile",
        "schema_migrations",
    } <= names


def test_connection_pragmas(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.row_factory is sqlite3.Row


def test_init_db_idempotent(tmp_path):
    path = tmp_path / "idem.db"
    first = dbmod.init_db(path)
    assert first == ["001_init.sql", "002_document_pdf.sql", "003_clinic_profile.sql", "004_templates.sql", "005_users_profile.sql",
                     "006_doctor_details_to_users.sql", "007_templates_scope.sql", "008_clinic_profile_prefix.sql",
                     "009_clinic_formulary.sql", "010_clinic_overlay.sql", "011_spoken_terms.sql"]
    # Second run is a no-op: nothing new applied, version row not duplicated.
    second = dbmod.init_db(path)
    assert second == []
    c = dbmod.get_conn(path)
    try:
        n = c.execute("SELECT COUNT(*) AS n FROM schema_migrations").fetchone()["n"]
    finally:
        c.close()
    assert n == 11


def test_migration_adds_pdf_path(conn):
    """002 adds the rendered-PDF path column to ``documents`` (additive)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(documents)")}
    assert "pdf_path" in cols


# --- patients --------------------------------------------------------------

def test_create_get_patient(conn):
    pid = dbmod.create_patient(conn, "Rahul Sharma", "45 / M", "OP-1001")
    row = dbmod.get_patient(conn, pid)
    assert row["name"] == "Rahul Sharma"
    assert row["age_sex"] == "45 / M"
    assert row["op_no"] == "OP-1001"
    assert row["created_at"].endswith("Z")
    assert dbmod.get_patient(conn, 999999) is None


def test_list_patients(conn):
    dbmod.create_patient(conn, "Asha", "30 / F", "OP-2")
    dbmod.create_patient(conn, "Bala", "50 / M", "OP-3")
    names = [r["name"] for r in dbmod.list_patients(conn)]
    assert names == ["Asha", "Bala"]


def test_find_patient_by_op(conn):
    pid = dbmod.create_patient(conn, "Anita", "45 / F", "OP-1234")
    assert dbmod.find_patient_by_op(conn, "OP-1234")["id"] == pid
    assert dbmod.find_patient_by_op(conn, "OP-9999") is None


def test_upsert_patient_updates_existing(conn):
    pid = dbmod.create_patient(conn, "Anita", "45 / F", "OP-1234")
    again = dbmod.upsert_patient(conn, "Anita Sharma", "46 / F", "OP-1234")
    assert again == pid
    row = dbmod.get_patient(conn, pid)
    assert row["name"] == "Anita Sharma" and row["age_sex"] == "46 / F"
    assert len(dbmod.list_patients(conn)) == 1


def test_upsert_patient_blank_op_always_inserts(conn):
    dbmod.upsert_patient(conn, "A", "", None)
    dbmod.upsert_patient(conn, "B", "", None)
    assert len(dbmod.list_patients(conn)) == 2


def test_upsert_patient_same_op_tiebreaks_by_name(conn):
    """Two patients share OP-9: the upsert updates the name-matching row only.

    Bob is inserted first so the old ``LIMIT 1`` lookup would have picked him.
    """
    bob = dbmod.create_patient(conn, "Bob", "50 / M", "OP-9")
    anita = dbmod.create_patient(conn, "Anita", "45 / F", "OP-9")
    updated = dbmod.upsert_patient(conn, "Anita", "46 / F", "OP-9")
    assert updated == anita
    assert dbmod.get_patient(conn, anita)["age_sex"] == "46 / F"
    assert dbmod.get_patient(conn, bob)["age_sex"] == "50 / M"
    assert len(dbmod.list_patients(conn)) == 2


def test_upsert_patient_same_op_new_name_inserts(conn):
    """No OP-9 row matches the incoming name -> insert, clobbering neither."""
    anita = dbmod.create_patient(conn, "Anita", "45 / F", "OP-9")
    bob = dbmod.create_patient(conn, "Bob", "50 / M", "OP-9")
    new_id = dbmod.upsert_patient(conn, "New Name", "50 / M", "OP-9")
    assert new_id not in (anita, bob)
    assert dbmod.get_patient(conn, anita)["name"] == "Anita"
    assert dbmod.get_patient(conn, bob)["name"] == "Bob"
    assert len(dbmod.list_patients(conn)) == 3


# --- encounters ------------------------------------------------------------

def test_create_get_encounter(conn):
    pid = dbmod.create_patient(conn, "Rahul", "45 / M", "OP-1001")
    eid = dbmod.create_encounter(conn, pid, op_no="OP-1001")
    row = dbmod.get_encounter(conn, eid)
    assert row["patient_id"] == pid
    assert row["doctor_id"] is None
    assert row["status"] == "draft"
    assert row["consent_at"] is None
    assert row["created_at"].endswith("Z")


def test_list_encounters_filter_by_patient(conn):
    p1 = dbmod.create_patient(conn, "A")
    p2 = dbmod.create_patient(conn, "B")
    dbmod.create_encounter(conn, p1, op_no="OP-1")
    dbmod.create_encounter(conn, p1, op_no="OP-2")
    dbmod.create_encounter(conn, p2, op_no="OP-3")
    only_p1 = dbmod.list_encounters(conn, patient_id=p1)
    assert [r["op_no"] for r in only_p1] == ["OP-1", "OP-2"]
    assert len(dbmod.list_encounters(conn)) == 3


def test_encounter_fk_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        dbmod.create_encounter(conn, 999999)


# --- users -----------------------------------------------------------------

def test_user_roundtrip_and_unique_username(conn):
    uid = dbmod.create_user(conn, "admin", "pbkdf2$hash", role="admin")
    row = dbmod.get_user_by_username(conn, "admin")
    assert row["id"] == uid
    assert row["role"] == "admin"
    assert row["is_active"] == 1
    assert dbmod.get_user_by_username(conn, "nobody") is None
    with pytest.raises(sqlite3.IntegrityError):
        dbmod.create_user(conn, "admin", "other")  # UNIQUE(username)


def test_role_check_constraint(conn):
    with pytest.raises(sqlite3.IntegrityError):
        dbmod.create_user(conn, "nurse1", "h", role="nurse")


# --- audit log -------------------------------------------------------------

def test_log_audit_serializes_detail(conn):
    aid = dbmod.log_audit(
        conn,
        actor="1",
        role="doctor",
        action="finalize",
        entity="encounter",
        entity_id="5",
        detail={"rows": 3, "ok": True},
        ip="127.0.0.1",
    )
    row = conn.execute("SELECT * FROM audit_log WHERE id = ?", (aid,)).fetchone()
    assert row["action"] == "finalize"
    assert row["entity"] == "encounter"
    assert row["entity_id"] == "5"
    assert json.loads(row["detail"]) == {"rows": 3, "ok": True}
    assert row["at"].endswith("Z")


# --- documents -------------------------------------------------------------

def test_save_and_get_document_by_sha(conn):
    pid = dbmod.create_patient(conn, "Rahul")
    eid = dbmod.create_encounter(conn, pid)
    did = dbmod.save_document(
        conn,
        eid,
        "abc123",
        {"diagnosis": ["Fever"]},
        engine="fallback-rules",
        model_versions={"whisper": "small.en"},
    )
    row = dbmod.get_document_by_sha(conn, "abc123")
    assert row["id"] == did
    assert row["encounter_id"] == eid
    assert json.loads(row["structured_json"]) == {"diagnosis": ["Fever"]}
    assert json.loads(row["model_versions"]) == {"whisper": "small.en"}
    assert row["finalized_at"] is None
    assert dbmod.get_document_by_sha(conn, "missing") is None


def test_save_document_records_pdf_path(conn):
    """``pdf_path`` is stored when given and left NULL otherwise (back-compat)."""
    pid = dbmod.create_patient(conn, "Rahul")
    eid = dbmod.create_encounter(conn, pid)
    with_pdf = dbmod.save_document(
        conn, eid, "sha-pdf", {"x": 1}, pdf_path="/tmp/x.pdf"
    )
    row = conn.execute(
        "SELECT pdf_path FROM documents WHERE id = ?", (with_pdf,)
    ).fetchone()
    assert row["pdf_path"] == "/tmp/x.pdf"
    without_pdf = dbmod.save_document(conn, eid, "sha-no-pdf", {"x": 1})
    row2 = conn.execute(
        "SELECT pdf_path FROM documents WHERE id = ?", (without_pdf,)
    ).fetchone()
    assert row2["pdf_path"] is None


def test_document_fk_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        dbmod.save_document(conn, 999999, "sha", {"x": 1})


# --- API endpoints ---------------------------------------------------------

def test_patients_endpoint_create_and_list(client):
    r = client.post(
        "/api/v1/patients",
        json={"name": "Asha", "age_sex": "30 / F", "op_no": "OP-2"},
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r2 = client.get("/api/v1/patients")
    assert r2.status_code == 200
    assert [p["id"] for p in r2.json()] == [pid]


def test_encounters_endpoint_create_and_filter(client):
    pid = client.post("/api/v1/patients", json={"name": "Bala"}).json()["id"]
    r = client.post(
        "/api/v1/encounters", json={"patient_id": pid, "op_no": "OP-3"}
    )
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    assert r.json()["status"] == "draft"
    r2 = client.get(f"/api/v1/encounters?patient_id={pid}")
    assert r2.status_code == 200
    assert [e["id"] for e in r2.json()] == [eid]
    assert client.get("/api/v1/encounters?patient_id=999999").json() == []


def test_encounter_endpoint_unknown_patient_404(client):
    r = client.post("/api/v1/encounters", json={"patient_id": 424242})
    assert r.status_code == 404
    assert "not found" in r.json()["error"]
