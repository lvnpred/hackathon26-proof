"""Create a bare episode (replaces the archived `POST /morning/episodes`, spec §9 "Archiving").

The episode has a label and no events: no `patient.registered`, no state. Tests and tools use it to get an
episode id; the care app registers patients through intake (`/journey/patients`, `/journey/intake`).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import Field

from app.journey.api import Strict, _store

episode_router = APIRouter(prefix="/journey")


class EpisodeIn(Strict):
    label: str = Field(default="Synthetic demo, R. Kumar", min_length=1, max_length=120)


@episode_router.post("/episodes")
def create_episode(body: EpisodeIn, request: Request) -> dict:
    return _store(request).create_episode(body.label)
