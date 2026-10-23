"""Shared world for the isolation suite (spec 13.1): seed-demo's two clinics, three signed-in doctors, fake Chromium.

Offline: stub LLM and STT, and a fake browser behind the REAL pdf-worker thread, so a stored "PDF" is
``%PDF-fake`` plus the exact sheet HTML that would have printed (tests assert on printed names). Every interface
assumed from M3, M4 or M5 is one small helper at the bottom, tagged with its assumption number from
docs/superpowers/plans/2026-10-14-m6-isolation-suite-and-demo.md; if a sibling plan named something
differently, change the helper, not the tests.
"""
import hashlib
import json
import sqlite3
import threading
from contextlib import ExitStack, closing, contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import accounts, admin_demo
from doctor_dictation import db as dbmod
from doctor_dictation.api import stt
from doctor_dictation.api.app import create_app
from doctor_dictation.config import override_settings
from doctor_dictation.db import templates as tdb
from doctor_dictation.pdf import renderer as R
from doctor_dictation.scope import clinic_dir
from template_fixtures import make_jpeg

H = {"X-DD-Client": "1"}
A, B = "rao", "iyer"
A_MARKERS = ("Rao Clinic", "Asha Verma", "Ravi Kulkarni", "Lakshmi Narayan", "Dr. A. Rao", "Dr. S. Mehta",
             "dr.rao", "dr.mehta", "adm.rao", "RAO-", admin_demo.RAO_PAD_LINE)
B_MARKERS = ("Iyer Clinic", "Bharat Menon", "Meena Pillai", "Dr. K. Iyer", "dr.iyer", "adm.iyer", "IYER-",
             admin_demo.IYER_PAD_LINE)
UPLOAD_PAD_LINE = "Child care, Tue and Thu evenings"
UPLOAD_PAD = {"header": [{"type": "logo", "crop": [0.05, 0.02, 0.25, 0.10], "align": "left"},
                         {"type": "text", "field": "doctor_name", "role": "title", "align": "center"},
                         {"type": "text", "text": UPLOAD_PAD_LINE, "role": "small", "align": "center"}],
              "footer": [], "body": {"top": 0.22, "bottom": 0.92}, "profile": {}}
TABLES = ("patients", "encounters", "documents", "templates", "users", "clinic_profile", "audit_log",
          "schema_migrations", "clinic_formulary", "clinic_formulary_docs",
          "spoken_terms", "spoken_term_docs", "spoken_term_strengths")


class _Page:
    def __init__(self, sink):
        self.sink, self.html = sink, ""

    def set_content(self, html, **_kw):
        self.html = html

    def pdf(self, path, **_kw):
        self.sink.append({"thread": threading.current_thread().name, "html": self.html})
        Path(path).write_bytes(b"%PDF-fake\n" + self.html.encode("utf-8"))


class _Context:
    def __init__(self, sink):
        self.sink = sink

    def new_page(self):
        return _Page(self.sink)

    def close(self):
        pass


class _Browser:
    def __init__(self, sink):
        self.sink = sink

    def new_context(self, **_kw):
        return _Context(self.sink)

    def is_connected(self):
        return True


@pytest.fixture()
def world(multi, monkeypatch):
    """The seeded clinics, a draft letterhead only Clinic A has, and one signed-in client per doctor."""
    monkeypatch.setenv(admin_demo.DEMO_ENV, "1")
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(UPLOAD_PAD))
    monkeypatch.setenv("STUB_TRANSCRIPT", "paracetamol 650 mg twice daily")
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, stt_chain=("stub",),
                      stt_use_hints=False, stt_trim_silence=False)
    renders = []
    fake = R.ChromiumPoolRenderer(lambda: (_Browser(renders), lambda: None))
    monkeypatch.setattr(R, "get_renderer", lambda: fake)     # A7: the real worker thread, a fake browser
    seeded = admin_demo.seed_demo()
    with closing(dbmod.get_conn(clinic_dir(A) / "app.db")) as conn:
        tdb.create_template_draft(conn, admin_demo.rao_pad())   # template 2: an id only Clinic A has
    app = create_app()
    try:
        with ExitStack() as stack:
            clients = {}
            for who in ("rao", "mehta", "iyer"):
                client = stack.enter_context(TestClient(app, follow_redirects=False))
                r = login(client, f"dr.{who}")
                assert r.status_code == 200 and r.json()["must_change_password"] is False, r.text
                clients[who] = client
            for slug, who in ((A, "rao_admin"), (B, "iyer_admin")):       # the team actions are admin only; the seeded doctors are doctors
                clients[who] = stack.enter_context(admin_client(app, slug, "adm." + slug))
            yield SimpleNamespace(root=multi, seeded=seeded, app=app, renders=renders, **clients)
    finally:
        fake.close()


def login(client, username, password=None):
    secret = admin_demo.doctor(username)["password"] if password is None else password
    return client.post("/api/v1/auth/login", json={"username": username, "password": secret}, headers=H)


@contextmanager
def admin_client(app, slug, username):
    """A clinic admin (created here, so the seeded doctors stay plain doctors) signed in on ``app``."""
    uid, _ = accounts.create_user(slug, username, role="admin", password="a-long-password-1")
    sql(slug, "UPDATE users SET must_change_password = 0 WHERE id = ?", uid)
    with TestClient(app, follow_redirects=False) as client:
        assert login(client, username, "a-long-password-1").status_code == 200
        yield client


def user_id(world, username):
    return world.seeded[admin_demo.doctor(username)["clinic"]]["users"][username]


def sql(slug, query, *args):
    """One statement on a clinic file, opened by path (setup and inspection only; never inside a spy window)."""
    with closing(dbmod.get_conn(clinic_dir(slug) / "app.db")) as conn:
        rows = conn.execute(query, args).fetchall()
        conn.commit()
    return rows


def fingerprint(slug):
    """Every row of the clinic's data tables plus its file names and content hashes: equal before and after means untouched."""
    rows = {t: [tuple(r) for r in sql(slug, f"SELECT * FROM {t} ORDER BY rowid")] for t in TABLES}
    root = clinic_dir(slug)
    files = sorted((str(p.relative_to(root)), hashlib.sha256(p.read_bytes()).hexdigest())
                   for p in root.rglob("*") if p.is_file() and not p.name.startswith("app.db"))
    return rows, files


def a_only_id(table):
    """The largest id Clinic A has in ``table`` that Clinic B does not."""
    mine = {r[0] for r in sql(A, f"SELECT id FROM {table}")}
    theirs = {r[0] for r in sql(B, f"SELECT id FROM {table}")}
    only = sorted(mine - theirs)
    assert only, f"the seeded world gives clinic A no {table} id that clinic B lacks"
    return only[-1]


def leaks(text, markers):
    return [m for m in markers if m in text]


def pdf_text(response):
    return response.content.decode("utf-8", "replace")


def reprint(client, slug, document_id):
    """Drop the stored PDF so the next GET renders now (today's letterhead rules), then return the printed text."""
    sql(slug, "UPDATE documents SET pdf_path = NULL WHERE id = ?", document_id)
    r = client.get(f"/api/v1/documents/{document_id}/pdf")
    assert r.status_code == 200, r.text
    return pdf_text(r)


def save_body(patient, op="", document_id=None, medicine="Paracetamol"):
    body = {"structured": {"patientName": patient, "ageSex": "40 / M", "opNo": op,
                           "rx": [{"form": "Tab.", "name": medicine, "status": "verified"}]},
            "confirmed_rows": []}
    if document_id is not None:
        body["document_id"] = document_id
    return body


def save(client, patient, op=""):
    r = client.post("/api/v1/documents", json=save_body(patient, op), headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def upload(client):
    return client.post("/api/v1/templates", files={"image": ("pad.jpg", make_jpeg(), "image/jpeg")}, headers=H)


@contextmanager
def opened_files(monkeypatch):
    """Record (thread name, path) for every sqlite3.connect, from any thread, while the block runs."""
    seen, real = [], sqlite3.connect

    def spy(database, *args, **kwargs):
        seen.append((threading.current_thread().name, str(database)))
        return real(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", spy)
    try:
        yield seen
    finally:
        monkeypatch.setattr(sqlite3, "connect", real)


# --- interfaces assumed from M3, M4 and M5: one helper each (the plan's Assumptions table) ----------------------

def owner_refusal(author_name):                                             # A2: doctor name, else display name
    return {"error": f"This prescription belongs to {author_name}. You can view and reprint it."}


def correct_body(document_id, patient):                                     # A3
    return {"transcript": "make paracetamol 650 mg", "current_form": save_body(patient)["structured"],
            "document_id": document_id}


def today(client, scope=None):                                              # A4
    r = client.get("/api/v1/encounters/today" + (f"?scope={scope}" if scope else ""))
    assert r.status_code == 200, r.text
    return r.json()


def hint_lookup():                                                          # A5
    return stt._doctor_terms()


def set_doctors(client, template_id, mode, ids=()):                         # A10
    return client.put(f"/api/v1/templates/{template_id}/doctors", json={"mode": mode, "ids": list(ids)}, headers=H)


def accept(client, template_id, scope="clinic"):                            # A11
    return client.post(f"/api/v1/templates/{template_id}/accept", json={"scope": scope}, headers=H)


def use_clinic_letterhead(client):                                          # A11
    return client.post("/api/v1/templates/deactivate", json={"scope": "mine"}, headers=H)


def doctor_warning(view, text) -> bool:                                     # A12
    for w in view.get("warnings") or []:
        if text in json.dumps(w, ensure_ascii=False):
            return True
        if isinstance(w, dict) and w.get("section") in ("header", "footer") and isinstance(w.get("index"), int):
            blocks = view.get("layout", {}).get(w["section"], [])
            if 0 <= w["index"] < len(blocks) and blocks[w["index"]].get("text") == text:
                return True
    return False


def disable_user(client, uid):                                              # A14
    return client.post(f"/api/v1/users/{uid}/disable", headers=H)


def enable_user(client, uid):                                               # A14
    return client.post(f"/api/v1/users/{uid}/enable", headers=H)


def reset_user(client, uid):                                                # A14
    return client.post(f"/api/v1/users/{uid}/reset-password", headers=H)
