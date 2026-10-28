"""Auth in the seeded world (spec 6.2, 13.1): forged and expired cookies, disable and reset end sessions, CSRF on
every write route, a lockout stays per user, and unknown-user timing stays close to a wrong password. Offline."""
import json
import os
import re
import statistics
import time
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from doctor_dictation import authn, passwords, sessions
from isolation_fixtures import (A, B, H, disable_user, enable_user, fingerprint, login, reset_user, sql, user_id,
                                world)  # noqa: F401

BAD = {"error": "Wrong username or password"}


def _me_status(app, token):
    c = TestClient(app, follow_redirects=False)
    c.cookies.set(sessions.COOKIE_NAME, token)
    return c.get("/api/v1/auth/me").status_code


def _fresh_login(app, username, password=None):
    return login(TestClient(app, follow_redirects=False), username, password)


def test_a_cookie_edited_to_name_another_clinic_is_rejected(world, monkeypatch):
    body, sig = world.rao.cookies.get(sessions.COOKIE_NAME).split(".")
    payload = json.loads(sessions._unb64(body))
    payload["clinic"] = B
    forged = sessions._b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()) + "." + sig
    real = os.environ["SESSION_SECRET"]
    monkeypatch.setenv("SESSION_SECRET", "a-different-secret-" + "z" * 30)
    foreign = sessions.sign(B, 1, 0)                      # validly signed, but with someone else's key
    monkeypatch.setenv("SESSION_SECRET", real)
    for token in (forged, foreign):
        assert _me_status(world.app, token) == 401


def test_an_expired_cookie_is_rejected_but_a_fresh_one_for_the_same_user_works(world):
    rao = user_id(world, "dr.rao")
    ver = sql(A, "SELECT session_version FROM users WHERE id = ?", rao)[0][0]
    stale = sessions.sign(A, rao, ver, now=time.time() - sessions.LIFETIME_SECONDS - 5)
    assert _me_status(world.app, stale) == 401
    assert _me_status(world.app, sessions.sign(A, rao, ver)) == 200


def test_disabling_a_colleague_ends_their_session_at_once(world):
    mehta = user_id(world, "dr.mehta")
    assert world.mehta.get("/api/v1/auth/me").status_code == 200
    assert disable_user(world.rao_admin, mehta).status_code == 200
    assert world.mehta.get("/api/v1/auth/me").status_code == 401
    assert _fresh_login(world.app, "dr.mehta").status_code == 401
    assert enable_user(world.rao_admin, mehta).status_code == 200
    assert _fresh_login(world.app, "dr.mehta").status_code == 200


def test_a_password_reset_ends_the_session_and_retires_the_old_password(world):
    assert reset_user(world.rao_admin, user_id(world, "dr.mehta")).status_code == 200
    assert world.mehta.get("/api/v1/auth/me").status_code == 401
    assert _fresh_login(world.app, "dr.mehta").status_code == 401


def test_every_write_route_refuses_a_request_without_the_csrf_header(world):
    before = fingerprint(A)
    wrong, checked = [], 0
    for path, ops in world.app.openapi()["paths"].items():
        for method in (m.upper() for m in ops):
            if method not in {"POST", "PUT", "DELETE", "PATCH"}:
                continue
            r = world.rao.request(method, re.sub(r"\{[^}]+\}", "1", path), json={})
            checked += 1
            if (r.status_code, r.json()) != (403, {"error": "missing X-DD-Client header"}):
                wrong.append(f"{method} {path} -> {r.status_code}")
    assert checked >= 10 and not wrong, wrong
    assert fingerprint(A) == before
    assert world.rao.get("/api/v1/auth/me").status_code == 200          # the refused logout ended nothing


def test_a_lockout_is_per_username_and_ip_so_other_users_in_both_clinics_still_sign_in(world):
    for _ in range(5):
        assert _fresh_login(world.app, "dr.rao", "wrong-password-0").status_code == 401
    r = _fresh_login(world.app, "dr.rao")
    assert (r.status_code, r.json()) == (401, BAD)                        # locked: same answer as a wrong password
    assert _fresh_login(world.app, "dr.iyer").status_code == 200
    assert _fresh_login(world.app, "dr.mehta").status_code == 200
    assert world.rao.get("/api/v1/auth/me").status_code == 200           # an open session survives a lockout


def test_unknown_usernames_cost_about_the_same_as_a_wrong_password(world):
    def took(username):
        start = time.perf_counter()
        assert _fresh_login(world.app, username, "not-the-password-1").status_code == 401
        return time.perf_counter() - start

    took("dr.iyer")                                                     # warm up: first clinic open
    took("warm-up-ghost")                                               # warm up: the cached dummy hash
    known = statistics.median(took("dr.rao") for _ in range(3))
    unknown = statistics.median(took(f"ghost-{i}") for i in range(3))
    assert 0.25 < unknown / known < 4, (unknown, known)                 # a loose bound, not a timing test


def _scrypt_counter(monkeypatch):
    """Count every scrypt computation: verify_password and dummy_verify both go through passwords._scrypt."""
    calls = []
    real = passwords._scrypt

    def counted(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(passwords, "_scrypt", counted)
    return calls


def test_every_kind_of_failed_login_costs_exactly_one_scrypt(world, monkeypatch):
    passwords.dummy_verify("warm-up")           # the first dummy_verify also hashes the dummy: warm it before counting
    calls = _scrypt_counter(monkeypatch)
    cases = {}
    calls.clear()
    assert _fresh_login(world.app, "dr.iyer", "wrong-password-0").status_code == 401
    cases["wrong password, real user"] = len(calls)
    calls.clear()
    assert _fresh_login(world.app, "nobody-here", "wrong-password-0").status_code == 401
    cases["unknown username"] = len(calls)
    sql(A, "UPDATE users SET is_active = 0 WHERE id = ?", user_id(world, "dr.mehta"))
    calls.clear()
    assert _fresh_login(world.app, "dr.mehta").status_code == 401           # the right password, but disabled
    cases["disabled user"] = len(calls)
    for _ in range(5):
        _fresh_login(world.app, "dr.rao", "wrong-password-0")
    calls.clear()
    assert _fresh_login(world.app, "dr.rao").status_code == 401             # the right password, but locked
    cases["locked pair"] = len(calls)
    assert cases == dict.fromkeys(cases, 1), cases


def test_wrong_password_and_unknown_username_answer_with_identical_bodies(world):
    wrong = _fresh_login(world.app, "dr.iyer", "wrong-password-0")
    ghost = _fresh_login(world.app, "nobody-here", "wrong-password-0")
    assert (wrong.status_code, wrong.content) == (ghost.status_code, ghost.content) and wrong.json() == BAD


def test_a_lock_expires_after_exactly_300_seconds_and_is_per_ip(world):
    t0 = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    password = "demo-iyer-pass-1"
    for _ in range(5):
        assert authn.authenticate("dr.iyer", "wrong-password-0", "10.0.0.1", now=t0) is None
    assert authn.authenticate("dr.iyer", password, "10.0.0.1", now=t0 + timedelta(seconds=1)) is None
    assert authn.authenticate("dr.iyer", password, "10.0.0.1", now=t0 + timedelta(seconds=299)) is None
    assert authn.authenticate("dr.iyer", password, "10.0.0.2", now=t0 + timedelta(seconds=1)) is not None   # per ip
    assert authn.authenticate("dr.iyer", password, "10.0.0.1", now=t0 + timedelta(seconds=300)) is not None


def test_an_inactive_flag_alone_ends_a_signed_in_session(world):
    """Straight SQL on is_active, no session_version bump: the next request must still be refused."""
    assert world.mehta.get("/api/v1/auth/me").status_code == 200
    before = sql(A, "SELECT session_version FROM users WHERE id = ?", user_id(world, "dr.mehta"))
    sql(A, "UPDATE users SET is_active = 0 WHERE id = ?", user_id(world, "dr.mehta"))
    assert sql(A, "SELECT session_version FROM users WHERE id = ?", user_id(world, "dr.mehta")) == before
    assert world.mehta.get("/api/v1/auth/me").status_code == 401


def test_logging_out_one_session_leaves_the_same_users_other_session_signed_in(world):
    other = TestClient(world.app, follow_redirects=False)
    assert login(other, "dr.rao").status_code == 200
    token = world.rao.cookies.get(sessions.COOKIE_NAME)
    assert world.rao.post("/api/v1/auth/logout", headers=H).status_code == 200
    assert other.get("/api/v1/auth/me").status_code == 200
    assert _me_status(world.app, token) == 401                              # the copied cookie is revoked
