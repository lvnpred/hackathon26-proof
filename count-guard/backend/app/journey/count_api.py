"""The theatre swab count: the pack opened, the closing, and the camera count it may come from (R16, R17)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, model_validator

from app.journey import states
from app.journey.api import At, _act, _require, _store
from app.journey.stories import by_ai

count_router = APIRouter(prefix="/journey/episodes/{episode_id}")
NEEDS_REASON = "Say what the team did: the count does not match."
NOT_THIS_STAY = "That camera count is not from this patient's theatre stay."
A_PERSON = "A person saves the swab count; the camera and the AI only advise."
ONLY_UP = "The pack count can only go up once surgery has begun. Record an extra pack instead."


class CountIn(At):
    step: Literal["opened", "closing"]
    quantity: int | None = Field(default=None, ge=1, le=200)  # required when step is "opened"
    returned: int | None = Field(default=None, ge=0, le=200)  # required when step is "closing"
    detail: str = Field(default="", max_length=200)
    by: str = Field(min_length=1, max_length=80)
    supersedes_id: str | None = None
    evidence_id: str | None = Field(None, pattern=r"^[0-9a-f]{32}$")  # the camera count this closing starts from
    via: Literal["typed", "camera"] = "typed"
    extra: bool = False  # an extra pack opened: adds to the count instead of naming the new total

    @model_validator(mode="after")
    def _step_fields(self):
        if self.step == "opened":
            if self.quantity is None:
                raise ValueError("quantity is required when the pack is opened")
            if self.supersedes_id:
                raise ValueError("an opened pack cannot replace a line")
        elif self.extra:
            raise ValueError("extra is only for an opened pack")
        elif self.returned is None:
            raise ValueError("returned is required for the closing count")
        return self


def _has_reason(detail: str) -> bool:
    """A reason says something: at least 3 letters once zero-width characters and no-break spaces are removed.
    "." or a lone zero-width space is not a reason (the gate's own check stays a plain non-blank test)."""
    kept = detail.translate({ord(c): None for c in "\u200b\u200c\u200d\u2060\ufeff\u00a0"})
    return sum(c.isalpha() for c in kept) >= 3


def _camera_count(events: list[dict], evidence_id: str) -> dict:
    """The `swabs.counted` event of this theatre stay that holds the id, else a 422."""
    held = [e for e in states.stay_events(events) if e["event_type"] == "swabs.counted" and e["payload"].get("evidence_id") == evidence_id]
    if not held:
        raise HTTPException(status_code=422, detail=NOT_THIS_STAY)
    return held[-1]


def _pack_quantity(events: list[dict], body: CountIn) -> int:
    """The swabs this pack adds. An extra pack adds its quantity. Otherwise, before surgery began a pack names the
    new total and replaces the earlier ones (`states.stay_packs`); once it began the count can only go up: a new total
    adds the difference, and a total that is not higher is a 422."""
    if states.surgery_status(events) == "none" or body.extra:
        return body.quantity
    current = states.stay_opened(events) or 0
    if body.quantity <= current:
        raise HTTPException(status_code=422, detail=ONLY_UP)
    return body.quantity - current


@count_router.post("/count")
def count(episode_id: str, body: CountIn, request: Request) -> dict:
    """The theatre nurse's swab count at the demo time. A corrected closing replaces the one it names."""
    _require(request, episode_id)
    if by_ai({"by": body.by}):  # U10: an AI or camera `by` never saves a pack or a closing
        raise HTTPException(status_code=422, detail=A_PERSON)
    store = _store(request)
    old = None
    if body.supersedes_id:
        old = store.get_event(body.supersedes_id)
        if old is None or old["episode_id"] != episode_id or old["event_type"] != "count.closing":
            raise HTTPException(status_code=404, detail="Closing count not found")
    events = store.events(episode_id)
    if body.step == "opened":
        payload = {"item_type": "swab", "quantity": _pack_quantity(events, body), "source": "typed", "by": body.by}
        if body.extra:
            payload["extra"] = True  # R27: before incision too, an extra pack adds instead of replacing
        return _act(request, episode_id, "count.pack_opened", payload, body.at_ms, body.supersedes_id)
    # A correction keeps the camera count its closing came from, so the record shows what was read and what was saved.
    evidence_id = body.evidence_id or (old["payload"].get("evidence_id") if old else None)
    camera = _camera_count(events, evidence_id) if evidence_id else None  # a 422 when not from this stay
    try:
        payload = states.closing_payload(events, body.returned, body.by, evidence_id=evidence_id, detail=body.detail,
                                         camera=camera)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    read = camera["payload"].get("count") if camera else None
    if not _has_reason(body.detail) and (payload["unaccounted"] != 0 or (read is not None and body.returned != read)):
        raise HTTPException(status_code=422, detail=NEEDS_REASON)
    return _act(request, episode_id, "count.closing", payload, body.at_ms, body.supersedes_id)
