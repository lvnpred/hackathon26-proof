"""The ward list (spec §8): patient episodes with a bed, built from patient.registered, and the demo clock routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from app.journey import clock
from app.journey import seed  # seed imports register from here; read BOARD_LABEL at call time
from app.journey.states import current_state

ward_router = APIRouter(prefix="/journey")


class ClockIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ms: int = Field(ge=0, strict=True)


def register(store, episode_id: str, *, bed: str, source: str, document_id: int | None, ts_ms: int) -> dict:
    """Put an episode on the ward in a bed and write patient.registered. Returns the event."""
    store.set_bed(episode_id, bed)
    payload = {"bed": bed, "source": source, "document_id": document_id}
    return store.append(episode_id, "patient.registered", payload, ts_ms=ts_ms)


def next_bed(store) -> str:
    """The lowest whole-number bed nobody holds, as text."""
    taken = set(store.beds().values())
    bed = 1
    while str(bed) in taken:
        bed += 1
    return str(bed)


def _bed_key(bed: str) -> tuple:
    return (0, int(bed), bed) if bed.isdigit() else (1, 0, bed)


def _registered(events: list[dict]) -> dict:
    rows = [e for e in events if e["event_type"] == "patient.registered"]
    return rows[-1]["payload"] if rows else {}


def ward_patients(store) -> list[dict]:
    patients = []
    for episode_id, bed in store.beds().items():
        episode = store.get_episode(episode_id)
        if episode is None or episode["label"] == seed.BOARD_LABEL:
            continue
        events = store.events(episode_id)
        patients.append({
            "id": episode_id,
            "name": episode["label"],
            "bed": bed,
            "state": current_state(events),
            "source": _registered(events).get("source", ""),
        })
    return sorted(patients, key=lambda p: _bed_key(p["bed"]))


def latest_board(store) -> str | None:
    """The newest staff board: it holds the doctor's status and is never a patient."""
    boards = [e for e in store.list_episodes() if e["label"] == seed.BOARD_LABEL]
    return max(boards, key=lambda e: (e["created_at"], e["id"]))["id"] if boards else None


@ward_router.get("/ward")
def ward(request: Request) -> dict:
    store = request.app.state.morning
    return {"now_ms": clock.now_ms(store), "patients": ward_patients(store), "board": latest_board(store)}


@ward_router.post("/clock")
def set_clock(body: ClockIn, request: Request) -> dict:
    """Move the shared demo time for every patient. The Demo dock's tick, jump and reset call this."""
    return {"now_ms": clock.set_ms(request.app.state.morning, body.ms)}
