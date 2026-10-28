"""Signed-in clients for the multi-clinic letterhead and OP-prefix tests (plan M4). Offline: stub LLM, fake PDF."""
import json
from contextlib import closing, contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import accounts, clinics
from doctor_dictation import db as dbmod
from doctor_dictation.config import override_settings
from doctor_dictation.scope import clinic_dir
from template_fixtures import GOOD_LAYOUT, make_jpeg

H = {"X-DD-Client": "1"}
PASSWORD = "letterhead-pass-1"
DOCTORS_LAYOUT = {
    "header": [{"type": "doctors", "role": "subtitle", "align": "center"},
               {"type": "text", "field": "clinic_name", "align": "center"}, {"type": "rule"}],
    "footer": [{"type": "text", "field": "address", "role": "small", "align": "center"}],
    "body": {"top": 0.22, "bottom": 0.92},
    "profile": {"doctor_name": "Dr Pad Name", "qualifications": "", "reg_no": "", "clinic_name": "Rao Clinic",
                "address": "1 Lake Road", "phone": ""},
}


def clinic_conn(slug="rao"):
    return closing(dbmod.get_conn(clinic_dir(slug) / "app.db"))


def add_doctor(slug, username, name, qualifications="MBBS", reg_no="", role="doctor") -> int:
    """A user who can sign in straight away (no forced password change)."""
    uid, _ = accounts.create_user(slug, username, display_name=name, doctor_name=name,
                                  qualifications=qualifications, reg_no=reg_no, role=role, password=PASSWORD)
    with clinic_conn(slug) as conn:
        conn.execute("UPDATE users SET must_change_password = 0 WHERE id = ?", (uid,))
        conn.commit()
    return uid


@contextmanager
def signed_in(app, username):
    with TestClient(app, follow_redirects=False) as c:
        r = c.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD}, headers=H)
        assert r.status_code == 200, r.text
        c.headers.update(H)
        yield c


def stub_layout(monkeypatch, layout) -> None:
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(layout))


def upload(c) -> int:
    r = c.post("/api/v1/templates", files={"image": ("pad.jpg", make_jpeg(), "image/jpeg")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def record_renders(monkeypatch, module="persistence") -> list:
    """Replace render_prescription in ``doctor_dictation.api.<module>``; return the (structured, meta, layout) calls."""
    calls = []

    def fake(structured, meta, out_path, layout=None):
        calls.append((structured, dict(meta), layout))
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-1.4 fake")
        return Path(out_path)
    monkeypatch.setattr(f"doctor_dictation.api.{module}.render_prescription", fake)
    return calls


@pytest.fixture()
def rao(multi, monkeypatch):
    """Rao Clinic (prefix RAO): Dr. Rao and Dr. Mehta signed in, Dr. Old disabled. Stub vision LLM."""
    clinics.provision_clinic("rao", "Rao Clinic", "RAO")
    ids = {"rao": add_doctor("rao", "dr.rao", "Dr. A. Rao", "MBBS, MD", "TS-1"),
           "mehta": add_doctor("rao", "dr.mehta", "Dr. S. Mehta", "MBBS, DNB", "TS-2"),
           "old": add_doctor("rao", "dr.old", "Dr. Old", "MBBS", "TS-3")}
    with clinic_conn() as conn:
        conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (ids["old"],))
        conn.commit()
    stub_layout(monkeypatch, GOOD_LAYOUT)
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True)
    from doctor_dictation.api.app import create_app
    app = create_app()
    with signed_in(app, "dr.rao") as a, signed_in(app, "dr.mehta") as b:
        yield SimpleNamespace(ids=ids, rao=a, mehta=b, app=app)
