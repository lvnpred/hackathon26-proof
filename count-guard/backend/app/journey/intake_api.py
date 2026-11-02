"""Intake routes (spec §7.1, §7.5): Doctor Dictation's push, a new patient made here, and the doctor's bed move."""

from __future__ import annotations

import hmac
import sqlite3
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.config import sync_token
from app.journey import clock, intake, sync, ward_api
from app.journey.api import At, Strict, _at, _require, _store, settle, view

intake_router = APIRouter(prefix="/journey")


class Loose(BaseModel):
    model_config = ConfigDict(extra="allow")  # the rest of Doctor Dictation's document rides along unread


class StructuredIn(Loose):
    patientName: str = Field(default="", max_length=120)
    ageSex: str = Field(default="", max_length=20)
    opNo: str = Field(default="", max_length=40)
    diagnosis: list[str] = Field(default_factory=list, max_length=20)
    rx: list[dict] = Field(default_factory=list, max_length=40)


class AuthorIn(Loose):
    doctor_name: str = Field(default="", max_length=80)


class DocumentIn(Loose):
    structured: StructuredIn = Field(default_factory=StructuredIn)
    author: AuthorIn = Field(default_factory=AuthorIn)


class IntakeIn(Strict):
    source: Literal["doctor-dictation"]
    document_id: int = Field(ge=1)
    status: Literal["admit", "send_home"] = "admit"
    admit_reason: str = Field(default="", max_length=300)
    finalized_at: str = Field(min_length=1, max_length=40)
    document: DocumentIn


class PatientIn(Strict):
    name: str = Field(min_length=1, max_length=80)
    age_sex: str = Field(default="", max_length=20)
    reason: str = Field(default="", max_length=300)


class SyncIn(Strict):
    since: str | None = Field(default=None, max_length=40)


class BedIn(At):
    bed: str = Field(min_length=1, max_length=8, pattern=r"^[A-Za-z0-9-]+$")
    by: str = Field(min_length=1, max_length=80)


def _check_token(given: str | None) -> None:
    """When CG_SYNC_TOKEN is set, the push must carry it. The value is never logged or echoed."""
    expected = sync_token()
    if expected and not hmac.compare_digest((given or "").encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="The sync token is missing or wrong.")


def _answer(request: Request, result: dict) -> JSONResponse:
    if result["created"] or result["updated"]:
        settle(request, result["episode_id"], result["at_ms"])
    return JSONResponse(result, status_code=201 if result["created"] else 200)


@intake_router.post("/intake")
def take_intake(body: IntakeIn, request: Request, x_cg_sync_token: str | None = Header(default=None)) -> JSONResponse:
    """Doctor Dictation's push on admit, and each row Sync pulls. 201 when the patient is new, else 200."""
    _check_token(x_cg_sync_token)
    store = _store(request)
    try:
        result = intake.take(store, body.model_dump(), now_ms=clock.now_ms(store))
    except intake.NotAdmitted as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _answer(request, result)


@intake_router.post("/patients")
def new_patient(body: PatientIn, request: Request) -> JSONResponse:
    """A patient made in Count Guard. While the demo seed is in use the name must end in "(synthetic)"."""
    store = _store(request)
    name = " ".join(body.name.split())
    if ward_api.latest_board(store) is not None and not name.endswith(intake.SYNTHETIC):
        raise HTTPException(status_code=422, detail='In the demo, the name must end in "(synthetic)".')
    result = intake.new_patient(store, name=name, age_sex=body.age_sex, reason=body.reason,
                                now_ms=clock.now_ms(store))
    return _answer(request, result)


@intake_router.post("/sync")
def sync_ward(request: Request, body: SyncIn | None = None) -> dict:
    """The Sync button: Count Guard asks Doctor Dictation (token sent here, never from the browser)."""
    store = _store(request)
    got = sync.pull(request.app.state.settings, store, since=body.since if body else None,
                    now_ms=clock.now_ms(store))
    for episode_id, at_ms in got.pop("changed"):
        settle(request, episode_id, at_ms)
    return got


@intake_router.post("/episodes/{episode_id}/bed")
def move_bed(episode_id: str, body: BedIn, request: Request) -> dict:
    """The doctor moves the patient to another bed. 409 when someone else holds it."""
    _require(request, episode_id)
    store = _store(request)
    before = store.beds().get(episode_id)
    if before is None:
        raise HTTPException(status_code=409, detail="This patient is not on the ward list.")
    if before == body.bed:
        return view(request, episode_id)
    try:
        store.set_bed(episode_id, body.bed)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=f"Bed {body.bed} is taken.") from exc
    ts = _at(store, episode_id, body.at_ms)
    store.append(episode_id, "bed.changed", {"from": before, "to": body.bed, "by": body.by}, ts_ms=ts)
    settle(request, episode_id, ts)
    return view(request, episode_id)
