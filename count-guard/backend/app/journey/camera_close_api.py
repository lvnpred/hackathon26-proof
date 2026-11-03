"""Count extras on the theatre count panel (spec §6.4, §6.5, U10, §9): replay of recorded detections (Prepared), the
bucket-dwell counter, resolve of camera advice with a reason, and closing the camera case with the drafted explanation
and the count-sheet PDF.

Moved from morning `count/replay`, `count_rules` and the camera counter's resolve, close and report routes
(`api/routes.py`). None of these routes writes `count.closing` or `count.pack_opened`: the old morning replay wrote a
closing with no `by`, and that write is not reused. Ending surgery reads none of their events; `count_gate` alone
decides, on the closing a person saved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import Field

from app.core.ledger import ledger_rows
from app.journey import advice, camera_explain, camera_extras
from app.journey.api import At, _at, _require, _store, settle
from app.journey.camera_api import START_FIRST, _theatre, _with_camera
from app.journey.stories import CAMERA_BY, by_ai

camera_close_router = APIRouter(prefix="/journey/episodes/{episode_id}/camera")

A_PERSON_RESOLVES = "A person resolves camera advice."
SAY_WHY = "Say why the advice is resolved."
A_PERSON_CLOSES = "A person closes the camera case."
NOT_CLOSED = "The count sheet is written when the camera case is closed."


class ByIn(At):
    by: str = Field(min_length=1, max_length=80)


class ResolveIn(At):
    by: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=200)


class DwellIn(At):
    track_id: str = Field(min_length=1, max_length=80)
    zone: Literal["tray", "field", "bucket"]
    frame_id: str | None = Field(default=None, max_length=120)
    t_ms: int = Field(ge=0)


def _person(by: str, detail: str) -> None:
    """The same check as /count: an AI or camera `by` (any case or spacing) is refused."""
    if by_ai({"by": by}):
        raise HTTPException(status_code=422, detail=detail)


@camera_close_router.post("/replay")
def replay(episode_id: str, body: ByIn, request: Request) -> dict:
    """The recorded detections through the dwell counter, labelled Prepared. Advice only; no count is written."""
    _theatre(request, episode_id)
    store = _store(request)
    summary = camera_extras.replay_summary()
    ts = _at(store, episode_id, body.at_ms)
    store.append(episode_id, "camera.replayed", {**summary, "started_by": body.by, "by": CAMERA_BY}, ts_ms=ts)
    case_id = advice.linked_case(store.events(episode_id))
    advice.write(store, episode_id, case_id, camera_extras.replay_advice(summary), ts, "prepared")
    settle(request, episode_id, ts)
    return _with_camera(request, episode_id)


@camera_close_router.post("/dwell")
def dwell(episode_id: str, body: DwellIn, request: Request) -> dict:
    """One camera frame through the bucket-dwell counter: a swab counts back after it sits in the bucket."""
    events = _theatre(request, episode_id)
    store = _store(request)
    frame = {"track_id": body.track_id, "zone": body.zone, "frame_id": body.frame_id, "t_ms": body.t_ms}
    ts = _at(store, episode_id, body.at_ms)
    written = camera_extras.dwell_frame(store, episode_id, events, frame, ts)
    if written:
        settle(request, episode_id, ts)
    back = camera_extras.returned(store.events(episode_id))
    return {"emitted": written, "returned": len(back), "out": sorted(back)}


@camera_close_router.post("/advice/{advice_id}/resolve")
def resolve(episode_id: str, advice_id: str, body: ResolveIn, request: Request) -> dict:
    """A person resolves camera advice with a reason. It resolves the advice (and the camera finding behind it), never
    the count."""
    _require(request, episode_id)
    _person(body.by, A_PERSON_RESOLVES)
    reason = " ".join(body.reason.split())
    if not reason:
        raise HTTPException(status_code=422, detail=SAY_WHY)
    store = _store(request)
    event = store.get_event(advice_id)
    if event is None or event["episode_id"] != episode_id or event["event_type"] != "camera.advice":
        raise HTTPException(status_code=404, detail="Camera advice not found")
    done = any(e["event_type"] == "camera.resolved" and e["payload"]["advice_id"] == advice_id for e in store.events(episode_id))
    if not done:
        p = event["payload"]
        case_id, _, finding = str(p.get("key") or "").partition(":")
        if case_id and case_id == p.get("case_id") and finding:
            try:
                request.app.state.engine.resolve(finding, reason, body.by)
            except KeyError:
                pass  # R6 and replay advice have no camera finding of their own
        ts = _at(store, episode_id, body.at_ms)
        store.append(episode_id, "camera.resolved", {"advice_id": advice_id, "by": body.by, "reason": reason}, ts_ms=ts)
        settle(request, episode_id, ts)
    return _with_camera(request, episode_id)


@camera_close_router.post("/close")
def close(episode_id: str, body: ByIn, request: Request) -> dict:
    """Close the camera case: the drafted explanation and the count sheet. Open advice stays open; it never blocks."""
    events = _theatre(request, episode_id)
    _person(body.by, A_PERSON_CLOSES)
    case_id = advice.linked_case(events)
    if case_id is None:
        raise HTTPException(status_code=409, detail=START_FIRST)
    camera, settings = request.app.state.store, request.app.state.settings
    explained = camera_explain.explain(camera, settings, case_id)
    camera_explain.write_sheet(camera, settings, case_id, explained, ledger_rows(camera.events(case_id)))
    store = _store(request)
    ts = _at(store, episode_id, body.at_ms)
    payload = {"case_id": case_id, "text": explained["text"], "narrative": explained["narrative"],
               "source": explained["source"], "model": explained["model"], "closed_by": body.by, "by": CAMERA_BY,
               "evidence": camera_explain.evidence(explained, case_id)}
    store.append(episode_id, "camera.closed", payload, ts_ms=ts)
    settle(request, episode_id, ts)
    return _with_camera(request, episode_id)


@camera_close_router.get("/count-sheet.pdf")
def count_sheet(episode_id: str, request: Request):
    """The count sheet of the camera case this patient's stay last closed."""
    _require(request, episode_id)
    closed = camera_extras.latest_closed(_store(request).events(episode_id), stay_only=False)
    report = request.app.state.store.get_report(closed["payload"]["case_id"]) if closed else None
    if report is None:
        raise HTTPException(status_code=409, detail=NOT_CLOSED)
    path = Path(report["path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="The count sheet file is missing.")
    return FileResponse(path, media_type="application/pdf", filename="count-sheet.pdf")
