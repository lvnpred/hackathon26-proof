"""Shared helpers for the M3 route tests: one clinic ("rao"), two signed-in doctors, a fake PDF renderer.

Offline. A doctor is "signed in" by putting a genuinely signed session cookie on the client (``as_user``), so the
real session middleware loads the identity and sets the clinic scope on every request.
"""
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import accounts, clinics, sessions
from doctor_dictation import db as dbmod
from doctor_dictation.scope import clinic_dir

H = {"X-DD-Client": "1"}
RAO = {"doctor_name": "Dr. Rao", "qualifications": "MBBS", "reg_no": "R-111"}
MEHTA = {"doctor_name": "Dr. Mehta", "qualifications": "MBBS, MD", "reg_no": "M-222"}
CLINIC = {"clinic_name": "Rao Clinic", "address": "1 Main Road", "phone": "040 111"}
OLD = {"doctor_name": "Old Shared", "qualifications": "OLD", "reg_no": "OLD-1"}   # pre-M3 doctor fields on clinic_profile
SAVE = {"structured": {"patientName": "Anita", "opNo": "OP-1", "rx": [{"name": "Tamsulosin", "status": "verified"}]},
        "confirmed_rows": []}


def clinic_conn(slug="rao"):
    return closing(dbmod.get_conn(clinic_dir(slug) / "app.db"))


def as_user(client, uid, slug="rao"):
    client.cookies.set(sessions.COOKIE_NAME, sessions.sign(slug, uid, 0))
    return client


def save(client, body=SAVE):
    r = client.post("/api/v1/documents", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def legacy_document(patient="Old Patient"):
    """A prescription saved before authorship existed: no doctor_id, no finalized_by."""
    with clinic_conn() as conn:
        eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, patient, "50 / F", "OP-OLD"), op_no="OP-OLD",
                                     status="finalized")
        return dbmod.save_document(conn, eid, "sha-old", {"patientName": patient, "rx": []},
                                   finalized_at=dbmod._utcnow())


@pytest.fixture()
def team(multi, monkeypatch):
    clinics.provision_clinic("rao", "Rao Clinic")
    rao, _ = accounts.create_user("rao", "dr.rao", display_name="Rao", password="rao-password-1", **RAO)
    mehta, _ = accounts.create_user("rao", "dr.mehta", display_name="Mehta", password="mehta-password-1", **MEHTA)
    with clinic_conn() as conn:
        conn.execute("UPDATE users SET must_change_password = 0")
        conn.commit()
        dbmod.save_profile(conn, **OLD, **CLINIC)
    rendered = []

    def fake(structured, meta, out_path, layout=None):
        rendered.append(meta)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)
    from doctor_dictation.api.app import create_app
    with TestClient(create_app()) as c:
        yield SimpleNamespace(client=c, rao=rao, mehta=mehta, rendered=rendered)
