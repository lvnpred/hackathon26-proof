"""The camera case behind a theatre stay, as frames, tracks and events (spec 9, Inspector Evidence).

Moved from the camera counter's `/frames`, `/tracks` and `/cases/{id}/events` routes. Each route answers only for the
case linked to THIS episode (`camera.linked`), so one patient never reads another patient's frames.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.engine import track_path
from app.journey import advice
from app.journey.api import _require, _store

camera_evidence_router = APIRouter(prefix="/journey/episodes/{episode_id}/camera/evidence")

NO_FRAME = "No camera frame for that id."
NO_TRACK = "No camera track for that id."


def _linked(request: Request, episode_id: str) -> str | None:
    _require(request, episode_id)
    return advice.linked_case(_store(request).events(episode_id))


@camera_evidence_router.get("")
def list_evidence(episode_id: str, request: Request) -> dict:
    case_id = _linked(request, episode_id)
    if case_id is None:
        return {"case_id": None, "frames": [], "tracks": [], "events": []}
    store = request.app.state.store
    events = store.events(case_id)
    base = f"/journey/episodes/{episode_id}/camera/evidence"
    ids = list(dict.fromkeys(e["payload"]["track_id"] for e in events if (e.get("payload") or {}).get("track_id")))
    return {
        "case_id": case_id,
        "frames": [{"id": f["id"], "media_ts_ms": f["media_ts_ms"], "url": f"{base}/frames/{f['id']}"} for f in store.frames(case_id)],
        "tracks": [{"track_id": t, **(store.track(case_id, t) or {})} for t in ids],
        "events": [{"id": e["id"], "event_type": e["event_type"], "media_ts_ms": e["media_ts_ms"], "payload": e["payload"]} for e in events],
    }


@camera_evidence_router.get("/frames/{frame_id}")
def evidence_frame(episode_id: str, frame_id: str, request: Request) -> FileResponse:
    case_id = _linked(request, episode_id)
    frame = request.app.state.store.get_frame(frame_id) if case_id else None
    if frame is None or frame["case_id"] != case_id or not Path(frame["path"]).is_file():
        raise HTTPException(status_code=404, detail=NO_FRAME)
    return FileResponse(frame["path"], media_type="image/png")


@camera_evidence_router.get("/tracks/{track_id}")
def evidence_track(episode_id: str, track_id: str, request: Request) -> dict:
    case_id = _linked(request, episode_id)
    store = request.app.state.store
    events = store.events(case_id) if case_id else []
    path = track_path(events, track_id)
    if not path and (case_id is None or store.track(case_id, track_id) is None):
        raise HTTPException(status_code=404, detail=NO_TRACK)
    return {"case_id": case_id, "track_id": track_id, "cached": store.track(case_id, track_id), "path": path}
