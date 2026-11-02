"""The older morning count routes stay off care episodes (spec §6.5, A6).

A morning pack or closing has no person's `by`. On a care theatre stay it would still add to the stay's opened
sum and stand as the latest closing, so these routes refuse any episode the care app has moved or registered.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

CARE_MARKS = ("patient.state", "patient.registered")
USE_PANEL = "use the theatre count panel"


class CareEpisode(Exception):
    """A morning route that writes a swab count was called on a care episode."""


def refuse_care(store, episode_id: str) -> None:
    if any(e["event_type"] in CARE_MARKS for e in store.events(episode_id)):
        raise CareEpisode(episode_id)


async def care_episode(request: Request, exc: CareEpisode) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": USE_PANEL})
