from pathlib import Path

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation.pdf import PdfUnavailable
from template_fixtures import make_jpeg, tclient  # noqa: F401

SAVE = {"structured": {"patientName": "Anita", "opNo": "OP-1", "rx": [{"name": "Tamsulosin", "status": "verified"}]},
        "confirmed_rows": []}


def _capture(monkeypatch, fail_with_layout=False):
    seen = {"calls": []}

    def fake(structured, meta, out_path, layout=None):
        seen.update(meta=meta, layout=layout)
        seen["calls"].append(layout)
        if fail_with_layout and layout is not None:
            raise RuntimeError("layout render failed")
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-1.4 fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)
    return seen


def _accept(c):
    tid = c.post("/api/v1/templates", files={"image": ("p.jpg", make_jpeg(), "image/jpeg")}).json()["id"]
    assert c.post(f"/api/v1/templates/{tid}/accept").status_code == 200
    return tid


def _set_db(sql, params=()):
    conn = dbmod.get_conn()
    conn.execute(sql, params)
    conn.commit()
    conn.close()


def _doc_pdf(r):
    conn = dbmod.get_conn()
    try:
        return dbmod.get_document(conn, r.json()["document_id"])["pdf_path"]
    finally:
        conn.close()


def test_save_passes_active_layout_and_logo(tclient, monkeypatch):
    seen = _capture(monkeypatch)
    _accept(tclient)
    assert tclient.post("/api/v1/documents", json=SAVE).status_code == 200
    assert seen["layout"] is not None and seen["meta"]["logo"].startswith("data:image/jpeg;base64,")
    assert seen["meta"]["profile"]["clinic_name"] == "Meridian Clinic" and seen["meta"]["patientName"] == "Anita"


def test_save_without_active_template_uses_builtin_layout(tclient, monkeypatch):
    seen = _capture(monkeypatch)
    assert tclient.post("/api/v1/documents", json=SAVE).status_code == 200
    assert seen["layout"] is None


def test_save_falls_back_when_stored_layout_is_invalid(tclient, monkeypatch):
    seen = _capture(monkeypatch)
    tid = _accept(tclient)
    _set_db("UPDATE templates SET layout_json = '{\"body\": 5}' WHERE id = ?", (tid,))
    assert tclient.post("/api/v1/documents", json=SAVE).status_code == 200
    assert seen["layout"] is None


def test_save_falls_back_when_layout_json_is_corrupt(tclient, monkeypatch):
    seen = _capture(monkeypatch)
    tid = _accept(tclient)
    _set_db("UPDATE templates SET layout_json = 'not json{' WHERE id = ?", (tid,))
    r = tclient.post("/api/v1/documents", json=SAVE)
    assert r.status_code == 200 and seen["layout"] is None and _doc_pdf(r)


def test_save_falls_back_when_layout_json_is_null(tclient, monkeypatch):
    seen = _capture(monkeypatch)
    tid = _accept(tclient)
    try:
        _set_db("UPDATE templates SET layout_json = NULL WHERE id = ?", (tid,))
    except Exception as e:
        pytest.skip(f"schema forbids NULL layout_json: {e}")
    r = tclient.post("/api/v1/documents", json=SAVE)
    assert r.status_code == 200 and seen["layout"] is None


def test_save_without_logo_file_still_renders_layout(tclient, monkeypatch):
    seen = _capture(monkeypatch)
    tid = _accept(tclient)
    _set_db("UPDATE templates SET logo_path = '/nonexistent/logo.jpg' WHERE id = ?", (tid,))
    r = tclient.post("/api/v1/documents", json=SAVE)
    assert r.status_code == 200 and seen["layout"] is not None
    assert not seen["meta"].get("logo") and _doc_pdf(r)


def test_save_retries_plain_header_when_layout_render_fails(tclient, monkeypatch):
    seen = _capture(monkeypatch, fail_with_layout=True)
    _accept(tclient)
    r = tclient.post("/api/v1/documents", json=SAVE)
    assert r.status_code == 200
    assert seen["calls"][0] is not None and seen["calls"][-1] is None
    assert _doc_pdf(r)


def test_save_ok_with_no_pdf_when_renderer_always_fails(tclient, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no chromium")
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", boom)
    _accept(tclient)
    r = tclient.post("/api/v1/documents", json=SAVE)
    assert r.status_code == 200 and _doc_pdf(r) is None


def test_save_ok_when_template_lookup_raises(tclient, monkeypatch):
    seen = _capture(monkeypatch)

    def boom(conn):
        raise RuntimeError("db unreadable")
    monkeypatch.setattr("doctor_dictation.templates.service.active_layout_for_save", boom)
    r = tclient.post("/api/v1/documents", json=SAVE)
    assert r.status_code == 200 and seen["layout"] is None and _doc_pdf(r)


def test_save_does_not_retry_when_renderer_unavailable(tclient, monkeypatch):
    calls = []

    def down(*a, **k):
        calls.append(k.get("layout"))
        raise PdfUnavailable("chromium down")
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", down)
    _accept(tclient)
    r = tclient.post("/api/v1/documents", json=SAVE)
    assert r.status_code == 200 and len(calls) == 1 and _doc_pdf(r) is None


def test_save_after_deactivate_route_uses_builtin_layout(tclient, monkeypatch):  # Review Focus 3, through the real routes
    seen = _capture(monkeypatch)
    _accept(tclient)
    assert tclient.post("/api/v1/documents", json={**SAVE, "transcript_sha256": "sha-a"}).status_code == 200
    assert seen["layout"] is not None
    assert tclient.post("/api/v1/templates/deactivate").json() == {"deactivated": True}
    r = tclient.post("/api/v1/documents", json={**SAVE, "transcript_sha256": "sha-b"})
    assert r.status_code == 200 and seen["layout"] is None and _doc_pdf(r)
