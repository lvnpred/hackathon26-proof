"""One model point's record for the care app's Expand view (care-app clarity §4.2).

`GET /journey/episodes/{id}/events/{event_id}/model` reads back one event of that episode: its type, time and payload
(the `evidence` of Task 3 with what went in, what the model returned and how the app used it, plus the source words).
Read only, and only for model points (ruling P11): an event of a model-point type, or one that carries `evidence`.
Any other event, another episode's event, or an unknown id is a 404. Secret-named keys and tokens in text are dropped
(`evidence_payload.clean`). `?lens=patient` leaves out the raw reply, the text sent, the calls and the model name, so
none of them reaches a patient screen.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from app.journey.api import _require, _store
from app.journey.evidence_payload import clean

model_record_router = APIRouter(prefix="/journey/episodes/{episode_id}")

NOT_FOUND = "Event not found"
# The events a model result is written as (the §4.2 points); anything else is the record, not a model point.
MODEL_POINTS = frozenset({
    "order.drafted", "discharge.drafted", "handover.drafted", "vitals.card", "druglog.parsed", "count.pack_heard",
    "check.photo", "proof.checked", "tray.checked", "setup.checked", "swabs.counted", "medicines.read",
    "brownbag.med_found", "question.answered", "review.requested", "task.done", "camera.closed", "camera.ran",
})
_STAFF_ONLY = ("calls", "raw", "prompt")  # payload keys a patient never gets


def _is_model_point(event: dict) -> bool:
    return event["event_type"] in MODEL_POINTS or isinstance((event.get("payload") or {}).get("evidence"), dict)


def _for_patient(payload: dict) -> dict:
    """The payload without the raw reply, the text sent, the calls or the model name."""
    out = {k: v for k, v in payload.items() if k not in _STAFF_ONLY}
    ev = out.get("evidence")
    if isinstance(ev, dict):
        captured = {k: v for k, v in (ev.get("captured") or {}).items() if k != "text"}
        returned = {**(ev.get("returned") or {}), "raw": None, "model": None, "ms": None}
        out["evidence"] = {k: v for k, v in {**ev, "captured": captured, "returned": returned}.items() if k != "calls"}
    return out


@model_record_router.get("/events/{event_id}/model")
def model_record(episode_id: str, event_id: str, request: Request,
                 lens: Literal["staff", "patient"] = Query("staff")) -> dict:
    _require(request, episode_id)
    event = next((e for e in _store(request).events(episode_id) if e["id"] == event_id), None)
    if event is None or not _is_model_point(event):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    payload = clean(event.get("payload") or {})
    if lens == "patient":
        payload = _for_patient(payload)
    return {**payload, "id": event["id"], "type": event["event_type"], "at_ms": event["ts_ms"]}
