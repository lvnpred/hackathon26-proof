"""Count Guard API. Research demo. Not for clinical use."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.ws import router as ws_router
from app.config import BANNER, Settings, get_settings
from app.engine import Engine
from app.journey.ai_api import evidence_router
from app.journey.api import demo_router, router as journey_router
from app.journey.flow_api import flow_router
from app.journey.ask_api import ask_router
from app.journey.staff_api import staff_router
from app.journey.media_api import media_router, models_router
from app.journey.video_api import video_router
from app.morning.api import router as morning_router
from app.morning.routes_extra import router as morning_extra_router
from app.morning.store import MorningStore
from app.site import router as site_router
from app.store import Store


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.frame_dir.mkdir(parents=True, exist_ok=True)
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    store = Store(settings.db_path)
    engine = Engine(store, settings)
    app = FastAPI(title="Count Guard", description=BANNER)
    app.state.settings = settings
    app.state.store = store
    app.state.engine = engine
    app.state.morning = MorningStore(settings.data_dir / "morning.db")
    app.state.decision_tier = os.environ.get("DECISION_TIER", "0") == "1"
    web_port = os.environ.get("CG_WEB_PORT", "5173")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[f"http://{host}:{web_port}" for host in ("127.0.0.1", "localhost")],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(ws_router)
    app.include_router(morning_router)
    app.include_router(morning_extra_router)
    app.include_router(site_router)
    app.include_router(journey_router)
    app.include_router(demo_router)
    app.include_router(flow_router)
    app.include_router(media_router)
    app.include_router(ask_router)
    app.include_router(staff_router)
    app.include_router(video_router)
    app.include_router(evidence_router)
    app.include_router(models_router)
    return app


app = create_app()
