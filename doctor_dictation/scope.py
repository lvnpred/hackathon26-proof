"""Request scope: which clinic (and user) the current work belongs to.

Stdlib only and imports nothing from ``doctor_dictation``: ``db``, ``directory`` and
``clinics`` all sit on top of it. The scope lives in a ``ContextVar``, so it follows
``asyncio.to_thread`` and anyio worker threads (they copy the context) but NOT a bare
``threading.Thread`` or a ``ThreadPoolExecutor`` (they start empty); anything running
there fails closed with ``NoScope`` instead of guessing a clinic.
"""
from __future__ import annotations

import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

MULTI_CLINIC_ENV = "MULTI_CLINIC"
DATA_DIR_ENV = "DATA_DIR"
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"
SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]{1,30}")  # always used with fullmatch: "$" would accept a trailing newline


class NoScope(RuntimeError):
    """Raised when clinic data is touched with no clinic scope (multi-clinic mode)."""


def valid_slug(slug) -> bool:
    return isinstance(slug, str) and SLUG_RE.fullmatch(slug) is not None


@dataclass(frozen=True)
class Scope:
    clinic_slug: str
    user_id: int | None = None
    username: str = "system"
    role: str = "system"

    def __post_init__(self):
        if not valid_slug(self.clinic_slug):
            raise ValueError(f"invalid clinic slug: {self.clinic_slug!r}")


_scope: ContextVar[Scope | None] = ContextVar("dd_scope", default=None)


def multi_clinic_enabled() -> bool:
    return os.getenv(MULTI_CLINIC_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def data_root() -> Path:
    env = os.getenv(DATA_DIR_ENV, "").strip()
    return Path(env).expanduser().resolve() if env else DEFAULT_DATA_DIR


def clinic_dir(slug: str) -> Path:
    if not valid_slug(slug):
        raise ValueError(f"invalid clinic slug: {slug!r}")
    return data_root() / "clinics" / slug


def current_scope() -> Scope | None:
    return _scope.get()


def require_scope() -> Scope:
    scope = _scope.get()
    if scope is None:
        raise NoScope("no clinic scope: sign in first")
    return scope


@contextmanager
def use_scope(scope: Scope):
    token = _scope.set(scope)
    try:
        yield scope
    finally:
        _scope.reset(token)
