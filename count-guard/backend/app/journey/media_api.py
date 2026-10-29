"""Voice and model routes: dictated orders and discharge become drafts a person signs (D10)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.journey import dictation, live, proof, spoken, states, tasks
from app.journey.api import MAX_PHOTO_BYTES, _act, _at, _require, _store, view
from app.morning.strips import parse_strip_text

media_router = APIRouter(prefix="/journey/episodes/{episode_id}")
models_router = APIRouter(prefix="/journey")

MAX_AUDIO_BYTES = 10 * 1024 * 1024
SPARK = "muse-spark-1.3"
PHOTO_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
NOTHING = "Nothing to draft was heard. Type the {what} instead."


@models_router.get("/models")
def models(request: Request) -> dict:
    settings = request.app.state.settings
    return {"live": settings.spark_configured, "voice": settings.voice_configured}


def _heard(settings, file: UploadFile | None, text: str | None) -> dict:
    """What was said, as {"text", "source"}: typed text, or a recording heard or prepared."""
    if (file is None) == (text is None):
        raise HTTPException(status_code=422, detail="Send either a recording or typed text, not both and not neither.")
    if text is not None:
        if not text.strip():
            raise HTTPException(status_code=422, detail="The typed text is empty.")
        return {"text": text.strip(), "source": "typed"}
    kind = (file.content_type or "").split(";")[0].strip().lower()
    if not (kind.startswith("audio/") or kind == "video/webm"):
        raise HTTPException(status_code=400, detail="The recording must be an audio file.")
    raw = file.file.read(MAX_AUDIO_BYTES + 1)
    if not raw or len(raw) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="The recording is empty or larger than 10 MB.")
    try:
        return live.transcribe(settings, raw, file.filename or "", kind)
    except live.NotHeard as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


def _structure(settings, prompt: str, transcript: str, from_reply, from_rules):
    """Model first, rules as the fallback. Returns (result, source). One place for the source wording."""
    reply = live.spark_text(settings, prompt + dictation.digits(transcript))
    got = from_reply(reply, transcript)
    if got is not None:
        return got, SPARK
    return from_rules(transcript), ("rules (model reply not usable)" if settings.spark_configured else "rules")


def _dictate(request, episode_id, allowed, refusal, file, text, prompt, from_reply, from_rules, what, empty):
    """Shared by both routes: state check, what was heard, then the draft content. Returns (result, heard, source)."""
    _require(request, episode_id)
    state = states.current_state(_store(request).events(episode_id))
    if state not in allowed:
        raise HTTPException(status_code=409, detail=refusal.format(state=state))
    settings = request.app.state.settings
    heard = _heard(settings, file, text)
    result, source = _structure(settings, prompt, heard["text"], from_reply, from_rules)
    if empty(result):
        raise HTTPException(status_code=422, detail=NOTHING.format(what=what))
    return result, {"transcript": heard["text"], "heard_by": heard["source"], "source": source}


@media_router.post("/dictate/orders")
def dictate_orders(
    episode_id: str,
    request: Request,
    by: str = Form(..., min_length=1, max_length=80),
    at_ms: int | None = Form(None, ge=0),
    text: str | None = Form(None, min_length=1, max_length=2000),
    file: UploadFile | None = File(None),
) -> dict:
    result, meta = _dictate(
        request, episode_id, tasks.ORDER_STATES,
        "Orders are dictated in clinic, admitting or ward. The patient is in {state}.",
        file, text, dictation.ORDER_PROMPT, dictation.items_from_reply, dictation.parse_order_text,
        "orders", lambda r: not r["items"] and not r["reason"],
    )
    return _act(request, episode_id, "order.drafted", {**meta, **result, "by": by}, at_ms)


@media_router.post("/dictate/discharge")
def dictate_discharge(
    episode_id: str,
    request: Request,
    by: str = Form(..., min_length=1, max_length=80),
    at_ms: int | None = Form(None, ge=0),
    text: str | None = Form(None, min_length=1, max_length=2000),
    file: UploadFile | None = File(None),
) -> dict:
    result, meta = _dictate(
        request, episode_id, ("ward",),
        "The discharge is dictated while the patient is on the ward. The patient is in {state}.",
        file, text, dictation.DISCHARGE_PROMPT, dictation.sections_from_reply, dictation.discharge_sections,
        "discharge summary", lambda r: not r,
    )
    return _act(request, episode_id, "discharge.drafted", {**meta, "sections": result, "by": by}, at_ms)


@media_router.post("/dictate/task")
def dictate_task(
    episode_id: str,
    request: Request,
    by: str = Form(..., min_length=1, max_length=80),
    at_ms: int | None = Form(None, ge=0),
    text: str | None = Form(None, min_length=1, max_length=2000),
    file: UploadFile | None = File(None),
) -> dict:
    """Which open tasks the nurse's sentence is about, and the values she stated. Writes nothing (D10)."""
    _require(request, episode_id)
    open_tasks = [t for t in tasks.task_list(_store(request).events(episode_id)) if t["status"] in spoken.OPEN]
    result, meta = _dictate(
        request, episode_id, ("ward",),
        "A finished task is spoken in the ward. The patient is in {state}.",
        file, text, spoken.task_prompt(open_tasks), lambda reply, said: spoken.completion_from_reply(reply, open_tasks, said),
        lambda said: {"task_ids": spoken.match_tasks(said, open_tasks), "values": spoken.parse_values(said)},
        "task", lambda r: False,
    )
    chosen = [t for t in open_tasks if t["id"] in result["task_ids"]]
    candidates = [{k: t[k] for k in ("id", "title", "kind", "mode", "status")} for t in chosen]
    return {**meta, "candidates": candidates, "values": result["values"]}


def _check_photo(settings, task: dict, raw: bytes, name: str, kind: str, stated: dict) -> dict:
    """The proof check for one photo. A reader that gave nothing, or a reply that does not parse, is `none`."""
    if task["kind"] == "dose":
        read = live.read_photo(settings, "strip", raw, name, kind)
        try:
            strips = parse_strip_text(read["text"] or "")
        except (ValueError, KeyError, TypeError, AttributeError):
            strips = []
        return {**proof.check_strip(strips, task), "source": read["source"]}
    if task["kind"] == "obs":
        read = live.read_photo(settings, "monitor", raw, name, kind)
        return {**proof.check_monitor(proof.parse_monitor_text(read["text"] or ""), stated), "source": read["source"]}
    return {"read": "", "match": "none", "why": proof.NO_READING, "source": "none"}


@media_router.post("/photos")
def add_photo(
    episode_id: str,
    request: Request,
    file: UploadFile = File(...),
    purpose: Literal["reference", "proof"] = Form(...),
    by: str = Form(..., min_length=1, max_length=80),
    at_ms: int | None = Form(None, ge=0),
    task_id: str | None = Form(None, min_length=1, max_length=64),
    sbp: int | None = Form(None, ge=30, le=300),
    dbp: int | None = Form(None, ge=10, le=200),
    hr: int | None = Form(None, ge=20, le=250),
) -> dict:
    _require(request, episode_id)
    if (purpose == "proof") != (task_id is not None):
        raise HTTPException(status_code=422, detail="A proof photo names a task; a reference photo names none.")
    kind = (file.content_type or "").split(";")[0].strip().lower()
    if kind not in PHOTO_TYPES:
        raise HTTPException(status_code=400, detail="The photo must be a JPEG, PNG or WebP image.")
    raw = file.file.read(MAX_PHOTO_BYTES + 1)
    if not raw or len(raw) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=400, detail="The photo is empty or larger than 8 MB.")
    store, settings = _store(request), request.app.state.settings
    task = None
    if task_id is not None:
        task = next((t for t in tasks.task_list(store.events(episode_id)) if t["id"] == task_id), None)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if task["status"] not in ("open", "running"):
            raise HTTPException(status_code=409, detail=f"This task is {task['status']}; a proof photo goes with an open task.")
    folder = settings.data_dir / "journey_media" / episode_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}{PHOTO_TYPES[kind]}"
    path.write_bytes(raw)
    ts = _at(store, episode_id, at_ms)
    added = {"purpose": purpose, "path": str(path.relative_to(settings.data_dir)), "by": by}
    if task_id is not None:
        added["task_id"] = task_id
    photo = store.append(episode_id, "photo.added", added, ts_ms=ts)
    if task is not None:
        stated = {k: v for k, v in (("sbp", sbp), ("dbp", dbp), ("hr", hr)) if v is not None}
        checked = _check_photo(settings, task, raw, file.filename or "", kind, stated)
        store.append(episode_id, "proof.checked", {"photo_id": photo["id"], "task_id": task_id, **checked}, ts_ms=ts)
    return view(request, episode_id)


@media_router.get("/photos/{photo_id}")
def get_photo(episode_id: str, photo_id: str, request: Request) -> FileResponse:
    _require(request, episode_id)
    event = _store(request).get_event(photo_id)
    if event is None or event["episode_id"] != episode_id or event["event_type"] != "photo.added":
        raise HTTPException(status_code=404, detail="Photo not found")
    data_dir = request.app.state.settings.data_dir.resolve()
    path = (data_dir / event["payload"]["path"]).resolve()
    if not path.is_relative_to(data_dir / "journey_media") or not path.is_file():
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(path)
