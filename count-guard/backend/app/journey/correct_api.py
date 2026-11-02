"""Correct a recorded line from the care app (spec §9 "morning correction route" → Inspector → Correct).

The new event supersedes the old one at the old one's time; the old one stays in the record. What may be corrected,
and why the rest is refused, lives in `journey/correction.py`.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, StrictFloat, StrictInt, ValidationError

from app.journey import correction
from app.journey.api import At, ObsIn, Strict, _require, _store, settle, view
from app.journey.clock import stamp
from app.journey.stories import by_ai

correct_router = APIRouter(prefix="/journey/episodes/{episode_id}")
A_PERSON = "A person corrects the record; the camera and the AI do not."
NOTHING = "Say which value to correct."


class CorrectIn(At):  # at_ms is the demo time of the correction; the corrected line keeps its own time
    event_id: str = Field(min_length=1, max_length=64)
    payload: dict
    by: str = Field(min_length=1, max_length=80)


class DrugFix(Strict):
    """A theatre drug line's dose and route, in the words `druglog.parse_drug_phrase` writes."""
    strength: str | None = Field(default=None, max_length=40)
    amount: StrictInt | StrictFloat | None = Field(default=None, gt=0, le=10_000)
    unit: Literal["mcg", "mg", "g", "ml"] | None = None
    route: Literal["local infiltration", "iv", "im", "subcutaneous", "oral"] | None = None


def _values(event_type: str, old: dict, payload: dict, by: str) -> dict:
    """The corrected values, checked with the same limits as the route that first wrote them (422 otherwise)."""
    if not payload:
        raise HTTPException(status_code=422, detail=NOTHING)
    extra = correction.unknown_fields(event_type, payload)
    if extra:
        raise HTTPException(status_code=422, detail=f"These cannot be corrected here: {', '.join(extra)}.")
    if event_type != "obs.recorded":
        try:
            return DrugFix.model_validate(payload).model_dump(include=set(payload))
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="Check the amount, unit and route.") from exc
    merged = {key: value for key, value in {**old, **payload}.items() if key in correction.OBS_FIELDS}
    try:
        checked = ObsIn.model_validate({**merged, "by": by})
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="That value is outside the range a reading can have.") from exc
    return {key: getattr(checked, key) for key in payload}


@correct_router.post("/correct")
def correct(episode_id: str, body: CorrectIn, request: Request) -> dict:
    _require(request, episode_id)
    if by_ai({"by": body.by}):  # the same check /count uses: an AI or camera `by` never writes a person's line
        raise HTTPException(status_code=422, detail=A_PERSON)
    store = _store(request)
    old = store.get_event(body.event_id)
    if old is None or old["episode_id"] != episode_id:
        raise HTTPException(status_code=404, detail="Event not found")
    refused = correction.refusal(old, store.events(episode_id))
    if refused:
        raise HTTPException(status_code=409, detail=refused)
    values = _values(old["event_type"], old["payload"], body.payload, body.by)
    store.append(episode_id, old["event_type"], correction.corrected(old["event_type"], old["payload"], values, body.by),
                 ts_ms=old["ts_ms"], tier=old["tier"], supersedes_id=old["id"])
    settle(request, episode_id, stamp(store, episode_id, body.at_ms))
    return view(request, episode_id)
