"""Template scope and doctors columns (migration 007), the OP-prefix column (008), scope-aware storage. Offline."""
import json
import shutil
import sqlite3

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation.db import templates as tdb
from template_fixtures import GOOD_LAYOUT, tconn  # noqa: F401


def _user(conn, username, role="doctor", active=1, **fields):
    uid = dbmod.create_user(conn, username, "x", role=role, is_active=active)
    if fields:
        conn.execute("UPDATE users SET " + ", ".join(f"{k} = ?" for k in fields) + " WHERE id = ?",
                     (*fields.values(), uid))
        conn.commit()
    return uid


def test_migrations_add_scope_doctors_and_prefix_columns_with_safe_defaults(tconn):
    cols = {r["name"] for r in tconn.execute("PRAGMA table_info(templates)")}
    assert {"owner_user_id", "doctors_mode", "doctors_ids"} <= cols
    assert "op_prefix" in {r["name"] for r in tconn.execute("PRAGMA table_info(clinic_profile)")}
    row = tdb.get_template(tconn, tdb.create_template_draft(tconn, GOOD_LAYOUT))
    assert (row["owner_user_id"], row["doctors_mode"], json.loads(row["doctors_ids"])) == (None, "author", [])
    with pytest.raises(sqlite3.IntegrityError):
        tconn.execute("UPDATE templates SET doctors_mode = 'everyone' WHERE id = ?", (row["id"],))


def test_existing_letterheads_survive_the_migration_as_clinic_letterheads(tmp_path):
    old = tmp_path / "before_007"
    old.mkdir()
    for path in sorted(dbmod.MIGRATIONS_DIR.glob("*.sql")):
        if path.name < "007":
            shutil.copy(path, old / path.name)
    conn = dbmod.get_conn(tmp_path / "old.db")
    try:
        dbmod.migrate(conn, old)
        cur = conn.execute("INSERT INTO templates(layout_json, status, created_at) VALUES (?, 'active', 'x')",
                           (json.dumps(GOOD_LAYOUT),))
        conn.execute("INSERT INTO clinic_profile(id, updated_at) VALUES (1, 'x')")
        conn.commit()
        applied = dbmod.migrate(conn)
        assert applied == ["007_templates_scope.sql", "008_clinic_profile_prefix.sql", "009_clinic_formulary.sql", "010_clinic_overlay.sql", "011_spoken_terms.sql", "012_spoken_mishearings.sql", "013_term_links.sql", "014_share_links.sql"]
        active = tdb.get_active_template(conn)
        assert active["id"] == cur.lastrowid and active["doctors_mode"] == "author"
        assert conn.execute("SELECT op_prefix FROM clinic_profile WHERE id = 1").fetchone()[0] is None
    finally:
        conn.close()


def test_each_scope_keeps_one_active_and_never_archives_the_other(tconn):
    a, b, c, d = (tdb.create_template_draft(tconn, GOOD_LAYOUT) for _ in range(4))
    assert tdb.set_template_active(tconn, a)                       # the clinic letterhead
    assert tdb.set_template_active(tconn, b, owner_user_id=5)      # doctor 5's own
    assert tdb.set_template_active(tconn, c)                       # a new clinic letterhead archives a only
    status = {r["id"]: r["status"] for r in tconn.execute("SELECT id, status FROM templates")}
    assert status == {a: "archived", b: "active", c: "active", d: "draft"}
    assert tdb.set_template_active(tconn, d, owner_user_id=5)      # doctor 5's newer one archives b
    assert tdb.get_template(tconn, b)["status"] == "archived"
    assert tdb.get_active_template(tconn)["id"] == c
    assert tdb.get_active_template(tconn, owner_user_id=5)["id"] == d
    assert tdb.get_active_template(tconn, owner_user_id=6) is None


def test_deactivate_touches_only_its_own_scope(tconn):
    clinic, mine, draft = (tdb.create_template_draft(tconn, GOOD_LAYOUT) for _ in range(3))
    tdb.set_template_active(tconn, clinic)
    tdb.set_template_active(tconn, mine, owner_user_id=5)
    assert tdb.deactivate_templates(tconn, owner_user_id=5) == 1
    assert tdb.get_active_template(tconn)["id"] == clinic
    assert tdb.get_active_template(tconn, owner_user_id=5) is None
    assert tdb.deactivate_templates(tconn) == 1 and tdb.get_active_template(tconn) is None
    assert tdb.get_template(tconn, draft)["status"] == "draft"


def test_set_template_doctors_round_trip(tconn):
    tid = tdb.create_template_draft(tconn, GOOD_LAYOUT)
    assert tdb.set_template_doctors(tconn, tid, "selected", [3, 1]) is True
    row = tdb.get_template(tconn, tid)
    assert (row["doctors_mode"], json.loads(row["doctors_ids"])) == ("selected", [3, 1])
    assert tdb.set_template_doctors(tconn, 999, "all", []) is False


def test_clinic_doctors_lists_active_doctors_oldest_first(tconn):
    b = _user(tconn, "dr.b", doctor_name="Dr B")
    _user(tconn, "nurse", role="assistant")
    _user(tconn, "dr.gone", active=0)
    a = _user(tconn, "dr.a", doctor_name="Dr A")
    rows = tdb.clinic_doctors(tconn)
    assert [r["id"] for r in rows] == [b, a] and rows[0]["doctor_name"] == "Dr B"
