"""Per-session revocation: sid in the cookie, the directory's revoked_sessions table, logout ends only that session. Offline."""
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import accounts as A
from doctor_dictation import authn as N
from doctor_dictation import clinics
from doctor_dictation import directory as D
from doctor_dictation import sessions
from doctor_dictation.api import auth as auth_routes
from doctor_dictation.api.app import create_app
from doctor_dictation.directory import revocations as R

H = {"X-DD-Client": "1"}
T0 = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)
GOOD = {"clinic": "rao", "uid": 1, "ver": 0, "iat": 1, "exp": 10**12, "sid": "a" * 22}


@pytest.fixture()
def world(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    uid, _ = A.create_user("rao", "dr.rao", display_name="Dr. Rao", password="temp-password-1", role="doctor")
    return uid


def _make_client():
    return TestClient(create_app(), follow_redirects=False)


def _login(c, pw="temp-password-1"):
    r = c.post("/api/v1/auth/login", json={"username": "dr.rao", "password": pw}, headers=H)
    assert r.status_code == 200, r.text
    return r


def _two_browsers(stack):
    a, b = (stack.enter_context(_make_client()) for _ in range(2))
    _login(a)
    r = a.post("/api/v1/auth/change-password", json={"current_password": "temp-password-1", "new_password": "brand-new-pass-1"}, headers=H)
    assert r.status_code == 200, r.text
    _login(b, "brand-new-pass-1")
    return a, b


@pytest.fixture()
def browsers(world):
    from contextlib import ExitStack
    with ExitStack() as stack:
        yield _two_browsers(stack)


def test_sign_gives_each_cookie_a_distinct_sid(multi):
    one, two = sessions.verify(sessions.sign("rao", 1, 0)), sessions.verify(sessions.sign("rao", 1, 0))
    assert set(one) == {"clinic", "uid", "ver", "iat", "exp", "sid"}
    assert one["sid"] != two["sid"]


def test_verify_rejects_a_missing_or_malformed_sid(multi):
    assert sessions.verify(sessions._encode(GOOD), now=2) is not None
    assert sessions.verify(sessions._encode({k: v for k, v in GOOD.items() if k != "sid"}), now=2) is None
    for bad in (5, True, "", "a" * 100, "a" * 15, "bad sid!" * 3, "é" * 20, None):
        assert sessions.verify(sessions._encode({**GOOD, "sid": bad}), now=2) is None, bad


def test_revoke_and_is_revoked_roundtrip_and_are_idempotent(multi):
    with closing(D.open_directory()) as d:
        assert not R.is_revoked(d, "s" * 22)
        R.revoke_session(d, "s" * 22, int(time.time()) + 100)
        R.revoke_session(d, "s" * 22, int(time.time()) + 100)
        assert R.is_revoked(d, "s" * 22)
        assert not R.is_revoked(d, "t" * 22)
        assert d.execute("SELECT COUNT(*) FROM revoked_sessions").fetchone()[0] == 1


def test_revoke_purges_rows_past_their_expiry(multi):
    with closing(D.open_directory()) as d:
        R.revoke_session(d, "old" * 7, 100, now=50)
        R.revoke_session(d, "new" * 7, 10_000, now=50)
        R.revoke_session(d, "x" * 22, 20_000, now=500)             # a write at t=500 purges the row that expired at 100
        assert not R.is_revoked(d, "old" * 7)
        assert R.is_revoked(d, "new" * 7) and R.is_revoked(d, "x" * 22)


def test_load_identity_rejects_a_revoked_sid(world):
    token = sessions.sign("rao", world, 0, now=T0.timestamp())
    assert N.load_identity(token, T0).sid == sessions.verify(token, T0.timestamp())["sid"]
    with closing(D.open_directory()) as d:
        R.revoke_session(d, sessions.verify(token, T0.timestamp())["sid"], int(T0.timestamp()) + 1000, now=T0.timestamp())
    assert N.load_identity(token, T0) is None


def test_other_sessions_of_the_same_user_survive_a_revocation(world):
    first, second = (sessions.sign("rao", world, 0, now=T0.timestamp()) for _ in range(2))
    with closing(D.open_directory()) as d:
        R.revoke_session(d, sessions.verify(first, T0.timestamp())["sid"], int(T0.timestamp()) + 1000, now=T0.timestamp())
    assert N.load_identity(first, T0) is None
    assert N.load_identity(second, T0) is not None


def test_logout_ends_that_session_only(browsers):
    a, b = browsers
    replay = a.cookies.get(sessions.COOKIE_NAME)
    assert a.post("/api/v1/auth/logout", headers=H).status_code == 200
    a.cookies.set(sessions.COOKIE_NAME, replay)
    assert a.get("/api/v1/auth/me").status_code == 401
    assert b.get("/api/v1/auth/me").status_code == 200


def test_replayed_cookie_after_logout_is_dead_even_if_the_browser_ignored_the_clear(world):
    with _make_client() as a:
        _login(a)
        copied = a.cookies.get(sessions.COOKIE_NAME)
        assert a.post("/api/v1/auth/logout", headers=H).status_code == 200
    with _make_client() as fresh:
        fresh.cookies.set(sessions.COOKIE_NAME, copied)
        assert fresh.get("/api/v1/auth/me").status_code == 401


def test_logout_that_cannot_revoke_is_503_and_keeps_the_cookie(world, monkeypatch):
    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")
    with _make_client() as a:
        _login(a)
        monkeypatch.setattr(auth_routes, "revoke_session", boom)
        r = a.post("/api/v1/auth/logout", headers=H)
        assert r.status_code == 503 and r.json() == {"error": "try again"}
        assert "set-cookie" not in r.headers
        assert a.get("/api/v1/auth/me").status_code == 200


def test_change_password_still_ends_every_session(browsers):
    a, b = browsers
    r = a.post("/api/v1/auth/change-password", json={"current_password": "brand-new-pass-1", "new_password": "another-pass-12"}, headers=H)
    assert r.status_code == 200, r.text
    assert a.get("/api/v1/auth/me").status_code == 200           # the re-issued cookie
    assert b.get("/api/v1/auth/me").status_code == 401


def test_a_cookie_without_a_sid_is_refused(world):
    payload = {k: v for k, v in GOOD.items() if k != "sid"}
    now = int(time.time())
    token = sessions._encode({**payload, "uid": world, "iat": now, "exp": now + 1000})
    with _make_client() as c:
        c.cookies.set(sessions.COOKIE_NAME, token)
        assert c.get("/api/v1/auth/me").status_code == 401


def test_two_logins_get_two_different_sids(world):
    with _make_client() as a, _make_client() as b:
        sids = [sessions.verify(_login(c).cookies.get(sessions.COOKIE_NAME) or c.cookies.get(sessions.COOKIE_NAME))["sid"] for c in (a, b)]
    assert sids[0] != sids[1]
