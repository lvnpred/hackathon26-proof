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


# ---- remove a line, keep one copy of a duplicated field, fix an active letterhead ----
def fresh_draft(tconn):
    lay = json.loads(json.dumps(GOOD_LAYOUT))
    lay["header"] = [
        {"type": "logo", "crop": [0.05, 0.02, 0.25, 0.10], "align": "left"},
        {"type": "text", "field": "doctor_name", "role": "title", "align": "center"},
        {"type": "text", "text": "Open Mon to Sat", "role": "small", "align": "center"},
        {"type": "rule", "color": "#1a3c6e", "thickness": "thin"},
        {"type": "text", "field": "phone", "role": "small", "align": "center"},
        {"type": "text", "text": "Name: Age:", "role": "small", "align": "left"},
    ]
    lay["footer"] = [{"type": "text", "field": "address", "role": "small", "align": "center"},
                     {"type": "text", "text": "Visit After", "role": "small", "align": "center"},
                     {"type": "text", "field": "phone", "role": "small", "align": "center"}]
    return tdb.create_template_draft(tconn, lay)


def test_remove_deletes_literal_lines_and_refuses_other_blocks(tconn):
    out = service.edit(tconn, fresh_draft(tconn), {}, [{"section": "header", "index": 5, "remove": True},
                                                        {"section": "footer", "index": 1, "remove": True}])
    assert [b.get("text") for b in out["layout"]["header"]][-1] is None and len(out["layout"]["footer"]) == 2
    assert out["fill_in"] == []
    for bad in ([{"section": "header", "index": 1, "remove": True}], [{"section": "header", "index": 2, "remove": "yes"}]):
        with pytest.raises(TemplateError) as e:
            service.edit(tconn, fresh_draft(tconn), {}, bad)
        assert e.value.status == 400


def test_removals_use_the_stored_indexes_and_apply_after_text_edits(tconn):
    out = service.edit(tconn, fresh_draft(tconn), {}, [
        {"section": "footer", "index": 1, "remove": True},
        {"section": "header", "index": 2, "text": "Open daily"},
        {"section": "header", "index": 5, "remove": True}])
    assert [b.get("text") for b in out["layout"]["header"]] == [None, None, "Open daily", None, None]
    assert [b.get("field") for b in out["layout"]["footer"]] == ["address", "phone"]


def test_removing_every_literal_line_leaves_a_valid_layout(tconn):
    tid = fresh_draft(tconn)
    service.edit(tconn, tid, {}, [{"section": "header", "index": 2, "remove": True},
                                  {"section": "header", "index": 5, "remove": True},
                                  {"section": "footer", "index": 1, "remove": True}])
    service.accept(tconn, tid)
    assert service.active_layout_for_save(tconn) != (None, None)


def test_keep_header_removes_the_footer_copy_and_both_keeps_both(tconn):
    out = service.edit(tconn, fresh_draft(tconn), {}, [], keep=[{"field": "phone", "where": "header"}])
    assert [b.get("field") for b in out["layout"]["footer"]] == ["address", None] and out["duplicates"] == []
    out = service.edit(tconn, fresh_draft(tconn), {}, [], keep=[{"field": "phone", "where": "footer"}])
    assert [b.get("field") for b in out["layout"]["header"]].count("phone") == 0 and out["duplicates"] == []
    out = service.edit(tconn, fresh_draft(tconn), {}, [], keep=[{"field": "phone", "where": "both"}])
    assert len(out["layout"]["header"]) == 6 and len(out["layout"]["footer"]) == 3
    for bad in ([{"field": "phone", "where": "middle"}], [{"field": "ssn", "where": "header"}], "x", ["x"]):
        with pytest.raises(TemplateError) as e:
            service.edit(tconn, fresh_draft(tconn), {}, [], keep=bad)
        assert e.value.status == 400


def test_keep_for_a_field_no_longer_duplicated_is_ignored(tconn):
    out = service.edit(tconn, fresh_draft(tconn), {}, [], keep=[{"field": "address", "where": "header"}])
    assert len(out["layout"]["header"]) == 6 and len(out["layout"]["footer"]) == 3


def test_a_cleared_line_without_remove_is_still_rejected(tconn):
    with pytest.raises(TemplateError) as e:
        service.edit(tconn, fresh_draft(tconn), {}, [{"section": "header", "index": 2, "text": "  "}])
    assert e.value.status == 400 and "edit rejected" in str(e.value)


def test_tidy_fixes_an_active_letterhead_and_audits_it(tconn):
    tid = fresh_draft(tconn)
    service.accept(tconn, tid)
    v = service.tidy(tconn, tid, [{"section": "footer", "index": 1, "remove": True},
                                     {"section": "header", "index": 5, "remove": True}],
                     [{"field": "phone", "where": "header"}], actor="demo")
    assert v["status"] == "active" and v["fill_in"] == [] and v["duplicates"] == []
    assert ("template_tidy", "demo") in _audit(tconn)
    detail = json.loads(tconn.execute("SELECT detail FROM audit_log WHERE action='template_tidy'").fetchone()[0])
    assert detail == {"clinic": "default", "removed": 2, "edited": 0, "keep": [{"field": "phone", "where": "header"}]}
    assert "Visit After" not in json.dumps(detail)
    lay, _ = service.active_layout_for_save(tconn)
    assert "Visit After" not in json.dumps(lay.footer if hasattr(lay, "footer") else lay["footer"])
    service.deactivate(tconn)
    with pytest.raises(TemplateError) as e:
        service.tidy(tconn, tid, [], [])
    assert e.value.status == 409
    with pytest.raises(TemplateError) as e:
        service.tidy(tconn, 999, [], [])
    assert e.value.status == 404


def test_keep_twice_for_one_field_is_refused(tconn):
    with pytest.raises(TemplateError) as e:
        service.edit(tconn, fresh_draft(tconn), {}, [], keep=[{"field": "phone", "where": "header"},
                                                              {"field": "phone", "where": "footer"}])
    assert e.value.status == 400 and "one place per field" in str(e.value)


def test_keep_removes_a_literal_line_only_when_it_holds_just_the_value(tconn):
    lay = json.loads(json.dumps(GOOD_LAYOUT))
    lay["header"] = [{"type": "text", "field": "phone", "role": "small", "align": "center"}]
    lay["footer"] = [{"type": "text", "text": "Timings 10-1 | Ph 040 1234 5678 | Sunday closed", "role": "small"},
                     {"type": "text", "text": "Ph: 040 1234 5678", "role": "small"}]
    tid = tdb.create_template_draft(tconn, lay)
    out = service.edit(tconn, tid, {}, [], keep=[{"field": "phone", "where": "header"}])
    assert [b["text"] for b in out["layout"]["footer"]] == ["Timings 10-1 | Ph 040 1234 5678 | Sunday closed"]
    assert [d["field"] for d in out["duplicates"]] == ["phone"]


def test_tidy_with_no_changes_writes_and_audits_nothing(tconn):
    tid = fresh_draft(tconn)
    service.accept(tconn, tid)
    before = _audit(tconn)
    assert service.tidy(tconn, tid, [], [])["status"] == "active"
    assert _audit(tconn) == before


def _phone_twice(tconn, header_text=None):
    lay = json.loads(json.dumps(GOOD_LAYOUT))
    lay["header"] = [{"type": "text", "text": header_text, "role": "small"} if header_text
                     else {"type": "text", "field": "phone", "role": "small", "align": "center"}]
    lay["footer"] = [{"type": "text", "text": "Ph: 040 1234 5678", "role": "small"}]
    return tdb.create_template_draft(tconn, lay)


def test_removing_the_kept_side_does_not_erase_the_field_everywhere(tconn):
    tid = _phone_twice(tconn, "Ph: 040 1234 5678")
    out = service.edit(tconn, tid, {}, [{"section": "header", "index": 0, "remove": True}],
                       keep=[{"field": "phone", "where": "header"}])
    assert out["layout"]["header"] == [] and [b["text"] for b in out["layout"]["footer"]] == ["Ph: 040 1234 5678"]


def test_keep_does_not_drop_a_line_edited_in_the_same_request(tconn):
    tid = _phone_twice(tconn)
    out = service.edit(tconn, tid, {}, [{"section": "footer", "index": 0, "text": "Ph: 040 1234 5678 Mon-Sat"}],
                       keep=[{"field": "phone", "where": "header"}])
    assert [b["text"] for b in out["layout"]["footer"]] == ["Ph: 040 1234 5678 Mon-Sat"]


def test_a_remove_with_stale_text_is_refused(tconn):
    tid = fresh_draft(tconn)
    with pytest.raises(TemplateError) as e:
        service.edit(tconn, tid, {}, [{"section": "header", "index": 5, "remove": True, "text": "Something else"}])
    assert e.value.status == 400 and "letterhead changed" in str(e.value)
    out = service.edit(tconn, tid, {}, [{"section": "header", "index": 5, "remove": True, "text": " Name:   Age: "}])
    assert len(out["layout"]["header"]) == 5


def test_tidy_audit_counts_only_lines_whose_text_changed(tconn):
    tid = fresh_draft(tconn)
    service.accept(tconn, tid)
    service.tidy(tconn, tid, [{"section": "header", "index": 2, "text": "Open  Mon to Sat"},
                              {"section": "footer", "index": 1, "text": "Visit Soon"}], [])
    detail = json.loads(tconn.execute("SELECT detail FROM audit_log WHERE action='template_tidy'").fetchone()[0])
    assert detail["edited"] == 1 and detail["removed"] == 0
