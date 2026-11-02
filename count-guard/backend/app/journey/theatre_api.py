"""Theatre routes (spec §6.4): drug given by voice, the simulated vitals strip, and the context card (CG-24).

Every route answers only while the patient is in theatre: a 409 `{"error": "not in theatre"}` otherwise.
Hard stop (§6.5): a heard pack writes `count.pack_heard`; only a person's confirm writes `count.pack_opened`
with that person's `by`. Nothing here writes `count.closing`.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import Field, field_validator

from app.journey import live, states, switches, theatre
from app.journey.api import At, _act, _at, _require, _store, settle, view
from app.journey.media_api import SPARK, _heard
from app.journey.theatre import DRUG_GIVEN, DRUG_HEARD, PACK_HEARD, PACK_OPENED
from app.morning.vitals import choose_wording

theatre_router = APIRouter(prefix="/journey/episodes/{episode_id}/theatre")
NOT_IN_THEATRE = "not in theatre"


class NotInTheatre(Exception):
    pass


async def not_in_theatre(_request: Request, _exc: NotInTheatre) -> JSONResponse:
    return JSONResponse({"error": NOT_IN_THEATRE, "detail": "The patient is not in theatre."}, status_code=409)


class ConfirmIn(At):
    by: str = Field(min_length=1, max_length=80)

    @field_validator("by")
    @classmethod
    def _person(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Say who confirms.")
        return value.strip()


class TierIn(At):
    on: bool


def _events(request: Request, episode_id: str) -> list[dict]:
    """This episode's events: 404 for an unknown episode, NotInTheatre (409) outside theatre."""
    _require(request, episode_id)
    events = _store(request).events(episode_id)
    if states.current_state(events) != "theatre":
        raise NotInTheatre()
    return events


def _tier(request: Request) -> bool:
    return bool(request.app.state.decision_tier)


def _reword(request: Request):
    """Spec §6.7: SPARK_LIVE on asks Spark to reword, kept only if the wording check passes; off, the template."""
    settings = request.app.state.settings

    def reword(template: str) -> tuple[str, str, str, list[dict]]:
        if not switches.is_live(settings, "spark"):
            return template, "template", "prepared", []
        start = time.monotonic()
        reply = live.spark_text(settings, theatre.CARD_PROMPT + template)
        ms = round((time.monotonic() - start) * 1000)
        text, wording = choose_wording(template, reply)
        source = SPARK if wording == "llm" else "template (model reply not used)"
        return text, wording, source, [live.call_of("spark", settings, source, ms)]

    return reword


def _write_card(request: Request, episode_id: str, ts: int) -> None:
    """Write the context card once per stay, when the tier is on and the strip shows a BP drop."""
    if not _tier(request):
        return
    store = _store(request)
    card = theatre.card_payload(store.events(episode_id), ts, _reword(request))
    if card is not None:
        store.append(episode_id, theatre.CARD, card, ts_ms=ts, tier="decision")


@theatre_router.get("")
def theatre_panel(episode_id: str, request: Request) -> dict:
    return theatre.panel(_events(request, episode_id), _tier(request))


@theatre_router.post("/drug")
def hear_drug(
    episode_id: str,
    request: Request,
    by: str = Form(..., min_length=1, max_length=80),
    at_ms: int | None = Form(None, ge=0),
    text: str | None = Form(None, min_length=1, max_length=400),
    heard_by: str = Form("", max_length=40),
    file: UploadFile | None = File(None),
) -> dict:
    """A spoken or typed theatre line. A drug is a draft row; a pack line ("opening twenty swabs") is a heard pack.
    Neither counts until a person confirms it."""
    _events(request, episode_id)
    said = _heard(request.app.state.settings, file, text, heard_by)
    kind, payload = theatre.heard(said["text"])
    if kind == DRUG_HEARD and not (payload["name_as_heard"] or "").strip():
        raise HTTPException(status_code=422, detail="No medicine name was heard. Say or type the drug again.")
    payload = {**payload, "by": by, "source": said["source"], "heard_by": said["source"], "calls": said["calls"]}
    return _act(request, episode_id, kind, payload, at_ms)


def _confirm(request: Request, episode_id: str, draft_id: str, kinds: tuple[str, str], missing: str) -> dict:
    heard_kind, done_kind = kinds
    stay = states.stay_events(_events(request, episode_id))
    found = theatre.draft(stay, heard_kind, draft_id)
    if found is None:
        raise HTTPException(status_code=404, detail=missing)
    if theatre.confirmed(stay, done_kind, draft_id):
        raise HTTPException(status_code=409, detail="Already confirmed.")
    return found


@theatre_router.post("/drug/{draft_id}/confirm")
def confirm_drug(episode_id: str, draft_id: str, body: ConfirmIn, request: Request) -> dict:
    """A person's tap: the heard row becomes a drug given, by them."""
    found = _confirm(request, episode_id, draft_id, (DRUG_HEARD, DRUG_GIVEN), "Heard drug line not found.")
    keep = {k: v for k, v in found["payload"].items() if k not in ("by", "calls")}
    payload = {**keep, "confirmed": True, "by": body.by, "draft_id": draft_id}
    return _act(request, episode_id, DRUG_GIVEN, payload, body.at_ms)


@theatre_router.post("/pack/{draft_id}/confirm")
def confirm_pack(episode_id: str, draft_id: str, body: ConfirmIn, request: Request) -> dict:
    """A person's tap: the heard pack is opened, by them. Like Add pack, a heard pack adds to the count."""
    found = _confirm(request, episode_id, draft_id, (PACK_HEARD, PACK_OPENED), "Heard pack not found.")
    heard = found["payload"]
    payload = {"item_type": heard["item_type"], "quantity": heard["n"], "source": "voice", "by": body.by,
               "draft_id": draft_id}
    return _act(request, episode_id, PACK_OPENED, payload, body.at_ms)


@theatre_router.post("/vitals/step")
def vitals_step(episode_id: str, body: At, request: Request) -> dict:
    """The next reading of the simulated strip, labelled Simulated. With the tier on, a BP drop writes the card."""
    events = _events(request, episode_id)
    reading = theatre.next_reading(states.stay_events(events))
    if reading is None:
        raise HTTPException(status_code=409, detail="The simulated strip has ended.")
    store = _store(request)
    ts = _at(store, episode_id, body.at_ms)
    store.append(episode_id, theatre.READING, reading, ts_ms=ts)
    _write_card(request, episode_id, ts)
    settle(request, episode_id, ts)
    return view(request, episode_id)


@theatre_router.post("/tier")
def set_tier(episode_id: str, body: TierIn, request: Request) -> dict:
    """The decision tier (CG-24), shared with the morning screens. Turned on after a drop, it writes the card then."""
    _events(request, episode_id)
    request.app.state.decision_tier = body.on
    if body.on:
        store = _store(request)
        _write_card(request, episode_id, _at(store, episode_id, body.at_ms))
    return {"decision_tier": body.on, "banner": theatre.RESEARCH_BANNER}


@theatre_router.get("/card")
def get_card(episode_id: str, request: Request) -> dict:
    """The context card with the research banner; 404 while the tier is off or before a drop."""
    events = _events(request, episode_id)
    if not _tier(request):
        raise HTTPException(status_code=404, detail="The context card is off.")
    card = states.stay_latest(events, theatre.CARD)
    if card is None:
        raise HTTPException(status_code=404, detail="No context card yet.")
    return {"banner": theatre.RESEARCH_BANNER, "card": {**card["payload"], "id": card["id"], "at_ms": card["ts_ms"]}}
