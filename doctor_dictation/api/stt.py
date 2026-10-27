"""Speech-to-text endpoint. Providers come from the factory at request time."""
import asyncio
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import PurePath
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse

from doctor_dictation import db as dbmod
from doctor_dictation.api import patientctx
from doctor_dictation.api.forms import FormLimitRoute
from doctor_dictation.api.formulary import use_clinic_layer
from doctor_dictation.audio.trim import trim_silence
from doctor_dictation.config import get_settings
from doctor_dictation.core import spoken
from doctor_dictation.core.hints import build_hints
from doctor_dictation.core.sayname import clean_said_name
from doctor_dictation.core.spoken import HintTerm
from doctor_dictation.db import spoken as spoken_db
from doctor_dictation.providers.stt.base import SttChainError
from doctor_dictation.providers.stt.factory import failure_response, make_stt, success_body
from doctor_dictation.scope import NoScope, current_scope

router = APIRouter(route_class=FormLimitRoute)


def _lift(conn, doctor_id, terms: list[HintTerm], term_ids, tier: int, what: str) -> list[HintTerm]:
    """``terms`` with those whose id ``term_ids(conn, doctor_id)`` returns lifted to at least ``tier``. A failed lookup
    is logged (the exception type only) and leaves ``terms`` as they were: one lift going wrong never drops the
    doctor's other hints."""
    try:
        lifted = term_ids(conn, doctor_id)
        return [replace(t, tier=max(t.tier, tier)) if t.term_id in lifted else t for t in terms]
    except NoScope:
        raise
    except Exception as exc:  # noqa: BLE001 - hints are optional
        print(f"hints: {what} unavailable: {type(exc).__name__}", flush=True)
        return terms


def _linked_tier(conn, doctor_id, terms: list[HintTerm], context) -> list[HintTerm]:
    """``terms`` with the doctor's terms linked to the correction's diagnosis lines lifted to tier 2 (H3)."""
    keys = spoken.diagnosis_keys((context or {}).get("diagnosis"))
    if not keys or not terms:
        return terms
    return _lift(conn, doctor_id, terms, lambda c, d: spoken_db.linked_term_ids(c, d, keys), 2, "diagnosis links")


def _doctor_terms(context=None) -> list[HintTerm]:
    """The signed-in doctor's spoken terms (every term in single-database mode, where no one signs in, doctor 0);
    any database problem means no personalisation. A term with an active corrected mishearing (H2) is lifted to
    tier 1, then a term linked to the correction's diagnosis (H3) to tier 2; a failed lift keeps the terms as they
    were. ``context`` is the parsed correction context. A term the patient it names got in their last 3 visits
    with this doctor is lifted to tier 3 (H4), only when that patient is exactly one person."""
    sc = current_scope()
    try:
        with closing(dbmod.get_conn()) as conn:
            doctor_id = sc.user_id if sc is not None and sc.user_id else 0
            terms = spoken_db.doctor_hint_terms(conn, doctor_id, datetime.now(timezone.utc).date())
            terms = _lift(conn, doctor_id, terms, spoken_db.active_mishearing_term_ids, 1, "mishearing lift")
            terms = _linked_tier(conn, doctor_id, terms, context)
            keys = patientctx.context_keys(conn, patientctx.doctor_id(), context)      # SH-H4: this patient's last 3 visits
            terms = [replace(t, tier=max(t.tier, 3)) if t.key in keys else t for t in terms]
            return terms
    except NoScope:
        raise                      # a missing scope is an auth bug, not "no hints"
    except Exception as exc:  # noqa: BLE001 - hints are optional
        print(f"hints: spoken terms unavailable: {exc}", flush=True)
        return []


async def _prepare_audio(raw: bytes, filename: str, settings, context=None) -> tuple[bytes, str, tuple[str, ...]]:
    """Apply the ACC2 flags. Both off returns (raw, filename, ())."""
    hints: tuple[str, ...] = ()
    if settings.stt_trim_silence:
        trimmed = await asyncio.to_thread(trim_silence, raw, filename)
        if trimmed is not raw:                         # new bytes are Ogg/Opus
            raw, filename = trimmed, PurePath(filename).stem + ".ogg"
    if settings.stt_use_hints:
        terms = await asyncio.to_thread(_doctor_terms, context)
        hints = tuple(build_hints(terms, settings.stt_hint_limit))
    return raw, filename, hints


@router.post("/api/transcribe", dependencies=[Depends(use_clinic_layer)])
async def transcribe(audio: UploadFile = File(...), context: Any = Form(None), mode: str = Form("")):
    settings = get_settings()
    max_bytes = settings.max_audio_bytes
    raw = await audio.read(max_bytes + 1)
    if len(raw) > max_bytes:
        return JSONResponse(status_code=413, content={
            "error": f"Audio is larger than the {max_bytes // (1024 * 1024)} MB "
                     "limit. Record a shorter dictation."})
    if not raw:
        return JSONResponse(status_code=400, content={"error": "Empty audio upload"})
    try:
        stt = make_stt(settings)
    except ValueError as e:
        return JSONResponse(status_code=500, content={
            "error": f"STT misconfigured: {e}", "fallback": "browser"})
    ctx, problem = spoken.parse_context(context)           # never sent to the speech engine
    if problem:
        print(f"transcribe: context ignored ({problem})", flush=True)      # the reason only, never the content
    raw, filename, hints = await _prepare_audio(raw, audio.filename or "dictation.webm", settings, ctx)
    try:
        transcript = await stt.transcribe(raw, filename, hints)
    except SttChainError as e:
        status, content = failure_response(e, stt.chain_names)
        return JSONResponse(status_code=status, content=content)
    body = success_body(transcript)
    if mode == "name":                                     # Say it: the transcript stays raw, the clean name rides beside it
        body["name"] = clean_said_name(transcript.text)
    return body
