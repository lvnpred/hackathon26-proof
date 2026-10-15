"""Application factory: middleware, lifespan, routers, then the static frontend."""
import os
import sqlite3
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from doctor_dictation import clinics
from doctor_dictation import db as dbmod
from doctor_dictation import sessions
from doctor_dictation.api import format as format_api
from doctor_dictation.api import auth, health, persistence, profile, stt
from doctor_dictation.api.session import SessionMiddleware
from doctor_dictation.api import templates as templates_api
from doctor_dictation.api import users as users_api
from doctor_dictation.pdf import close_renderer
from doctor_dictation.scope import NoScope, multi_clinic_enabled

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


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
    if sqlite3.sqlite_version_info < (3, 35):
        found = ".".join(map(str, sqlite3.sqlite_version_info))
        raise RuntimeError(f"multi-clinic mode needs SQLite 3.35 or newer (found {found}): "
                           "change_password uses UPDATE ... RETURNING")
    if os.getenv(sessions.DEV_FLAG_ENV, "") == "1":             # same test as sessions.session_secret
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    _startup(app)
    yield
    close_renderer()   # nothing starts at startup; Chromium launches on the first Save


def create_app() -> FastAPI:
    # .env must be loaded before the first get_settings() call (settings are cached).
    load_dotenv()
    app = FastAPI(title="Doctor Dictation Demo", lifespan=lifespan)

    # Multi-clinic mode with no scope (before login exists, or a bypassed middleware): never a 500 and never a default database.
    @app.exception_handler(NoScope)
    async def _no_scope(_request, _exc):
        return JSONResponse(status_code=401, content={"error": "sign in required"})
    app.add_middleware(SessionMiddleware)  # added first = inner; CORS wraps it so 401/403 carry CORS headers
    # Exactly today's CORS. D0a replaces this with an allow-list.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (auth, health, stt, format_api, profile, persistence, users_api):
        app.include_router(module.router)
    app.include_router(templates_api.router)
    # Serve the frontend from the same process; mounted last so it never shadows /api.
    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    return app
