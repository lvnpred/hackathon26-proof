"""Gap Task 2: a reprint after the share link expires drops the dead QR instead of serving the stored PDF."""
import logging
import os
from datetime import datetime, timedelta, timezone

from doctor_dictation import db as dbmod
from doctor_dictation.api import share as share_api
from doctor_dictation.db import share as sdb
from template_fixtures import tclient  # noqa: F401
from test_share_save import SAVE, _capture, _rows, _write

T0 = datetime(2026, 10, 26, 4, 0, tzinfo=timezone.utc)


def _saved(tclient, monkeypatch):
    seen = _capture(monkeypatch)
    monkeypatch.setattr(share_api, "_now", lambda: T0)
    doc_id = tclient.post("/api/v1/documents", json=SAVE).json()["document_id"]
    return seen, doc_id


def test_an_expired_link_clears_the_stored_pdf_and_renders_without_a_qr(tclient, monkeypatch):
    seen, doc_id = _saved(tclient, monkeypatch)
    assert "share" in seen["meta"]
    monkeypatch.setattr(share_api, "_now", lambda: T0 + sdb.TTL + timedelta(seconds=1))
    renders = len(seen["metas"])
    r = tclient.get(f"/api/v1/documents/{doc_id}/pdf")
    assert r.status_code == 200
    assert len(seen["metas"]) == renders + 1 and "share" not in seen["meta"]


def test_an_expired_link_sets_the_document_pdf_path_to_null_before_the_render(tclient, monkeypatch):
    seen, doc_id = _saved(tclient, monkeypatch)
    monkeypatch.setattr(share_api, "_now", lambda: T0 + sdb.TTL + timedelta(seconds=1))
    paths = []
    orig = dbmod.set_document_pdf_path
    monkeypatch.setattr(dbmod, "set_document_pdf_path", lambda c, d, p: (paths.append(p), orig(c, d, p))[1])
    tclient.get(f"/api/v1/documents/{doc_id}/pdf")
    assert paths[0] is None


def test_a_live_link_serves_the_stored_pdf(tclient, monkeypatch):
    seen, doc_id = _saved(tclient, monkeypatch)
    monkeypatch.setattr(share_api, "_now", lambda: T0 + timedelta(days=1))
    renders = len(seen["metas"])
    r = tclient.get(f"/api/v1/documents/{doc_id}/pdf")
    assert r.status_code == 200 and r.content == b"%PDF-1.4 fake"
    assert len(seen["metas"]) == renders
    assert _rows("SELECT pdf_path FROM documents")[0]["pdf_path"]


def test_no_link_row_serves_the_stored_pdf(tclient, monkeypatch):
    seen, doc_id = _saved(tclient, monkeypatch)
    _write("DELETE FROM share_links")
    monkeypatch.setattr(share_api, "_now", lambda: T0 + timedelta(days=30))
    renders = len(seen["metas"])
    r = tclient.get(f"/api/v1/documents/{doc_id}/pdf")
    assert r.status_code == 200 and r.content == b"%PDF-1.4 fake"
    assert len(seen["metas"]) == renders


def test_a_lookup_error_serves_the_stored_pdf_and_logs_only_the_type(tclient, monkeypatch, caplog):
    seen, doc_id = _saved(tclient, monkeypatch)

    def boom(conn, encounter_id):
        raise RuntimeError("secret-token-xyz Anita")
    monkeypatch.setattr(sdb, "link_for_encounter", boom)
    renders = len(seen["metas"])
    with caplog.at_level(logging.WARNING):
        r = tclient.get(f"/api/v1/documents/{doc_id}/pdf")
    assert r.status_code == 200 and r.content == b"%PDF-1.4 fake"
    assert len(seen["metas"]) == renders
    assert "RuntimeError" in caplog.text
    assert "secret-token-xyz" not in caplog.text and "Anita" not in caplog.text


def _pdf_renders(tclient, doc_id, seen, times):
    renders = len(seen["metas"])
    for _ in range(times):
        assert tclient.get(f"/api/v1/documents/{doc_id}/pdf").status_code == 200
    return len(seen["metas"]) - renders


def test_reprints_after_expiry_render_once_then_serve_the_qr_free_pdf(tclient, monkeypatch):
    # the stored file's age is real file time, so the clock here is real time moved back past the TTL
    now = datetime.now(timezone.utc)
    saved_at = now - sdb.TTL - timedelta(days=1)
    seen = _capture(monkeypatch)
    monkeypatch.setattr(share_api, "_now", lambda: saved_at)
    doc_id = tclient.post("/api/v1/documents", json=SAVE).json()["document_id"]
    stored = _rows("SELECT pdf_path FROM documents")[0]["pdf_path"]
    os.utime(stored, (saved_at.timestamp(), saved_at.timestamp()))    # written at save time, before the link died
    monkeypatch.setattr(share_api, "_now", lambda: now)
    assert _pdf_renders(tclient, doc_id, seen, 3) == 1
    assert "share" not in seen["meta"]


def test_reprints_after_a_revoke_render_once(tclient, monkeypatch):
    now = datetime.now(timezone.utc)
    seen = _capture(monkeypatch)
    monkeypatch.setattr(share_api, "_now", lambda: now - timedelta(hours=1))
    doc_id = tclient.post("/api/v1/documents", json=SAVE).json()["document_id"]
    monkeypatch.setattr(share_api, "_now", lambda: now - timedelta(minutes=1))
    assert tclient.post(f"/api/v1/documents/{doc_id}/share/revoke").status_code == 200
    assert _rows("SELECT pdf_path FROM documents")[0]["pdf_path"] is None
    monkeypatch.setattr(share_api, "_now", lambda: now)
    assert _pdf_renders(tclient, doc_id, seen, 2) == 1
    assert "share" not in seen["meta"]
