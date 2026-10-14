# M2b: Login over HTTP (session middleware, auth routes, login page, operator commands)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the M2a primitives behind HTTP. In multi-clinic mode every request needs a valid session cookie, the request runs inside that user's clinic scope, and a signed-out browser lands on a login page. The operator gets commands to create the first user and reset passwords.

**Architecture:** One pure-ASGI middleware (`api/session.py`) does CSRF header check, public-path allow-list, cookie verification via `authn.load_identity`, the must-change-password gate, and wraps the downstream app in `use_scope(...)`. `api/auth.py` holds the five auth routes. `app.py` gets `_startup(app)` (secret check, failed-clinic list, safe purge). The frontend gets a login page and one `auth.js` that wraps `window.fetch`. In single mode (`MULTI_CLINIC` off) the middleware is a pass-through and the auth API answers 404, so today's behaviour and tests are untouched.

**Tech Stack:** FastAPI/Starlette (already installed), stdlib `http.cookies`, vanilla JS, pytest + `TestClient`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-14-multi-clinic-multi-doctor-design.md` section 6.2 (login flow, cookie, CSRF, public paths), 7.4 (`logout` audit), 8.2 (account part used by the CLI). **Requires M2a done** (`docs/superpowers/plans/2026-10-14-m2a-auth-primitives.md`): `passwords`, `sessions`, `accounts`, `authn`, `policy`, the users migration and the extended `tests/conftest.py` (`multi` fixture sets `SESSION_SECRET`).

**Plan 3 of 7 (M2b).** Before the first task run `.venv/bin/python -m pytest tests/ -q` and note `N` (after M2a it is 478 + 54 = 532, 1 skipped). **This plan adds 45 tests** (11 + 13 + 6 + 5 + 10) and edits one existing assertion (the route table in `tests/test_api_app.py`), so the count after it must be `N + 45`.

## Deliberate differences from the spec

- **CSRF check also covers PATCH**, and runs before the public-path check so `POST /api/v1/auth/login` needs the header too (login CSRF is real). `OPTIONS` is never blocked.
- **A user who must change their password is gated to three endpoints** (`change-password`, `logout`, `me`); an HTML navigation is redirected to `/login`, which shows the change-password form. The spec says "forces the change" without saying how.
- **Client IP for throttling is `request.client.host`.** Behind a reverse proxy run uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy>`; do not read `X-Forwarded-For` in app code (it is client-controlled).
- **`GET /login` in single mode is 404**, same as the auth API: there is nothing to sign in to.

## Global Constraints

- "Keep files under 500 lines": `doctor_dictation/admin.py` is about 150 lines and grows by about 90; `frontend/app.js` is not edited except the one script tag in `index.html`.
- Never run `git commit` or `git push` (user rule). Each task ends with "leave uncommitted".
- Environment variables are read at call time, never at import.
- Middleware is **pure ASGI** (a class with `__call__(scope, receive, send)`), never `BaseHTTPMiddleware`: that class runs the app in a separate task and the `ContextVar` scope would not reach the routes reliably.
- The response to a bad login is identical for wrong user, wrong password, locked, disabled and failed clinic: `401 {"error": "Wrong username or password"}`.
- Cookie `dd_session`: `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age=43200`, `Secure` only when the request is https (`request.url.scheme` or the first `X-Forwarded-Proto` value).
- Passwords and temporary passwords are printed by the CLI exactly once and never logged or audited.
- Tests never touch the network or `doctor_dictation/data/`: every test that needs a clinic uses the `multi` fixture and `TestClient`.

## Carry-overs from the M2a final review (apply while executing this plan)

- `authn.authenticate` can raise `sqlite3.Error` when a clinic database is locked at login (the success-path write is outside a try). In `api/auth.py` login, let it surface as a 503 `{"error": "try again"}`, never as the "Wrong username or password" 401.
- Every login (even unknown or locked) costs one scrypt on the default thread pool that `load_identity` also uses. Wrap `authenticate` in a module-level `asyncio.Semaphore(4)` so a login flood cannot starve signed-in traffic.
- `adopt-existing --first-user` must create its user through `accounts.create_user` (which indexes the username), never `db.create_user`.
- `lookup_username` takes an open directory connection: the CLI opens `open_directory()` itself.
- `RETURNING` (used by `accounts.change_password`) needs SQLite 3.35+; confirm the deploy image's SQLite.

## Review Focus

1. **Scope reaches the route** (`ContextVar` set by the middleware is visible in a route and in an `asyncio.to_thread` call inside it). Task 1 `test_route_runs_inside_the_users_clinic_scope`.
2. **Every non-public path is closed** without a cookie, with a tampered cookie, after a password change elsewhere, and while must-change-password is set. Task 1 tests.
3. **CSRF header** on every unsafe method including login. Task 1 `test_unsafe_methods_need_the_csrf_header_including_login`.
4. **A failed clinic is never recreated empty** by the startup purge. Task 3 `test_failed_clinic_is_not_recreated_by_the_startup_purge`.
5. **`adopt-existing --first-user` checks the username before moving any file.** Task 6 `test_adopt_first_user_rejects_a_taken_username_before_moving_anything`.

---

### Task 1: Session middleware

**Files:**
- Create: `doctor_dictation/api/session.py`, `tests/test_session_middleware.py`
- Modify: `doctor_dictation/api/app.py` (register the middleware, `_startup(app)` signature only; behaviour in Task 3)

**Interfaces:**
- Consumes: M2a `authn.load_identity`, `sessions.COOKIE_NAME`, `scope.Scope/use_scope/multi_clinic_enabled`.
- Produces (`doctor_dictation.api.session`): `PUBLIC_PATHS`, `GATE_PATHS`, `UNSAFE_METHODS`, `CSRF_HEADER = "x-dd-client"`; class `SessionMiddleware(app)`. After it runs, `request.state.identity` is the `sessions.Identity` and the downstream app runs inside `use_scope(Scope(clinic, user_id, username, role))`.
- Behaviour table (multi-clinic mode only; single mode passes everything through):

| Request | Result |
|---|---|
| non-http scope (lifespan, websocket) | pass through |
| `OPTIONS` | pass through |
| `POST/PUT/DELETE/PATCH` without `X-DD-Client: 1` | `403 {"error": "missing X-DD-Client header"}` |
| path in `PUBLIC_PATHS` | pass through (no scope) |
| no cookie / bad cookie / revoked session | `/api/*` or non-GET: `401 {"error": "sign in required"}`; HTML GET: `303 /login` |
| valid session, `must_change_password`, path not in `GATE_PATHS` | `/api/*` or non-GET: `403 {"error": "password change required", "code": "must_change_password"}`; HTML GET: `303 /login` |
| valid session | run app inside the scope |

`PUBLIC_PATHS = {"/login", "/login.css", "/login.js", "/api/health", "/health", "/api/v1/auth/login", "/favicon.ico"}`; `GATE_PATHS = {"/api/v1/auth/change-password", "/api/v1/auth/logout", "/api/v1/auth/me"}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_session_middleware.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_session_middleware.py -q`
Expected: ImportError for `doctor_dictation.api.session`.

- [ ] **Step 3: Write `doctor_dictation/api/session.py`**

```python
"""Session middleware (pure ASGI): CSRF header, public paths, cookie to identity, clinic scope.

Pure ASGI on purpose: ``BaseHTTPMiddleware`` runs the app in another task, so the ``ContextVar``
scope set here would not reliably reach the routes. Here ``await self.app(...)`` runs in this
task, inside ``use_scope``. In single mode (``MULTI_CLINIC`` off) everything passes through.
"""
from __future__ import annotations

import asyncio
from http.cookies import CookieError, SimpleCookie

from starlette.responses import JSONResponse, RedirectResponse

from doctor_dictation import authn
from doctor_dictation.scope import Scope, multi_clinic_enabled, use_scope
from doctor_dictation.sessions import COOKIE_NAME

CSRF_HEADER = b"x-dd-client"
UNSAFE_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})
PUBLIC_PATHS = frozenset({"/login", "/login.css", "/login.js", "/api/health", "/health",
                          "/api/v1/auth/login", "/favicon.ico"})
GATE_PATHS = frozenset({"/api/v1/auth/change-password", "/api/v1/auth/logout", "/api/v1/auth/me"})


def _cookie_token(headers: dict) -> str | None:
    raw = headers.get(b"cookie")
    if not raw:
        return None
    try:
        jar = SimpleCookie()
        jar.load(raw.decode("latin-1"))
        morsel = jar.get(COOKIE_NAME)
    except CookieError:
        return None
    return morsel.value if morsel else None


class SessionMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not multi_clinic_enabled() or scope["method"] == "OPTIONS":
            return await self.app(scope, receive, send)
        method, path = scope["method"], scope["path"]
        headers = dict(scope["headers"])
        if method in UNSAFE_METHODS and headers.get(CSRF_HEADER) != b"1":
            return await JSONResponse({"error": "missing X-DD-Client header"}, status_code=403)(scope, receive, send)
        if path in PUBLIC_PATHS:
            return await self.app(scope, receive, send)

        wants_json = path.startswith("/api") or method != "GET"
        token = _cookie_token(headers)
        failed = getattr(scope["app"].state, "failed_clinics", frozenset()) if "app" in scope else frozenset()
        ident = await asyncio.to_thread(authn.load_identity, token, None, failed) if token else None
        if ident is None:
            if wants_json:
                return await JSONResponse({"error": "sign in required"}, status_code=401)(scope, receive, send)
            return await RedirectResponse("/login", status_code=303)(scope, receive, send)
        if ident.must_change_password and path not in GATE_PATHS:
            if wants_json:
                return await JSONResponse({"error": "password change required", "code": "must_change_password"},
                                          status_code=403)(scope, receive, send)
            return await RedirectResponse("/login", status_code=303)(scope, receive, send)

        scope.setdefault("state", {})["identity"] = ident
        with use_scope(Scope(ident.clinic_slug, ident.user_id, ident.username, ident.role)):
            await self.app(scope, receive, send)
```

- [ ] **Step 4: Register it in `app.py`**

In `create_app()`, add the session middleware **before** the CORS middleware (the last one added is the outermost, so CORS headers also appear on 401/403 and preflights are answered first):

```python
    app.add_middleware(SessionMiddleware)   # innermost of the two: CORS wraps it
    app.add_middleware(CORSMiddleware, ...)  # unchanged
```

with `from doctor_dictation.api.session import SessionMiddleware`.

- [ ] **Step 5: Run the tests, then the suite**

Run: `.venv/bin/python -m pytest tests/test_session_middleware.py -q` → 11 passed.
Run: `.venv/bin/python -m pytest tests/ -q` → `N + 11` passed, 1 skipped. (Single mode is a pass-through, so no existing test changes.)

- [ ] **Step 6: Leave uncommitted.**

---

### Task 2: Auth routes

**Files:**
- Create: `doctor_dictation/api/auth.py`, `tests/test_auth_routes.py`
- Modify: `doctor_dictation/api/app.py` (include the router), `tests/test_api_app.py` (`EXPECTED_ROUTES`)

**Interfaces:**
- Consumes: Task 1 middleware; M2a `authn.authenticate`, `authn.clinic_name`, `accounts.change_password`, `accounts.AccountError`, `passwords.PasswordError`, `sessions.sign/COOKIE_NAME/LIFETIME_SECONDS`.
- Produces routes: `GET /login` (serves `frontend/login.html`), `POST /api/v1/auth/login {username, password}` → `200 {"ok": true, "must_change_password": bool}` + cookie, `POST /api/v1/auth/logout` → `200 {"ok": true}`, cookie cleared, audit `logout`; `GET /api/v1/auth/me` → `{clinic_slug, clinic_name, username, display_name, role, must_change_password}`; `POST /api/v1/auth/change-password {current_password, new_password}` → `200 {"ok": true}` with a fresh cookie, or `400 {"error": <message>}`. In single mode all five answer `404 {"error": "sign-in is not enabled"}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_auth_routes.py`:

```python
"""Auth routes through the real app: login, cookie flags, throttling, me, change-password, logout. Offline."""
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
    A.create_user("rao", "dr.rao", display_name="Dr. Rao", password="temp-password-1")
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
    shapes = {(_r := _login(client, u, p)).status_code: _r.json() for u, p in
              (("dr.rao", "wrong"), ("nobody", "whatever"), ("", ""))}
    assert shapes == {401: BAD}
    assert "set-cookie" not in _login(client, "dr.rao", "wrong").headers


def test_five_failures_lock_and_the_right_password_is_then_refused(client):
    for _ in range(5):
        assert _login(client, pw="wrong").status_code == 401
    r = _login(client)
    assert (r.status_code, r.json()) == (401, BAD)


def test_me_returns_the_top_bar_fields(client):
    _login(client)
    r = client.get("/api/v1/auth/me")
    assert r.json() == {"clinic_slug": "rao", "clinic_name": "Rao Clinic", "username": "dr.rao",
                        "display_name": "Dr. Rao", "role": "doctor", "must_change_password": True}


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
    assert r.status_code == 200 and "dd_session=\"\"" in r.headers["set-cookie"] or "max-age=0" in r.headers["set-cookie"].lower()
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
    A.create_user("iyer", "dr.iyer", password="iyer-password-1")
    _set_permanent(client)
    client.put("/api/v1/profile", json={"clinic_name": "Rao Changed"}, headers=H)
    with TestClient(create_app(), follow_redirects=False) as other:
        other.post("/api/v1/auth/login", json={"username": "dr.iyer", "password": "iyer-password-1"}, headers=H)
        other.post("/api/v1/auth/change-password",
                   json={"current_password": "iyer-password-1", "new_password": "iyer-new-pass-12"}, headers=H)
        assert other.get("/api/v1/profile").json().get("clinic_name") != "Rao Changed"


def test_single_mode_answers_404_on_every_auth_route(tmp_path, monkeypatch):
    monkeypatch.delenv("MULTI_CLINIC", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    with TestClient(create_app()) as c:
        for method, url in (("post", "/api/v1/auth/login"), ("post", "/api/v1/auth/logout"),
                            ("get", "/api/v1/auth/me"), ("post", "/api/v1/auth/change-password"), ("get", "/login")):
            r = getattr(c, method)(url, **({"json": {}} if method == "post" else {}))
            assert (r.status_code, r.json()) == (404, {"error": "sign-in is not enabled"}), url
```

(Adjust `/api/v1/profile` field names to what `GET/PUT /api/v1/profile` really returns; read `doctor_dictation/api/profile.py` first. The point of the last two tests is "own clinic only" and "404 in single mode", not the field name.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_auth_routes.py -q` → fails (no routes yet).

- [ ] **Step 3: Write `doctor_dictation/api/auth.py`**

```python
"""Auth routes: login, logout, me, change-password, and the login page. 404 when MULTI_CLINIC is off."""
import asyncio
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from doctor_dictation import accounts, authn
from doctor_dictation import db as dbmod
from doctor_dictation.passwords import PasswordError
from doctor_dictation.scope import multi_clinic_enabled
from doctor_dictation.sessions import COOKIE_NAME, LIFETIME_SECONDS, sign

router = APIRouter()
LOGIN_PAGE = Path(__file__).resolve().parents[2] / "frontend" / "login.html"
OFF = {"error": "sign-in is not enabled"}
BAD_LOGIN = {"error": "Wrong username or password"}


class LoginBody(BaseModel):
    username: str = ""
    password: str = ""


class ChangeBody(BaseModel):
    current_password: str = ""
    new_password: str = ""


def _is_https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or proto == "https"


def _set_cookie(response, request: Request, ident_or_parts) -> None:
    clinic, uid, version = ident_or_parts
    response.set_cookie(COOKIE_NAME, sign(clinic, uid, version), max_age=LIFETIME_SECONDS, httponly=True,
                        samesite="lax", path="/", secure=_is_https(request))


@router.get("/login")
def login_page():
    if not multi_clinic_enabled():
        return JSONResponse(status_code=404, content=OFF)
    return FileResponse(LOGIN_PAGE)


@router.post("/api/v1/auth/login")
async def login(request: Request, body: LoginBody):
    if not multi_clinic_enabled():
        return JSONResponse(status_code=404, content=OFF)
    ip = request.client.host if request.client else "unknown"
    failed = getattr(request.app.state, "failed_clinics", frozenset())
    ident = await asyncio.to_thread(authn.authenticate, body.username, body.password, ip, None, failed)
    if ident is None:
        return JSONResponse(status_code=401, content=BAD_LOGIN)
    response = JSONResponse({"ok": True, "must_change_password": ident.must_change_password})
    _set_cookie(response, request, (ident.clinic_slug, ident.user_id, ident.session_version))
    return response


@router.post("/api/v1/auth/logout")
async def logout(request: Request):
    if not multi_clinic_enabled():
        return JSONResponse(status_code=404, content=OFF)
    ident = request.state.identity

    def _audit():
        with closing(dbmod.get_conn()) as conn:                    # scope set by the middleware
            dbmod.log_audit(conn, action="logout", entity="user", entity_id=str(ident.user_id))

    await asyncio.to_thread(_audit)
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/api/v1/auth/me")
async def me(request: Request):
    if not multi_clinic_enabled():
        return JSONResponse(status_code=404, content=OFF)
    i = request.state.identity
    name = await asyncio.to_thread(authn.clinic_name, i.clinic_slug)
    return {"clinic_slug": i.clinic_slug, "clinic_name": name, "username": i.username,
            "display_name": i.display_name, "role": i.role, "must_change_password": i.must_change_password}


@router.post("/api/v1/auth/change-password")
async def change_password(request: Request, body: ChangeBody):
    if not multi_clinic_enabled():
        return JSONResponse(status_code=404, content=OFF)
    i = request.state.identity
    try:
        version = await asyncio.to_thread(accounts.change_password, i, body.current_password, body.new_password)
    except (PasswordError, accounts.AccountError) as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    response = JSONResponse({"ok": True})
    _set_cookie(response, request, (i.clinic_slug, i.user_id, version))       # the old cookie is now revoked
    return response
```

Note the single-mode 404 must come **before** touching `request.state.identity` (it does not exist in single mode).

- [ ] **Step 4: Wire the router and update the route-table test**

In `create_app()`: `from doctor_dictation.api import auth` and add `auth` to the `for module in (health, stt, ...)` tuple. In `tests/test_api_app.py` add to `EXPECTED_ROUTES`:

```python
    ("GET", "/login"), ("POST", "/api/v1/auth/login"), ("POST", "/api/v1/auth/logout"),
    ("GET", "/api/v1/auth/me"), ("POST", "/api/v1/auth/change-password"),
```

- [ ] **Step 5: Run the tests, then the suite**

Run: `.venv/bin/python -m pytest tests/test_auth_routes.py tests/test_api_app.py -q` → all pass (`test_auth_routes.py`: 13).
Run: `.venv/bin/python -m pytest tests/ -q` → `N + 24` passed, 1 skipped.

- [ ] **Step 6: Leave uncommitted.**

---

### Task 3: Startup safety (`_startup(app)`) and the transcribe NoScope fix

**Files:**
- Modify: `doctor_dictation/api/app.py`, `doctor_dictation/api/stt.py`
- Test: `tests/test_startup.py` (new)

**Interfaces:**
- Produces: `_startup(app)` sets `app.state.failed_clinics` (a `frozenset` of slugs); in multi-clinic mode it calls `sessions.session_secret()` first (so a missing or short `SESSION_SECRET` aborts startup with `SecretError`), prints a warning when `DEV_INSECURE_SESSION_SECRET` is set, and **skips the purge for failed clinics**. `stt._doctor_top` lets `NoScope` propagate (the existing 401 handler answers) instead of returning "no hints".

**Why the skip matters:** `templates_api.purge_on_startup()` calls `_open()`, which calls `get_conn()`, which creates the folder and an empty `app.db` when the file is missing. For a registered clinic whose files were lost, `migrate_all` reports the failure and the purge would then silently replace the data with an empty database. This is the M1 fix that was parked.

- [ ] **Step 1: Write the failing tests**

`tests/test_startup.py`:

```python
"""Startup: secret check, failed clinics recorded and never recreated, dev-flag warning. Offline."""
import shutil

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import clinics
from doctor_dictation.api.app import create_app
from doctor_dictation.scope import clinic_dir
from doctor_dictation.sessions import SecretError


def test_multi_mode_refuses_to_start_without_a_real_secret(multi, monkeypatch):
    monkeypatch.delenv("SESSION_SECRET")
    with pytest.raises(SecretError):
        with TestClient(create_app()):
            pass


def test_single_mode_does_not_need_a_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("MULTI_CLINIC", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with TestClient(create_app()) as c:
        assert c.get("/api/health").status_code == 200


def test_dev_flag_warns_and_starts(multi, monkeypatch, capsys):
    monkeypatch.delenv("SESSION_SECRET")
    monkeypatch.setenv("DEV_INSECURE_SESSION_SECRET", "1")
    with TestClient(create_app()):
        pass
    assert "DEV_INSECURE_SESSION_SECRET" in capsys.readouterr().err


def test_failed_clinic_is_recorded_and_other_clinics_still_serve(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    clinics.provision_clinic("iyer", "Iyer Clinic")
    shutil.rmtree(clinic_dir("rao"))
    app = create_app()
    with TestClient(app) as c:
        assert app.state.failed_clinics == frozenset({"rao"})
        assert c.get("/api/health").status_code == 200


def test_failed_clinic_is_not_recreated_by_the_startup_purge(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    shutil.rmtree(clinic_dir("rao"))
    with TestClient(create_app()):
        pass
    assert not (clinic_dir("rao") / "app.db").exists()


def test_transcribe_without_a_scope_is_401_not_an_unpersonalised_success(multi, monkeypatch):
    from doctor_dictation.api import stt
    from doctor_dictation.scope import NoScope
    with pytest.raises(NoScope):
        stt._doctor_top(10)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_startup.py -q` → fails.

- [ ] **Step 3: Edit `app.py`**

Replace `_startup` and the `lifespan` call:

```python
def _startup(app: FastAPI) -> None:
    """Single mode: migrate the one database. Multi-clinic: check the session secret (the app
    refuses to start without one), migrate every clinic (one bad clinic is reported and its
    users are locked out, not fatal), then purge each healthy clinic's expired template drafts."""
    app.state.failed_clinics = frozenset()
    if not multi_clinic_enabled():
        dbmod.init_db()
        templates_api.purge_on_startup()
        return
    sessions.session_secret()                                   # raises SecretError: refuse to boot
    if os.getenv(sessions.DEV_FLAG_ENV, "").strip() == "1":     # same test as sessions.session_secret
        print(f"warning: {sessions.DEV_FLAG_ENV} is set: sessions are signed with a public key. "
              "Local development only.", file=sys.stderr)
    _done, failed = clinics.migrate_all()
    app.state.failed_clinics = frozenset(failed)
    for slug, why in failed.items():
        print(f"warning: clinic {slug} was not migrated: {why}", file=sys.stderr)
    for slug in clinics.for_each_clinic():
        if slug in failed:       # purge's get_conn would recreate an empty app.db for a lost clinic
            continue
        templates_api.purge_on_startup()
```

`lifespan` becomes `_startup(app)` (rename the parameter from `_app` to `app`). Add `import os` and `from doctor_dictation import sessions`. Do not `break` or raise out of the `for_each_clinic` loop (it holds the scope across `yield`); `continue` is fine.

- [ ] **Step 4: Edit `api/stt.py`**

```python
    except NoScope:
        raise                      # a missing scope is an auth bug, not "no hints"
    except Exception as exc:  # noqa: BLE001 - hints are optional
```

with `from doctor_dictation.scope import NoScope`. Put the `except NoScope` clause **before** the broad one.

- [ ] **Step 5: Run the tests, then the suite**

Run: `.venv/bin/python -m pytest tests/test_startup.py -q` → 6 passed.
Run: `.venv/bin/python -m pytest tests/ -q` → `N + 30` passed, 1 skipped (11 + 13 + 6). (Existing tests that call `_startup()` with no argument: grep `_startup(` in `tests/` and pass an app; the earlier survey found none.)

- [ ] **Step 6: Leave uncommitted.**

---

### Task 4: Frontend (login page, `auth.js`, sign-out)

**Files:**
- Create: `frontend/login.html`, `frontend/login.css`, `frontend/login.js`, `frontend/auth.js`
- Modify: `frontend/index.html` (one script tag, one button), `frontend/styles.css` only if the sign-out button needs a rule (reuse the existing `.topbar-actions button` style first)
- Test: `tests/test_frontend_auth.py` (static checks, no browser)

**Interfaces:**
- `auth.js` replaces `window.fetch` with a wrapper that (a) adds `X-DD-Client: 1` to POST/PUT/DELETE/PATCH, (b) on a 401 or on a 403 with `code === "must_change_password"` redirects to `/login` (guarded so it fires once), (c) otherwise returns the response untouched. It also fills `#topClinic` / `#topDoctor` from `/api/v1/auth/me` **only when the user is signed in** (in single mode `/me` is 404 and the wrapper must not redirect), and wires `#signOutBtn`.
- Because `auth.js` wraps `window.fetch`, `app.js` and `letterhead.js` need **no edits**. Load `auth.js` before `app.js`.
- `login.js`: one page, two states. State A: username and password form (`POST /api/v1/auth/login`; on `must_change_password` switch to state B). State B: current/new/confirm form (`POST /api/v1/auth/change-password`, then go to `/`). On load it calls `/api/v1/auth/me`: 200 with `must_change_password` shows state B, 200 without goes to `/`, 401 shows state A. Error text comes from `body.error`; the page never says which of username/password was wrong.

- [ ] **Step 1: Write the static test**

`tests/test_frontend_auth.py`:

```python
"""The browser side is plain JS; check the wiring that must not regress. No browser needed."""
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def test_auth_js_loads_before_app_js():
    html = _read("index.html")
    assert html.index("auth.js") < html.index("app.js")


def test_index_has_a_sign_out_button():
    assert 'id="signOutBtn"' in _read("index.html")


def test_auth_js_adds_the_csrf_header_and_handles_401_and_the_gate():
    js = _read("auth.js")
    assert "X-DD-Client" in js and "/login" in js
    assert "must_change_password" in js and "401" in js
    assert re.search(r"POST|PUT|DELETE|PATCH", js)


def test_login_page_posts_to_the_auth_routes_and_never_names_the_wrong_field():
    js, html = _read("login.js"), _read("login.html")
    assert "/api/v1/auth/login" in js and "/api/v1/auth/change-password" in js
    assert 'type="password"' in html
    assert "username is wrong" not in js.lower() and "password is wrong" not in js.lower()


def test_login_assets_are_the_public_ones_the_middleware_allows():
    from doctor_dictation.api.session import PUBLIC_PATHS
    html = _read("login.html")
    for asset in ("login.css", "login.js"):
        assert asset in html and "/" + asset in PUBLIC_PATHS
    assert "auth.js" not in html          # the login page must not redirect to itself
```

- [ ] **Step 2: Run to verify failure** (`FileNotFoundError` for `auth.js`).

- [ ] **Step 3: Write the files**

`frontend/auth.js`:

```js
/* Session plumbing for the main app. Wraps fetch so app.js and letterhead.js need no changes. */
(function () {
  "use strict";
  const UNSAFE = new Set(["POST", "PUT", "DELETE", "PATCH"]);
  const nativeFetch = window.fetch.bind(window);
  let leaving = false;

  function toLogin() {
    if (leaving) return;
    leaving = true;
    window.location.assign("/login");
  }

  window.fetch = async function (input, init) {
    const opts = Object.assign({}, init || {});
    const method = String(opts.method || (input && input.method) || "GET").toUpperCase();
    if (UNSAFE.has(method)) {
      const h = new Headers(opts.headers || (input && input.headers) || {});
      h.set("X-DD-Client", "1");
      opts.headers = h;                       // FormData bodies keep their own multipart Content-Type
    }
    const r = await nativeFetch(input, opts);
    if (r.status === 401) { toLogin(); return r; }
    if (r.status === 403) {
      try {
        const body = await r.clone().json();
        if (body && body.code === "must_change_password") toLogin();
      } catch (e) { /* not JSON: leave it to the caller */ }
    }
    return r;
  };

  async function init() {
    const out = document.getElementById("signOutBtn");
    let me = null;
    try {
      const r = await nativeFetch("/api/v1/auth/me");
      if (r.status === 200) me = await r.json();
      else if (r.status === 401) { toLogin(); return; }
    } catch (e) { /* offline: keep the page usable */ }
    if (!me) return;                          // single mode (404): no sign-out button, no top-bar change
    const clinic = document.getElementById("topClinic");
    const doctor = document.getElementById("topDoctor");
    if (clinic && me.clinic_name) clinic.textContent = me.clinic_name;
    if (doctor && me.display_name) doctor.textContent = me.display_name;
    if (out) {
      out.hidden = false;
      out.addEventListener("click", async () => {
        try { await window.fetch("/api/v1/auth/logout", { method: "POST" }); } catch (e) { /* ignore */ }
        window.location.assign("/login");
      });
    }
  }
  document.addEventListener("DOMContentLoaded", init);
})();
```

`app.js` later overwrites `#topClinic` / `#topDoctor` from the saved profile; check the order at `app.js` around line 158 and, if the profile wins, that is acceptable for M2b (M3 moves the doctor fields to the user). Do not edit `app.js` here.

`frontend/login.html`: standalone page (`<link href="login.css">`, `<script src="login.js">`, **no** `auth.js`), a `<form id="loginForm">` (username `autocomplete="username"`, password `autocomplete="current-password"`), a `<form id="changeForm" hidden>` (current `autocomplete="current-password"`, new and confirm `autocomplete="new-password"`, hint "at least 10 characters"), an `<p id="msg" role="alert">`. `frontend/login.css`: a centred card reusing the CSS variables from `styles.css` where possible (copy the few colour values; the login page cannot load `styles.css` unless it is made public, so keep it self-contained).

`frontend/login.js` (outline, write it in full):

```js
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const H = { "Content-Type": "application/json", "X-DD-Client": "1" };
  const msg = (t) => { $("msg").textContent = t || ""; };
  const show = (which) => { $("loginForm").hidden = which !== "login"; $("changeForm").hidden = which !== "change"; };
  async function post(url, body) {
    const r = await fetch(url, { method: "POST", headers: H, body: JSON.stringify(body) });
    let data = {}; try { data = await r.json(); } catch (e) { /* keep {} */ }
    return { ok: r.ok, status: r.status, data };
  }
  $("loginForm").addEventListener("submit", async (e) => {
    e.preventDefault(); msg("");
    const r = await post("/api/v1/auth/login", { username: $("username").value, password: $("password").value });
    if (!r.ok) { msg(r.data.error || "Could not sign in"); return; }
    if (r.data.must_change_password) { show("change"); $("current").value = $("password").value; $("newpw").focus(); }
    else window.location.assign("/");
  });
  $("changeForm").addEventListener("submit", async (e) => {
    e.preventDefault(); msg("");
    if ($("newpw").value !== $("confirm").value) { msg("The two new passwords do not match"); return; }
    const r = await post("/api/v1/auth/change-password", { current_password: $("current").value, new_password: $("newpw").value });
    if (!r.ok) { msg(r.data.error || "Could not change the password"); return; }
    window.location.assign("/");
  });
  (async () => {                                 // already signed in? skip the form
    try {
      const r = await fetch("/api/v1/auth/me");
      if (r.status !== 200) return;
      const me = await r.json();
      if (me.must_change_password) show("change"); else window.location.assign("/");
    } catch (e) { /* stay on the form */ }
  })();
})();
```

`frontend/index.html`: add `<button id="signOutBtn" type="button" hidden title="Sign out">Sign out</button>` after the Profile button, and `<script src="auth.js?v=1"></script>` immediately before the `app.js?v=18` tag. Bump the app.js cache-buster only if `app.js` changed (it does not).

- [ ] **Step 4: Run the tests, then the suite**

Run: `.venv/bin/python -m pytest tests/test_frontend_auth.py -q` → 5 passed. Whole suite → `N + 35`.

- [ ] **Step 5: Manual check (needs a browser; the Playwright skill can drive it).** Covered by the smoke test in Task 7.

- [ ] **Step 6: Leave uncommitted.**

---

### Task 5: Operator commands for users

**Files:**
- Modify: `doctor_dictation/admin.py`, `tests/test_admin.py`

**Interfaces:**
- `create-clinic ... --first-user USERNAME [--display-name N]`: after the clinic is created, create that user with a generated temporary password; print the password **once**. A bad or taken username must fail **before** the clinic is created (pre-check with `accounts.check_username` and `logins.lookup_username`), leaving no clinic behind.
- `create-user --clinic SLUG --username U [--display-name N] [--role doctor|assistant|admin]`: prints the temporary password once.
- `reset-password --user U`: prints a new temporary password once; the target's sessions end (session_version bump is inside `accounts.reset_password`).
- `adopt-existing ... --first-user U`: copies `doctor_name`, `qualifications`, `reg_no` from the saved `clinic_profile` into the new user. **The username pre-check happens before any file moves** (`_adopt` today validates then moves; add the check beside `check_clinic_fields`). If creating the user fails after the move, print the recovery command (`create-user --clinic ... --username ...`) instead of a traceback.
- All four map `accounts.AccountError`, `passwords.PasswordError` and `DirectoryError` to `error: ...` on stderr and exit code 1 (they are `ValueError` subclasses, which `main` already catches).
- File size: `admin.py` must stay under 500 lines; move the user commands into `doctor_dictation/admin_users.py` if it would not.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_admin.py`; 10 tests)

```python
def test_create_clinic_with_first_user_prints_the_password_once(multi, capsys):
    assert admin.main(["create-clinic", "--slug", "rao", "--name", "Rao Clinic", "--first-user", "dr.rao",
                       "--display-name", "Dr. Rao"]) == 0
    out = capsys.readouterr().out
    m = re.search(r"temporary password: (\S+)", out)
    assert m and len(m.group(1)) == 16
    assert authn.authenticate("dr.rao", m.group(1), "1.1.1.1") is not None


def test_create_clinic_first_user_bad_username_leaves_no_clinic(multi, capsys):
    assert admin.main(["create-clinic", "--slug", "rao", "--name", "Rao", "--first-user", "x"]) == 1
    assert "username" in capsys.readouterr().err
    assert not (multi / "clinics" / "rao").exists()


def test_create_clinic_first_user_taken_username_leaves_no_clinic(multi, capsys):
    admin.main(["create-clinic", "--slug", "rao", "--name", "Rao", "--first-user", "dr.rao"])
    assert admin.main(["create-clinic", "--slug", "iyer", "--name", "Iyer", "--first-user", "DR.RAO"]) == 1
    assert not (multi / "clinics" / "iyer").exists()


def test_create_user_adds_a_second_user_and_audits(multi, capsys):
    admin.main(["create-clinic", "--slug", "rao", "--name", "Rao"])
    assert admin.main(["create-user", "--clinic", "rao", "--username", "dr.mehta", "--display-name", "Dr. Mehta"]) == 0
    assert "temporary password:" in capsys.readouterr().out


def test_create_user_unknown_clinic_and_bad_role_fail_cleanly(multi, capsys):
    assert admin.main(["create-user", "--clinic", "nope", "--username", "dr.x"]) == 1
    admin.main(["create-clinic", "--slug", "rao", "--name", "Rao"])
    assert admin.main(["create-user", "--clinic", "rao", "--username", "dr.x", "--role", "wizard"]) == 2  # argparse choices


def test_reset_password_ends_the_old_session_and_prints_a_new_password(multi, capsys):
    admin.main(["create-clinic", "--slug", "rao", "--name", "Rao", "--first-user", "dr.rao"])
    pw = re.search(r"temporary password: (\S+)", capsys.readouterr().out).group(1)
    ident = authn.authenticate("dr.rao", pw, "1.1.1.1")
    token = sessions.sign(ident.clinic_slug, ident.user_id, ident.session_version)
    assert admin.main(["reset-password", "--user", "dr.rao"]) == 0
    new = re.search(r"temporary password: (\S+)", capsys.readouterr().out).group(1)
    assert new != pw and authn.load_identity(token) is None
    assert authn.authenticate("dr.rao", new, "1.1.1.1") is not None


def test_reset_password_unknown_user_is_an_error(multi, capsys):
    assert admin.main(["reset-password", "--user", "ghost"]) == 1


def test_adopt_first_user_copies_the_doctor_fields_from_the_saved_profile(tmp_path, monkeypatch, capsys):
    ...  # copy the setup of test_adopt_existing_moves_everything...; seed clinic_profile doctor_name/qualifications/reg_no;
         # run adopt-existing --first-user dr.old; assert the users row has those three fields and the profile row is unchanged.


def test_adopt_first_user_rejects_a_taken_username_before_moving_anything(tmp_path, monkeypatch, capsys):
    ...  # a user "dr.old" already exists in clinic A; adopt with --first-user dr.old; assert exit 1, source app.db still at its old path, no target folder.


def test_admin_never_logs_the_password_to_the_audit_log(multi, capsys):
    admin.main(["create-clinic", "--slug", "rao", "--name", "Rao", "--first-user", "dr.rao"])
    pw = re.search(r"temporary password: (\S+)", capsys.readouterr().out).group(1)
    with closing(dbmod.get_conn(S.clinic_dir("rao") / "app.db")) as c:
        assert pw not in " ".join(str(tuple(r)) for r in c.execute("SELECT * FROM audit_log"))
```

Fill the two `...` tests by copying the fixtures of the existing adopt tests in the same file (they already build an old single-mode data folder); keep the assertions listed in the comments.

- [ ] **Step 2: Run to verify failure** → new tests fail (unknown arguments).

- [ ] **Step 3: Implement**

- `_create`: if `args.first_user`: `accounts.check_username(args.first_user)` and a `lookup_username` check **before** `provision_clinic`; after it, `accounts.create_user(args.slug, args.first_user, display_name=args.display_name or "", actor="operator")` and print `f"user '{u}' created; temporary password: {pw}"` plus `"(shown once; the user must change it at first sign-in)"`. Remove the "no users yet" line when a user was created.
- `_create_user`, `_reset_password`: thin wrappers over `accounts.create_user` / `accounts.reset_password` with the same print format. `--role` uses `choices=accounts.ROLES`.
- `_adopt`: add `--first-user` and `--display-name`; run the username pre-check next to `check_clinic_fields`; after `create_clinic(d, ...)` read `doctor_name, qualifications, reg_no` from the moved `clinic_profile` row (`sqlite3` read, tolerate a missing table) and call `accounts.create_user(...)`; on failure print the recovery command and return 1.
- The module docstring "M1 commands ... Users arrive with M2" becomes the real list of commands.

- [ ] **Step 4: Run the tests, then the suite**

Run: `.venv/bin/python -m pytest tests/test_admin.py -q` → all pass.
Run: `.venv/bin/python -m pytest tests/ -q` → `N + 45` passed, 1 skipped; `tests/test_file_sizes.py` still passes.

- [ ] **Step 5: Leave uncommitted.**

---

### Task 6: `.env.example`, README note, curl smoke test

**Files:**
- Modify: `.env.example`, `README.md` (a short "Multi-clinic sign-in" paragraph; edit the existing file, do not add a new one)

- [ ] **Step 1: `.env.example`** (append under the multi-clinic block)

```
# Required when MULTI_CLINIC=1: signs session cookies. At least 32 random characters, e.g.
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
# SESSION_SECRET=
# Local development only: lets the app start without SESSION_SECRET (sessions are then forgeable).
# DEV_INSECURE_SESSION_SECRET=1
```

- [ ] **Step 2: Smoke test with a real server** (scratch data folder; nothing in `doctor_dictation/data/`)

```bash
export DATA_DIR=$(mktemp -d) MULTI_CLINIC=1 SESSION_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(48))")
.venv/bin/python -m doctor_dictation.admin create-clinic --slug rao --name "Rao Clinic" --first-user dr.rao   # note the password
.venv/bin/python -m uvicorn doctor_dictation.main:app --port 8765 &
curl -si localhost:8765/ | head -3                                       # 303 -> /login
curl -si localhost:8765/api/v1/profile | head -1                         # 401
curl -si localhost:8765/api/health | head -1                             # 200 (public)
curl -si -c jar -H 'X-DD-Client: 1' -H 'Content-Type: application/json' \
  -d '{"username":"dr.rao","password":"<temp>"}' localhost:8765/api/v1/auth/login   # 200 + Set-Cookie
curl -si -b jar localhost:8765/api/v1/profile | head -1                  # 403 must_change_password
# change the password through /login in a browser (or POST change-password), then:
curl -si -b jar localhost:8765/api/v1/profile | head -1                  # 200
kill %1
```

Then open `http://localhost:8765/` in a browser: expect redirect to `/login`, the forced change-password step, the app, and **Sign out** returning to `/login`. Report what you saw; do not claim the browser part passed if it was not driven.

- [ ] **Step 3: Whole-suite run and final count**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 45` passed, 1 skipped (Task 1: 11, Task 2: 13, Task 3: 6, Task 4: 5, Task 5: 10).

- [ ] **Step 4: Leave uncommitted and list the changed files** (`git status --short`).

---

## Self-review (against the spec)

- **6.2 cookie, CSRF, public paths, 401/303, logout/me/change-password, forced change:** Tasks 1 and 2. The "refuse to start without a secret" rule: Task 3.
- **7.4 `logout` audit:** Task 2 (`login`, `password_change` come from M2a).
- **Parked M1 fix (purge recreates a lost clinic's database):** Task 3.
- **Operator path to a first user and password reset:** Task 5.
- **Placeholder scan:** two test bodies in Task 5 are marked `...` with exact setup and assertions described, because they copy long fixtures that already exist in the same file; the implementer must fill them from `test_adopt_existing_moves_everything_even_with_the_old_db_open`.
- **Test count:** 11 + 13 + 6 + 5 + 10 = 45; running totals after each task are `N + 11`, `N + 24`, `N + 30`, `N + 35`, `N + 45`.
- **Order dependency:** Task 2 needs Task 1; Task 3 needs Task 2 only for `app.state.failed_clinics` being read by the middleware (Task 1 already tolerates its absence); Tasks 4 to 6 are independent of each other after Task 3.

## Not in this plan

Wiring `policy.can()` into routes and per-doctor authorship (M3); the Team screen and disable/enable users (M5); the CORS allow-list (D0a); account lockout alerts; remember-me or refresh of the 12-hour session; password-strength meter in the login page; moving the doctor fields from `clinic_profile` to the user in the UI (M3).
