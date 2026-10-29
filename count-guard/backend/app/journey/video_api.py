"""The video route: a tray check, with the clip read once and only its frames kept (D11)."""

from __future__ import annotations

import shutil
import uuid
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.journey import live, states, tasks
from app.journey.live import segment_clip
from app.journey.api import _at, _require, _store, raise_nudges, view
from app.journey.procedures import setup_for
from app.journey.video import NO_FRAMES, compare, expected_for_setup, expected_for_tray, frame_times, unchecked_for_tray
from app.media_pipeline import cut_frames

video_router = APIRouter(prefix="/journey/episodes/{episode_id}")

SETUP_LIVE = True  # D3 cut switch: False makes the set-up check use the prepared result only
MAX_VIDEO_BYTES = 50 * 1024 * 1024
VIDEO_TYPES = {"video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm"}
NAMES_TASK = "A set-up check names its task; a tray check names none."
NOT_THEATRE = "The tray is checked in theatre, after the tray plan is confirmed."
BEGUN = "Surgery has begun; the tray is checked before it begins."


def _is_video(kind: str, raw: bytes) -> bool:
    if kind == "video/webm":
        return raw[:4] == b"\x1a\x45\xdf\xa3"
    return raw[4:8] == b"ftyp"


def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    kind = (file.content_type or "").split(";")[0].strip().lower()
    if kind not in VIDEO_TYPES:
        raise HTTPException(status_code=400, detail="The clip must be an MP4, MOV or WebM video.")
    raw = file.file.read(MAX_VIDEO_BYTES + 1)
    if not raw or len(raw) > MAX_VIDEO_BYTES:
        raise HTTPException(status_code=400, detail="The clip is empty or larger than 50 MB.")
    if not _is_video(kind, raw):
        raise HTTPException(status_code=400, detail="The file is not a real MP4, MOV or WebM video.")
    return raw, VIDEO_TYPES[kind]


def _tray_refusal(events: list[dict]) -> str | None:
    if states.current_state(events) != "theatre":
        return NOT_THEATRE
    last_move = max(i for i, e in enumerate(events) if e["event_type"] == "patient.state")
    if not any(e["event_type"] == "tray.planned" for e in events[last_move:]):
        return NOT_THEATRE
    return BEGUN if states.surgery_status(events) != "none" else None


def _setup_refusal(events: list[dict], task_id: str) -> tuple[str | None, int, str]:
    """(set-up key, status, detail) for a refused set-up check; the key is set when it is allowed."""
    task = next((t for t in tasks.task_list(events) if t["id"] == task_id), None)
    if task is None:
        return None, 404, "Task not found"
    if states.current_state(events) != "ward":
        return None, 409, "A set-up check is made on the ward."
    if task["proof"] != "video":
        return None, 409, "This task has no video check."
    if task["status"] not in ("open", "running"):
        return None, 409, f"This task is {task['status']}; a video check goes with an open task."
    key = setup_for(task)
    if key is None:
        return None, 409, "There is no set-up list for this task."
    return key, 200, ""


def _read_clip(request: Request, episode_id: str, raw: bytes, suffix: str, filename: str, rows: list[dict], live_ok: bool):
    """Check the clip against the rows and keep its frames: (found, result, kept paths)."""
    settings = request.app.state.settings
    folder = settings.data_dir / "journey_media" / episode_id
    work = folder / f"tmp-{uuid.uuid4().hex}"
    work.mkdir(parents=True)
    try:
        clip = work / f"clip{suffix}"  # a server-made name; the client's name is never a path
        clip.write_bytes(raw)
        try:
            found = segment_clip(settings, clip, filename, [r["concept"] for r in rows], live_ok=live_ok)
        except live.NotHeard as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
        result = compare(rows, found["detections"], found["source"])
        try:
            cut = cut_frames(clip, frame_times(result["rows"]), work)
        except (RuntimeError, OSError):
            cut = []
            if frame_times(result["rows"]):
                result["why"] += NO_FRAMES
        kept = []
        for path in cut:
            target = folder / path.name
            shutil.move(path, target)
            kept.append(target)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return found, result, kept


@video_router.post("/video")
def add_video(
    episode_id: str,
    request: Request,
    file: UploadFile = File(...),
    check: Literal["tray", "setup"] = Form(...),
    by: str = Form(..., min_length=1, max_length=80),
    at_ms: int | None = Form(None, ge=0),
    task_id: str | None = Form(None, min_length=1, max_length=64),
) -> dict:
    _require(request, episode_id)
    if (check == "setup") != (task_id is not None):
        raise HTTPException(status_code=422, detail=NAMES_TASK)
    raw, suffix = _read_upload(file)
    store, settings = _store(request), request.app.state.settings
    events = store.events(episode_id)
    if check == "setup":
        key, status, detail = _setup_refusal(events, task_id)
        if key is None:
            raise HTTPException(status_code=status, detail=detail)
        rows, live_ok = expected_for_setup(key), SETUP_LIVE
        extra, planned = {"setup": key, "task_id": task_id}, None
    else:
        refusal = _tray_refusal(events)
        if refusal:
            raise HTTPException(status_code=409, detail=refusal)
        planned = next(e for e in reversed(events) if e["event_type"] == "tray.planned")["payload"]
        rows, live_ok = expected_for_tray(planned), True
        extra = {"template": planned["template"]}
    filename = file.filename or ""
    found, result, kept = _read_clip(request, episode_id, raw, suffix, filename, rows, live_ok)
    ts = _at(store, episode_id, at_ms)
    frame = {"purpose": "frame", "video": check, "by": by, **({"task_id": task_id} if task_id else {})}
    frame_ids = [
        store.append(episode_id, "photo.added", {**frame, "path": str(p.relative_to(settings.data_dir))}, ts_ms=ts)["id"]
        for p in kept
    ]
    payload = {
        **extra,
        **{k: result[k] for k in ("rows", "missing")},
        **({"unchecked": unchecked_for_tray(planned)} if planned else {}),
        **{k: result[k] for k in ("match", "why")},
        "source": found["source"],
        "clip": filename.lower() if live.safe_stem(filename) else "",
        "frame_ids": frame_ids,
        "by": by,
    }
    store.append(episode_id, "tray.checked" if planned else "setup.checked", payload, ts_ms=ts)
    raise_nudges(store, episode_id, ts)
    return view(request, episode_id)
