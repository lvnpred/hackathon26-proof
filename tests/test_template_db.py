import json
import sqlite3

import pytest

from doctor_dictation.config import get_settings
from doctor_dictation.db import templates as tdb
from template_fixtures import GOOD_LAYOUT, tconn  # noqa: F401


def test_settings_defaults():
    s = get_settings()
    assert (s.template_uploads_per_day, s.template_draft_ttl_hours) == (10, 24)
    assert s.template_max_image_bytes == 8 * 1024 * 1024 and s.template_max_pixels == 40_000_000


def test_migration_creates_table_and_status_check(tconn):
    cols = {r["name"] for r in tconn.execute("PRAGMA table_info(templates)")}
    assert {"id", "clinic", "layout_json", "logo_path", "status", "created_at", "accepted_at"} <= cols
    with pytest.raises(sqlite3.IntegrityError):
        tconn.execute("INSERT INTO templates(layout_json, status, created_at) VALUES ('{}', 'bogus', 'x')")


def test_create_get_update_layout(tconn):
    tid = tdb.create_template_draft(tconn, GOOD_LAYOUT)
    row = tdb.get_template(tconn, tid)
    assert row["status"] == "draft" and json.loads(row["layout_json"]) == GOOD_LAYOUT
    assert tdb.update_template_layout(tconn, tid, {"x": 1}) is True
    assert json.loads(tdb.get_template(tconn, tid)["layout_json"]) == {"x": 1}
    assert tdb.update_template_layout(tconn, 999, {}) is False


def test_set_active_archives_previous_and_scopes_to_clinic(tconn):
    a, b = (tdb.create_template_draft(tconn, GOOD_LAYOUT) for _ in range(2))
    other = tdb.create_template_draft(tconn, GOOD_LAYOUT, clinic="other")
    assert tdb.set_template_active(tconn, a) and tdb.set_template_active(tconn, other)
    assert tdb.set_template_active(tconn, b)
    status = {r["id"]: r["status"] for r in tconn.execute("SELECT id, status FROM templates")}
    assert status == {a: "archived", b: "active", other: "active"}
    assert tdb.get_active_template(tconn)["id"] == b
    assert tdb.set_template_active(tconn, a) is False  # archived is not a draft


def test_get_active_none_when_empty(tconn):
    assert tdb.get_active_template(tconn) is None


def test_delete_and_purge_only_expired_drafts(tconn):
    old = tdb.create_template_draft(tconn, GOOD_LAYOUT, created_at="2026-10-01T00:00:00Z")
    fresh = tdb.create_template_draft(tconn, GOOD_LAYOUT, created_at="2026-10-13T00:00:00Z")
    act = tdb.create_template_draft(tconn, GOOD_LAYOUT, created_at="2026-09-01T00:00:00Z")
    tdb.set_template_active(tconn, act)
    gone = tdb.purge_expired_drafts(tconn, "2026-10-12T00:00:00Z")
    assert [r["id"] for r in gone] == [old]
    assert tdb.get_template(tconn, fresh) and tdb.get_template(tconn, act)
    assert tdb.delete_template(tconn, fresh) is True and tdb.delete_template(tconn, fresh) is False


def test_count_uploads_since_counts_audit_rows_per_clinic(tconn):
    from doctor_dictation import db as dbmod
    for clinic, at in [("default", "2026-10-13T01:00:00Z"), ("default", "2026-10-12T23:59:59Z"), ("other", "2026-10-13T02:00:00Z")]:
        dbmod.log_audit(tconn, action="template_upload", entity="template", detail={"clinic": clinic}, at=at)
    assert tdb.count_uploads_since(tconn, "default", "2026-10-13T00:00:00Z") == 1
