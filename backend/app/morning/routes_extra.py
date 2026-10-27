"""Count replay, spoken pack, corrections, vitals transport, and strip text."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from app.core.ledger import ledger_rows, open_discrepancies
from app.morning.camera_file import camera_count_events
from app.morning.count_rules import demo_frames, fresh_state, observe, replay
from app.morning.discharge import fold
from app.morning.guide import build_guide, explain_event
from app.morning.druglog import parse_drug_phrase
from app.morning.intents import parse_pack
from app.morning.sim import apply as apply_sim
from app.morning.strips import parse_strip_text

router = APIRouter()


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HearIn(Strict):
    text: str = Field(min_length=1, max_length=400)


class ManualIn(Strict):
    track_id: str = Field(min_length=1, max_length=80)


class CaseLink(Strict):
    case_id: str = Field(min_length=1)


class FrameIn(Strict):
    track_id: str
    zone: str
    frame_id: str
    t_ms: int = Field(ge=0)


class CorrectIn(Strict):
    payload: dict


class SimIn(Strict):
    action: str
    t_ms: int | None = None
    step_ms: int = 30_000


def _store(request: Request):
    return request.app.state.morning


def _require(request: Request, episode_id: str) -> dict:
    episode = _store(request).get_episode(episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


def _view(request: Request, episode_id: str) -> dict:
    episode = _require(request, episode_id)
    events = []
    for event in _store(request).events(episode_id):
        shown = dict(event)
        shown["plain"] = explain_event(event)
        events.append(shown)
    return {
        "episode": episode,
        "events": events,
        "sheet": fold(events),
        "guide": build_guide(events, episode["label"]),
    }


def _next_ts(store, episode_id: str) -> int:
    rows = store.events(episode_id)
    if not rows:
        return 0
    return max(row["ts_ms"] for row in rows) + 1000


@router.post("/morning/episodes/{episode_id}/hear")
def hear(episode_id: str, body: HearIn, request: Request) -> dict:
    _require(request, episode_id)
    pack = parse_pack(body.text)
    store = _store(request)
    ts = _next_ts(store, episode_id)
    if pack:
        event = store.append(episode_id, "count.pack_opened", pack, ts_ms=ts)
        return {"kind": "pack", "event": event}
    parsed = parse_drug_phrase(body.text)
    event = store.append(episode_id, "druglog.parsed", parsed, ts_ms=ts)
    return {"kind": "drug", "event": event, "needs_confirm": True, "grounded": parsed["grounded"]}


@router.post("/morning/episodes/{episode_id}/count/replay")
def replay_count(episode_id: str, request: Request) -> dict:
    _require(request, episode_id)
    store = _store(request)
    for event in replay(demo_frames(), opened=20):
        store.append(
            episode_id,
            event["event_type"],
            event["payload"],
            ts_ms=event["ts_ms"],
            tier=event["tier"],
        )
    return _view(request, episode_id)


@router.post("/morning/episodes/{episode_id}/count/from-case")
def file_camera_count(episode_id: str, body: CaseLink, request: Request) -> dict:
    """Write the camera ledger onto this patient. A second click does not add a second count."""
    _require(request, episode_id)
    case = request.app.state.store.get_case(body.case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Camera case not found")
    morning = _store(request)
    already = [
        event
        for event in morning.events(episode_id)
        if event["event_type"] == "count.closing"
        and (event.get("payload") or {}).get("case_id") == body.case_id
    ]
    if already:
        view = _view(request, episode_id)
        view["already_filed"] = True
        return view
    camera_events = request.app.state.store.events(body.case_id)
    drafted = camera_count_events(
        ledger_rows(camera_events),
        open_discrepancies(camera_events),
        body.case_id,
    )
    ts = _next_ts(morning, episode_id)
    for offset, event in enumerate(drafted):
        morning.append(episode_id, event["event_type"], event["payload"], ts_ms=ts + offset)
    view = _view(request, episode_id)
    view["filed"] = True
    return view


@router.post("/morning/episodes/{episode_id}/count/manual")
def manual_out(episode_id: str, body: ManualIn, request: Request) -> dict:
    _require(request, episode_id)
    store = _store(request)
    store.append(
        episode_id,
        "count.item_out",
        {"track_id": body.track_id, "frame_id": None, "source": "manual"},
        ts_ms=_next_ts(store, episode_id),
    )
    return _view(request, episode_id)


@router.post("/morning/episodes/{episode_id}/count/frame")
def count_frame(episode_id: str, body: FrameIn, request: Request) -> dict:
    """One camera frame. The dwell counter lives on the episode sim bag."""
    _require(request, episode_id)
    store = _store(request)
    bag = store.sim_state(episode_id)
    state = bag.setdefault("count", fresh_state())
    drafted = observe(
        state,
        {"track_id": body.track_id, "zone": body.zone, "frame_id": body.frame_id, "t_ms": body.t_ms},
    )
    written = []
    for event in drafted:
        written.append(
            store.append(episode_id, event["event_type"], event["payload"], ts_ms=event["ts_ms"])
        )
    return {"emitted": written, "out": sorted(state["out"])}


@router.post("/morning/episodes/{episode_id}/events/{event_id}/correct")
def correct_event(episode_id: str, event_id: str, body: CorrectIn, request: Request) -> dict:
    _require(request, episode_id)
    store = _store(request)
    old = store.get_event(event_id)
    if old is None or old["episode_id"] != episode_id:
        raise HTTPException(status_code=404, detail="Event not found")
    store.append(
        episode_id,
        old["event_type"],
        body.payload,
        ts_ms=old["ts_ms"],
        tier=old["tier"],
        supersedes_id=event_id,
    )
    return _view(request, episode_id)


@router.post("/morning/episodes/{episode_id}/vitals/sim")
def vitals_sim(episode_id: str, body: SimIn, request: Request) -> dict:
    _require(request, episode_id)
    try:
        state = apply_sim(
            _store(request),
            episode_id,
            action=body.action,
            t_ms=body.t_ms,
            step_ms=body.step_ms,
            decision_tier=bool(request.app.state.decision_tier),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Use start, pause, seek, or tick.") from exc
    view = _view(request, episode_id)
    view["sim"] = state
    return view


@router.post("/morning/episodes/{episode_id}/brownbag/text")
def brownbag_text(episode_id: str, body: HearIn, request: Request) -> dict:
    """Ground a model's strip list. The photo itself is stored and not sent anywhere here."""
    _require(request, episode_id)
    strips = parse_strip_text(body.text)
    store = _store(request)
    ts = _next_ts(store, episode_id)
    for offset, strip in enumerate(strips):
        store.append(episode_id, "brownbag.med_found", strip, ts_ms=ts + offset)
    return _view(request, episode_id)


@router.post("/morning/episodes/{episode_id}/brownbag/photo")
async def brownbag_photo(
    episode_id: str,
    request: Request,
    file: UploadFile = File(...),
) -> dict:
    _require(request, episode_id)
    raw = await file.read()
    folder = request.app.state.settings.data_dir / "strips" / episode_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (file.filename or "strip.jpg")
    path.write_bytes(raw)
    if not request.app.state.settings.spark_configured:
        return {
            "status": "no_model",
            "saved": path.name,
            "detail": "No Muse Spark key. Type the strip names. The photo stays on this machine.",
        }
    return {
        "status": "saved",
        "saved": path.name,
        "detail": "Photo saved. A model call is not made until a strip prompt is posted to brownbag/text.",
    }
