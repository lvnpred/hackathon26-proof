"""GET /api/v1/documents/{id}/pdf: serve the stored PDF, else render on demand."""
from pathlib import Path

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation.pdf import PdfUnavailable
from template_fixtures import make_jpeg, tclient  # noqa: F401

SAVE = {"structured": {"patientName": "Anita", "opNo": "OP-1", "rx": [{"name": "Tamsulosin", "status": "verified"}]},
        "confirmed_rows": []}


def _fake(monkeypatch, payload=b"%PDF-fake", unavailable=False):
    seen = {"calls": [], "meta": [], "layouts": []}

    def fake(structured, meta, out_path, layout=None):
        seen["calls"].append(str(out_path))
        seen["meta"].append(meta)
        seen["layouts"].append(layout)
        if unavailable:
            raise PdfUnavailable("no chromium")
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(payload)
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)
    return seen


def _save(c, body=SAVE):
    r = c.post("/api/v1/documents", json=body)
    assert r.status_code == 200
    return r.json()["document_id"]


def _row(doc_id):
    conn = dbmod.get_conn()
    try:
        return dict(dbmod.get_document(conn, doc_id))
    finally:
        conn.close()


def _set_path(doc_id, value):
    conn = dbmod.get_conn()
    conn.execute("UPDATE documents SET pdf_path = ? WHERE id = ?", (value, doc_id))
    conn.commit()
    conn.close()


def test_unknown_document_is_404(tclient):
    r = tclient.get("/api/v1/documents/999/pdf")
    assert r.status_code == 404 and r.json() == {"error": "document_id 999 not found"}


def test_serves_the_stored_file_with_headers(tclient, monkeypatch):
    seen = _fake(monkeypatch)
    doc = _save(tclient)
    r = tclient.get(f"/api/v1/documents/{doc}/pdf")
    assert r.status_code == 200 and r.content == b"%PDF-fake"
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == f'inline; filename="prescription-{doc}.pdf"'
    assert r.headers["cache-control"] == "no-store"
    assert len(seen["calls"]) == 1  # served, not re-rendered


def test_path_outside_pdf_dir_is_never_served(tclient, monkeypatch, tmp_path):
    seen = _fake(monkeypatch, payload=b"%PDF-regen")
    doc = _save(tclient)
    secret = tmp_path / "secret.pdf"
    secret.write_bytes(b"TOP-SECRET")
    _set_path(doc, str(secret))
    r = tclient.get(f"/api/v1/documents/{doc}/pdf")
    assert r.status_code == 200 and r.content == b"%PDF-regen" and b"TOP-SECRET" not in r.content
    assert len(seen["calls"]) == 2
    assert Path(_row(doc)["pdf_path"]).resolve().is_relative_to(dbmod.pdf_dir().resolve())
    assert secret.read_bytes() == b"TOP-SECRET"


def test_dotdot_path_escaping_pdf_dir_is_not_served(tclient, monkeypatch, tmp_path):
    _fake(monkeypatch, payload=b"%PDF-regen")
    doc = _save(tclient)
    (tmp_path / "x.pdf").write_bytes(b"TOP-SECRET")
    _set_path(doc, str(dbmod.pdf_dir() / ".." / "x.pdf"))
    r = tclient.get(f"/api/v1/documents/{doc}/pdf")
    assert r.content == b"%PDF-regen"


@pytest.mark.parametrize("mode", ["null", "missing"])
def test_missing_pdf_renders_on_demand_then_serves_stored(tclient, monkeypatch, mode):
    seen = _fake(monkeypatch, payload=b"%PDF-ondemand")
    doc = _save(tclient)
    if mode == "null":
        _set_path(doc, None)
    else:
        Path(_row(doc)["pdf_path"]).unlink()
    n = len(seen["calls"])
    r = tclient.get(f"/api/v1/documents/{doc}/pdf")
    assert r.status_code == 200 and r.content == b"%PDF-ondemand"
    assert len(seen["calls"]) == n + 1
    stored = _row(doc)["pdf_path"]
    assert stored and Path(stored).read_bytes() == b"%PDF-ondemand"
    assert tclient.get(f"/api/v1/documents/{doc}/pdf").content == b"%PDF-ondemand"
    assert len(seen["calls"]) == n + 1  # second GET: no re-render


def test_on_demand_meta_matches_the_save_path(tclient, monkeypatch):
    seen = _fake(monkeypatch)
    doc = _save(tclient)
    _set_path(doc, None)
    tclient.get(f"/api/v1/documents/{doc}/pdf")
    saved, regen = seen["meta"][0], seen["meta"][1]
    assert regen["opNo"] == "OP-1" and regen["patientName"] == "Anita"
    assert regen["date"] == saved["date"] and regen["profile"] == saved["profile"]


def test_renderer_unavailable_is_503_json(tclient, monkeypatch):
    _fake(monkeypatch)
    doc = _save(tclient)
    _set_path(doc, None)
    _fake(monkeypatch, unavailable=True)
    r = tclient.get(f"/api/v1/documents/{doc}/pdf")
    assert r.status_code == 503
    assert r.json() == {"error": "PDF rendering is not available on this server", "fallback": "browser"}
    assert _row(doc)["pdf_path"] is None


def test_renderer_crash_is_503_not_500(tclient, monkeypatch):
    _fake(monkeypatch)
    doc = _save(tclient)
    _set_path(doc, None)

    def boom(*a, **k):
        raise RuntimeError("kaboom")
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", boom)
    r = tclient.get(f"/api/v1/documents/{doc}/pdf")
    assert r.status_code == 503 and r.json()["fallback"] == "browser" and "kaboom" not in r.text


def test_no_write_lock_held_while_rendering(tclient, monkeypatch):
    _fake(monkeypatch)
    doc = _save(tclient)
    _set_path(doc, None)
    probe = {}

    def fake(structured, meta, out_path, layout=None):
        c = dbmod.get_conn()
        try:
            c.execute("PRAGMA busy_timeout = 0")
            c.execute("BEGIN IMMEDIATE")  # would raise "database is locked" if a writer is open
            c.rollback()
            probe["ok"] = True
        finally:
            c.close()
        Path(out_path).write_bytes(b"%PDF-x")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)
    assert tclient.get(f"/api/v1/documents/{doc}/pdf").status_code == 200 and probe.get("ok")


def _accept(c):
    tid = c.post("/api/v1/templates", files={"image": ("p.jpg", make_jpeg(), "image/jpeg")}).json()["id"]
    assert c.post(f"/api/v1/templates/{tid}/accept").status_code == 200
    return tid


def test_on_demand_uses_active_template_layout_and_logo(tclient, monkeypatch):
    seen = _fake(monkeypatch)
    doc = _save(tclient)  # saved with the plain header
    assert seen["layouts"][0] is None
    _accept(tclient)
    _set_path(doc, None)
    assert tclient.get(f"/api/v1/documents/{doc}/pdf").status_code == 200
    assert seen["layouts"][1] is not None
    assert seen["meta"][1]["logo"].startswith("data:image/jpeg;base64,")


def test_on_demand_without_template_uses_profile_header(tclient, monkeypatch):
    seen = _fake(monkeypatch)
    doc = _save(tclient)
    _set_path(doc, None)
    tclient.get(f"/api/v1/documents/{doc}/pdf")
    assert seen["layouts"][1] is None and "logo" not in seen["meta"][1]


def test_resaved_document_serves_the_new_file(tclient, monkeypatch):
    _fake(monkeypatch, payload=b"%PDF-v1")
    doc = _save(tclient)
    assert tclient.get(f"/api/v1/documents/{doc}/pdf").content == b"%PDF-v1"
    _fake(monkeypatch, payload=b"%PDF-v2")
    assert tclient.post("/api/v1/documents", json={**SAVE, "document_id": doc}).status_code == 200
    assert tclient.get(f"/api/v1/documents/{doc}/pdf").content == b"%PDF-v2"


def test_real_chromium_save_then_get_pdf(tclient):
    pytest.importorskip("playwright.sync_api")
    r = tclient.post("/api/v1/documents", json=SAVE)
    assert r.status_code == 200
    doc = r.json()["document_id"]
    if not _row(doc)["pdf_path"]:
        pytest.skip("Chromium is not installed")
    g = tclient.get(f"/api/v1/documents/{doc}/pdf")
    assert g.status_code == 200 and g.content.startswith(b"%PDF")
    assert g.headers["content-type"] == "application/pdf"
