"""authenticate / load_identity: success, every failure shape, lockout, session revocation. Offline."""
import shutil
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from doctor_dictation import accounts as A
from doctor_dictation import authn as N
from doctor_dictation import clinics
from doctor_dictation import db as dbmod
from doctor_dictation import directory as D
from doctor_dictation import sessions
from doctor_dictation.scope import clinic_dir
from doctor_dictation.sessions import Identity

T0 = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)
IP = "10.0.0.1"


@pytest.fixture()
def world(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    clinics.provision_clinic("iyer", "Iyer Clinic")
    rao, _ = A.create_user("rao", "dr.rao", display_name="Dr. Rao", password="rao-password-1", role="doctor")
    iyer, _ = A.create_user("iyer", "dr.iyer", password="iyer-password-1", role="doctor")
    return {"rao": rao, "iyer": iyer}


def _sql(slug, sql, *args):
    with closing(dbmod.get_conn(clinic_dir(slug) / "app.db")) as c:
        c.execute(sql, args)
        c.commit()


def _failures():
    with closing(D.open_directory()) as d:
        return d.execute("SELECT failed_count FROM login_attempts").fetchall()


def _count_dummy(monkeypatch):
    calls, real = [], N.passwords.dummy_verify
    monkeypatch.setattr(N.passwords, "dummy_verify", lambda pw: calls.append(1) or real(pw))
    return calls


def test_login_success_returns_identity_audits_and_updates_last_login(world):
    ident = N.authenticate("dr.rao", "rao-password-1", IP, T0)
    assert ident == Identity("rao", world["rao"], "dr.rao", "doctor", "Dr. Rao", True, 0)
    with closing(dbmod.get_conn(clinic_dir("rao") / "app.db")) as c:
        assert c.execute("SELECT last_login_at FROM users").fetchone()[0] is not None
        audit = c.execute("SELECT actor, role FROM audit_log WHERE action = 'login'").fetchone()
    assert (audit["actor"], audit["role"]) == ("dr.rao", "doctor")


def test_wrong_password_returns_none_and_counts_a_failure(world):
    assert N.authenticate("dr.rao", "wrong-password", IP, T0) is None
    assert [r["failed_count"] for r in _failures()] == [1]


def test_unknown_username_pays_for_a_hash_and_counts_a_failure(world, monkeypatch):
    calls = _count_dummy(monkeypatch)
    assert N.authenticate("nobody", "whatever-pass", IP, T0) is None
    assert calls == [1] and [r["failed_count"] for r in _failures()] == [1]


def test_fifth_failure_locks_and_a_correct_password_is_then_refused(world, monkeypatch):
    for _ in range(5):
        assert N.authenticate("dr.rao", "wrong-password", IP, T0) is None
    calls = _count_dummy(monkeypatch)
    assert N.authenticate("dr.rao", "rao-password-1", IP, T0 + timedelta(seconds=10)) is None
    assert calls == [1]                                      # a locked attempt still pays for one hash
    assert N.authenticate("dr.rao", "rao-password-1", "10.0.0.2", T0 + timedelta(seconds=10)) is not None   # the lock is per (username, ip)


def test_the_lock_expires_after_five_minutes(world):
    for _ in range(5):
        N.authenticate("dr.rao", "wrong-password", IP, T0)
    assert N.authenticate("dr.rao", "rao-password-1", IP, T0 + timedelta(seconds=300)) is not None


def test_success_clears_earlier_failures(world):
    for _ in range(3):
        N.authenticate("dr.rao", "wrong-password", IP, T0)
    assert N.authenticate("dr.rao", "rao-password-1", IP, T0) is not None
    assert _failures() == []


def test_a_disabled_user_is_refused_after_a_dummy_hash(world, monkeypatch):
    _sql("rao", "UPDATE users SET is_active = 0")
    calls = _count_dummy(monkeypatch)
    assert N.authenticate("dr.rao", "rao-password-1", IP, T0) is None
    assert calls == [1]


def test_a_disabled_clinic_is_refused(world):
    with closing(D.open_directory()) as d:
        d.execute("UPDATE clinics SET status = 'disabled' WHERE slug = 'rao'")
        d.commit()
    assert N.authenticate("dr.rao", "rao-password-1", IP, T0) is None
    assert N.authenticate("dr.iyer", "iyer-password-1", IP, T0) is not None


def test_a_clinic_that_failed_startup_is_refused(world):
    assert N.authenticate("dr.rao", "rao-password-1", IP, T0, failed_clinics=frozenset({"rao"})) is None


def test_username_is_case_insensitive_and_trimmed(world):
    assert N.authenticate("  DR.RAO ", "rao-password-1", IP, T0) is not None


def test_load_identity_accepts_a_fresh_cookie(world):
    token = sessions.sign("rao", world["rao"], 0, now=T0.timestamp())
    ident = N.load_identity(token, T0)
    assert (ident.username, ident.clinic_slug, ident.session_version, ident.must_change_password) == ("dr.rao", "rao", 0, True)


def test_load_identity_ends_sessions_on_reset_disable_clinic_disable_and_failed_clinic(world):
    token = sessions.sign("rao", world["rao"], 0, now=T0.timestamp())
    assert N.load_identity(token, T0) is not None
    assert N.load_identity(token, T0, failed_clinics=frozenset({"rao"})) is None
    A.reset_password("dr.rao")                                # session_version 0 -> 1
    assert N.load_identity(token, T0) is None
    token = sessions.sign("rao", world["rao"], 1, now=T0.timestamp())
    assert N.load_identity(token, T0) is not None
    _sql("rao", "UPDATE users SET is_active = 0")
    assert N.load_identity(token, T0) is None
    _sql("rao", "UPDATE users SET is_active = 1")
    with closing(D.open_directory()) as d:
        d.execute("UPDATE clinics SET status = 'disabled' WHERE slug = 'rao'")
        d.commit()
    assert N.load_identity(token, T0) is None


def test_load_identity_rejects_expired_garbage_unknown_user_and_missing_folder(world):
    old = sessions.sign("rao", world["rao"], 0, now=T0.timestamp() - sessions.LIFETIME_SECONDS - 1)
    assert N.load_identity(old, T0) is None
    assert N.load_identity("garbage", T0) is None and N.load_identity(None, T0) is None
    assert N.load_identity(sessions.sign("rao", 999, 0, now=T0.timestamp()), T0) is None
    token = sessions.sign("iyer", world["iyer"], 0, now=T0.timestamp())
    shutil.rmtree(clinic_dir("iyer"))
    assert N.load_identity(token, T0) is None and not clinic_dir("iyer").exists()   # nothing re-created
