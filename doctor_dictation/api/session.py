"""Session middleware (pure ASGI): CSRF header, public paths, cookie to identity, clinic scope.

Pure ASGI on purpose: ``BaseHTTPMiddleware`` runs the app in another task, so the ``ContextVar``
scope set here would not reliably reach the routes. Here ``await self.app(...)`` runs in this
task, inside ``use_scope``. In single mode (``MULTI_CLINIC`` off) everything passes through.
"""
from __future__ import annotations

import asyncio
import re

from starlette.requests import cookie_parser
from starlette.responses import JSONResponse, RedirectResponse

from doctor_dictation import authn
from doctor_dictation.scope import Scope, multi_clinic_enabled, use_scope
from doctor_dictation.sessions import COOKIE_NAME

CSRF_HEADER = b"x-dd-client"
UNSAFE_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})
PUBLIC_PATHS = frozenset({"/login", "/login.css", "/login.js", "/api/health", "/health",
                          "/api/v1/auth/login", "/favicon.ico"})
PUBLIC_SHARE = re.compile(r"/s/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+")   # patient download link: exactly two segments, no dots
GATE_PATHS = frozenset({"/api/v1/auth/change-password", "/api/v1/auth/logout", "/api/v1/auth/me"})


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or PUBLIC_SHARE.fullmatch(path) is not None


def _cookie_token(headers: dict) -> str | None:
    raw = headers.get(b"cookie")
    if not raw:
        return None
    return cookie_parser(raw.decode("latin-1")).get(COOKIE_NAME) or None   # tolerant: a bad neighbour cookie is skipped


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
        if is_public(path):
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
