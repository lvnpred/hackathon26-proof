"""The theatre swab camera (spec §6.4, §6.5): a camera case linked to the stay, a clip run through rules R1–R6,
the advice they give, a person's acknowledgement, and the last frame of a missing swab as proof.

Moved from the camera counter (`api/routes.py` case create/zones/upload) and morning `count/from-case`,
`count/manual`, `count/frame`. Everything the camera writes carries CAMERA_BY. It never writes `count.closing`
or `count.pack_opened`, and ending surgery never reads `camera.ack` (U10): `count_gate` alone decides.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from PIL import Image
from pydantic import Field

from app.core.ledger import ledger_rows
from app.core.tracker import Tracker
from app.journey import advice, camera_extras, live, states, switches
from app.journey.api import At, _at, _require, _store, settle, view
from app.journey.stories import CAMERA_BY, by_ai
from app.media_pipeline import SamCallFailed, run_recorded_video
from app.morning.count_rules import fresh_state, observe
from app.scenarios import ZONES, get_scenario

camera_router = APIRouter(prefix="/journey/episodes/{episode_id}/camera")

ITEM_TYPES = ["gauze swab", "lap sponge"]
CONCEPTS = ["gauze swab", "lap sponge"]
NOT_THEATRE = "The swab camera runs while the patient is in theatre."
START_FIRST = "Start the swab camera first."
A_PERSON = "A person acknowledges camera advice."
PREPARED = switches.PREPARED_BY_CHECK["swabs"]


class CaseIn(At):
    by: str = Field(min_length=1, max_length=80)
    case_id: str | None = Field(default=None, min_length=1, max_length=64)  # link a case the camera already made


class AckIn(At):
    by: str = Field(min_length=1, max_length=80)
    reason: str = Field(default="", max_length=200)


class ManualIn(At):
    track_id: str = Field(min_length=1, max_length=80)
    by: str = Field(min_length=1, max_length=80)


# ---- moved bodies (the morning routes call these until Task 16 archives them) ----

def manual_out(store, episode_id: str, track_id: str, ts: int, by: str | None = None) -> dict:
    """A person says this swab is out (morning `count/manual`). Counted back by hand, never a closing."""
    payload = {"track_id": track_id, "frame_id": None, "source": "manual", **({"by": by} if by else {})}
    return store.append(episode_id, "count.item_out", payload, ts_ms=ts)


def observe_frame(store, episode_id: str, frame: dict) -> dict:
    """One camera frame through the bucket dwell counter (morning `count/frame`). The counter lives on the sim bag."""
    bag = store.sim_state(episode_id)
    state = bag.setdefault("count", fresh_state())
    written = [store.append(episode_id, e["event_type"], e["payload"], ts_ms=e["ts_ms"]) for e in observe(state, frame)]
    return {"emitted": written, "out": sorted(state["out"])}


def create_case(engine, label: str) -> str:
    """A camera case with the tray, field and bucket zones saved (`api/routes.py` create and zones)."""
    case = engine.create_case(label, ITEM_TYPES)
    engine.set_zones(case["id"], [{"name": name, "polygon": polygon} for name, polygon in ZONES.items()])
    return case["id"]


def ingest_prepared(engine, case_id: str) -> None:
    """The fixed prepared result for a swab check, fed through the same tracker and rules a live clip goes through."""
    found = live.prepared(PREPARED) or {}
    zones = engine.store.zones(case_id)
    tracker = Tracker(lost_after_frames=engine.settings.lost_after_frames, low_confidence=engine.settings.low_confidence)
    last = 0
    for frame in found.get("frames") or []:
        last = int(float(frame["t"]) * 1000)
        detections = [
            {"track_id": f"prepared-{o['id']}", "label": o["label"], "bbox": o["bbox"], "score": o["score"]}
            for o in frame.get("objects") or [] if o.get("kept", True)
        ]
        engine._ingest_detections(case_id, tracker, zones, detections, media_ts_ms=last, width=640, height=360,
                                  source="prepared", chunk_id="prepared", external_ids=True)
    engine.apply_rules(case_id, now_ms=last, finalize=True)
    engine._cache_tracks(case_id, tracker)


def run_clip(request: Request, case_id: str, raw: bytes, suffix: str) -> str:
    """Live SAM 3.1 when the swab switch is on; else, or when the call fails, the fixed prepared result (§6.7)."""
    engine, settings = request.app.state.engine, request.app.state.settings
    if switches.is_live(settings, "swabs"):
        dest = settings.data_dir / "uploads" / case_id / f"clip-{uuid.uuid4().hex}{suffix}"  # a server-made name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        try:
            run_recorded_video(engine, case_id, dest, concepts=CONCEPTS)
            return "sam-3.1"
        except (SamCallFailed, RuntimeError, OSError):
            dest.unlink(missing_ok=True)
    ingest_prepared(engine, case_id)
    return "prepared"


# ---- the care view of the camera ----

def camera_state(request: Request, episode_id: str) -> dict:
    events = _store(request).events(episode_id)
    case_id = advice.linked_case(events)
    ran = states.stay_latest(events, "camera.ran")
    store = request.app.state.store
    return {
        "case_id": case_id,
        "source": ran["payload"]["source"] if ran else None,
        "fixture": ran["payload"].get("fixture") if ran else None,
        "ledger": ledger_rows(store.events(case_id)) if case_id else [],
        "advice": advice.advice_view(episode_id, events),
        "live": switches.is_live(request.app.state.settings, "swabs"),
        **camera_extras.view(episode_id, events),
    }


def _with_camera(request: Request, episode_id: str) -> dict:
    return {**view(request, episode_id), "camera": camera_state(request, episode_id)}


def _theatre(request: Request, episode_id: str) -> list[dict]:
    _require(request, episode_id)
    events = _store(request).events(episode_id)
    if states.current_state(events) != "theatre":
        raise HTTPException(status_code=409, detail=NOT_THEATRE)
    return events


@camera_router.get("")
def get_camera(episode_id: str, request: Request) -> dict:
    _require(request, episode_id)
    return camera_state(request, episode_id)


@camera_router.post("/case")
def link_case(episode_id: str, body: CaseIn, request: Request) -> dict:
    """Create the camera case (or link one the camera made) to this theatre stay. A second click adds nothing."""
    events = _theatre(request, episode_id)
    store, engine = _store(request), request.app.state.engine
    current = advice.linked_case(events)
    if body.case_id and request.app.state.store.get_case(body.case_id) is None:
        raise HTTPException(status_code=404, detail="Camera case not found")
    if current is None or (body.case_id and body.case_id != current):
        case_id = body.case_id or create_case(engine, f"Theatre swab camera, {_require(request, episode_id)['label']}")
        ts = _at(store, episode_id, body.at_ms)
        store.append(episode_id, "camera.linked", {"case_id": case_id, "started_by": body.by, "by": CAMERA_BY}, ts_ms=ts)
        settle(request, episode_id, ts)
    return _with_camera(request, episode_id)


@camera_router.post("/clip")
def run_camera(
    episode_id: str,
    request: Request,
    file: UploadFile | None = File(None),
    scenario: str | None = Form(None, pattern=r"^[a-z0-9-]{1,20}$"),
    by: str = Form(..., min_length=1, max_length=80),
    at_ms: int | None = Form(None, ge=0),
) -> dict:
    """Run a clip (or a recorded scenario) through the camera case, then write what the rules found as advice."""
    from app.journey.video_api import _read_upload  # video_api imports the journey routes this module also uses

    events = _theatre(request, episode_id)
    case_id = advice.linked_case(events)
    if case_id is None:
        raise HTTPException(status_code=409, detail=START_FIRST)
    if (file is None) == (scenario is None):
        raise HTTPException(status_code=422, detail="Send one clip or one recorded scenario.")
    engine = request.app.state.engine
    extra: dict = {}
    if scenario is not None:
        try:
            engine.replay(case_id, get_scenario(scenario))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="That recorded clip is not known.") from exc
        source, extra = "prepared", {"scenario": scenario}  # scripted perception, never passed off as live
    else:
        raw, suffix = _read_upload(file)
        source = run_clip(request, case_id, raw, suffix)
        extra = {"fixture": PREPARED} if source == "prepared" else {}
    store = _store(request)
    ts = _at(store, episode_id, at_ms)
    rows = ledger_rows(request.app.state.store.events(case_id))
    store.append(episode_id, "camera.ran",
                 {"case_id": case_id, "source": source, **extra, "ledger": rows, "started_by": by, "by": CAMERA_BY}, ts_ms=ts)
    advice.write(store, episode_id, case_id, advice.from_case(engine, case_id), ts, source)
    settle(request, episode_id, ts)
    return _with_camera(request, episode_id)


@camera_router.get("/frame")
def missing_frame(episode_id: str, request: Request, item: str) -> Response:
    """The last frame the camera saw a missing item in, as a JPEG. Only this stay's advice can name a frame."""
    _require(request, episode_id)
    rows = [a for a in advice.advice_view(episode_id, _store(request).events(episode_id))
            if a["frame_id"] and item in (a["item"], a["item_type"])]
    rows.sort(key=lambda a: a["rule"] != "R3")  # a missing swab's last frame first
    frame = request.app.state.store.get_frame(rows[0]["frame_id"]) if rows else None
    if frame is None or not Path(frame["path"]).is_file():
        raise HTTPException(status_code=404, detail="No camera frame for that item.")
    out = io.BytesIO()
    Image.open(frame["path"]).convert("RGB").save(out, format="JPEG", quality=85)
    return Response(content=out.getvalue(), media_type="image/jpeg")


@camera_router.post("/advice/{advice_id}/ack")
def acknowledge(episode_id: str, advice_id: str, body: AckIn, request: Request) -> dict:
    """A person has seen the advice (with a reason if they disagree). Recorded only; ending surgery never reads it."""
    _require(request, episode_id)
    if by_ai({"by": body.by}):
        raise HTTPException(status_code=422, detail=A_PERSON)
    store = _store(request)
    event = store.get_event(advice_id)
    if event is None or event["episode_id"] != episode_id or event["event_type"] != "camera.advice":
        raise HTTPException(status_code=404, detail="Camera advice not found")
    done = any(e["event_type"] == "camera.ack" and e["payload"]["advice_id"] == advice_id for e in store.events(episode_id))
    if not done:
        ts = _at(store, episode_id, body.at_ms)
        store.append(episode_id, "camera.ack", {"advice_id": advice_id, "by": body.by, "reason": body.reason.strip()}, ts_ms=ts)
        settle(request, episode_id, ts)
    return _with_camera(request, episode_id)


@camera_router.post("/manual")
def manual(episode_id: str, body: ManualIn, request: Request) -> dict:
    """A swab counted back by hand. It is a note on the count, never the closing."""
    _theatre(request, episode_id)
    if by_ai({"by": body.by}):
        raise HTTPException(status_code=422, detail="A person counts a swab back by hand.")
    store = _store(request)
    ts = _at(store, episode_id, body.at_ms)
    manual_out(store, episode_id, body.track_id, ts, by=body.by)
    settle(request, episode_id, ts)
    return _with_camera(request, episode_id)
