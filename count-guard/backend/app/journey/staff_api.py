"""Staff routes: the doctor's status. A hand-set status is written on the ward staff board, never on a patient."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field, model_validator

from app.journey import seed
from app.journey.api import Strict, _require, _store
from app.journey.doctor_status import current

staff_router = APIRouter(prefix="/journey/staff")

NOT_BOARD = "That is not the ward staff board."
IDS_BAD = "Give 1 to 10 patient ids, each 1 to 64 characters."
MAX_HOURS = 12 * 3_600_000


class StatusIn(Strict):
    board: str = Field(min_length=1, max_length=64)
    ids: list[str] = Field(min_length=1, max_length=10)
    doctor: str = Field(default=seed.DOCTOR, min_length=1, max_length=80)
    status: Literal["available", "busy", "auto"]
    until_ms: int | None = None
    at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _window(self):
        if any(not 1 <= len(i) <= 64 for i in self.ids):
            raise ValueError(IDS_BAD)
        if self.status == "auto":
            if self.until_ms is not None:
                raise ValueError("An automatic status has no end time.")
        elif self.until_ms is None or not self.at_ms < self.until_ms <= self.at_ms + MAX_HOURS:
            raise ValueError("The end time must be after now and within 12 hours.")
        return self


def _context(request: Request, board: str, ids: list[str]) -> list[list[dict]]:
    """The staff board is checked, then each patient's events. Unknown id: 404."""
    store = _store(request)
    if _require(request, board)["label"] != seed.BOARD_LABEL:
        raise HTTPException(status_code=422, detail=NOT_BOARD)
    if board in ids:
        raise HTTPException(status_code=422, detail=NOT_BOARD)
    for episode_id in ids:
        _require(request, episode_id)
    return [store.events(episode_id) for episode_id in dict.fromkeys(ids)]


def _read(request: Request, board: str, ids: list[str], doctor: str, at_ms: int) -> dict:
    episodes = _context(request, board, ids)
    return current(doctor, episodes, _store(request).events(board), at_ms)


@staff_router.get("/doctor")
def doctor_status(
    request: Request,
    board: str = Query(min_length=1, max_length=64),
    ids: str = Query(min_length=1, max_length=900),
    at_ms: int = Query(ge=0),
    doctor: str = Query(default=seed.DOCTOR, min_length=1, max_length=80),
) -> dict:
    wanted = ids.split(",")
    if len(wanted) > 10 or any(not 1 <= len(i) <= 64 for i in wanted):
        raise HTTPException(status_code=422, detail=IDS_BAD)
    return _read(request, board, wanted, doctor, at_ms)


@staff_router.post("/doctor")
def set_doctor_status(body: StatusIn, request: Request) -> dict:
    _context(request, body.board, body.ids)
    payload = {"doctor": body.doctor, "status": body.status, "until_ms": body.until_ms, "source": "manual", "by": body.doctor}
    _store(request).append(body.board, "doctor.status", payload, ts_ms=body.at_ms)
    return _read(request, body.board, body.ids, body.doctor, body.at_ms)
