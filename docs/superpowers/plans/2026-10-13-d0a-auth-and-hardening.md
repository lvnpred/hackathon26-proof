# D0a: Demo Login and Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the first (fake-patients-only) deployment behind one shared login, lock CORS to an allow-list, stamp the logged-in name on audit rows, add safe response headers, and show a "Demo, fake patients only" banner.

**Architecture:** `doctor_dictation/api/security.py` holds a pure-ASGI `BasicAuthMiddleware`, a pure-ASGI `SecurityHeadersMiddleware` and `install_security(app, settings)`, the single place that decides middleware order. The authenticated username travels in a `ContextVar` (`doctor_dictation/request_actor.py`) that `db.log_audit` reads when no `actor` is passed, so every route that writes an audit row (document save/resave, template upload/accept/discard) gets the actor without editing each route. The banner is a hidden strip in `index.html` that `app.js` reveals when `/api/health` says `demo: true`.

**Tech Stack:** Python 3.12 (`.venv`), FastAPI/Starlette, `hmac`, `contextvars`, pytest, vanilla JS/CSS. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` (sections 8.1-8.5); contracts file sections 4.1 and 4.8. Plan 14 of 15. **Adds 17 tests.** Run the suite first (`.venv/bin/python -m pytest tests/ -q`), note the count N, expect N + 17 at the end.

## Assumptions about earlier plans

- **B1a:** package `doctor_dictation`, absolute imports. **B1c (contract 4.1):** `config.py` has frozen `Settings`, `build_settings()`, `get_settings()`, `override_settings(monkeypatch, **fields) -> Settings`.
- **B1e:** `api/app.py::create_app()` calls `load_dotenv()`, then `app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)` (comment "D0a replaces this"); `api/health.py` serves `/api/health` and `/health`; the frontend mount is added last.
- **B2b/B2c:** template routes write audit rows through `db.log_audit(...)` (contract 4.6); the Letterhead panel is in the page; `index.html` loads `app.js?v=N` (`v=8` today).
- `load_secret(name)` takes any name (`backend/secret_loader.py:50`): env wins, else the secrets file.

## Global Constraints

- No file over 500 lines. Tests are offline: `override_settings`, a temp `DB_PATH`, no network.
- **No `git commit` or `git push`** (user rule): every task ends uncommitted. Existing status codes and JSON shapes do not change, except `/api/health` gaining `demo`.
- The password is never logged, never in a response body, never in `/api/health`. Settings are read at app-build or call time, never at import.

## Design decisions

- **Pure ASGI, not `BaseHTTPMiddleware`.** The latter runs the app in another task and wraps the body in a stream (cost on 8 MiB audio and PDF downloads, plus a history of `contextvars` surprises). Pure ASGI is about 40 lines with no body copy; a `ContextVar` set before `await self.app(...)` is visible in async and sync routes (prototype: both read `"dr"`).
- **Order, innermost to outermost: auth, CORS (only if configured), headers** (Starlette makes the last-added outermost). CORS must wrap auth because a browser sends the OPTIONS preflight **without** credentials; auth-outermost would 401 every preflight (prototype: preflight 200, and the 401 carries CORS headers so a cross-origin page can read it). Without CORS an OPTIONS request is not a valid preflight and gets 401 like anything else.
- **Compare** with `hmac.compare_digest` on username **and** password as two statements before combining; malformed headers compare empty bytes so the work is the same. Bytes, because `compare_digest` rejects non-ASCII `str`.
- **CORS:** `allow_credentials=True` only with an explicit list; `*` or a scheme-less entry makes `build_settings()` raise at startup; methods and headers are listed, not `*`.
- **CSP deferred.** Not verified against the B2c Letterhead panel (image/PDF previews may use blob, data or frame sources) or `app.js` style toggling; a wrong policy could blank a screen. Revisit as `Content-Security-Policy-Report-Only` after D0b. Shipped: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: SAMEORIGIN`.

---

### Task 1: Settings fields and `.env.example`

**Files:**
- Modify: `doctor_dictation/config.py` (`Settings`, `build_settings`); `.env.example` (append)
- Create: `tests/test_security_settings.py`

**Interfaces:**
- Produces: `Settings.demo_mode: bool`, `.demo_username: str`, `.demo_password: str`, `.allowed_origins: tuple[str, ...]`. Env: `DEMO_MODE`, `DEMO_USERNAME`, `DEMO_PASSWORD` (via `load_secret`), `ALLOWED_ORIGINS`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_security_settings.py`:
```python
"""D0a settings parse correctly and fail loud.  Run: .venv/bin/python -m pytest tests/test_security_settings.py -q"""
import pytest
from doctor_dictation.config import build_settings
@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for name in ("DEMO_MODE", "DEMO_USERNAME", "DEMO_PASSWORD", "ALLOWED_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SECRETS_FILE", str(tmp_path / "none.json"))
def test_defaults_are_open_and_same_origin():
    s = build_settings()
    assert s.demo_mode is False and (s.demo_username, s.demo_password) == ("", "")
    assert s.allowed_origins == ()
def test_env_values_are_parsed(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_USERNAME", "doctor1")
    monkeypatch.setenv("DEMO_PASSWORD", "pw-123")
    monkeypatch.setenv("ALLOWED_ORIGINS", " https://a.example/ , http://localhost:3000 ,,")
    s = build_settings()
    assert s.demo_mode is True and (s.demo_username, s.demo_password) == ("doctor1", "pw-123")
    assert s.allowed_origins == ("https://a.example", "http://localhost:3000")
def test_bad_origins_fail_at_startup(monkeypatch):
    for bad in ("*", "https://a.example,*", "a.example", "ftp://a.example"):
        monkeypatch.setenv("ALLOWED_ORIGINS", bad)
        with pytest.raises(ValueError, match="ALLOWED_ORIGINS"):
            build_settings()
```
- [ ] **Step 2: Run to verify it fails** — `.venv/bin/python -m pytest tests/test_security_settings.py -q`; expected 3 FAIL, `AttributeError: 'Settings' object has no attribute 'demo_mode'`.

- [ ] **Step 3: Implement.** Add at the end of the `Settings` fields (defaults keep every existing `Settings(...)` call valid):
```python
    # --- D0a: demo login and CORS ---
    demo_mode: bool = False
    demo_username: str = ""
    demo_password: str = ""
    allowed_origins: tuple = ()
```
Above `build_settings` add the parser, and add the four keywords to the `Settings(...)` call:
```python
def _origins_env(name: str) -> tuple:
    """Comma list of exact origins; '*' and scheme-less entries are errors."""
    out = []
    for item in os.getenv(name, "").split(","):
        item = item.strip().rstrip("/")
        if not item:
            continue
        if item == "*" or not item.startswith(("http://", "https://")):
            raise ValueError(f"{name} must list exact origins like https://host, got {item!r}")
        out.append(item)
    return tuple(out)
```
```python
        demo_mode=os.getenv("DEMO_MODE", "").strip().lower() in ("1", "true", "yes", "on"),
        demo_username=os.getenv("DEMO_USERNAME", "").strip(),
        demo_password=load_secret("DEMO_PASSWORD"),
        allowed_origins=_origins_env("ALLOWED_ORIGINS"),
```
Append to `.env.example`:
```
# --- Demo deployment (D0a): leave commented for local development ---
# Login needs BOTH set (prefer DEMO_PASSWORD in the secrets file); DEMO_MODE shows the banner.
# DEMO_USERNAME=demo
# DEMO_PASSWORD=change-me
# DEMO_MODE=true
# ALLOWED_ORIGINS=https://demo.example.com   # unset = same-origin only; never *
```
- [ ] **Step 4: Run to verify it passes** — `.venv/bin/python -m pytest tests/test_security_settings.py -q`; expected `3 passed`.

---

### Task 2: `BasicAuthMiddleware`, security headers, request actor

**Files:**
- Create: `doctor_dictation/request_actor.py`, `doctor_dictation/api/security.py`, `tests/test_security_middleware.py`

**Interfaces:**
- Produces: `request_actor.current_actor: ContextVar`; `security.BasicAuthMiddleware(app, username, password)`; `security.SecurityHeadersMiddleware(app)`; `security.install_security(app, settings) -> None`; `security.EXEMPT_PATHS`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_security_middleware.py`:
```python
"""Basic login, headers and request actor.  Run: .venv/bin/python -m pytest tests/test_security_middleware.py -q"""
import base64
from fastapi import FastAPI
from fastapi.testclient import TestClient
from doctor_dictation.api import security
from doctor_dictation.config import override_settings
from doctor_dictation.request_actor import current_actor
PW = "s3cret-pw-XYZ"
def _basic(user, pw):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}
def _client(monkeypatch, **fields):
    app = FastAPI()
    @app.get("/sync")
    def sync_route(): return {"actor": current_actor.get()}
    @app.get("/async")
    async def async_route(): return {"actor": current_actor.get()}
    for path in ("/health", "/api/health"):
        app.add_api_route(path, lambda: {"ok": True})
    security.install_security(app, override_settings(monkeypatch, **fields))
    return TestClient(app)
def _on(monkeypatch):
    return _client(monkeypatch, demo_username="doc", demo_password=PW)
def test_inert_unless_both_fields_are_set(monkeypatch):
    for fields in ({}, {"demo_username": "doc"}, {"demo_password": PW}):
        assert _client(monkeypatch, **fields).get("/sync").status_code == 200
def test_missing_header_gets_challenge_without_leaking_the_password(monkeypatch):
    r = _on(monkeypatch).get("/sync")
    assert r.status_code == 401 and r.json() == {"error": "authentication required"}
    assert r.headers["www-authenticate"] == 'Basic realm="Doctor Dictation"'
    assert r.headers["x-content-type-options"] == "nosniff"  # headers wrap 401s too
    assert PW not in r.text and PW not in str(dict(r.headers))
def test_right_credentials_pass_with_actor_and_headers(monkeypatch):
    c = _on(monkeypatch)
    r = c.get("/sync", headers=_basic("doc", PW))
    assert r.status_code == 200 and r.json() == {"actor": "doc"}
    assert c.get("/async", headers=_basic("doc", PW)).json() == {"actor": "doc"}
    assert r.headers["referrer-policy"] == "no-referrer" and r.headers["x-frame-options"] == "SAMEORIGIN"
    assert current_actor.get() is None  # reset after the request
def test_wrong_username_with_right_password_is_denied(monkeypatch):
    assert _on(monkeypatch).get("/sync", headers=_basic("other", PW)).status_code == 401
def test_wrong_password_and_malformed_headers_are_denied(monkeypatch):
    c = _on(monkeypatch)
    assert c.get("/sync", headers=_basic("doc", "nope")).status_code == 401
    for value in ("Bearer abc", "Basic", "Basic !!!not-base64", "Basic " + base64.b64encode(b"nocolon").decode()):
        assert c.get("/sync", headers={"Authorization": value}).status_code == 401, value
def test_health_paths_are_exempt(monkeypatch):
    c = _on(monkeypatch)
    assert c.get("/health").status_code == 200 and c.get("/api/health").status_code == 200
def test_both_fields_are_compared_even_when_the_username_is_wrong(monkeypatch):
    calls, real = [], security.hmac.compare_digest
    monkeypatch.setattr(security.hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    assert _on(monkeypatch).get("/sync", headers=_basic("other", PW)).status_code == 401
    assert len(calls) == 2
```
- [ ] **Step 2: Run to verify it fails** — `.venv/bin/python -m pytest tests/test_security_middleware.py -q`; expected collection error `No module named 'doctor_dictation.request_actor'`.

- [ ] **Step 3: Implement.** `doctor_dictation/request_actor.py`:
```python
"""Who is making the current request (set by the login middleware, read by the audit log)."""
from contextvars import ContextVar
current_actor: ContextVar = ContextVar("current_actor", default=None)
```
`doctor_dictation/api/security.py`:
```python
"""Demo login, CORS allow-list and response headers (D0a). Pure ASGI: no body buffering."""
import base64
import binascii
import hmac
import json
from fastapi.middleware.cors import CORSMiddleware
from doctor_dictation.request_actor import current_actor
EXEMPT_PATHS = frozenset({"/health", "/api/health"})
_DENIED = json.dumps({"error": "authentication required"}).encode()
class BasicAuthMiddleware:
    """HTTP Basic login for everything except the health paths. Nothing secret in any output."""
    def __init__(self, app, username: str, password: str):
        self.app = app
        self._user, self._pw = username.encode("utf-8"), password.encode("utf-8")
        self._enabled = bool(self._user and self._pw)
    def _who(self, headers):
        value = next((v for k, v in headers if k == b"authorization"), b"")
        scheme, _, token = value.partition(b" ")
        user = pw = b""
        if scheme.lower() == b"basic":
            try:
                user, _, pw = base64.b64decode(token.strip(), validate=True).partition(b":")
            except (binascii.Error, ValueError):
                user = pw = b""
        user_ok = hmac.compare_digest(user, self._user)  # both always run: no early exit
        pw_ok = hmac.compare_digest(pw, self._pw)
        return user.decode("utf-8", "replace") if (user_ok and pw_ok) else None
    async def __call__(self, scope, receive, send):
        if not self._enabled or scope["type"] != "http" or scope["path"] in EXEMPT_PATHS:
            return await self.app(scope, receive, send)
        who = self._who(scope["headers"])
        if who is None:
            await send({"type": "http.response.start", "status": 401, "headers": [
                (b"www-authenticate", b'Basic realm="Doctor Dictation"'),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_DENIED)).encode())]})
            return await send({"type": "http.response.body", "body": _DENIED})
        token = current_actor.set(who)
        try:
            await self.app(scope, receive, send)
        finally:
            current_actor.reset(token)
class SecurityHeadersMiddleware:
    """Headers that cannot break same-origin loading. CSP is deliberately not here."""
    _HEADERS = ((b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"),
                (b"x-frame-options", b"SAMEORIGIN"))
    def __init__(self, app):
        self.app = app
    async def __call__(self, scope, receive, send):
        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                have = {k.lower() for k, _ in message["headers"]}
                message["headers"] = list(message["headers"]) + [h for h in self._HEADERS if h[0] not in have]
            await send(message)
        await self.app(scope, receive, send_with_headers if scope["type"] == "http" else send)
def install_security(app, settings) -> None:
    """Add middleware innermost to outermost: login, CORS (if configured), headers."""
    if settings.demo_username and settings.demo_password:
        app.add_middleware(BasicAuthMiddleware,
                           username=settings.demo_username, password=settings.demo_password)
    if settings.allowed_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins),
                           allow_credentials=True, allow_methods=["GET", "POST", "PUT", "DELETE"],
                           allow_headers=["Authorization", "Content-Type"])
    app.add_middleware(SecurityHeadersMiddleware)
```
The app has no websocket routes, so the login only guards `http` scopes and lets other scope types through unchanged.

- [ ] **Step 4: Run to verify it passes** — `.venv/bin/python -m pytest tests/test_security_middleware.py -q`; expected `7 passed`.

---

### Task 3: Wire into `create_app`, drop allow-all CORS, `demo` in health

**Files:**
- Modify: `doctor_dictation/api/app.py` (CORS block and import); `doctor_dictation/api/health.py` (returned dict)
- Create: `tests/test_security_app.py`

**Interfaces:** consumes `install_security` (Task 2); produces `"demo": bool` in `/api/health` and `/health`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_security_app.py`:
```python
"""The real app via create_app().  Run: .venv/bin/python -m pytest tests/test_security_app.py -q"""
import base64
from fastapi.testclient import TestClient
from doctor_dictation import db as dbmod
from doctor_dictation.api.app import create_app
from doctor_dictation.config import override_settings
PW = "s3cret-pw-XYZ"
AUTH = {"Authorization": "Basic " + base64.b64encode(f"doc:{PW}".encode()).decode()}
ORIGIN, EVIL = "https://demo.example", "https://evil.example"
PREFLIGHT = {"Access-Control-Request-Method": "PUT", "Access-Control-Request-Headers": "authorization,content-type"}
def _client(monkeypatch, tmp_path, **fields):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "sec.db"))
    dbmod.init_db()  # TestClient without `with` skips the lifespan
    override_settings(monkeypatch, **fields)
    return TestClient(create_app())
def test_no_cors_headers_by_default(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    assert "access-control-allow-origin" not in c.get("/api/health", headers={"Origin": ORIGIN}).headers
    assert "access-control-allow-origin" not in c.options("/api/v1/profile", headers={"Origin": ORIGIN, **PREFLIGHT}).headers
def test_cors_is_exactly_the_configured_origins_and_preflight_needs_no_login(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path, demo_username="doc", demo_password=PW, allowed_origins=(ORIGIN,))
    ok = c.get("/api/health", headers={"Origin": ORIGIN})
    assert ok.headers["access-control-allow-origin"] == ORIGIN
    assert ok.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in c.get("/api/health", headers={"Origin": EVIL}).headers
    assert c.options("/api/v1/profile", headers={"Origin": ORIGIN, **PREFLIGHT}).status_code == 200
    denied = c.get("/api/v1/profile", headers={"Origin": ORIGIN})  # 401 stays readable cross-origin
    assert denied.status_code == 401 and denied.headers["access-control-allow-origin"] == ORIGIN
def test_page_and_api_are_both_protected(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path, demo_username="doc", demo_password=PW)
    for path in ("/", "/app.js", "/styles.css", "/api/v1/profile", "/api/v1/encounters/today"):
        assert c.get(path).status_code == 401, path
    assert c.get("/", headers=AUTH).status_code == 200
    assert c.get("/api/v1/profile", headers=AUTH).status_code == 200
def test_health_reports_demo_flag_stays_open_and_hides_the_password(monkeypatch, tmp_path):
    assert _client(monkeypatch, tmp_path).get("/api/health").json()["demo"] is False
    on = _client(monkeypatch, tmp_path, demo_mode=True, demo_username="doc", demo_password=PW)
    for path in ("/api/health", "/health"):  # no credentials sent: health is exempt
        r = on.get(path)
        assert r.status_code == 200 and r.json()["demo"] is True and PW not in r.text
```
- [ ] **Step 2: Run to verify it fails** — `.venv/bin/python -m pytest tests/test_security_app.py -q`; expected failures: allow-all CORS answers every origin, no 401s, `KeyError: 'demo'`.

- [ ] **Step 3: Implement.** Locate with `grep -n "CORSMiddleware" doctor_dictation/api/app.py`. Delete the `app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)` call and its import. In its place (after `app = FastAPI(...)`):
```python
    settings = get_settings()
    install_security(app, settings)
    if settings.demo_mode and not (settings.demo_username and settings.demo_password):
        logging.getLogger(__name__).warning(
            "DEMO_MODE is on but DEMO_USERNAME and DEMO_PASSWORD are not both set: the app is open")
```
Add imports if missing: `import logging`, `from doctor_dictation.api.security import install_security`, `from doctor_dictation.config import get_settings`. In `api/health.py` find the dict with `grep -n '"ok": True' doctor_dictation/api/health.py` and add (import `get_settings` if absent):
```python
        "demo": get_settings().demo_mode,
```
- [ ] **Step 4: Run to verify it passes** — `.venv/bin/python -m pytest tests/test_security_app.py -q`; expected `4 passed`. Then the whole suite, expected N + 14. If an older test relied on allow-all CORS, change only its setup line (contracts section 2, rule 9).

---

### Task 4: Audit actor from the logged-in name

**Files:**
- Modify: `doctor_dictation/db/__init__.py` (`log_audit`, import)
- Create: `tests/test_audit_actor.py`

**Interfaces:**
- Produces: `log_audit(conn, actor=None, ...)` stores `current_actor.get()` when `actor` is `None`; an explicit `actor` wins. No route edits: the document route calls `log_audit` without an actor (`backend/main.py:1011` before the move), as do the template routes.

- [ ] **Step 1: Write the failing tests** — create `tests/test_audit_actor.py`:
```python
"""audit_log.actor comes from the login.  Run: .venv/bin/python -m pytest tests/test_audit_actor.py -q"""
import base64
import pytest
from fastapi.testclient import TestClient
from doctor_dictation import db as dbmod
from doctor_dictation.api.app import create_app
from doctor_dictation.config import override_settings
from doctor_dictation.request_actor import current_actor
PW = "s3cret-pw-XYZ"
BODY = {"structured": {"patientName": "Asha Test", "ageSex": "30 / F", "opNo": "OP-9", "rx": []},
        "confirmed_rows": []}
@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "actor.db"))
    c = dbmod.get_conn()
    dbmod.migrate(c)
    yield c
    c.close()
def _actors(conn):
    return [(r["action"], r["actor"]) for r in conn.execute("SELECT action, actor FROM audit_log ORDER BY id")]
def test_log_audit_uses_the_request_actor_unless_given_one(conn):
    token = current_actor.set("doc")
    try:
        dbmod.log_audit(conn, action="a")
        dbmod.log_audit(conn, actor="explicit", action="b")
    finally:
        current_actor.reset(token)
    dbmod.log_audit(conn, action="c")  # outside a login: stays NULL
    assert _actors(conn) == [("a", "doc"), ("b", "explicit"), ("c", None)]
def test_document_save_and_resave_are_stamped_with_the_login(conn, monkeypatch):
    def boom(*a, **k): raise RuntimeError("no browser in tests")
    for name in ("render_pdf", "render_prescription"):  # whichever the save route uses after B2b
        monkeypatch.setattr(f"doctor_dictation.pdf.{name}", boom, raising=False)
    override_settings(monkeypatch, demo_username="doc", demo_password=PW)
    auth = {"Authorization": "Basic " + base64.b64encode(f"doc:{PW}".encode()).decode()}
    c = TestClient(create_app())
    first = c.post("/api/v1/documents", json=BODY, headers=auth)
    assert first.status_code == 200, first.text
    again = c.post("/api/v1/documents", json={**BODY, "document_id": first.json()["document_id"]}, headers=auth)
    assert again.status_code == 200, again.text
    assert _actors(conn) == [("finalize", "doc"), ("resave", "doc")]
```
- [ ] **Step 2: Run to verify it fails** — `.venv/bin/python -m pytest tests/test_audit_actor.py -q`; expected 2 FAIL (actor `None` where `"doc"` is expected).

- [ ] **Step 3: Implement.** In `db/__init__.py` add `from doctor_dictation.request_actor import current_actor` with the other imports, and as the first lines of `log_audit` (`backend/db/__init__.py:252` before the move):
```python
    if actor is None:
        actor = current_actor.get()  # set by BasicAuthMiddleware; None when login is off
```
Confirm no route hard-codes an actor: `grep -rn 'actor="' doctor_dictation/` should print nothing (B2b's services take an `actor` parameter that routes leave as `None`, which is fine: `log_audit` fills it in).

- [ ] **Step 4: Run to verify it passes** — `.venv/bin/python -m pytest tests/test_audit_actor.py -q`; expected `2 passed`; whole suite expected N + 16. Template upload/accept/discard rows use the same path; Task 6 checks one by hand.

---

### Task 5: Demo banner in the page

**Files:**
- Modify: `frontend/index.html` (first child of `<body>`; script tag version), `frontend/styles.css` (append), `frontend/app.js` (health handler)
- Create: `tests/test_demo_banner.py`

**Interfaces:** consumes `demo` in `/api/health`; produces element `#demoBanner` and body class `has-demo`.

- [ ] **Step 1: Write the failing test** — create `tests/test_demo_banner.py`:
```python
"""Banner markup exists and app.js reveals it.  Run: .venv/bin/python -m pytest tests/test_demo_banner.py -q"""
from pathlib import Path
FE = Path(__file__).resolve().parents[1] / "frontend"
def test_banner_is_wired_into_the_page():
    html, js, css = [(FE / n).read_text() for n in ("index.html", "app.js", "styles.css")]
    assert 'id="demoBanner" class="demo-banner no-print" role="status" hidden>Demo, fake patients only<' in html
    assert "h.demo" in js and "has-demo" in js
    assert ".demo-banner[hidden]" in css
```
- [ ] **Step 2: Run to verify it fails** — `.venv/bin/python -m pytest tests/test_demo_banner.py -q`; expected FAIL on the first assert.

- [ ] **Step 3: Implement.** `index.html`: directly after `<body>` insert the line below, and bump the script tag by one (`grep -n "app.js?v=" frontend/index.html`; N becomes N+1).
```html
<div id="demoBanner" class="demo-banner no-print" role="status" hidden>Demo, fake patients only</div>
```
Append to `styles.css` (`.no-print` already hides it when printing, `styles.css:171`):
```css
/* --- demo banner (revealed only when /api/health reports demo) --- */
.demo-banner { position:sticky; top:0; z-index:6; background:#fff4cc; color:#5c4400; border-bottom:2px solid #e0b400;
  text-align:center; font-weight:700; font-size:14px; line-height:28px; height:30px; letter-spacing:.3px; }
.demo-banner[hidden] { display:none; }
body.has-demo .topbar { top:30px; }
body.has-demo .sidebar, body.has-demo .middle { top:100px; }
```
In `app.js` (`grep -n 'fetch("/api/health")' frontend/app.js`) add one line at the start of the handler; the rest is unchanged. If B2c moved the sidebar offsets, use the existing `top` plus 30 instead of `100px`.
```js
fetch("/api/health").then(r => r.json()).then(h => {
  if (h.demo) { $("demoBanner").hidden = false; document.body.classList.add("has-demo"); }
```
- [ ] **Step 4: Run to verify it passes** — `.venv/bin/python -m pytest tests/test_demo_banner.py -q`; expected `1 passed`.

- [ ] **Step 5: Verify in the browser and LOOK at the screenshot.** Green tests do not show a readable screen. Start a throwaway server:
```bash
DB_PATH=$(mktemp -d)/app.db DEMO_MODE=true DEMO_USERNAME=demo DEMO_PASSWORD=demo-pass-123 \
  .venv/bin/uvicorn doctor_dictation.main:app --port 8001
```
With the Playwright browser tools navigate to `http://demo:demo-pass-123@127.0.0.1:8001/` (Chromium remembers the login), then to `http://127.0.0.1:8001/`. Do not stay on the credentialed URL: the page's own `fetch("/api/health")` throws there and the banner never shows. Screenshot and read it: a pale-yellow strip across the top reading "Demo, fake patients only" in dark readable text, the top bar fully visible beneath it (not covered), the panes starting below the top bar. Run `window.scrollTo(0, 400)` via `browser_evaluate`, screenshot again, and confirm the strip stays. Restart without the three `DEMO_*` variables and confirm no strip and the old layout. Record what you saw, then stop the server.

---

### Task 6: Final verification

- [ ] **Step 1: Full suite** — `.venv/bin/python -m pytest tests/ -q`; expected **N + 17 passed**, 0 failed.
- [ ] **Step 2: Static checks** — `grep -rn 'allow_origins=\["\*"\]' doctor_dictation/; wc -l doctor_dictation/api/security.py doctor_dictation/db/__init__.py doctor_dictation/config.py`; expected: grep prints nothing, each file under 500 lines (report any that were already over; do not split here).
- [ ] **Step 3: Run with login and exercise it** (explicit DB path so Step 4 can read it):
```bash
export DB_PATH=/tmp/d0a-verify.db; rm -f $DB_PATH
DEMO_MODE=true DEMO_USERNAME=demo DEMO_PASSWORD=demo-pass-123 ALLOWED_ORIGINS=https://demo.example.com \
  .venv/bin/uvicorn doctor_dictation.main:app --port 8001
```
In another shell (expected result after each `#`):
```bash
curl -s -o /dev/null -w "%{http_code}\n" localhost:8001/                          # 401
curl -si localhost:8001/ | grep -i "www-authenticate\|x-content-type"           # Basic realm="Doctor Dictation", nosniff
curl -s -o /dev/null -w "%{http_code}\n" -u demo:demo-pass-123 localhost:8001/    # 200
curl -s localhost:8001/api/health | grep -o '"demo":[a-z]*'                       # "demo":true
curl -s localhost:8001/api/health | grep -c demo-pass-123                         # 0
curl -si -H "Origin: https://demo.example.com" localhost:8001/api/health | grep -i access-control-allow-origin  # https://demo.example.com
curl -si -H "Origin: https://evil.example" localhost:8001/api/health | grep -ic access-control-allow-origin    # 0
```
- [ ] **Step 4: One audit row by hand.**
```bash
curl -s -u demo:demo-pass-123 -H "Content-Type: application/json" \
  -d '{"structured":{"patientName":"Fake Patient","opNo":"OP-1","rx":[]},"confirmed_rows":[]}' localhost:8001/api/v1/documents
sqlite3 /tmp/d0a-verify.db "select action, actor from audit_log order by id desc limit 1"   # finalize|demo
```
If B2b is applied, also accept or discard one template draft and confirm its audit row shows `demo`.

- [ ] **Step 5: Stop the server, delete `/tmp/d0a-verify.db`, leave everything uncommitted,** and list the changed files (`git status --short`): new `api/security.py`, `request_actor.py` and five `tests/test_*` files named in Tasks 1-5; modified `config.py`, `db/__init__.py`, `api/app.py`, `api/health.py`, `index.html`, `styles.css`, `app.js`, `.env.example`. The final report must state: CSP deferred (design decisions); one shared account, so the audit `actor` names the account, not a person; Basic auth over plain HTTP exposes the password, so D0b must put HTTPS in front before real use; anything above you could not run.
