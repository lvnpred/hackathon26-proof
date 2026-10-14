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


# ---- letterhead details -> Profile (merge rule, use-details) ----
_OLD = {"doctor_name": "Old Doc", "qualifications": "Old Qual", "reg_no": "OLD-1",
        "clinic_name": "Old Clinic", "address": "Old Address", "phone": "999 000 1111"}


def _blank_layout(monkeypatch, **blank):
    lay = json.loads(json.dumps(GOOD_LAYOUT))
    lay["profile"].update({k: "" for k in blank})
    lay["profile"]["qualifications"] = "   "          # whitespace-only counts as blank
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(lay))


def _profile(conn):
    row = dbmod.get_profile(conn)
    return {k: row[k] for k in _OLD}


def test_merge_profile_blank_keeps_existing_nonblank_wins():
    out = service._merge_profile(_OLD, {"doctor_name": " New ", "qualifications": "  ", "phone": ""})
    assert out["doctor_name"] == "New" and out["qualifications"] == "Old Qual" and out["phone"] == "999 000 1111"
    assert out["reg_no"] == "OLD-1" and set(out) == set(_OLD)
    assert service._merge_profile({}, {"doctor_name": "X"})["phone"] == ""


def test_accept_keeps_existing_profile_values_for_blank_letterhead_fields(tconn, monkeypatch):
    dbmod.save_profile(tconn, **_OLD)
    _blank_layout(monkeypatch, phone=1, reg_no=1)
    service.accept(tconn, _up(tconn)["id"])
    p = _profile(tconn)
    assert p["phone"] == "999 000 1111" and p["reg_no"] == "OLD-1" and p["qualifications"] == "Old Qual"
    assert p["doctor_name"] == "Dr A. Rao" and p["clinic_name"] == "Meridian Clinic"
    assert p["address"] == "12 MG Road, Hyderabad"


def test_use_details_saves_profile_deletes_draft_and_files_and_audits(tconn):
    v = _up(tconn)
    logo = service.templates_dir() / f"{v['id']}_logo.jpg"
    out = service.use_details(tconn, v["id"], actor="demo")
    assert out["discarded"] is True and out["profile"]["clinic_name"] == "Meridian Clinic"
    assert _profile(tconn)["doctor_name"] == "Dr A. Rao"
    assert tdb.get_template(tconn, v["id"]) is None
    assert not service.original_path(v["id"]).exists() and not logo.exists()
    row = tconn.execute("SELECT * FROM audit_log WHERE action = 'template_use_details'").fetchone()
    assert row["actor"] == "demo" and row["entity"] == "template" and row["entity_id"] == str(v["id"])
    assert json.loads(row["detail"]) == {"clinic": "default"}


def test_use_details_merges_blanks_with_existing_profile(tconn, monkeypatch):
    dbmod.save_profile(tconn, **_OLD)
    _blank_layout(monkeypatch, phone=1)
    out = service.use_details(tconn, _up(tconn)["id"])
    assert out["profile"]["phone"] == "999 000 1111" and out["profile"]["doctor_name"] == "Dr A. Rao"


def test_use_details_saves_the_edited_value(tconn):
    v = _up(tconn)
    service.edit(tconn, v["id"], {"doctor_name": "Dr Edited"}, [])
    assert service.use_details(tconn, v["id"])["profile"]["doctor_name"] == "Dr Edited"
    assert _profile(tconn)["doctor_name"] == "Dr Edited"


def test_use_details_leaves_active_template_active(tconn):
    active = _up(tconn)
    service.accept(tconn, active["id"])
    draft = _up(tconn)
    service.use_details(tconn, draft["id"])
    assert tdb.get_template(tconn, active["id"])["status"] == "active"
    assert service.get_active(tconn)["id"] == active["id"]


def test_use_details_404_and_409(tconn):
    with pytest.raises(TemplateError) as e:
        service.use_details(tconn, 999)
    assert e.value.status == 404
    v = _up(tconn)
    service.accept(tconn, v["id"])
    with pytest.raises(TemplateError) as e2:
        service.use_details(tconn, v["id"])
    assert e2.value.status == 409
