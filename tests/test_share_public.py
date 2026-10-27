"""Plan FB-D Task 4: the public download route, its rate limit, the one expired page and the log masking."""
import logging
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation.api import share as share_api
from doctor_dictation.api import share_public
from template_fixtures import tclient  # noqa: F401

SAVE = {"structured": {"patientName": "Anita", "opNo": "OP-1", "rx": [{"name": "Tamsulosin", "status": "verified"}]},
        "confirmed_rows": []}
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _fresh_window():
    share_public._hits.clear()
    yield
    share_public._hits.clear()


def _capture(monkeypatch):
    count = {"n": 0}

    def fake(structured, meta, out_path, layout=None):
        count["n"] += 1
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-1.4 fake save-" + str(count["n"]).encode())
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)


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


def _save(client, op="OP-1"):
    body = {**SAVE, "structured": {**SAVE["structured"], "opNo": op}}
    doc = client.post("/api/v1/documents", json=body).json()
    row = _rows("SELECT token FROM share_links WHERE encounter_id = ?", (doc["encounter_id"],))[0]
    return doc, row["token"]


def test_a_live_link_serves_exactly_its_own_stored_pdf(tclient, monkeypatch):
    _capture(monkeypatch)
    (d1, t1), (d2, t2) = _save(tclient, "OP-1"), _save(tclient, "OP-2")
    for doc, tok in ((d1, t1), (d2, t2)):
        stored = _rows("SELECT pdf_path FROM documents WHERE id = ?", (doc["document_id"],))[0]["pdf_path"]
        r = tclient.get(f"/s/local/{tok}")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content == Path(stored).read_bytes()
        assert r.headers["cache-control"] == "no-store"
        assert r.headers["x-robots-tag"] == "noindex"
        assert r.headers["referrer-policy"] == "no-referrer"
        assert "prescription.pdf" in r.headers["content-disposition"]
        assert "inline" in r.headers["content-disposition"]
    assert t1 != t2


def test_every_miss_gets_the_same_expired_page(tclient, monkeypatch):
    _capture(monkeypatch)
    _, live = _save(tclient, "OP-1")
    doc, expired = _save(tclient, "OP-2")
    _, revoked = _save(tclient, "OP-3")
    revoked_doc = _rows("SELECT d.id FROM documents d JOIN share_links s ON s.encounter_id = d.encounter_id WHERE s.token = ?",
                        (revoked,))[0]["id"]
    assert tclient.post(f"/api/v1/documents/{revoked_doc}/share/revoke").status_code == 200
    later = share_api._now() + timedelta(days=8)
    paths = {
        "revoked": f"/s/local/{revoked}",
        "unknown": "/s/local/" + "a" * 22,
        "short": "/s/local/short",
        "long": "/s/local/" + "a" * 23,
        "wrong slug": f"/s/rao/{live}",
    }
    bodies = set()
    for name, path in paths.items():
        r = tclient.get(path)
        assert r.status_code == 404, name
        bodies.add(r.text)
    monkeypatch.setattr(share_api, "_now", lambda: later)
    r = tclient.get(f"/s/local/{expired}")
    assert r.status_code == 404
    bodies.add(r.text)
    assert len(bodies) == 1
    assert "This link has expired" in r.text and "ask the clinic" in r.text


def test_a_link_without_a_stored_pdf_or_with_a_path_outside_the_pdf_folder_is_expired(tclient, monkeypatch, tmp_path):
    _capture(monkeypatch)
    doc, tok = _save(tclient)
    ok = tclient.get(f"/s/local/{tok}")
    assert ok.status_code == 200
    _write("UPDATE documents SET pdf_path = NULL WHERE id = ?", (doc["document_id"],))
    miss = tclient.get(f"/s/local/{tok}")
    assert miss.status_code == 404 and "This link has expired" in miss.text
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-1.4 secret")
    _write("UPDATE documents SET pdf_path = ? WHERE id = ?", (str(outside), doc["document_id"]))
    miss = tclient.get(f"/s/local/{tok}")
    assert miss.status_code == 404 and b"secret" not in miss.content


def test_the_rate_limit_answers_429_before_any_database_is_opened(tclient, monkeypatch):
    _capture(monkeypatch)
    _, tok = _save(tclient)
    monkeypatch.setattr(share_public, "LIMIT", 3)
    share_public._hits.clear()
    for _ in range(3):
        assert tclient.get(f"/s/local/{tok}").status_code == 200
    opened = []
    real = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: opened.append(a) or real(*a, **k))
    r = tclient.get(f"/s/local/{tok}")
    assert r.status_code == 429 and "Too many requests" in r.text
    assert opened == []


def test_opening_a_link_logs_no_patient_detail_and_no_token(tclient, monkeypatch, caplog):
    _capture(monkeypatch)
    _, tok = _save(tclient)
    with caplog.at_level(logging.INFO):
        assert tclient.get(f"/s/local/{tok}").status_code == 200
    text = "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("doctor_dictation"))   # httpx is the test client, not the app
    assert "share link opened" in text
    for forbidden in ("Anita", "OP-1", tok):
        assert forbidden not in text
    audit = _rows("SELECT * FROM audit_log WHERE action = 'share.open'")
    assert len(audit) == 1
    row = audit[0]
    assert (row["entity"], row["actor"], row["detail"], row["ip"]) == ("share_link", "public", None, None)
    rec = logging.LogRecord("uvicorn.access", 20, "", 0, '%s - "%s %s HTTP/%s" %d',
                            ("1.2.3.4:5", "GET", f"/s/local/{tok}", "1.1", 200), None)
    assert share_public.MASK.filter(rec)
    assert tok not in rec.getMessage() and "/s/local/-" in rec.getMessage()


def test_the_proxy_log_masks_share_tokens_and_the_env_example_names_the_base_url():
    assert "request>uri regexp" in (ROOT / "Caddyfile").read_text()
    assert "PUBLIC_BASE_URL=" in (ROOT / ".env.production.example").read_text()


def test_multi_clinic_unknown_slugs_create_nothing(multi):
    from fastapi.testclient import TestClient
    from doctor_dictation.api.app import create_app
    token = "a" * 22
    with TestClient(create_app()) as c:
        before = sorted(p.name for p in multi.rglob("*"))
        for slug in ("nope", "a", "RAO", "x" * 40):
            r = c.get(f"/s/{slug}/{token}")
            assert r.status_code == 404 and "This link has expired" in r.text
        assert sorted(p.name for p in multi.rglob("*")) == before


def test_only_the_exact_share_link_shape_is_public():
    from doctor_dictation.api.session import is_public
    assert is_public("/s/local/" + "a" * 22)
    for path in ("/s", "/s/", "/sx/a/b", "/s/a/../../app.js", "/s/a/b/c", "/s/a/", "/s/a/b.js", "/s//b"):
        assert not is_public(path), path


def test_a_traversal_under_the_share_prefix_does_not_reach_the_static_files_without_a_cookie(multi):
    from fastapi.testclient import TestClient
    from doctor_dictation.api.app import create_app
    with TestClient(create_app(), follow_redirects=False) as c:
        for path in ("/s/x/../../app.js", "/s/x/../../index.html", "/s/x/%2e%2e/%2e%2e/app.js", "/s/x/../../"):
            assert c.get(path).status_code in (303, 404, 401), path
        assert c.get("/s/x/%2e%2e/%2e%2e/app.js").status_code != 200


def test_a_database_error_on_lookup_is_the_expired_page(tclient, monkeypatch):
    _capture(monkeypatch)
    _, tok = _save(tclient)

    def boom(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(share_public.dbmod, "get_conn", boom)
    r = tclient.get(f"/s/local/{tok}")
    assert r.status_code == 404 and "This link has expired" in r.text
    assert r.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("exc", [OSError("disk gone"), ValueError("bad path")])
def test_an_unreadable_file_or_value_on_lookup_is_the_expired_page(tclient, monkeypatch, exc):
    _capture(monkeypatch)
    _, tok = _save(tclient)

    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(share_public, "_find_pdf", boom)
    r = tclient.get(f"/s/local/{tok}")
    assert r.status_code == 404 and "This link has expired" in r.text


def test_the_rate_limiter_has_a_real_docstring():
    assert share_public.allow.__doc__ and "Sliding window" in share_public.allow.__doc__
