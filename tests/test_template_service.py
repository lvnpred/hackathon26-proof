import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation.config import get_settings, override_settings
from doctor_dictation.db import templates as tdb
from doctor_dictation.templates import TemplateError, service
from template_fixtures import GOOD_LAYOUT, make_jpeg, tconn  # noqa: F401


@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch):
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(GOOD_LAYOUT))
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True)


def _up(conn, actor=None, raw=None):
    return asyncio.run(service.upload(conn, raw or make_jpeg(), get_settings(), actor=actor))


def _audit(conn):
    return [(r["action"], r["actor"]) for r in conn.execute("SELECT action, actor FROM audit_log ORDER BY id")]


def test_upload_stores_draft_files_and_audit(tconn):
    v = _up(tconn, actor="demo")
    assert v["status"] == "draft" and v["profile"]["clinic_name"] == "Meridian Clinic" and "profile" not in v["layout"]
    row = tdb.get_template(tconn, v["id"])
    assert service.original_path(v["id"]).exists() and row["logo_path"] and (service.templates_dir() / f"{v['id']}_logo.jpg").exists()
    assert _audit(tconn) == [("template_upload", "demo")]


def test_invalid_llm_output_stores_nothing(tconn, monkeypatch):
    bad = json.loads(json.dumps(GOOD_LAYOUT))
    bad["body"] = {"top": 0.9, "bottom": 0.1}
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(bad))
    with pytest.raises(TemplateError) as e:
        _up(tconn)
    assert e.value.status == 502
    assert tconn.execute("SELECT COUNT(*) FROM templates").fetchone()[0] == 0
    assert not service.templates_dir().exists() or list(service.templates_dir().iterdir()) == []


def test_rate_limit_boundary(tconn, monkeypatch):
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, template_uploads_per_day=2)
    with pytest.raises(TemplateError) as e0:   # a bad image never reaches the quota
        _up(tconn, raw=b"not an image")
    assert e0.value.status == 400
    _up(tconn)
    _up(tconn)
    with pytest.raises(TemplateError) as e:
        _up(tconn)
    assert e.value.status == 429
    assert tdb.count_uploads_since(tconn, "default", "2000-01-01T00:00:00Z") == 2


def test_failed_llm_call_still_counts_toward_limit(tconn, monkeypatch):
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, template_uploads_per_day=1)
    monkeypatch.setenv("STUB_LLM_JSON", "{}")
    with pytest.raises(TemplateError):
        _up(tconn)
    with pytest.raises(TemplateError) as e:
        _up(tconn)
    assert e.value.status == 429


def test_purge_expired_removes_row_and_files_keeps_active(tconn):
    v = _up(tconn)
    keep = _up(tconn)
    tdb.set_template_active(tconn, keep["id"])
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
    tconn.execute("UPDATE templates SET created_at = ?", (old,))
    tconn.commit()
    assert service.purge_expired(tconn, get_settings()) == 1
    assert tdb.get_template(tconn, v["id"]) is None and not service.original_path(v["id"]).exists()
    assert not (service.templates_dir() / f"{v['id']}_logo.jpg").exists()
    assert tdb.get_template(tconn, keep["id"])["status"] == "active"


def test_upload_purges_lazily(tconn):
    v = _up(tconn)
    old = (datetime.now(timezone.utc) - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    tconn.execute("UPDATE templates SET created_at = ? WHERE id = ?", (old, v["id"]))
    tconn.commit()
    _up(tconn)
    assert tdb.get_template(tconn, v["id"]) is None


def test_accept_archives_previous_saves_profile_deletes_original(tconn):
    first, second = _up(tconn), _up(tconn)
    service.accept(tconn, first["id"], actor="demo")
    out = service.accept(tconn, second["id"], actor="demo")
    assert out["status"] == "active" and tdb.get_template(tconn, first["id"])["status"] == "archived"
    assert dbmod.get_profile(tconn)["clinic_name"] == "Meridian Clinic"
    assert not service.original_path(second["id"]).exists()
    assert (service.templates_dir() / f"{second['id']}_logo.jpg").exists()   # the small logo crop is kept
    assert ("template_accept", "demo") in _audit(tconn)
    assert service.get_active(tconn)["id"] == second["id"]


def test_accept_or_edit_non_draft_is_409_and_missing_is_404(tconn):
    v = _up(tconn)
    service.accept(tconn, v["id"])
    for call in (lambda: service.accept(tconn, v["id"]), lambda: service.edit(tconn, v["id"], {}, [])):
        with pytest.raises(TemplateError) as e:
            call()
        assert e.value.status == 409
    with pytest.raises(TemplateError) as e:
        service.accept(tconn, 999)
    assert e.value.status == 404


def test_discard_deletes_row_files_and_audits(tconn):
    v = _up(tconn)
    service.discard(tconn, v["id"], actor="demo")
    assert tdb.get_template(tconn, v["id"]) is None and not service.original_path(v["id"]).exists()
    assert ("template_discard", "demo") in _audit(tconn)
    with pytest.raises(TemplateError) as e:
        service.discard(tconn, v["id"])
    assert e.value.status == 404


def test_edit_profile_and_literal_line_revalidated(tconn):
    v = _up(tconn)
    out = service.edit(tconn, v["id"], {"phone": " 99999 "}, [{"section": "header", "index": 2, "text": "Open daily"}])
    assert out["profile"]["phone"] == "99999" and out["layout"]["header"][2]["text"] == "Open daily"
    for profile, lines in (({"ssn": "x"}, []), ({}, [{"section": "header", "index": 1, "text": "x"}]),
                           ({}, [{"section": "header", "index": 9, "text": "x"}]),
                           ({}, [{"section": "header", "index": 2, "text": "y" * 201}]),
                           ({}, [{"section": "profile", "index": 0, "text": "x"}])):
        with pytest.raises(TemplateError) as e:
            service.edit(tconn, v["id"], profile, lines)
        assert e.value.status == 400
    assert service.view(tdb.get_template(tconn, v["id"]))["layout"]["header"][2]["text"] == "Open daily"


def test_active_layout_for_save_falls_back_when_stored_layout_is_invalid(tconn):
    assert service.active_layout_for_save(tconn) == (None, None)
    v = _up(tconn)
    service.accept(tconn, v["id"])
    layout, logo = service.active_layout_for_save(tconn)
    assert layout is not None and logo.endswith(f"{v['id']}_logo.jpg")
    assert service.logo_data_uri(logo).startswith("data:image/jpeg;base64,") and service.logo_data_uri("/no/such.jpg") is None
    tconn.execute("UPDATE templates SET layout_json = '{\"body\": 5}' WHERE id = ?", (v["id"],))
    tconn.commit()
    assert service.active_layout_for_save(tconn) == (None, None)


def test_quota_checked_before_decoding_so_a_full_quota_is_429_not_400(tconn, monkeypatch):
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, template_uploads_per_day=1)
    _up(tconn)
    def boom(*a, **kw):
        raise AssertionError("clean_image must not run once the quota is spent")
    monkeypatch.setattr(service, "clean_image", boom)
    with pytest.raises(TemplateError) as e:
        _up(tconn, raw=b"not an image")
    assert e.value.status == 429


def test_at_most_two_image_decodes_run_at_once(tconn, monkeypatch):
    import time
    real, state = service.clean_image, {"now": 0, "peak": 0}
    def slow(*a, **kw):
        state["now"] += 1; state["peak"] = max(state["peak"], state["now"])
        time.sleep(0.05)
        state["now"] -= 1
        return real(*a, **kw)
    monkeypatch.setattr(service, "clean_image", slow)
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, template_uploads_per_day=50)
    async def burst():
        await asyncio.gather(*(service.upload(tconn, make_jpeg(), get_settings()) for _ in range(5)))
    asyncio.run(burst())
    assert state["peak"] == 2
