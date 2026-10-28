"""Auth routes through the real app: login, cookie flags, throttling, me, change-password, logout. Offline."""
import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import accounts as A
from doctor_dictation import clinics
from doctor_dictation import db as dbmod
from doctor_dictation import sessions
from doctor_dictation.api.app import create_app
from doctor_dictation.scope import clinic_dir

H = {"X-DD-Client": "1"}
BAD = {"error": "Wrong username or password"}


@pytest.fixture()
def client(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    A.create_user("rao", "dr.rao", display_name="Dr. Rao", password="temp-password-1", role="doctor")
    with TestClient(create_app(), follow_redirects=False) as c:     # `with` runs the lifespan (_startup)
        yield c


def _login(c, user="dr.rao", pw="temp-password-1"):
    return c.post("/api/v1/auth/login", json={"username": user, "password": pw}, headers=H)


def _set_permanent(c, new="brand-new-pass-1"):
    assert _login(c).status_code == 200
    r = c.post("/api/v1/auth/change-password", json={"current_password": "temp-password-1", "new_password": new}, headers=H)
    assert r.status_code == 200, r.text
    return new


def test_login_sets_a_http_only_lax_cookie_and_reports_must_change(client):
    r = _login(client)
    assert (r.status_code, r.json()) == (200, {"ok": True, "must_change_password": True})
    cookie = r.headers["set-cookie"].lower()
    assert "dd_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "path=/" in cookie and "max-age=43200" in cookie and "secure" not in cookie


def test_cookie_is_secure_behind_an_https_proxy(client):
    r = client.post("/api/v1/auth/login", json={"username": "dr.rao", "password": "temp-password-1"},
                    headers={**H, "X-Forwarded-Proto": "https"})
    assert "secure" in r.headers["set-cookie"].lower()


def test_every_bad_login_has_the_identical_response(client):
    A.create_user("rao", "dr.off", password="off-password-12", role="doctor")
    with closing(dbmod.get_conn(clinic_dir("rao") / "app.db")) as c, c:
        c.execute("UPDATE users SET is_active = 0 WHERE username = 'dr.off'")
    cases = (("dr.rao", "wrong"), ("nobody", "whatever"), ("", ""), ("dr.off", "off-password-12"))
    seen = []
    for u, p in cases:
        r = _login(client, u, p)
        seen.append((r.status_code, r.json()["error"], "set-cookie" in r.headers))
    assert len(seen) == len(cases)
    assert set(seen) == {(401, BAD["error"], False)}


def test_oversized_credentials_are_422_with_no_cookie(client):
    r = _login(client, pw="x" * 5000)
    assert r.status_code == 422 and "set-cookie" not in r.headers


def test_five_failures_lock_and_the_right_password_is_then_refused(client):
    for _ in range(5):
        assert _login(client, pw="wrong").status_code == 401
    r = _login(client)
    assert (r.status_code, r.json()) == (401, BAD)


def test_me_returns_the_top_bar_fields(client):
    _login(client)
    r = client.get("/api/v1/auth/me")
    assert r.json() == {"clinic_slug": "rao", "clinic_name": "Rao Clinic", "username": "dr.rao",
                        "display_name": "Dr. Rao", "role": "doctor", "must_change_password": True, "is_owner": False}


def test_me_without_a_session_is_401(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_change_password_clears_the_gate_and_reissues_the_cookie(client):
    _login(client)
    old = client.cookies.get(sessions.COOKIE_NAME)
    _set_permanent(client)
    assert client.cookies.get(sessions.COOKIE_NAME) != old
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200 and r.json()["must_change_password"] is False
    assert client.get("/api/v1/profile").status_code == 200          # a normal route now works


def test_change_password_errors_are_400_with_the_reason(client):
    _login(client)
    body = lambda cur, new: {"current_password": cur, "new_password": new}
    r = client.post("/api/v1/auth/change-password", json=body("wrong-current", "brand-new-pass-1"), headers=H)
    assert (r.status_code, r.json()["error"]) == (400, "Current password is incorrect")
    r = client.post("/api/v1/auth/change-password", json=body("temp-password-1", "short"), headers=H)
    assert r.status_code == 400 and "10" in r.json()["error"]
    r = client.post("/api/v1/auth/change-password", json=body("temp-password-1", "temp-password-1"), headers=H)
    assert r.status_code == 400


def test_old_cookie_dies_after_a_password_change_elsewhere(client, multi):
    _login(client)
    stale = client.cookies.get(sessions.COOKIE_NAME)
    A.change_password(__import__("doctor_dictation.authn", fromlist=["x"]).load_identity(stale), "temp-password-1", "other-pass-123")
    client.cookies.set(sessions.COOKIE_NAME, stale)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_clears_the_cookie_and_audits(client):
    _set_permanent(client)
    r = client.post("/api/v1/auth/logout", headers=H)
    assert r.status_code == 200
    cleared = r.headers["set-cookie"].lower()
    assert cleared.startswith("dd_session=") and ("max-age=0" in cleared or 'dd_session=""' in cleared)
    with closing(dbmod.get_conn(clinic_dir("rao") / "app.db")) as c:
        row = c.execute("SELECT actor FROM audit_log WHERE action = 'logout'").fetchone()
    assert row["actor"] == "dr.rao"
    client.cookies.clear()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_without_the_csrf_header_is_403(client):
    r = client.post("/api/v1/auth/login", json={"username": "dr.rao", "password": "temp-password-1"})
    assert r.status_code == 403


def test_signed_in_user_reaches_real_routes_in_their_own_clinic_only(client):
    clinics.provision_clinic("iyer", "Iyer Clinic")
    A.create_user("iyer", "dr.iyer", password="iyer-password-1", role="doctor")
    _set_permanent(client)
    assert client.put("/api/v1/profile", json={"clinic_name": "Rao Changed"}, headers=H).status_code == 200
    mine = client.get("/api/v1/profile")
    assert (mine.status_code, mine.json()["clinic_name"]) == (200, "Rao Changed")
    with TestClient(create_app(), follow_redirects=False) as other:
        assert other.post("/api/v1/auth/login", json={"username": "dr.iyer", "password": "iyer-password-1"},
                          headers=H).status_code == 200
        assert other.post("/api/v1/auth/change-password",
                          json={"current_password": "iyer-password-1", "new_password": "iyer-new-pass-12"},
                          headers=H).status_code == 200
        theirs = other.get("/api/v1/profile")
        assert theirs.status_code == 200
        assert theirs.json()["clinic_name"] == ""      # a fresh clinic has an empty profile


def test_single_mode_answers_404_on_every_auth_route(tmp_path, monkeypatch):
    monkeypatch.delenv("MULTI_CLINIC", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    with TestClient(create_app()) as c:
        for method, url in (("post", "/api/v1/auth/login"), ("post", "/api/v1/auth/logout"),
                            ("get", "/api/v1/auth/me"), ("post", "/api/v1/auth/change-password"), ("get", "/login")):
            r = getattr(c, method)(url, **({"json": {}} if method == "post" else {}))
            assert (r.status_code, r.json()) == (404, {"error": "sign-in is not enabled"}), url


def test_a_locked_clinic_database_at_login_is_503_not_a_wrong_password(client, monkeypatch):
    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr("doctor_dictation.authn.authenticate", boom)
    r = _login(client)
    assert (r.status_code, r.json()) == (503, {"error": "try again"})
    assert "set-cookie" not in r.headers


def test_a_locked_database_during_change_password_is_503(client, monkeypatch):
    assert _login(client).status_code == 200

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr("doctor_dictation.accounts.change_password", boom)
    r = client.post("/api/v1/auth/change-password",
                    json={"current_password": "temp-password-1", "new_password": "brand-new-pass-1"}, headers=H)
    assert (r.status_code, r.json()) == (503, {"error": "try again"})
