"""Plan FB-D Task 2: migration 014 and the share-link store."""
from datetime import datetime, timedelta, timezone

import pytest

import doctor_dictation.db as dbmod
from doctor_dictation.db.share import (
    TOKEN_RE, TTL, document_for_encounter, ensure_link, find_by_token, is_live, link_for_encounter, new_token, revoke,
)

T0 = datetime(2026, 10, 26, 4, 0, tzinfo=timezone.utc)


@pytest.fixture()
def conn(tmp_path):
    dbmod.init_db(tmp_path / "s.db")
    c = dbmod.get_conn(tmp_path / "s.db")
    pid = dbmod.create_patient(c, "Asha Verma")
    yield c, dbmod.create_encounter(c, pid), dbmod.create_encounter(c, pid)
    c.close()


def test_migration_014_adds_the_link_table(conn):
    conn, e1, e2 = conn
    names = [r["name"] for r in conn.execute("PRAGMA table_info(share_links)")]
    assert names == ["id", "encounter_id", "token", "created_at", "saved_at", "expires_at", "revoked_at", "revoked_by"]


def test_the_first_save_creates_a_link_and_a_re_save_keeps_it_and_moves_the_expiry(conn):
    conn, e1, e2 = conn
    a = ensure_link(conn, e1, T0)
    assert TOKEN_RE.fullmatch(a["token"]) and a["expires_at"] == "2026-11-02T04:00:00Z"
    b = ensure_link(conn, e1, T0 + timedelta(days=3))
    assert (b["token"], b["id"]) == (a["token"], a["id"])
    assert b["expires_at"] == "2026-11-05T04:00:00Z" and b["created_at"] == a["created_at"]
    assert ensure_link(conn, e2, T0)["token"] != a["token"]


def test_a_re_save_after_a_revoke_issues_a_new_token_and_the_old_one_is_gone(conn):
    conn, e1, e2 = conn
    old = ensure_link(conn, e1, T0)["token"]
    assert revoke(conn, e1, 7, T0) is True
    assert revoke(conn, e1, 7, T0) is False
    assert is_live(link_for_encounter(conn, e1), T0) is False
    c = ensure_link(conn, e1, T0)
    assert c["token"] != old and c["revoked_at"] is None
    assert find_by_token(conn, old) is None


def test_a_link_is_live_until_the_second_it_expires(conn):
    conn, e1, e2 = conn
    row = ensure_link(conn, e1, T0)
    assert is_live(row, T0 + TTL - timedelta(seconds=1)) is True
    assert is_live(row, T0 + TTL) is False
    assert is_live(None, T0) is False
    assert len({new_token() for _ in range(200)}) == 200
    assert document_for_encounter(conn, e1) is None
