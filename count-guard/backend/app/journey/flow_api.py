"""Patient state routes: guarded moves between states, and the surgery start and end."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, field_validator, model_validator

from app.journey import states, tasks
from app.journey.api import At, Limits, Strict, _act, _at, _latest, _require, _store, raise_nudges, view
from app.journey.dictation import draft_refusal
from app.journey.doctor_status import theatre_payload
from app.journey.procedures import tray_plan
from app.journey.seed import card_payload
from app.journey.stories import CARE_TEMPLATES

flow_router = APIRouter(prefix="/journey/episodes/{episode_id}")


class StateIn(At):
    to: Literal["clinic", "clinic_done", "admitting", "ward", "theatre", "discharging", "home"]
    by: str = Field(min_length=1, max_length=80)
    reason: str = Field(default="", max_length=300)
    procedure: str | None = Field(None, min_length=1, max_length=40)
    checklist: dict[str, bool] = Field(default_factory=dict, max_length=10)

    @field_validator("procedure")
    @classmethod
    def _known_procedure(cls, value: str | None) -> str | None:
        if value is not None and value not in states.PROCEDURES:
            raise ValueError("Unknown procedure.")
        return value


class SurgeryIn(At):
    step: Literal["began", "ended"]
    by: str = Field(min_length=1, max_length=80)


@flow_router.post("/state")
def move(episode_id: str, body: StateIn, request: Request) -> dict:
    _require(request, episode_id)
    events = _store(request).events(episode_id)
    try:
        payload = states.move_payload(events, body.to, body.model_dump())
    except states.MoveRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store = _store(request)
    ts = _at(store, episode_id, body.at_ms)
    store.append(episode_id, "patient.state", payload, ts_ms=ts)
    if body.to == "theatre":  # the plan the doctor confirms is the template as published
        plan = tray_plan(payload["procedure"])
        store.append(episode_id, "tray.planned", {**plan, "by": body.by}, ts_ms=ts)
        status = theatre_payload(body.by, _require(request, episode_id)["label"], ts, plan["expected_minutes"])
        store.append(episode_id, "doctor.status", {**status, "by": body.by}, ts_ms=ts)
    raise_nudges(store, episode_id, ts)
    return view(request, episode_id)


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


class OrderItem(Strict):
    kind: Literal["dose", "obs", "procedure", "check", "other"]
    text: str = Field(min_length=1, max_length=200)
    name: str = Field(default="", max_length=80)
    amount: str = Field(default="", max_length=40)
    every_h: float | None = Field(default=None, gt=0, le=72)
    mode: Literal["tick", "start_end"] = "tick"
    proof: Literal["none", "photo", "video"] = "none"
    limits: Limits = Field(default_factory=Limits)


class SignIn(At):
    items: list[OrderItem] = Field(min_length=1, max_length=20)
    by: str = Field(min_length=1, max_length=80)
    draft_id: str | None = Field(default=None, min_length=1, max_length=64)


class AckIn(At):
    by: str = Field(min_length=1, max_length=80)


class BeginIn(At):
    by: str = Field(min_length=1, max_length=80)


class Values(Strict):
    sbp: int = Field(ge=30, le=300)
    dbp: int = Field(ge=10, le=200)
    hr: int = Field(ge=20, le=250)
    spo2: int | None = Field(default=None, ge=50, le=100)
    temp: float | None = Field(default=None, ge=30, le=45)


class DoneIn(At):
    by: str = Field(min_length=1, max_length=80)
    via: Literal["tap", "voice", "text"] = "tap"
    note: str = Field(default="", max_length=300)
    values: Values | None = None
    transcript: str = Field(default="", max_length=2000)
    proof_id: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _voice_needs_words(self):
        if self.via == "voice" and not self.transcript.strip():
            raise ValueError("A completion by voice needs what was said.")
        return self


class DischargeIn(At):
    summary: str = Field(min_length=1, max_length=2000)
    template: str = Field(default="hernia-repair", max_length=40)
    by: str = Field(min_length=1, max_length=80)
    draft_id: str | None = Field(default=None, min_length=1, max_length=64)


def _write(request: Request, episode_id: str, at_ms: int | None, action) -> dict:
    """Run a tasks.py writer at the demo time, map its refusal to HTTP, then raise nudges."""
    _require(request, episode_id)
    store = _store(request)
    try:
        ts = action(store, _at(store, episode_id, at_ms))
    except tasks.TaskError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    raise_nudges(store, episode_id, ts)
    return view(request, episode_id)


@flow_router.post("/orders/sign")
def sign_orders(episode_id: str, body: SignIn, request: Request) -> dict:
    items = []
    for item in body.items:
        row = item.model_dump()
        row["limits"] = {k: v for k, v in row["limits"].items() if v is not None} if item.kind == "obs" else {}
        items.append(row)
    return _write(request, episode_id, body.at_ms, lambda s, ts: tasks.sign_order(s, episode_id, items, body.by, ts, body.draft_id))


@flow_router.post("/orders/{order_id}/ack")
def acknowledge(episode_id: str, order_id: str, body: AckIn, request: Request) -> dict:
    return _write(request, episode_id, body.at_ms, lambda s, ts: tasks.acknowledge_order(s, episode_id, order_id, body.by, ts))


@flow_router.post("/tasks/{task_id}/begin")
def begin(episode_id: str, task_id: str, body: BeginIn, request: Request) -> dict:
    return _write(request, episode_id, body.at_ms, lambda s, ts: tasks.begin_task(s, episode_id, task_id, body.by, ts))


@flow_router.post("/tasks/{task_id}/done")
def done(episode_id: str, task_id: str, body: DoneIn, request: Request) -> dict:
    values = body.values.model_dump(exclude_none=True) if body.values else None
    extra = {"transcript": body.transcript.strip(), "proof_id": body.proof_id}
    return _write(
        request,
        episode_id,
        body.at_ms,
        lambda s, ts: tasks.complete_task(s, episode_id, task_id, body.by, ts, via=body.via, note=body.note, values=values, **extra),
    )


@flow_router.post("/discharge/sign")
def sign_discharge(episode_id: str, body: DischargeIn, request: Request) -> dict:
    _require(request, episode_id)
    if body.template not in CARE_TEMPLATES:
        raise HTTPException(status_code=404, detail="Unknown care template")
    store = _store(request)
    events = store.events(episode_id)
    if states.current_state(events) != "ward":
        raise HTTPException(status_code=409, detail="The discharge is signed only while the patient is on the ward.")
    refusal = draft_refusal(events, "discharge", body.draft_id)
    if refusal:
        raise HTTPException(status_code=refusal[0], detail=refusal[1])
    ts = _at(store, episode_id, body.at_ms)
    rx = _latest(events, "rx.ordered")
    signed = {"summary": body.summary.strip(), "by": body.by, **({"draft_id": body.draft_id} if body.draft_id else {})}
    store.append(episode_id, "discharge.signed", signed, ts_ms=ts)
    store.append(episode_id, "discharge.card", card_payload(body.template, rx["payload"] if rx else None, body.by), ts_ms=ts)
    # Every refusal is above. check_move needs the signed event, so a refusal here would be a bug (P2-R6).
    move = states.move_payload(store.events(episode_id), "discharging", {"by": body.by})
    store.append(episode_id, "patient.state", move, ts_ms=ts)
    raise_nudges(store, episode_id, ts)
    return view(request, episode_id)
