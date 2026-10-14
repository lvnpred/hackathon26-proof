"""Walk the live route table in multi-clinic mode with no cookie: nothing but the public set may answer."""
import re

from fastapi.testclient import TestClient

from doctor_dictation.api.app import create_app
from doctor_dictation.api.session import PUBLIC_PATHS

H = {"X-DD-Client": "1"}
PAGES = ["/", "/index.html", "/app.js", "/styles.css", "/auth.js", "/letterhead.js", "/login.html",
         "/docs", "/redoc", "/openapi.json"]


def _targets(app):
    seen = set()
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            if method.upper() in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                seen.add((method.upper(), re.sub(r"\{[^}]+\}", "1", path)))
    seen.update(("GET", p) for p in PAGES)
    return sorted(seen)


def test_every_route_is_closed_without_a_session(multi):
    app = create_app()
    leaks, checked = [], 0
    with TestClient(app, follow_redirects=False) as c:
        for method, path in _targets(app):
            r = c.request(method, path, headers=H)
            checked += 1
            if path in PUBLIC_PATHS:
                if r.status_code in (401, 303):
                    leaks.append(f"public {method} {path} was gated: {r.status_code}")
                continue
            api_like = path.startswith("/api") or method != "GET"
            if api_like and r.status_code != 401:
                leaks.append(f"{method} {path} -> {r.status_code}, want 401")
            elif not api_like and (r.status_code, r.headers.get("location")) != (303, "/login"):
                leaks.append(f"{method} {path} -> {r.status_code}, want 303 /login")
    assert checked > 20
    assert not leaks, leaks
