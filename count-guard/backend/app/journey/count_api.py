"""The theatre swab count: the pack opened, the closing, and the camera count it may come from (R16, R17)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, model_validator

from app.journey import states
from app.journey.api import At, _act, _require, _store

count_router = APIRouter(prefix="/journey/episodes/{episode_id}")
NEEDS_REASON = "Say what the team did: the count does not match."
NOT_THIS_STAY = "That camera count is not from this patient's theatre stay."


class CountIn(At):
    step: Literal["opened", "closing"]
    quantity: int | None = Field(default=None, ge=1, le=200)  # required when step is "opened"
    returned: int | None = Field(default=None, ge=0, le=200)  # required when step is "closing"
    detail: str = Field(default="", max_length=200)
    by: str = Field(min_length=1, max_length=80)
    supersedes_id: str | None = None
    evidence_id: str | None = Field(None, pattern=r"^[0-9a-f]{32}$")  # the camera count this closing starts from
    via: Literal["typed", "camera"] = "typed"

    @model_validator(mode="after")
    def _step_fields(self):
        if self.step == "opened":
            if self.quantity is None:
                raise ValueError("quantity is required when the pack is opened")
            if self.supersedes_id:
                raise ValueError("an opened pack cannot replace a line")
        elif self.returned is None:
            raise ValueError("returned is required for the closing count")
        return self


def _camera_count(events: list[dict], evidence_id: str) -> dict:
    """The `swabs.counted` event of this theatre stay that holds the id, else a 422."""
    held = [e for e in states.stay_events(events) if e["event_type"] == "swabs.counted" and e["payload"].get("evidence_id") == evidence_id]
    if not held:
        raise HTTPException(status_code=422, detail=NOT_THIS_STAY)
    return held[-1]


@count_router.post("/count")
def count(episode_id: str, body: CountIn, request: Request) -> dict:
    """The theatre nurse's swab count at the demo time. A corrected closing replaces the one it names."""
    _require(request, episode_id)
    store = _store(request)
    old = None
    if body.supersedes_id:
        old = store.get_event(body.supersedes_id)
        if old is None or old["episode_id"] != episode_id or old["event_type"] != "count.closing":
            raise HTTPException(status_code=404, detail="Closing count not found")
    if body.step == "opened":
        payload = {"item_type": "swab", "quantity": body.quantity, "source": "typed", "by": body.by}
        return _act(request, episode_id, "count.pack_opened", payload, body.at_ms, body.supersedes_id)
    events = store.events(episode_id)
    # A correction keeps the camera count its closing came from, so the record shows what was read and what was saved.
    evidence_id = body.evidence_id or (old["payload"].get("evidence_id") if old else None)
    camera = _camera_count(events, evidence_id) if evidence_id else None  # a 422 when not from this stay
    try:
        payload = states.closing_payload(events, body.returned, body.by, evidence_id=evidence_id, detail=body.detail,
                                         camera=camera)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    read = camera["payload"].get("count") if camera else None
    if not body.detail.strip() and (payload["unaccounted"] != 0 or (read is not None and body.returned != read)):
        raise HTTPException(status_code=422, detail=NEEDS_REASON)
    return _act(request, episode_id, "count.closing", payload, body.at_ms, body.supersedes_id)
