"""Journey routes: the doctor's, nurse's and patient's actions on one episode, and the nudges between them."""

from __future__ import annotations

import base64

import httpx
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from app.adapters.spark import SparkAdapter
from app.config import BANNER
from app.journey import nudges as rules
from app.journey.play import play_journey
from app.journey.rx import DEMO_DOCUMENT, fetch_document, from_document, key_of
from app.journey.schedule import build as build_schedule, reminders_ics
from app.journey.stories import CARE_TEMPLATES, audit_rows, build_stories, clock, plain
from app.morning.brownbag import read_strip
from app.morning.discharge import visible_events
from app.morning.druglog import parse_drug_phrase
from app.morning.strips import parse_strip_text

router = APIRouter(prefix="/journey/episodes/{episode_id}")

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


class SeenIn(Strict):
    by: str = Field(min_length=1, max_length=80)
    note: str = Field(default="", max_length=300)


class CardIn(At):
    template: str = Field(default="hernia-repair", max_length=40)
    by: str = Field(min_length=1, max_length=80)


class HelpIn(At):
    says: str = Field(min_length=1, max_length=300)


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
    if at_ms is not None:
        return at_ms
    rows = store.events(episode_id)
    return max((row["ts_ms"] for row in rows), default=-1000) + 1000


def raise_nudges(store, episode_id: str, at_ms: int) -> list[dict]:
    """Write each nudge not raised before. Called after every action and on a tick."""
    written = []
    for nudge in rules.fresh(store.events(episode_id), at_ms):
        written.append(store.append(episode_id, "nudge.raised", nudge, ts_ms=nudge["at_ms"]))
    return written


def _latest(events: list[dict], kind: str) -> dict | None:
    rows = [event for event in visible_events(events) if event["event_type"] == kind]
    return rows[-1] if rows else None


def view(request: Request, episode_id: str) -> dict:
    episode = _require(request, episode_id)
    events = _store(request).events(episode_id)
    rx = _latest(events, "rx.ordered")
    card = _latest(events, "discharge.card")
    orders = _latest(events, "ward.orders_set")
    return {
        "episode": episode,
        "banner": BANNER,
        "stories": build_stories(events),
        "rx": rx["payload"] if rx else None,
        "schedule": build_schedule(rx["payload"]) if rx else [],
        "orders": orders["payload"] if orders else None,
        "card": card["payload"] if card else None,
        "strips": [e["payload"] for e in visible_events(events) if e["event_type"] == "brownbag.med_found"],
        "nudges": [
            {**e["payload"], "id": e["id"], "when": clock(e["ts_ms"])} for e in rules.open_nudges(events)
        ],
        "timeline": [
            {"id": e["id"], "when": clock(e["ts_ms"]), "type": e["event_type"], "plain": plain(e)}
            for e in events
        ],
        "templates": {key: value["title"] for key, value in CARE_TEMPLATES.items()},
        # Present once reminders were added, so a reload keeps the download link without a second post.
        "ics_url": f"/journey/episodes/{episode_id}/reminders.ics"
        if any(e["event_type"] == "reminders.added" for e in events)
        else None,
    }


def _act(request: Request, episode_id: str, kind: str, payload: dict, at_ms: int | None) -> dict:
    _require(request, episode_id)
    store = _store(request)
    ts = _at(store, episode_id, at_ms)
    store.append(episode_id, kind, payload, ts_ms=ts)
    raise_nudges(store, episode_id, ts)
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
    return _act(request, episode_id, "rx.ordered", from_document(DEMO_DOCUMENT, source="demo"), body.at_ms)


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
    raise_nudges(store, episode_id, ts + len(body.strips))
    return view(request, episode_id)


@router.post("/strips/photo")
async def strips_photo(episode_id: str, request: Request, file: UploadFile = File(...)) -> dict:
    """Muse Spark 1.3 reads the strip labels. Without a key the photo is not sent anywhere."""
    _require(request, episode_id)
    settings = request.app.state.settings
    if not settings.spark_configured:
        raise HTTPException(status_code=409, detail="No Meta Model API key. Type the strip names instead.")
    raw = await file.read()
    if not raw or len(raw) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=400, detail="Send one photo under 8 MB.")
    kind = file.content_type if (file.content_type or "").startswith("image/") else "image/jpeg"
    data_url = f"data:{kind};base64,{base64.b64encode(raw).decode()}"
    try:
        text = SparkAdapter(settings).read_strips(data_url)
        strips = parse_strip_text(text)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="The strip reader did not return a usable list.") from exc
    store = _store(request)
    ts = _at(store, episode_id, None)
    for offset, strip in enumerate(strips):
        store.append(episode_id, "brownbag.med_found", {**strip, "by": "patient", "source": "muse-spark-1.3"}, ts_ms=ts + offset)
    raise_nudges(store, episode_id, ts + len(strips))
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
    raise_nudges(store, episode_id, _at(store, episode_id, body.at_ms))
    return view(request, episode_id)


@router.post("/nudges/{nudge_id}/seen")
def nudge_seen(episode_id: str, nudge_id: str, body: SeenIn, request: Request) -> dict:
    _require(request, episode_id)
    nudge = _store(request).get_event(nudge_id)
    if nudge is None or nudge["episode_id"] != episode_id or nudge["event_type"] != "nudge.raised":
        raise HTTPException(status_code=404, detail="Nudge not found")
    payload = {"nudge_id": nudge_id, "by": body.by, "note": body.note}
    return _act(request, episode_id, "nudge.seen", payload, None)


@router.post("/discharge-card")
def discharge_card(episode_id: str, body: CardIn, request: Request) -> dict:
    template = CARE_TEMPLATES.get(body.template)
    if template is None:
        raise HTTPException(status_code=404, detail="Unknown care template")
    events = _store(request).events(episode_id)
    rx = _latest(events, "rx.ordered")
    payload = {
        "template": body.template,
        "title": template["title"],
        "warning_signs": template["warning_signs"],
        "wound_care": template["wound_care"],
        "help_line": template["help_line"],
        "review": template["review"],
        "schedule": build_schedule(rx["payload"]) if rx else [],
        "by": body.by,
    }
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
