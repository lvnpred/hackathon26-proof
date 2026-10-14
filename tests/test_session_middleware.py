"""Session middleware: public paths, CSRF header, 401/303, must-change gate, scope reaches the route. Offline."""
import asyncio

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from doctor_dictation import accounts as A
from doctor_dictation import clinics
from doctor_dictation import sessions
from doctor_dictation.api.session import SessionMiddleware
from doctor_dictation.scope import current_scope

H = {"X-DD-Client": "1"}


@pytest.fixture()
def world(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    uid, _ = A.create_user("rao", "dr.rao", password="rao-password-1")
    return {"uid": uid}


def _app():
    app = FastAPI()
    app.add_middleware(SessionMiddleware)

    @app.get("/api/v1/whoami")
    async def whoami(request: Request):
        inner = await asyncio.to_thread(current_scope)          # the scope must follow a worker thread
        s = current_scope()
        return {"clinic": s.clinic_slug, "user": s.username, "role": s.role, "uid": s.user_id,
                "thread_clinic": inner.clinic_slug, "state": request.state.identity.username}

    @app.get("/")
    async def index():
        return {"page": "index"}

    @app.get("/login")
    async def login_page():
        return {"page": "login"}

    @app.post("/api/v1/auth/login")
    async def login():
        return {"ok": True}

    @app.post("/api/v1/auth/change-password")
    async def change():
        return {"ok": True}

    @app.post("/api/v1/thing")
    async def thing():
        return {"ok": True}

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    return app


def _cookie(world, ver=0, clinic="rao"):
    return {sessions.COOKIE_NAME: sessions.sign(clinic, world["uid"], ver)}


def _client(world=None, **cookie_kw):
    c = TestClient(_app(), follow_redirects=False)
    if world is not None:
        c.cookies.update(_cookie(world, **cookie_kw))
    return c


def _clear_must_change(world):
    from contextlib import closing
    from doctor_dictation import db as dbmod
    from doctor_dictation.scope import clinic_dir
    with closing(dbmod.get_conn(clinic_dir("rao") / "app.db")) as c:
        c.execute("UPDATE users SET must_change_password = 0 WHERE id = ?", (world["uid"],))
        c.commit()


def test_public_paths_need_no_session(world):
    c = _client()
    assert c.get("/api/health").status_code == 200
    assert c.get("/login").status_code == 200


def test_no_cookie_gives_401_for_api_and_post_but_303_for_a_page(world):
    c = _client()
    r = c.get("/api/v1/whoami")
    assert (r.status_code, r.json()) == (401, {"error": "sign in required"})
    assert c.post("/api/v1/thing", headers=H).status_code == 401
    r = c.get("/")
    assert (r.status_code, r.headers["location"]) == (303, "/login")


def test_tampered_cookie_is_rejected(world):
    c = _client()
    c.cookies.set(sessions.COOKIE_NAME, sessions.sign("rao", world["uid"], 0)[:-3] + "AAA")
    assert c.get("/api/v1/whoami").status_code == 401


def test_unsafe_methods_need_the_csrf_header_including_login(world):
    c = _client(world)
    _clear_must_change(world)
    for method in ("post", "put", "delete", "patch"):
        r = getattr(c, method)("/api/v1/thing")
        assert (r.status_code, r.json()["error"]) == (403, "missing X-DD-Client header"), method
    assert c.post("/api/v1/auth/login").status_code == 403           # public path, still needs the header
    assert c.post("/api/v1/auth/login", headers=H).status_code == 200
    assert c.post("/api/v1/thing", headers=H).status_code == 200


def test_options_is_never_blocked(world):
    assert _client().options("/api/v1/thing").status_code != 403


def test_route_runs_inside_the_users_clinic_scope(world):
    _clear_must_change(world)
    r = _client(world).get("/api/v1/whoami")
    assert r.status_code == 200
    assert r.json() == {"clinic": "rao", "user": "dr.rao", "role": "doctor", "uid": world["uid"],
                        "thread_clinic": "rao", "state": "dr.rao"}
    assert current_scope() is None                                   # reset after the request


def test_must_change_password_gates_everything_but_three_endpoints(world):
    c = _client(world)                                               # new users start with must_change_password = 1
    r = c.get("/api/v1/whoami")
    assert (r.status_code, r.json()["code"]) == (403, "must_change_password")
    assert c.post("/api/v1/thing", headers=H).status_code == 403
    assert c.post("/api/v1/auth/change-password", headers=H).status_code == 200
    r = c.get("/")
    assert (r.status_code, r.headers["location"]) == (303, "/login")


def test_session_version_mismatch_ends_the_session(world):
    _clear_must_change(world)
    assert _client(world, ver=0).get("/api/v1/whoami").status_code == 200
    assert _client(world, ver=1).get("/api/v1/whoami").status_code == 401


def test_failed_clinic_in_app_state_blocks_its_users(world):
    _clear_must_change(world)
    app = _app()
    app.state.failed_clinics = frozenset({"rao"})
    c = TestClient(app, follow_redirects=False)
    c.cookies.update(_cookie(world))
    assert c.get("/api/v1/whoami").status_code == 401


def test_single_mode_passes_everything_through(tmp_path, monkeypatch):
    monkeypatch.delenv("MULTI_CLINIC", raising=False)
    c = TestClient(_app(), follow_redirects=False)
    assert c.get("/") .status_code == 200
    assert c.post("/api/v1/thing").status_code == 200                # no CSRF header needed, no session


def test_non_http_scopes_pass_through(world):
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["type"])

    asyncio.run(SessionMiddleware(inner)({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]


@pytest.mark.parametrize("shape", ['pref={"x": 1}; {c}', "x=a b; {c}", "{c}; theme=dark mode"])
def test_a_malformed_neighbouring_cookie_does_not_hide_the_session_cookie(world, shape):
    _clear_must_change(world)
    token = sessions.sign("rao", world["uid"], 0)
    raw = shape.replace("{c}", f"{sessions.COOKIE_NAME}={token}")
    r = TestClient(_app(), follow_redirects=False).get("/api/v1/whoami", headers={"Cookie": raw})
    assert r.status_code == 200, raw
