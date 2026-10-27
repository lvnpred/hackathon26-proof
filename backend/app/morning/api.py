"""Morning routes. The fact card is 404 while the decision tier is off."""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.config import BANNER
from app.morning.brownbag import duplicate_generics, read_strip
from app.morning.discharge import fold
from app.morning.guide import PATIENT_RULE, build_guide, explain_event
from app.morning.druglog import parse_drug_phrase
from app.morning.ics import follow_up_ics
from app.morning.pdf import write_discharge
from app.morning.script import play
from app.morning.vitals import collect_facts, demo_readings, evaluate, template_card

router = APIRouter()

FOLLOW_POLL_S = 0.25
FOLLOW_MAX_S = 30.0


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EpisodeIn(Strict):
    label: str = Field(default="Synthetic demo, R. Kumar", min_length=1, max_length=120)


class PhraseIn(Strict):
    text: str = Field(min_length=1, max_length=400)


class StripIn(Strict):
    name: str
    strength: str = ""


class StripsIn(Strict):
    strips: list[StripIn] = Field(min_length=1)


class TierIn(Strict):
    enabled: bool


class ConfirmIn(Strict):
    by: str = Field(default="demo user", min_length=1, max_length=80)


def _store(request: Request):
    return request.app.state.morning


def _tier(request: Request) -> bool:
    return bool(request.app.state.decision_tier)


def _require(request: Request, episode_id: str) -> dict:
    episode = _store(request).get_episode(episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


@router.get("/morning/tier")
def get_tier(request: Request) -> dict:
    return {"decision_tier": 1 if _tier(request) else 0, "banner": BANNER}


@router.post("/morning/tier")
def set_tier(body: TierIn, request: Request) -> dict:
    request.app.state.decision_tier = body.enabled
    return get_tier(request)


@router.get("/morning/episodes")
def list_episodes(request: Request) -> dict:
    return {"episodes": _store(request).list_episodes(), "rule": PATIENT_RULE}


@router.post("/morning/episodes")
def create_episode(body: EpisodeIn, request: Request) -> dict:
    return _store(request).create_episode(body.label)


@router.get("/morning/episodes/{episode_id}")
def get_episode(episode_id: str, request: Request) -> dict:
    episode = _require(request, episode_id)
    events = _present(request, episode_id)
    return {
        "episode": episode,
        "events": events,
        "sheet": fold(events),
        "guide": build_guide(events, episode["label"]),
        "decision_tier": _tier(request),
    }


@router.get("/morning/episodes/{episode_id}/stream")
def stream_episode(
    episode_id: str,
    request: Request,
    follow: bool = False,
    timeout_s: float = Query(default=FOLLOW_MAX_S, gt=0),
):
    _require(request, episode_id)
    store = _store(request)
    after = request.headers.get("last-event-id")
    rows = store.events(episode_id, after_id=after)

    def frame(event: dict) -> str:
        return f"id: {event['id']}\ndata: {json.dumps(event)}\n\n"

    def generate():
        for event in rows:
            yield frame(event)
        if not rows:
            yield ": idle\n\n"

    async def follow_events():
        # Poll the store and send new rows until the timeout or a disconnect.
        last = rows[-1]["id"] if rows else after
        for event in rows:
            yield frame(event)
        if not rows:
            yield ": idle\n\n"
        deadline = time.monotonic() + min(timeout_s, FOLLOW_MAX_S)
        while time.monotonic() < deadline:
            await asyncio.sleep(FOLLOW_POLL_S)
            if await request.is_disconnected():
                return
            for event in store.events(episode_id, after_id=last):
                last = event["id"]
                yield frame(event)

    body = follow_events() if follow else generate()
    return StreamingResponse(body, media_type="text/event-stream")


@router.post("/morning/episodes/{episode_id}/play")
def play_episode(episode_id: str, request: Request) -> dict:
    _require(request, episode_id)
    try:
        result = play(_store(request), episode_id, decision_tier=_tier(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Episode not found") from exc
    body = get_episode(episode_id, request)
    body["play"] = result
    return body


@router.post("/morning/episodes/{episode_id}/brownbag")
def add_strips(episode_id: str, body: StripsIn, request: Request) -> dict:
    _require(request, episode_id)
    store = _store(request)
    strips = [read_strip(item.name, item.strength) for item in body.strips]
    ts = _next_ts(store, episode_id)
    for offset, strip in enumerate(strips):
        store.append(episode_id, "brownbag.med_found", strip, ts_ms=ts + offset)
    if _tier(request):
        for generic in duplicate_generics(strips):
            store.append(
                episode_id,
                "brownbag.same_drug_twice",
                {"generic": generic},
                ts_ms=ts + len(strips),
                tier="decision",
            )
    return get_episode(episode_id, request)


@router.post("/morning/episodes/{episode_id}/druglog")
def hear_drug(episode_id: str, body: PhraseIn, request: Request) -> dict:
    _require(request, episode_id)
    parsed = parse_drug_phrase(body.text)
    event = _store(request).append(
        episode_id,
        "druglog.parsed",
        parsed,
        ts_ms=_next_ts(_store(request), episode_id),
    )
    return {"draft": event, "needs_confirm": True, "grounded": parsed["grounded"]}


@router.post("/morning/episodes/{episode_id}/druglog/{event_id}/confirm")
def confirm_drug(episode_id: str, event_id: str, body: ConfirmIn, request: Request) -> dict:
    _require(request, episode_id)
    event = _store(request).get_event(event_id)
    if event is None or event["episode_id"] != episode_id or event["event_type"] != "druglog.parsed":
        raise HTTPException(status_code=404, detail="Spoken line not found")
    payload = dict(event["payload"])
    payload["confirmed"] = True
    payload["by"] = body.by
    _store(request).append(
        episode_id,
        "druglog.given",
        payload,
        ts_ms=event["ts_ms"],
        supersedes_id=None,
    )
    return get_episode(episode_id, request)


@router.post("/morning/episodes/{episode_id}/vitals/play")
def play_vitals(episode_id: str, request: Request) -> dict:
    _require(request, episode_id)
    store = _store(request)
    fired: dict[str, int] = {}
    readings = demo_readings()
    base = _next_ts(store, episode_id)
    for reading in readings:
        ts = base + reading.ts_ms
        store.append(
            episode_id,
            "vitals.reading",
            {"systolic": reading.systolic, "diastolic": reading.diastolic, "hr": reading.hr},
            ts_ms=ts,
        )
        if not _tier(request):
            continue
        so_far = [row for row in readings if row.ts_ms <= reading.ts_ms]
        # Shift rule timestamps onto the episode clock for cooldown checks.
        shifted = [
            type(row)(base + row.ts_ms, row.systolic, row.diastolic, row.hr) for row in so_far
        ]
        for fire in evaluate(shifted, last_fired=fired):
            fired[fire["rule_id"]] = fire["ts_ms"]
            if fire["rule_id"] != "bp_drop_pct":
                continue
            facts = collect_facts(store.events(episode_id), ts)
            text = template_card(fire, facts)
            store.append(
                episode_id,
                "vitals.card",
                {"text": text, "wording": "template", "facts": facts, "rule_id": "bp_drop_pct"},
                ts_ms=ts,
                tier="decision",
            )
            store.append(
                episode_id,
                "vitals.change",
                {"rule_id": "bp_drop_pct", "drop_pct": fire["drop_pct"]},
                ts_ms=ts,
                tier="decision",
            )
    return get_episode(episode_id, request)


@router.get("/morning/episodes/{episode_id}/card")
def get_card(episode_id: str, request: Request) -> dict:
    _require(request, episode_id)
    if not _tier(request):
        raise HTTPException(status_code=404, detail="The fact card is off.")
    cards = [
        event
        for event in _store(request).events(episode_id)
        if event["event_type"] == "vitals.card"
    ]
    if not cards:
        raise HTTPException(status_code=404, detail="No fact card yet.")
    return {"banner": BANNER, "card": cards[-1]}


@router.post("/morning/episodes/{episode_id}/discharge")
def draft_discharge(episode_id: str, request: Request) -> dict:
    episode = _require(request, episode_id)
    sheet = fold(_store(request).events(episode_id))
    path = request.app.state.settings.report_dir / "morning" / f"{episode_id}.pdf"
    write_discharge(path, label=episode["label"], sheet=sheet)
    _store(request).append(
        episode_id,
        "discharge.drafted",
        {"pdf": f"/morning/episodes/{episode_id}/discharge.pdf"},
        ts_ms=_next_ts(_store(request), episode_id),
    )
    return {
        "sheet": sheet,
        "pdf_url": f"/morning/episodes/{episode_id}/discharge.pdf",
        "ics_url": f"/morning/episodes/{episode_id}/follow-up.ics",
        "banner": BANNER,
    }


@router.get("/morning/episodes/{episode_id}/discharge.pdf")
def discharge_pdf(episode_id: str, request: Request):
    episode = _require(request, episode_id)
    path = request.app.state.settings.report_dir / "morning" / f"{episode_id}.pdf"
    if not path.is_file():
        sheet = fold(_store(request).events(episode_id))
        write_discharge(path, label=episode["label"], sheet=sheet)
    return Response(path.read_bytes(), media_type="application/pdf")


@router.get("/morning/episodes/{episode_id}/follow-up.ics")
def follow_up(episode_id: str, request: Request):
    episode = _require(request, episode_id)
    body = follow_up_ics(episode["label"])
    return Response(
        body,
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=follow-up.ics"},
    )


def _present(request: Request, episode_id: str) -> list[dict]:
    events = []
    for event in _store(request).events(episode_id):
        shown = dict(event)
        shown["plain"] = explain_event(event)
        events.append(shown)
    return events


def _next_ts(store, episode_id: str) -> int:
    rows = store.events(episode_id)
    if not rows:
        return 0
    return max(row["ts_ms"] for row in rows) + 1000
