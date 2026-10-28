"""Plan FB-D Task 3: the save path attaches the private link; the doctor's share endpoints, policy and base URL."""
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation import policy
from doctor_dictation.api import share as share_api
from doctor_dictation.api import visit
from doctor_dictation.config import build_settings
from doctor_dictation.db import share as sdb
from doctor_dictation.pdf import PdfUnavailable
from isolation_fixtures import world  # noqa: F401
from template_fixtures import tclient  # noqa: F401

SAVE = {"structured": {"patientName": "Anita", "opNo": "OP-1", "rx": [{"name": "Tamsulosin", "status": "verified"}]},
        "confirmed_rows": []}
T0 = datetime(2026, 10, 26, 4, 0, tzinfo=timezone.utc)


def _capture(monkeypatch, fail=False):
    seen = {"metas": []}

    def fake(structured, meta, out_path, layout=None):
        seen["meta"] = meta
        seen["metas"].append(meta)
        if fail:
            raise PdfUnavailable("no chromium")
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-1.4 fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)
    return seen


def _rows(sql, params=()):
    conn = dbmod.get_conn()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _write(sql, params=()):
    conn = dbmod.get_conn()
    conn.execute(sql, params)
    conn.commit()
    conn.close()


def test_the_first_save_renders_the_pdf_with_its_link(tclient, monkeypatch):
    seen = _capture(monkeypatch)
    monkeypatch.setattr(share_api, "_now", lambda: T0)
    r = tclient.post("/api/v1/documents", json=SAVE)
    assert r.status_code == 200
    assert set(r.json()) == {"patient_id", "encounter_id", "document_id", "op_no", "visit_date"}
    share = seen["meta"]["share"]
    assert re.fullmatch(r"http://testserver/s/local/[A-Za-z0-9_-]{22}", share["url"])
    assert share["until"] == visit.date_text(visit.to_clinic(T0 + sdb.TTL).date())
    assert "Anita" not in share["url"]


def test_a_re_save_keeps_the_link_and_moves_the_expiry(tclient, monkeypatch):
    seen = _capture(monkeypatch)
    monkeypatch.setattr(share_api, "_now", lambda: T0)
    first = tclient.post("/api/v1/documents", json=SAVE).json()
    url = seen["meta"]["share"]["url"]
    monkeypatch.setattr(share_api, "_now", lambda: T0 + timedelta(days=2))
    assert tclient.post("/api/v1/documents", json={**SAVE, "document_id": first["document_id"]}).status_code == 200
    assert seen["meta"]["share"]["url"] == url
    assert _rows("SELECT expires_at FROM share_links")[0]["expires_at"] == sdb.iso(T0 + timedelta(days=9))


def test_a_failed_render_still_saves_and_a_later_print_carries_the_live_link(tclient, monkeypatch):
    _capture(monkeypatch, fail=True)
    monkeypatch.setattr(share_api, "_now", lambda: T0)
    r = tclient.post("/api/v1/documents", json=SAVE)
    assert r.status_code == 200
    assert len(_rows("SELECT * FROM share_links")) == 1
    url = _rows("SELECT token FROM share_links")[0]["token"]
    seen = _capture(monkeypatch)
    doc_id = r.json()["document_id"]
    assert tclient.get(f"/api/v1/documents/{doc_id}/pdf").status_code == 200
    assert seen["meta"]["share"]["url"].endswith(f"/s/local/{url}")
    _write("UPDATE documents SET pdf_path = NULL")
    monkeypatch.setattr(share_api, "_now", lambda: T0 + timedelta(days=8))
    assert tclient.get(f"/api/v1/documents/{doc_id}/pdf").status_code == 200
    assert "share" not in seen["meta"]


def test_the_share_endpoint_answers_for_a_linked_prescription_only(tclient, monkeypatch):
    _capture(monkeypatch)
    doc_id = tclient.post("/api/v1/documents", json=SAVE).json()["document_id"]
    body = tclient.get(f"/api/v1/documents/{doc_id}/share").json()
    assert body["active"] is True and body["revoked"] is False and body["can_revoke"] is True
    assert body["qr"].startswith("data:image/svg+xml")
    assert body["subject"] == "Your prescription"
    assert body["message"] == f"Your prescription is ready to download (valid until {body['valid_until']}): {body['url']}"
    assert {"url", "expires_at", "valid_until"} <= set(body)
    assert tclient.post(f"/api/v1/documents/{doc_id}/share/revoke").json() == {"revoked": True}
    assert tclient.post(f"/api/v1/documents/{doc_id}/share/revoke").status_code == 404
    after = tclient.get(f"/api/v1/documents/{doc_id}/share").json()
    assert after["active"] is False and after["revoked"] is True
    _write("DELETE FROM share_links")
    gone = tclient.get(f"/api/v1/documents/{doc_id}/share")
    assert gone.status_code == 404 and gone.json() == {"error": "no share link for this prescription"}
    missing = tclient.get("/api/v1/documents/999/share")
    assert missing.status_code == 404 and missing.json() == {"error": "document_id 999 not found"}


def test_the_public_base_url_setting_wins_and_a_bad_value_is_ignored(tclient, monkeypatch):
    from doctor_dictation.config import override_settings
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://gsr.lightday.online/")
    assert build_settings().public_base_url == "https://gsr.lightday.online"
    monkeypatch.setenv("PUBLIC_BASE_URL", "gsr.lightday.online")
    assert build_settings().public_base_url == ""
    seen = _capture(monkeypatch)
    override_settings(monkeypatch, public_base_url="https://gsr.lightday.online")
    assert tclient.post("/api/v1/documents", json=SAVE).status_code == 200
    assert seen["meta"]["share"]["url"].startswith("https://gsr.lightday.online/s/local/")


def test_a_link_store_failure_never_blocks_the_save(tclient, monkeypatch):
    seen = _capture(monkeypatch)

    def boom(*a, **k):
        raise sqlite3.OperationalError("locked")
    monkeypatch.setattr("doctor_dictation.db.share.ensure_link", boom)
    r = tclient.post("/api/v1/documents", json=SAVE)
    assert r.status_code == 200
    assert _rows("SELECT pdf_path FROM documents")[0]["pdf_path"]
    assert "share" not in seen["meta"]


def test_only_the_author_or_an_admin_may_revoke():
    doctor = SimpleNamespace(user_id=1, role="doctor")
    assert policy.can(doctor, "share.revoke", {"author_id": 1}) is True
    assert policy.can(SimpleNamespace(user_id=2, role="doctor"), "share.revoke", {"author_id": 1}) is False
    assert policy.can(SimpleNamespace(user_id=2, role="admin"), "share.revoke", {"author_id": 1}) is True
    assert policy.can(doctor, "share.revoke", {"author_id": None}) is True


def test_a_naive_datetime_is_refused():
    with pytest.raises(ValueError):
        sdb.iso(datetime(2026, 10, 26, 4, 0))


def test_a_concurrent_first_save_integrity_error_leaves_no_qr_and_still_saves(tclient, monkeypatch):
    seen = _capture(monkeypatch)

    def clash(*a, **k):
        raise sqlite3.IntegrityError("UNIQUE constraint failed: share_links.encounter_id")
    monkeypatch.setattr("doctor_dictation.db.share.ensure_link", clash)
    assert tclient.post("/api/v1/documents", json=SAVE).status_code == 200
    assert "share" not in seen["meta"]


@pytest.mark.parametrize("raw", ["https://a.example/path", "https://a.example?x=1", "https://a.example#f", "https://a.example /",
                                 "https://", "ftp://a.example", "javascript:alert(1)", "https://a.ex ample"])
def test_a_public_base_url_that_is_not_a_bare_origin_is_ignored(monkeypatch, raw):
    monkeypatch.setenv("PUBLIC_BASE_URL", raw)
    assert build_settings().public_base_url == ""


def test_a_bare_origin_with_a_port_is_kept(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", " http://localhost:8000/ ")
    assert build_settings().public_base_url == "http://localhost:8000"


def test_any_link_failure_never_becomes_a_500(tclient, monkeypatch):
    seen = _capture(monkeypatch)
    monkeypatch.setattr("doctor_dictation.db.share.ensure_link", lambda *a, **k: 1 / 0)
    assert tclient.post("/api/v1/documents", json=SAVE).status_code == 200
    assert "share" not in seen["meta"]


def test_revoke_is_author_or_admin_in_multi_clinic(world):
    from isolation_fixtures import H, user_id  # noqa: F401
    body = world.rao.get("/api/v1/documents/1").json()
    assert body["author"]["user_id"] == user_id(world, "dr.rao")
    denied = world.mehta.post("/api/v1/documents/1/share/revoke", headers=H)
    assert denied.status_code == 403 and denied.json() == {
        "error": f"This prescription belongs to {body['author']['name']}. You can view and reprint it."}
    assert world.rao_admin.post("/api/v1/documents/1/share/revoke", headers=H).json() == {"revoked": True}


def test_print_after_a_revoke_renders_without_the_dead_qr(tclient, monkeypatch):
    seen = _capture(monkeypatch)
    doc_id = tclient.post("/api/v1/documents", json=SAVE).json()["document_id"]
    assert "share" in seen["meta"]
    assert _rows("SELECT pdf_path FROM documents")[0]["pdf_path"]
    assert tclient.post(f"/api/v1/documents/{doc_id}/share/revoke").json() == {"revoked": True}
    assert _rows("SELECT pdf_path FROM documents")[0]["pdf_path"] is None
    renders = len(seen["metas"])
    r = tclient.get(f"/api/v1/documents/{doc_id}/pdf")
    assert r.status_code == 200 and r.content != b""
    assert len(seen["metas"]) == renders + 1 and "share" not in seen["meta"]


def test_the_share_json_says_whether_a_new_link_can_still_be_issued(tclient, monkeypatch):
    _capture(monkeypatch)
    doc_id = tclient.post("/api/v1/documents", json=SAVE).json()["document_id"]
    assert tclient.get(f"/api/v1/documents/{doc_id}/share").json()["renewable"] is True
    _write("UPDATE documents SET created_at = '2020-01-01T00:00:00+00:00'")
    assert tclient.get(f"/api/v1/documents/{doc_id}/share").json()["renewable"] is False


def test_a_rejected_public_base_url_is_logged_without_its_path(monkeypatch, caplog):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://clinic.example/secret/path?t=1")
    with caplog.at_level("WARNING", logger="doctor_dictation.config"):
        assert build_settings().public_base_url == ""
    assert "PUBLIC_BASE_URL ignored" in caplog.text and "https://clinic.example" in caplog.text
    assert "secret" not in caplog.text and "t=1" not in caplog.text
    caplog.clear()
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://clinic.example")
    with caplog.at_level("WARNING", logger="doctor_dictation.config"):
        build_settings()
    assert "PUBLIC_BASE_URL" not in caplog.text
