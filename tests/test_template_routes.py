import json
from pathlib import Path

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation.config import override_settings
from template_fixtures import GOOD_LAYOUT, PROFILE, make_jpeg, tclient  # noqa: F401

URL = "/api/v1/templates"


def _post(c, data=None, name="pad.jpg"):
    return c.post(URL, files={"image": (name, data or make_jpeg(), "image/jpeg")})


def _fake_render(monkeypatch, seen=None):
    def fake(structured, meta, out_path, layout=None):
        if seen is not None:
            seen.update(structured=structured, meta=meta, layout=layout)
        Path(out_path).write_bytes(b"%PDF-1.4 fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.templates.render_prescription", fake)


def test_post_201_shape(tclient):
    r = _post(tclient)
    body = r.json()
    assert r.status_code == 201 and body["status"] == "draft" and body["profile"] == PROFILE
    assert set(body) == {"id", "status", "layout", "profile"} and "profile" not in body["layout"]


def test_post_without_image_or_with_text_is_400(tclient):
    assert tclient.post(URL).status_code == 400
    assert _post(tclient, b"just words", "photo.jpg").status_code == 400


def test_post_too_large_is_413(tclient, monkeypatch):
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, template_max_image_bytes=100)
    assert _post(tclient).status_code == 413


def test_post_over_daily_limit_is_429(tclient, monkeypatch):
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, template_uploads_per_day=1)
    assert _post(tclient).status_code == 201
    assert _post(tclient).status_code == 429


def test_post_invalid_layout_is_502_and_nothing_stored(tclient, monkeypatch):
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps({"header": [], "footer": [], "body": {"top": 1, "bottom": 0}}))
    assert _post(tclient).status_code == 502
    assert tclient.get(URL + "/active").status_code == 404
    conn = dbmod.get_conn()
    assert conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0] == 0
    conn.close()


def test_post_without_llm_is_503(tclient, monkeypatch):
    override_settings(monkeypatch, llm_provider="openai", allow_stub_providers=False, openai_api_key="", deepseek_api_key="")
    assert _post(tclient).status_code == 503


def test_preview_pdf_renders_sample_with_draft_layout(tclient, monkeypatch):
    seen = {}
    _fake_render(monkeypatch, seen)
    tid = _post(tclient).json()["id"]
    r = tclient.get(f"{URL}/{tid}/preview.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert seen["layout"] is not None and seen["meta"]["profile"]["clinic_name"] == "Meridian Clinic"
    assert seen["structured"]["rx"] and seen["meta"]["logo"].startswith("data:image/jpeg;base64,")


def test_preview_missing_is_404_and_renderer_missing_is_503(tclient, monkeypatch):
    assert tclient.get(f"{URL}/999/preview.pdf").status_code == 404
    from doctor_dictation.pdf import PdfUnavailable

    def boom(*a, **k):
        raise PdfUnavailable("no chromium")
    monkeypatch.setattr("doctor_dictation.api.templates.render_prescription", boom)
    tid = _post(tclient).json()["id"]
    assert tclient.get(f"{URL}/{tid}/preview.pdf").status_code == 503


def test_put_edits_and_rejects(tclient):
    tid = _post(tclient).json()["id"]
    ok = tclient.put(f"{URL}/{tid}", json={"profile": {"phone": "111"}, "lines": [{"section": "header", "index": 2, "text": "Open daily"}]})
    assert ok.status_code == 200 and ok.json()["profile"]["phone"] == "111"
    assert tclient.put(f"{URL}/{tid}", json={"profile": {"ssn": "1"}, "lines": []}).status_code == 400
    assert tclient.put(f"{URL}/999", json={"profile": {}, "lines": []}).status_code == 404


def test_accept_then_active_and_profile_saved(tclient):
    assert tclient.get(URL + "/active").status_code == 404
    tid = _post(tclient).json()["id"]
    assert tclient.post(f"{URL}/{tid}/accept").status_code == 200
    act = tclient.get(URL + "/active")
    assert act.status_code == 200 and act.json()["id"] == tid and act.json()["status"] == "active"
    assert tclient.get("/api/v1/profile").json()["doctor_name"] == "Dr A. Rao"
    assert tclient.post(f"{URL}/{tid}/accept").status_code == 409
    assert tclient.put(f"{URL}/{tid}", json={"profile": {}, "lines": []}).status_code == 409
    assert tclient.post(f"{URL}/999/accept").status_code == 404


def test_accept_second_template_archives_first(tclient):
    a, b = (_post(tclient).json()["id"] for _ in range(2))
    tclient.post(f"{URL}/{a}/accept")
    tclient.post(f"{URL}/{b}/accept")
    assert tclient.get(URL + "/active").json()["id"] == b
    assert tclient.delete(f"{URL}/{a}").status_code == 409  # archived is not a draft


def test_delete_discards_draft(tclient):
    tid = _post(tclient).json()["id"]
    assert tclient.delete(f"{URL}/{tid}").status_code == 204
    assert tclient.delete(f"{URL}/{tid}").status_code == 404
    assert tclient.get(f"{URL}/{tid}/preview.pdf").status_code == 404


def test_every_action_writes_an_audit_row(tclient):
    a, b = (_post(tclient).json()["id"] for _ in range(2))
    tclient.post(f"{URL}/{a}/accept")
    tclient.delete(f"{URL}/{b}")
    conn = dbmod.get_conn()
    actions = [r[0] for r in conn.execute("SELECT action FROM audit_log ORDER BY id")]
    conn.close()
    assert actions == ["template_upload", "template_upload", "template_accept", "template_discard"]


def test_expired_drafts_purged_at_startup(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from doctor_dictation.api.app import create_app
    from doctor_dictation.db import templates as tdb
    monkeypatch.setenv("DB_PATH", str(tmp_path / "boot.db"))
    dbmod.init_db()
    conn = dbmod.get_conn()
    tid = tdb.create_template_draft(conn, GOOD_LAYOUT, created_at="2020-01-01T00:00:00Z")
    conn.close()
    with TestClient(create_app()):
        pass
    conn = dbmod.get_conn()
    assert tdb.get_template(conn, tid) is None
    conn.close()


def test_uploads_never_written_under_a_public_path(tclient):
    tid = _post(tclient).json()["id"]
    conn = dbmod.get_conn()
    logo = Path(conn.execute("SELECT logo_path FROM templates WHERE id = ?", (tid,)).fetchone()[0]).resolve()
    conn.close()
    frontend = Path(__file__).resolve().parents[1] / "frontend"
    assert frontend not in logo.parents and logo.parent.name == "templates"
    for name in (f"{tid}_logo.jpg", f"{tid}_original.jpg", f"templates/{tid}_logo.jpg"):
        assert tclient.get("/" + name).status_code == 404


@pytest.mark.parametrize("lines", [
    "x", ["x"], [None], [1], {"section": "header"},
    [{"section": "header", "index": True, "text": "a"}],
    [{"section": "header", "index": 2, "text": None}],
    [{"section": "header", "index": "2", "text": "a"}],
    [{"section": "header", "index": 2}],
])
def test_put_malformed_lines_is_400_not_500(tclient, lines):
    tid = _post(tclient).json()["id"]
    r = tclient.put(f"{URL}/{tid}", json={"profile": {}, "lines": lines})
    assert r.status_code == 400 and "error" in r.json()


@pytest.mark.parametrize("profile", ["x", ["a"], {"phone": None}, {"phone": 5}])
def test_put_malformed_profile_is_400_not_500(tclient, profile):
    tid = _post(tclient).json()["id"]
    assert tclient.put(f"{URL}/{tid}", json={"profile": profile, "lines": []}).status_code == 400


def test_expired_drafts_purged_on_every_templates_request(tclient):
    from doctor_dictation.db import templates as tdb
    conn = dbmod.get_conn()
    tid = tdb.create_template_draft(conn, GOOD_LAYOUT, created_at="2020-01-01T00:00:00Z")
    conn.close()
    assert tclient.get(URL + "/active").status_code == 404
    conn = dbmod.get_conn()
    assert tdb.get_template(conn, tid) is None
    conn.close()


def test_concurrent_previews_use_distinct_files_and_do_not_delete_each_other(tclient, monkeypatch):
    paths = []

    def fake(structured, meta, out_path, layout=None):
        paths.append(Path(out_path))
        Path(out_path).write_bytes(b"%PDF-1.4 fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.templates.render_prescription", fake)
    tid = _post(tclient).json()["id"]
    r1 = tclient.get(f"{URL}/{tid}/preview.pdf")
    r2 = tclient.get(f"{URL}/{tid}/preview.pdf")
    assert r1.status_code == r2.status_code == 200
    assert paths[0] != paths[1]
    assert not paths[0].exists() and not paths[1].exists()  # each request removed only its own file


def test_purge_failure_does_not_stop_startup_or_fail_requests(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from doctor_dictation.api.app import create_app
    from doctor_dictation.templates import service
    monkeypatch.setenv("DB_PATH", str(tmp_path / "boom.db"))

    def boom(*a, **k):
        raise PermissionError("cannot unlink")
    monkeypatch.setattr(service, "purge_expired", boom)
    with TestClient(create_app()) as c:  # startup purge raises: app must still boot
        assert c.get(URL + "/active").status_code == 404  # per-request purge raises: still not a 500
