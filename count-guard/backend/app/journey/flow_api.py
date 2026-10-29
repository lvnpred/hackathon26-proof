"""Patient state routes: guarded moves between states, and the surgery start and end."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from app.journey import states
from app.journey.api import At, Strict, _act, _require, _store, view

flow_router = APIRouter(prefix="/journey/episodes/{episode_id}")


class StateIn(At):
    to: Literal["clinic", "clinic_done", "admitting", "ward", "theatre", "discharging", "home"]
    by: str = Field(min_length=1, max_length=80)
    reason: str = Field(default="", max_length=300)
    procedure: Literal["hernia-repair"] | None = None
    checklist: dict[str, bool] = Field(default_factory=dict, max_length=10)


class SurgeryIn(At):
    step: Literal["began", "ended"]
    by: str = Field(min_length=1, max_length=80)


@flow_router.post("/state")
def move(episode_id: str, body: StateIn, request: Request) -> dict:
    _require(request, episode_id)
    events = _store(request).events(episode_id)
    refusal = states.check_move(events, body.to, body.model_dump())
    if refusal:
        raise HTTPException(status_code=409, detail=refusal)
    payload = {"from": states.current_state(events), "to": body.to, "by": body.by, "reason": body.reason.strip()}
    if body.procedure:
        payload["procedure"] = body.procedure
    if body.checklist:
        payload["checklist"] = body.checklist
    return _act(request, episode_id, "patient.state", payload, body.at_ms)


@flow_router.post("/surgery")
def surgery(episode_id: str, body: SurgeryIn, request: Request) -> dict:
    _require(request, episode_id)
    events = _store(request).events(episode_id)
    if states.current_state(events) != "theatre":
        raise HTTPException(status_code=409, detail="Surgery is recorded only while the patient is in theatre.")
    status = states.surgery_status(events)
    if body.step == "began" and status != "none":
        raise HTTPException(status_code=409, detail="Surgery has already begun.")
    if body.step == "ended" and status != "began":
        raise HTTPException(status_code=409, detail="Surgery has not begun, or has already ended.")
    return _act(request, episode_id, f"surgery.{body.step}", {"by": body.by}, body.at_ms)
