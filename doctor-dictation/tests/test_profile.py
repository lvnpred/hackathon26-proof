"""Clinic/doctor profile tests (Task 1): single-row storage + GET/PUT endpoints.

Offline: both fixtures use an isolated temp DB via ``DB_PATH`` so the real
default DB (``doctor_dictation/data/app.db``) is never touched. Fixtures are defined
locally (not imported across test modules).

Run:  ./.venv-arm64/Scripts/python -m pytest tests/ -q
"""
import pytest
from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    """A migrated connection to a throwaway temp DB (via DB_PATH)."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "profile.db"))
    c = dbmod.get_conn()
    dbmod.migrate(c)
    yield c
    c.close()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient with DB_PATH pointed at a temp DB; lifespan runs init_db()."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "profile_api.db"))
    from doctor_dictation.main import app

    with TestClient(app) as c:
        yield c


def test_profile_defaults_empty(conn):
    assert dbmod.get_profile(conn) is None


def test_profile_roundtrip(conn):
    dbmod.save_profile(conn, doctor_name="A. Rao", reg_no="12345", clinic_name="Meridian")
    dbmod.save_profile(conn, doctor_name="A. Rao", qualifications="MBBS", reg_no="12345", clinic_name="Meridian")
    p = dbmod.get_profile(conn)
    assert p["doctor_name"] == "A. Rao" and p["qualifications"] == "MBBS"
    assert conn.execute("SELECT COUNT(*) c FROM clinic_profile").fetchone()["c"] == 1


def test_profile_endpoint_put_then_get(client):
    assert client.get("/api/v1/profile").json()["clinic_name"] == ""
    client.put("/api/v1/profile", json={"doctor_name": "A. Rao", "clinic_name": "Meridian"})
    assert client.get("/api/v1/profile").json()["clinic_name"] == "Meridian"


def test_single_mode_put_cleans_hidden_and_control_characters(client):
    r = client.put("/api/v1/profile", json={"doctor_name": "Dr.‮ A​\nRao", "clinic_name": " Clinic One ",
                                            "reg_no": "ಕ‍"})
    body = client.get("/api/v1/profile").json()
    assert r.status_code == 200 and (body["doctor_name"], body["clinic_name"], body["reg_no"]) == ("Dr. A Rao", "Clinic One", "ಕ‍")
