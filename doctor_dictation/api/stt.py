"""Speech-to-text endpoint. Providers come from the factory at request time."""
import asyncio
from contextlib import closing
from pathlib import PurePath

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse

from doctor_dictation import db as dbmod
from doctor_dictation.api.forms import FormLimitRoute
from doctor_dictation.api.formulary import use_clinic_layer
from doctor_dictation.audio.trim import trim_silence
from doctor_dictation.config import get_settings
from doctor_dictation.core.hints import build_hints
from doctor_dictation.providers.stt.base import SttChainError
from doctor_dictation.providers.stt.factory import failure_response, make_stt, success_body
from doctor_dictation.scope import NoScope, current_scope

router = APIRouter(route_class=FormLimitRoute)


def _doctor_top(limit: int) -> list[str]:
    """The signed-in doctor's most-used medicines (every prescription in single-database mode, where no one
    signs in); any database problem means no personalisation."""
    sc = current_scope()
    try:
        with closing(dbmod.get_conn()) as conn:
            return dbmod.top_medicines(conn, min(30, limit), doctor_id=sc.user_id if sc is not None else None)
    except NoScope:
        raise                      # a missing scope is an auth bug, not "no hints"
    except Exception as exc:  # noqa: BLE001 - hints are optional
        print(f"hints: top_medicines unavailable: {exc}", flush=True)
        return []


async def _prepare_audio(raw: bytes, filename: str, settings) -> tuple[bytes, str, tuple[str, ...]]:
    """Apply the ACC2 flags. Both off returns (raw, filename, ())."""
    hints: tuple[str, ...] = ()
    if settings.stt_trim_silence:
        trimmed = await asyncio.to_thread(trim_silence, raw, filename)
        if trimmed is not raw:                         # new bytes are Ogg/Opus
            raw, filename = trimmed, PurePath(filename).stem + ".ogg"
    if settings.stt_use_hints:
        top = await asyncio.to_thread(_doctor_top, settings.stt_hint_limit)
        hints = tuple(build_hints(top, settings.stt_hint_limit))
    return raw, filename, hints


@router.post("/api/transcribe", dependencies=[Depends(use_clinic_layer)])
async def transcribe(audio: UploadFile = File(...)):
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
    raw, filename, hints = await _prepare_audio(raw, audio.filename or "dictation.webm", settings)
    try:
        transcript = await stt.transcribe(raw, filename, hints)
    except SttChainError as e:
        status, content = failure_response(e, stt.chain_names)
        return JSONResponse(status_code=status, content=content)
    return success_body(transcript)
