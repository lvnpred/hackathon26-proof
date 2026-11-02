"""Count Guard API. Research demo. Not for clinical use."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.ws import router as ws_router
from app.config import BANNER, Settings, get_settings
from app.engine import Engine
from app.journey.ai_api import ai_router, evidence_router
from app.journey.api import demo_router, router as journey_router
from app.journey.flow_api import flow_router
from app.journey.intake_api import intake_router
from app.journey.ask_api import ask_router
from app.journey.camera_api import camera_router
from app.journey.camera_extra_api import camera_live_router
from app.journey.count_api import count_router
from app.journey.discharge_api import discharge_router
from app.journey.staff_api import staff_router
from app.journey.theatre_api import NotInTheatre, not_in_theatre, theatre_router
from app.journey.media_api import media_router, models_router
from app.journey.verdict_api import verdict_router
from app.journey.video_api import video_router
from app.journey.ward_api import ward_router
from app.ops.api import ops_site_router, router as ops_router
from app.morning.api import router as morning_router
from app.morning.routes_extra import router as morning_extra_router
from app.morning.care_guard import CareEpisode, care_episode
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
    app.include_router(count_router)
    app.include_router(camera_router)
    app.include_router(camera_live_router)
    app.include_router(theatre_router)
    app.add_exception_handler(NotInTheatre, not_in_theatre)
    app.add_exception_handler(CareEpisode, care_episode)
    app.include_router(demo_router)
    app.include_router(ward_router)
    app.include_router(intake_router)
    app.include_router(flow_router)
    app.include_router(discharge_router)
    app.include_router(media_router)
    app.include_router(verdict_router)
    app.include_router(ask_router)
    app.include_router(staff_router)
    app.include_router(video_router)
    app.include_router(evidence_router)
    app.include_router(ai_router)
    app.include_router(models_router)
    app.include_router(ops_router)
    app.include_router(ops_site_router)
    return app


app = create_app()
