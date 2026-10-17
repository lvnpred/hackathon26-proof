"""Account operations: create, reset, change password. Offline."""
import json
import sqlite3
from contextlib import closing

import pytest

from doctor_dictation import accounts as A
from doctor_dictation import clinics
from doctor_dictation import db as dbmod
from doctor_dictation import directory as D
from doctor_dictation import passwords as P
from doctor_dictation.directory import logins
from doctor_dictation.scope import clinic_dir
from doctor_dictation.sessions import Identity


@pytest.fixture()
def two(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    clinics.provision_clinic("iyer", "Iyer Clinic")
    return multi


def _conn(slug):
    return dbmod.get_conn(clinic_dir(slug) / "app.db")


def _user(slug, username):
    with closing(_conn(slug)) as c:
        return c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def _audit(slug, action):
    with closing(_conn(slug)) as c:
        return c.execute("SELECT actor, action, entity_id, detail FROM audit_log WHERE action = ?", (action,)).fetchone()


def test_migration_005_adds_user_columns_with_defaults(two):
    with closing(_conn("rao")) as c:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(users)")}
        c.execute("INSERT INTO users(username, password_hash, created_at) VALUES ('legacy', 'x', '2026-01-01T00:00:00Z')")
        c.commit()
        row = c.execute("SELECT * FROM users WHERE username = 'legacy'").fetchone()
    assert {"display_name", "doctor_name", "qualifications", "reg_no", "session_version", "must_change_password", "last_login_at"} <= cols
    assert (row["session_version"], row["must_change_password"], row["display_name"], row["last_login_at"]) == (0, 1, "", None)


def test_create_user_hashes_password_indexes_username_and_returns_temp_once(two):
    uid, temp = A.create_user("rao", "dr.rao", display_name="Dr. Rao", doctor_name="Dr A. Rao", qualifications="MBBS", reg_no="TS-1")
    row = _user("rao", "dr.rao")
    assert row["id"] == uid and len(temp) == 16
    assert temp not in row["password_hash"] and P.verify_password(temp, row["password_hash"])
    assert (row["role"], row["is_active"], row["must_change_password"], row["session_version"]) == ("admin", 1, 1, 0)   # DEFAULT_ROLE (until RBAC)
    assert (row["display_name"], row["doctor_name"], row["qualifications"], row["reg_no"]) == ("Dr. Rao", "Dr A. Rao", "MBBS", "TS-1")
    with closing(D.open_directory()) as d:
        entry = logins.lookup_username(d, "DR.RAO")
    assert (entry["clinic_slug"], entry["user_id"]) == ("rao", uid)


def test_create_user_audits_the_actor_without_leaking_the_password(two):
    _uid, temp = A.create_user("rao", "dr.rao", actor="admin-cli")
    row = _audit("rao", "user_create")
    assert row["actor"] == "admin-cli" and json.loads(row["detail"]) == {"username": "dr.rao"}
    assert temp not in (row["detail"] or "")


def test_create_user_rejects_bad_usernames_roles_and_unknown_clinics(two):
    for bad in ("", "ab", "a b", "../x", "x" * 41, "dr/rao", "dr.rao\n", None, 7):
        with pytest.raises(A.AccountError):
            A.create_user("rao", bad)
    with pytest.raises(A.AccountError):
        A.create_user("rao", "dr.rao", role="owner")
    with pytest.raises(A.AccountError, match="clinic"):
        A.create_user("ghost", "dr.rao")
    assert _user("rao", "dr.rao") is None


def test_create_user_rejects_taken_username_across_clinics_and_case(two):
    A.create_user("rao", "Dr.Rao")
    for slug, name in (("iyer", "dr.rao"), ("rao", "DR.RAO")):
        with pytest.raises(A.AccountError, match="taken"):
            A.create_user(slug, name)
    assert _user("iyer", "dr.rao") is None and _user("rao", "DR.RAO") is None


def test_create_user_removes_its_clinic_row_when_the_directory_index_fails(two, monkeypatch):
    def boom(*_a, **_k):
        raise D.DirectoryError("directory is down")

    monkeypatch.setattr(A, "index_username", boom)
    with pytest.raises(A.AccountError, match="directory is down"):
        A.create_user("rao", "dr.rao")
    assert _user("rao", "dr.rao") is None


def test_create_user_with_an_explicit_password_applies_the_password_rules(two):
    with pytest.raises(P.PasswordError):
        A.create_user("rao", "dr.rao", password="short")
    assert _user("rao", "dr.rao") is None
    _uid, pw = A.create_user("rao", "dr.rao", password="a-long-enough-pw")
    assert pw == "a-long-enough-pw" and P.verify_password(pw, _user("rao", "dr.rao")["password_hash"])


def test_reset_password_bumps_version_sets_must_change_and_audits(two):
    uid, _ = A.create_user("rao", "dr.rao", password="first-password-1")
    with closing(_conn("rao")) as c:
        c.execute("UPDATE users SET must_change_password = 0 WHERE id = ?", (uid,))
        c.commit()
    new = A.reset_password("DR.RAO", actor="admin-cli")
    row = _user("rao", "dr.rao")
    assert P.verify_password(new, row["password_hash"]) and not P.verify_password("first-password-1", row["password_hash"])
    assert (row["session_version"], row["must_change_password"]) == (1, 1)
    audit = _audit("rao", "password_reset")
    assert (audit["actor"], audit["entity_id"]) == ("admin-cli", str(uid)) and new not in (audit["detail"] or "")


def test_reset_password_for_an_unknown_user_raises(two):
    with pytest.raises(A.AccountError, match="no such user"):
        A.reset_password("nobody")


def test_change_password_checks_current_enforces_rules_bumps_version_clears_flag_and_audits(two):
    uid, temp = A.create_user("rao", "dr.rao")
    me = Identity("rao", uid, "dr.rao", "doctor", must_change_password=True)
    with pytest.raises(P.PasswordError):
        A.change_password(me, temp, "short")
    with pytest.raises(A.AccountError, match="different"):
        A.change_password(me, temp, temp)
    version = A.change_password(me, temp, "a-brand-new-password")
    row = _user("rao", "dr.rao")
    assert version == row["session_version"] == 1 and row["must_change_password"] == 0
    assert P.verify_password("a-brand-new-password", row["password_hash"])
    assert _audit("rao", "password_change")["actor"] == "dr.rao"


def test_change_password_with_a_wrong_current_password_changes_nothing(two):
    uid, temp = A.create_user("rao", "dr.rao")
    me = Identity("rao", uid, "dr.rao", "doctor")
    with pytest.raises(A.AccountError, match="Current password is incorrect"):
        A.change_password(me, "not-the-password-1", "a-brand-new-password")
    row = _user("rao", "dr.rao")
    assert row["session_version"] == 0 and P.verify_password(temp, row["password_hash"])


def test_reset_password_for_an_indexed_user_with_no_clinic_row_raises_and_writes_no_audit(two):
    uid, _ = A.create_user("rao", "dr.rao")
    with closing(_conn("rao")) as c:
        c.execute("DELETE FROM users WHERE id = ?", (uid,))
        c.commit()
    with pytest.raises(A.AccountError, match="no such user"):
        A.reset_password("dr.rao", actor="admin-cli")
    assert _audit("rao", "password_reset") is None


def test_change_password_loses_to_a_reset_that_lands_between_read_and_write(two, monkeypatch):
    uid, temp = A.create_user("rao", "dr.rao")
    me = Identity("rao", uid, "dr.rao", "doctor")
    real_verify = A.verify_password
    state = {"reset": None}

    def verify_then_reset(plain, hashed):
        ok = real_verify(plain, hashed)
        if state["reset"] is None:                         # first verify = the read step; reset lands right after it
            monkeypatch.setattr(A, "verify_password", real_verify)
            state["reset"] = A.reset_password("dr.rao", actor="admin-cli")
        return ok

    monkeypatch.setattr(A, "verify_password", verify_then_reset)
    with pytest.raises(A.AccountError, match="changed elsewhere"):
        A.change_password(me, temp, "a-brand-new-password")
    row = _user("rao", "dr.rao")
    assert P.verify_password(state["reset"], row["password_hash"]) and row["session_version"] == 1
    assert _audit("rao", "password_change") is None


def test_create_user_removes_its_clinic_row_when_the_directory_index_raises_a_sqlite_error(two, monkeypatch):
    def locked(*_a, **_k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(A, "index_username", locked)
    with pytest.raises(A.AccountError, match="could not index"):
        A.create_user("rao", "dr.rao")
    with closing(_conn("rao")) as c:
        assert c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
