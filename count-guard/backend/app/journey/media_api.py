"""Voice and model routes: dictated orders and discharge become drafts a person signs (D10)."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.journey import dictation, live, states, tasks
from app.journey.api import _act, _require, _store

media_router = APIRouter(prefix="/journey/episodes/{episode_id}")
models_router = APIRouter(prefix="/journey")

MAX_AUDIO_BYTES = 10 * 1024 * 1024
SPARK = "muse-spark-1.3"
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
