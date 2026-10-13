"""Application factory: middleware, lifespan, routers, then the static frontend."""
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from doctor_dictation import db as dbmod
from doctor_dictation.api import format as format_api
from doctor_dictation.api import health, persistence, profile, stt
from doctor_dictation.api import templates as templates_api
from doctor_dictation.pdf import close_renderer

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Create the DB directory and apply pending migrations; idempotent.
    dbmod.init_db()
    templates_api.purge_on_startup()
    yield
    close_renderer()   # nothing starts at startup; Chromium launches on the first Save


def create_app() -> FastAPI:
    # .env must be loaded before the first get_settings() call (settings are cached).
    load_dotenv()
    app = FastAPI(title="Doctor Dictation Demo", lifespan=lifespan)
    # Exactly today's CORS. D0a replaces this with an allow-list.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (health, stt, format_api, profile, persistence):
        app.include_router(module.router)
    app.include_router(templates_api.router)
    # Serve the frontend from the same process; mounted last so it never shadows /api.
    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    return app
