"""Signed session cookie: HMAC-SHA256 over a small JSON payload. Stateless; revocation is the per-user
``session_version`` check ``authn.load_identity`` does on every request."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

from doctor_dictation.scope import valid_slug

COOKIE_NAME = "dd_session"
LIFETIME_SECONDS = 12 * 60 * 60
MIN_SECRET_LENGTH = 32
DEV_FLAG_ENV = "DEV_INSECURE_SESSION_SECRET"
_DEV_SECRET = b"dev-only-insecure-session-secret!"   # 33 bytes; used only with DEV_INSECURE_SESSION_SECRET=1


class SecretError(RuntimeError):
    """SESSION_SECRET is missing or too short."""


@dataclass(frozen=True)
class Identity:
    clinic_slug: str
    user_id: int
    username: str
    role: str
    display_name: str = ""
    must_change_password: bool = False
    session_version: int = 0


def session_secret() -> bytes:
    secret = os.getenv("SESSION_SECRET", "")
    if len(secret) >= MIN_SECRET_LENGTH:
        return secret.encode("utf-8")
    if os.getenv(DEV_FLAG_ENV, "") == "1":
        return _DEV_SECRET
    raise SecretError(f"SESSION_SECRET must be set to at least {MIN_SECRET_LENGTH} characters "
                      f"(or set {DEV_FLAG_ENV}=1 for local development only)")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(body: str) -> str:
    return _b64(hmac.new(session_secret(), body.encode("ascii"), hashlib.sha256).digest())


def _encode(payload: dict) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{body}.{_mac(body)}"


def sign(clinic_slug: str, user_id: int, session_version: int, now=None) -> str:
    issued = int(time.time() if now is None else now)
    return _encode({"clinic": clinic_slug, "uid": user_id, "ver": session_version, "iat": issued, "exp": issued + LIFETIME_SECONDS})


def verify(token, now=None) -> dict | None:
    """The payload for a genuine, unexpired token with well-typed fields; otherwise None (never raises, except SecretError)."""
    try:
        body, sig = token.split(".")
        if not hmac.compare_digest(sig, _mac(body)):
            return None
        payload = json.loads(_unb64(body))
        current = time.time() if now is None else now
        if not (valid_slug(payload["clinic"]) and type(payload["uid"]) is int and type(payload["ver"]) is int
                and type(payload["exp"]) is int and payload["exp"] > current):
            return None
    except (ValueError, TypeError, KeyError, AttributeError):
        return None
    return payload
