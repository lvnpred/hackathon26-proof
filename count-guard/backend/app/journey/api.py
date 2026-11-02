"""Journey routes: the doctor's, nurse's and patient's actions on one episode, and the nudges between them."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from app.config import BANNER
from app.journey import home_medicines, nudges as rules
from app.journey.ai_moments import moments
from app.journey.handover import draft as draft_handover
from app.journey.intake import chart_header
from app.journey.medicines import day_plan
from app.journey.play import play_journey
from app.journey.rx import document_for, fetch_document, from_document, key_of
from app.journey.schedule import build as build_schedule, reminders_ics
from app.journey.seed import card_payload, seed_ward
from app.journey.clock import stamp
from app.journey.clocktext import latest_ms, when_text
from app.journey.states import flow_view
from app.journey.verdict import checks_view
from app.journey.stories import CARE_TEMPLATES, audit_rows, build_stories, timeline_items
from app.morning.brownbag import read_strip
from app.morning.discharge import visible_events
from app.morning.druglog import parse_drug_phrase
from app.ops import run as ops_run
from app.ops import site as ops_site
from app.ops.items import ops_view

router = APIRouter(prefix="/journey/episodes/{episode_id}")
demo_router = APIRouter(prefix="/journey/demo")

MAX_PHOTO_BYTES = 8 * 1024 * 1024


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class At(Strict):
    at_ms: int | None = Field(default=None, ge=0)


class ImportIn(At):
    document_id: int = Field(ge=1)


class DoseOrder(Strict):
    name: str = Field(min_length=1, max_length=80)
    amount: str = Field(default="", max_length=40)
    every_h: float = Field(gt=0, le=72)


class Limits(Strict):
    sbp_min: int | None = Field(default=None, ge=40, le=250)
    sbp_max: int | None = Field(default=None, ge=40, le=250)
    hr_max: int | None = Field(default=None, ge=20, le=250)
    spo2_min: int | None = Field(default=None, ge=50, le=100)
    temp_max: float | None = Field(default=None, ge=34, le=43)


class OrdersIn(At):
    doses: list[DoseOrder] = Field(default_factory=list, max_length=20)
    obs_every_h: float | None = Field(default=None, gt=0, le=24)
    limits: Limits = Field(default_factory=Limits)
    by: str = Field(min_length=1, max_length=80)


class Strip(Strict):
    name: str = Field(min_length=1, max_length=80)
    strength: str = Field(default="", max_length=40)


class StripsIn(At):
    strips: list[Strip] = Field(min_length=1, max_length=20)


class DoseIn(At):
    text: str | None = Field(default=None, min_length=1, max_length=200)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    amount: str = Field(default="", max_length=40)
    by: str = Field(min_length=1, max_length=80)


class ObsIn(At):
    sbp: int = Field(ge=30, le=300)
    dbp: int = Field(ge=10, le=200)
    hr: int = Field(ge=20, le=250)
    spo2: int | None = Field(default=None, ge=50, le=100)
    temp: float | None = Field(default=None, ge=30, le=45)
    by: str = Field(min_length=1, max_length=80)


class SeenIn(At):
    by: str = Field(min_length=1, max_length=80)
    note: str = Field(default="", max_length=300)


class CardIn(At):
    template: str = Field(default="hernia-repair", max_length=40)
    by: str = Field(min_length=1, max_length=80)


class HelpIn(At):
    says: str = Field(min_length=1, max_length=300)


class HandoverIn(At):
    from_nurse: str = Field(min_length=1, max_length=80)
    to_nurse: str = Field(min_length=1, max_length=80)
    since_ms: int | None = Field(default=None, ge=0)
    use_model: bool = True


class AcceptIn(At):
    by: str = Field(min_length=1, max_length=80)


class CheckinIn(At):
    day: int = Field(ge=1, le=60)
    feels: str = Field(min_length=1, max_length=80)
    signs: list[str] = Field(default_factory=list, max_length=10)
    note: str = Field(default="", max_length=300)


def _store(request: Request):
    return request.app.state.morning


def _require(request: Request, episode_id: str) -> dict:
    episode = _store(request).get_episode(episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


def _at(store, episode_id: str, at_ms: int | None) -> int:
    return stamp(store, episode_id, at_ms)


def raise_nudges(store, episode_id: str, at_ms: int) -> list[dict]:
    """Write each nudge not raised before. Called after every action and on a tick."""
    written = []
    for nudge in rules.fresh(store.events(episode_id), at_ms):
        written.append(store.append(episode_id, "nudge.raised", nudge, ts_ms=nudge["at_ms"]))
    return written


def settle(request: Request, episode_id: str, ts: int) -> None:
    """After every write: raise nudges, then let the ops agent act, inside the same request (R5)."""
    store = _store(request)
    raise_nudges(store, episode_id, ts)
    try:
        ops_run.run(store, episode_id, ts, settings=request.app.state.settings,
                    write=getattr(request.app.state, "ops_write", None))
    except Exception:  # the agent must never fail the person's write
        logging.getLogger(__name__).exception("ops agent failed for episode %s", episode_id)


def _latest(events: list[dict], kind: str) -> dict | None:
    rows = [event for event in visible_events(events) if event["event_type"] == kind]
    return rows[-1] if rows else None


def view(request: Request, episode_id: str) -> dict:
    episode = _require(request, episode_id)
    store = _store(request)
    events = store.events(episode_id)
    now = latest_ms(events)  # the record's own now: the newest time written
    rx = _latest(events, "rx.ordered")
    card = _latest(events, "discharge.card")
    orders = _latest(events, "ward.orders_set")
    handover = _latest(events, "handover.drafted")
    accepted = [e for e in events if e["event_type"] == "handover.accepted"]
    if handover:
        took = next((e for e in accepted if e["payload"]["handover_id"] == handover["id"]), None)
        handover = {**handover["payload"], "id": handover["id"], "accepted_by": took["payload"]["by"] if took else None}
    return {
        "episode": episode,
        "header": chart_header(events, store.beds().get(episode_id), request.app.state.settings.dd_base),
        "banner": BANNER,
        "stories": build_stories(events),
        "rx": rx["payload"] if rx else None,
        "schedule": build_schedule(rx["payload"]) if rx else [],
        "day_plan": day_plan(rx["payload"], (_latest(events, "medicines.read") or {}).get("payload")) if rx else None,
        "orders": orders["payload"] if orders else None,
        "card": card["payload"] if card else None,
        "handover": handover,
        "strips": home_medicines.with_match(visible_events(events)),
        "nudges": [
            {**e["payload"], "id": e["id"], "when": when_text(e["ts_ms"], now)} for e in rules.open_nudges(events)
        ],
        "timeline": timeline_items(events, now),
        "ai_moments": moments(events, now),
        "ops": ops_view(events, paused=ops_site.paused(store)[0], now_ms=now),
        "templates": {key: value["title"] for key, value in CARE_TEMPLATES.items()},
        **flow_view(events, now),
        "photo_checks": checks_view(events),
        # Present once reminders were added, so a reload keeps the download link without a second post.
        "ics_url": f"/journey/episodes/{episode_id}/reminders.ics"
        if any(e["event_type"] == "reminders.added" for e in events)
        else None,
    }


def _act(
    request: Request, episode_id: str, kind: str, payload: dict, at_ms: int | None, supersedes_id: str | None = None
) -> dict:
    _require(request, episode_id)
    store = _store(request)
    ts = _at(store, episode_id, at_ms)
    store.append(episode_id, kind, payload, ts_ms=ts, supersedes_id=supersedes_id)
    settle(request, episode_id, ts)
    return view(request, episode_id)


@router.get("")
def get_journey(episode_id: str, request: Request) -> dict:
    return view(request, episode_id)


@router.post("/rx/import")
def import_rx(episode_id: str, body: ImportIn, request: Request) -> dict:
    """Option A: read the saved prescription from a running Doctor Dictation."""
    _require(request, episode_id)
    base = request.app.state.settings.dd_base
    try:
        document = fetch_document(base, body.document_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Doctor Dictation did not answer at {base}.") from exc
    payload = from_document(document, source="doctor-dictation")
    if not payload["rows"]:
        raise HTTPException(status_code=422, detail="That prescription has no medicine rows.")
    return _act(request, episode_id, "rx.ordered", payload, body.at_ms)


@router.post("/rx/demo")
def demo_rx(episode_id: str, body: At, request: Request) -> dict:
    episode = _require(request, episode_id)
    return _act(request, episode_id, "rx.ordered", from_document(document_for(episode["label"]), source="demo"), body.at_ms)


@router.post("/orders")
def set_orders(episode_id: str, body: OrdersIn, request: Request) -> dict:
    payload = {
        "doses": [{**order.model_dump(), "key": key_of(order.name)} for order in body.doses],
        "obs_every_h": body.obs_every_h,
        "limits": {k: v for k, v in body.limits.model_dump().items() if v is not None},
        "by": body.by,
    }
    return _act(request, episode_id, "ward.orders_set", payload, body.at_ms)


@router.post("/strips")
def scan_strips(episode_id: str, body: StripsIn, request: Request) -> dict:
    _require(request, episode_id)
    store = _store(request)
    ts = _at(store, episode_id, body.at_ms)
    for offset, strip in enumerate(body.strips):
        found = {**read_strip(strip.name, strip.strength), "by": "patient", "source": "typed"}
        store.append(episode_id, "brownbag.med_found", found, ts_ms=ts + offset)
    settle(request, episode_id, ts + len(body.strips))
    return view(request, episode_id)


@router.post("/reminders")
def add_reminders(episode_id: str, body: At, request: Request) -> dict:
    events = _store(request).events(episode_id)
    rx = _latest(events, "rx.ordered")
    if rx is None:
        raise HTTPException(status_code=409, detail="No prescription yet.")
    count = sum(1 for row in build_schedule(rx["payload"]) if not row["as_needed"])
    result = _act(request, episode_id, "reminders.added", {"count": count, "by": "patient"}, body.at_ms)
    result["ics_url"] = f"/journey/episodes/{episode_id}/reminders.ics"
    return result


@router.get("/reminders.ics")
def reminders_file(episode_id: str, request: Request):
    episode = _require(request, episode_id)
    rx = _latest(_store(request).events(episode_id), "rx.ordered")
    if rx is None:
        raise HTTPException(status_code=404, detail="No prescription yet.")
    body = reminders_ics(build_schedule(rx["payload"]), episode["label"])
    return Response(body, media_type="text/calendar",
                    headers={"Content-Disposition": "attachment; filename=dose-reminders.ics"})


@router.post("/dose")
def log_dose(episode_id: str, body: DoseIn, request: Request) -> dict:
    """A dose line typed or spoken by the nurse. The voice parser fills name and amount."""
    if body.text:
        heard = parse_drug_phrase(body.text)
        name = (heard["generic"] or heard["name_as_heard"] or "").strip()
        amount = " ".join(str(part) for part in (heard["amount"], heard["unit"]) if part)
        source = "spoken"
    elif body.name:
        name, amount, source = body.name, body.amount, "typed"
    else:
        raise HTTPException(status_code=422, detail="Send text or a name.")
    if not name:
        raise HTTPException(status_code=422, detail="No medicine name was heard.")
    payload = {"key": key_of(name), "name": name.capitalize(), "amount": amount, "by": body.by, "source": source}
    return _act(request, episode_id, "dose.given", payload, body.at_ms)


@router.post("/obs")
def log_obs(episode_id: str, body: ObsIn, request: Request) -> dict:
    payload = body.model_dump(exclude={"at_ms"})
    return _act(request, episode_id, "obs.recorded", payload, body.at_ms)


@router.post("/tick")
def tick(episode_id: str, body: At, request: Request) -> dict:
    """Check overdue doses and observations at a clock time. The ward screen calls this."""
    _require(request, episode_id)
    store = _store(request)
    settle(request, episode_id, _at(store, episode_id, body.at_ms))
    return view(request, episode_id)


@router.post("/nudges/{nudge_id}/seen")
def nudge_seen(episode_id: str, nudge_id: str, body: SeenIn, request: Request) -> dict:
    _require(request, episode_id)
    nudge = _store(request).get_event(nudge_id)
    if nudge is None or nudge["episode_id"] != episode_id or nudge["event_type"] != "nudge.raised":
        raise HTTPException(status_code=404, detail="Nudge not found")
    payload = {"nudge_id": nudge_id, "by": body.by, "note": body.note}
    at_ms = max(body.at_ms, nudge["ts_ms"]) if body.at_ms is not None else None  # never before the nudge
    return _act(request, episode_id, "nudge.seen", payload, at_ms)


@router.post("/handover")
def handover(episode_id: str, body: HandoverIn, request: Request) -> dict:
    """Draft the shift handover. Muse Spark 1.3 rewords it only when the wording check passes."""
    episode = _require(request, episode_id)
    store = _store(request)
    at = _at(store, episode_id, body.at_ms)
    events = store.events(episode_id)
    since = body.since_ms
    if since is None:  # from the last handover, else from the ward orders
        earlier = [e for e in events if e["event_type"] == "handover.drafted"]
        orders = _latest(events, "ward.orders_set")
        since = earlier[-1]["ts_ms"] if earlier else (orders["ts_ms"] if orders else 0)
    payload = draft_handover(
        events,
        patient=episode["label"],
        since_ms=since,
        at_ms=at,
        from_nurse=body.from_nurse,
        to_nurse=body.to_nurse,
        settings=request.app.state.settings,
        use_model=body.use_model,
        write=getattr(request.app.state, "handover_write", None),
    )
    return _act(request, episode_id, "handover.drafted", payload, at)


@router.post("/handover/{handover_id}/accept")
def accept_handover(episode_id: str, handover_id: str, body: AcceptIn, request: Request) -> dict:
    _require(request, episode_id)
    drafted = _store(request).get_event(handover_id)
    if drafted is None or drafted["episode_id"] != episode_id or drafted["event_type"] != "handover.drafted":
        raise HTTPException(status_code=404, detail="Handover not found")
    at_ms = max(body.at_ms, drafted["ts_ms"]) if body.at_ms is not None else None  # never before the draft
    return _act(request, episode_id, "handover.accepted", {"handover_id": handover_id, "by": body.by}, at_ms)


@router.post("/discharge-card")
def discharge_card(episode_id: str, body: CardIn, request: Request) -> dict:
    template = CARE_TEMPLATES.get(body.template)
    if template is None:
        raise HTTPException(status_code=404, detail="Unknown care template")
    events = _store(request).events(episode_id)
    rx = _latest(events, "rx.ordered")
    payload = card_payload(body.template, rx["payload"] if rx else None, body.by)
    return _act(request, episode_id, "discharge.card", payload, body.at_ms)


@router.post("/help")
def need_help(episode_id: str, body: HelpIn, request: Request) -> dict:
    return _act(request, episode_id, "help.requested", {"says": body.says, "by": "patient"}, body.at_ms)


@router.post("/checkin")
def check_in(episode_id: str, body: CheckinIn, request: Request) -> dict:
    payload = {**body.model_dump(exclude={"at_ms"}), "by": "patient"}
    return _act(request, episode_id, "checkin.recorded", payload, body.at_ms)


@router.get("/audit")
def audit(episode_id: str, request: Request) -> dict:
    episode = _require(request, episode_id)
    return {"episode": episode, "banner": BANNER, "rows": audit_rows(_store(request).events(episode_id))}


@router.post("/play")
def play(episode_id: str, request: Request) -> dict:
    """The three-act demo on this episode: doctor, nurse, patient."""
    _require(request, episode_id)
    play_journey(_store(request), episode_id, raise_nudges)
    return view(request, episode_id)


@demo_router.post("/seed")
def seed(request: Request) -> dict:
    """Three new synthetic patients and the staff board. Earlier episodes stay."""
    return seed_ward(_store(request), raise_nudges)
