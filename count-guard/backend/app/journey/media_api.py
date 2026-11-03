"""Voice and model routes: dictated orders and discharge become drafts a person signs (D10)."""

from __future__ import annotations

import time
import uuid
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.journey import audio_api, dictation, evidence, expected, home_medicines, live, proof, spoken, states, switches, tasks, verdict
from app.journey.evidence_payload import evidence_of, fallback, heard_inputs
from app.journey.api import MAX_PHOTO_BYTES, _act, _at, _require, _store, settle, view
from app.journey.regions import strips_from
from app.journey.rx import key_of

media_router = APIRouter(prefix="/journey/episodes/{episode_id}")
models_router = APIRouter(prefix="/journey")

MAX_AUDIO_BYTES = 10 * 1024 * 1024
SPARK = "muse-spark-1.3"
PHOTO_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAGIC = {
    "image/jpeg": lambda b: b.startswith(b"\xff\xd8\xff"),
    "image/png": lambda b: b.startswith(b"\x89PNG"),
    "image/webp": lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP",
}
HEARERS = live.HEARERS
NOTHING = "Nothing to draft was heard. Type the {what} instead."
AMENDED = ("from_timeline", "timeline", "summary", "lines", "wording", "summary_source", "model_note", "pdf_url", "ics_url")


@models_router.get("/models")
def models(request: Request) -> dict:
    settings = request.app.state.settings
    on = switches.report(settings)
    return {"live": any(on.values()), "voice": on["voice"], "switches": on}


def _heard(settings, file: UploadFile | None, text: str | None, heard_by: str = "") -> dict:
    """What was said, as {"text", "source", "calls"}: typed text, or a recording heard or prepared.

    A recording that was heard also carries its bytes under "recording"; `keep_recording` keeps it once the route
    has passed its refusals, and drops the bytes (§4.2).

    Text the page took from an earlier hearing keeps that hearer, if it is one the server names. Else it is typed.
    Such text records the voice call with no time: the hearing was in an earlier request (R4)."""
    if (file is None) == (text is None):
        raise HTTPException(status_code=422, detail="Send either a recording or typed text, not both and not neither.")
    if text is not None:
        if not text.strip():
            raise HTTPException(status_code=422, detail="The typed text is empty.")
        if heard_by in HEARERS:
            return {"text": text.strip(), "source": heard_by, "calls": [live.call_of("voice", settings, heard_by, None)]}
        return {"text": text.strip(), "source": "typed", "calls": []}
    kind = (file.content_type or "").split(";")[0].strip().lower()
    if not (kind.startswith("audio/") or kind == "video/webm"):
        raise HTTPException(status_code=400, detail="The recording must be an audio file.")
    raw = file.file.read(MAX_AUDIO_BYTES + 1)
    if not raw or len(raw) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="The recording is empty or larger than 10 MB.")
    try:
        heard = live.transcribe(settings, raw, file.filename or "", kind)
    except live.NotHeard as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    if heard["source"] == switches.UNAVAILABLE:
        raise HTTPException(status_code=502, detail=heard["why"])  # §6.7: an error to retry, nothing prepared
    return {**heard, "recording": (raw, kind)}


def keep_recording(settings, episode_id: str, heard: dict) -> dict:
    """The heard line with `audio_id`: the recording kept for playback (None when typed), its bytes dropped."""
    recording = heard.get("recording")
    kept = {k: v for k, v in heard.items() if k != "recording"}
    audio_id = audio_api.save(settings, episode_id, *recording, kept) if recording else None
    return {**kept, "audio_id": audio_id}


def _structure(settings, prompt: str, transcript: str, from_reply, from_rules):
    """Model first, rules as the fallback. Returns (result, source, calls). One place for the source wording."""
    return _structure_reply(settings, prompt, transcript, from_reply, from_rules)[:3]


def _structure_reply(settings, prompt: str, transcript: str, from_reply, from_rules):
    """`_structure` and the model's raw reply (None when no model was asked): (result, source, calls, reply).

    `rules` (no key) is no model call; a reply that could not be used is a failed Spark call (R5)."""
    start = time.monotonic()
    reply = live.spark_text(settings, prompt + dictation.digits(transcript))
    ms = round((time.monotonic() - start) * 1000)
    got = from_reply(reply, transcript)
    if got is not None:
        return got, SPARK, [live.call_of("spark", settings, SPARK, ms)], reply
    if switches.is_live(settings, "spark"):
        source = "rules (model reply not usable)"
        return from_rules(transcript), source, [live.call_of("spark", settings, source, ms)], reply
    return from_rules(transcript), "rules", [], None


def _dictate(request, episode_id, allowed, refusal, file, text, prompt, from_reply, from_rules, what, empty, heard_by=""):
    """Shared by the dictate routes: state check, what was heard, then the draft content. Returns (result, meta).

    meta carries `evidence` (§4.2): the recording and transcript, Spark's raw reply, and what was drafted."""
    _require(request, episode_id)
    state = states.current_state(_store(request).events(episode_id))
    if state not in allowed:
        raise HTTPException(status_code=409, detail=refusal.format(state=state))
    settings = request.app.state.settings
    heard = _heard(settings, file, text, heard_by)
    result, source, structure_calls, reply = _structure_reply(settings, prompt, heard["text"], from_reply, from_rules)
    if empty(result):
        raise HTTPException(status_code=422, detail=NOTHING.format(what=what))
    heard = keep_recording(settings, episode_id, heard)  # kept only once the draft is not refused
    calls = heard["calls"] + structure_calls
    used = {**(result if isinstance(result, dict) else {"sections": result}), "fallback": fallback(source)}
    if not structure_calls and heard["calls"]:
        reply = heard["text"]  # no Spark call: the last model reply is what Muse Voice heard
    found = evidence_of(f"dictate.{what.split()[0]}", inputs=heard_inputs(heard), reply=reply, used=used, calls=calls)
    return result, {"transcript": heard["text"], "heard_by": heard["source"], "source": source, "calls": calls, "evidence": found}


@media_router.post("/dictate/orders")
def dictate_orders(
    episode_id: str,
    request: Request,
    by: str = Form(..., min_length=1, max_length=80),
    at_ms: int | None = Form(None, ge=0),
    text: str | None = Form(None, min_length=1, max_length=2000),
    heard_by: str = Form("", max_length=40),
    file: UploadFile | None = File(None),
) -> dict:
    result, meta = _dictate(
        request, episode_id, tasks.ORDER_STATES,
        "Orders are dictated in clinic, admitting or ward. The patient is in {state}.",
        file, text, dictation.ORDER_PROMPT, dictation.items_from_reply, dictation.parse_order_text,
        "orders", lambda r: not r["items"] and not r["reason"], heard_by,
    )
    spans = dictation.order_spans(meta["transcript"], result["items"])
    return _act(request, episode_id, "order.drafted", {**meta, **result, "spans": spans, "by": by}, at_ms)


@media_router.post("/dictate/discharge")
def dictate_discharge(
    episode_id: str,
    request: Request,
    by: str = Form(..., min_length=1, max_length=80),
    at_ms: int | None = Form(None, ge=0),
    text: str | None = Form(None, min_length=1, max_length=2000),
    heard_by: str = Form("", max_length=40),
    file: UploadFile | None = File(None),
) -> dict:
    result, meta = _dictate(
        request, episode_id, ("ward",),
        "The discharge is dictated while the patient is on the ward. The patient is in {state}.",
        file, text, dictation.DISCHARGE_PROMPT, dictation.sections_from_reply, dictation.discharge_sections,
        "discharge summary", lambda r: not r, heard_by,
    )
    # Dictation amends an open draft written from the timeline: the new draft keeps that draft's record and summary.
    open_draft = dictation.open_drafts(_store(request).events(episode_id))["discharge"]
    kept = {k: open_draft[k] for k in AMENDED if k in open_draft} if open_draft and open_draft.get("from_timeline") else {}
    amends = {"amends": open_draft["id"]} if kept else {}
    return _act(request, episode_id, "discharge.drafted", {**kept, **meta, "sections": result, "by": by, **amends}, at_ms)


@media_router.post("/dictate/task")
def dictate_task(
    episode_id: str,
    request: Request,
    by: str = Form(..., min_length=1, max_length=80),
    at_ms: int | None = Form(None, ge=0),
    text: str | None = Form(None, min_length=1, max_length=2000),
    heard_by: str = Form("", max_length=40),
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
        "task", lambda r: False, heard_by,
    )
    chosen = [t for t in open_tasks if t["id"] in result["task_ids"]]
    candidates = [{k: t[k] for k in ("id", "title", "kind", "mode", "status")} for t in chosen]
    return {**meta, "candidates": candidates, "values": result["values"]}


def keep_photo_evidence(settings, episode_id: str, kind: str, photo_id: str, read: dict, regions: list[dict]) -> dict:
    """Save a photo read's regions, calls and raw output as a sidecar. {} when nothing was found (no regions)."""
    if not regions:
        return {}
    saved = evidence.save(settings, episode_id, {
        "kind": kind, "media": "photos", "images": [{"photo_id": photo_id, "t": None, "index": 0}],
        "frames": None, "regions": regions, "expected": None, "min_score": settings.low_confidence, "fps": None,
        "calls": read["calls"], "raw": read["raw"], "handmade": read["handmade"],
    })
    return {"evidence_id": saved, "regions": regions, "handmade": bool(read["handmade"])}


def _check_photo(settings, episode_id: str, photo_id: str, task: dict, raw: bytes, name: str, kind: str, stated: dict) -> dict:
    """The proof check for one photo. A reader that gave nothing, or a reply that does not parse, is `none`."""
    if task["kind"] == "dose":
        read = live.read_photo(settings, "strip", raw, name, kind)
        strips = strips_from(read["text"] or "")
        wanted = key_of(task.get("name") or task["title"])
        regions = [
            {**r, "match": None if r["row"] is None or r["row"] >= len(strips) else "ok" if key_of(strips[r["row"]]["name_as_read"]) == wanted else "mismatch"}
            for r in read["regions"]
        ]
        return {**proof.check_strip(strips, task), "source": read["source"], "calls": read["calls"],
                **keep_photo_evidence(settings, episode_id, "strip", photo_id, read, regions)}
    if task["kind"] == "obs":
        read = live.read_photo(settings, "monitor", raw, name, kind)
        values_read = proof.parse_monitor_text(read["text"] or "")
        # values_read is kept so that Confirm can compare the photo with the values the nurse confirms.
        return {**proof.check_monitor(values_read, stated), "source": read["source"], "values_read": values_read, "calls": read["calls"],
                **keep_photo_evidence(settings, episode_id, "monitor", photo_id, read, read["regions"])}
    return {"read": "", "match": "none", "why": proof.NO_READING, "source": "none", "calls": []}


def read_upload_photo(file: UploadFile) -> tuple[bytes, str]:
    """The bytes and image type of an uploaded photo, or a 400 for a wrong type, size or magic bytes."""
    kind = (file.content_type or "").split(";")[0].strip().lower()
    if kind not in PHOTO_TYPES:
        raise HTTPException(status_code=400, detail="The photo must be a JPEG, PNG or WebP image.")
    raw = file.file.read(MAX_PHOTO_BYTES + 1)
    if not raw or len(raw) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=400, detail="The photo is empty or larger than 8 MB.")
    if not MAGIC[kind](raw):
        raise HTTPException(status_code=400, detail="The file is not a real JPEG, PNG or WebP image.")
    return raw, kind


def write_photo(settings, store, episode_id: str, raw: bytes, kind: str, added: dict, ts: int) -> dict:
    """Save the photo under journey_media/<episode>/ with a server name and append `photo.added`."""
    folder = settings.data_dir / "journey_media" / episode_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}{PHOTO_TYPES[kind]}"
    path.write_bytes(raw)
    payload = {**added, "path": str(path.relative_to(settings.data_dir))}
    return store.append(episode_id, "photo.added", payload, ts_ms=ts)


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
    raw, kind = read_upload_photo(file)
    store, settings = _store(request), request.app.state.settings
    task = None
    if task_id is not None:
        task = next((t for t in tasks.task_list(store.events(episode_id)) if t["id"] == task_id), None)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if task["status"] not in ("open", "running"):
            raise HTTPException(status_code=409, detail=f"This task is {task['status']}; a proof photo goes with an open task.")
    added = {"purpose": purpose, "by": by}
    if task_id is not None:
        added["task_id"] = task_id
    ts = _at(store, episode_id, at_ms)
    photo = write_photo(settings, store, episode_id, raw, kind, added, ts)
    if task is not None:
        stated = {k: v for k, v in (("sbp", sbp), ("dbp", dbp), ("hr", hr)) if v is not None}
        checked = _check_photo(settings, episode_id, photo["id"], task, raw, file.filename or "", kind, stated)
        store.append(episode_id, "proof.checked", {"photo_id": photo["id"], "task_id": task_id, **checked}, ts_ms=ts)
        item = f"task:{task_id}"  # U9: the verdict keeps only this task open, never a move
        judged = verdict.check(settings, item=item, raw=raw, content_type=kind, expect=expected.expect_for(item, task["kind"]),
                               photo_id=photo["id"])
        store.append(episode_id, "check.photo", {"item": item, "photo_id": photo["id"], "by": by, **judged}, ts_ms=ts)
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
    return FileResponse(path, headers={"X-Content-Type-Options": "nosniff"})


NO_STRIPS = "No strips were read from the photo. Type them instead."


@media_router.post("/strips/photo")
def strips_photo(
    episode_id: str,
    request: Request,
    file: UploadFile = File(...),
    by: str = Form("patient", min_length=1, max_length=80),
    at_ms: int | None = Form(None, ge=0),
) -> dict:
    """A photo of strips is read like the medicines photo: boxes, values, a kept sidecar. Offline it uses the prepared fixture (R11)."""
    _require(request, episode_id)
    raw, kind = read_upload_photo(file)
    store, settings = _store(request), request.app.state.settings
    read = home_medicines.read(settings, raw, file.filename or "", kind)  # prepared by the photo's bytes; live failure is a 502
    strips = strips_from(read["text"] or "")
    if not strips:
        raise HTTPException(status_code=422, detail=NO_STRIPS)
    ts = _at(store, episode_id, at_ms)
    photo = write_photo(settings, store, episode_id, raw, kind, {"purpose": "strips", "by": by}, ts)
    kept = keep_photo_evidence(settings, episode_id, "strip", photo["id"], read, read["regions"])
    for offset, strip in enumerate(strips):
        row = {**strip, "by": by, "source": read["source"], "photo_id": photo["id"], **({"evidence_id": kept["evidence_id"]} if kept else {})}
        if offset == 0:
            row["calls"] = read["calls"]  # one row carries the calls, so the summary counts each call once (R12)
        store.append(episode_id, "brownbag.med_found", row, ts_ms=ts + 1 + offset)
    settle(request, episode_id, ts + 1 + len(strips))
    return view(request, episode_id)
