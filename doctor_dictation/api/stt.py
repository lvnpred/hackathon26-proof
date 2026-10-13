"""Speech-to-text endpoint. Providers come from the factory at request time."""
import asyncio
from contextlib import closing
from pathlib import PurePath

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from doctor_dictation import db as dbmod
from doctor_dictation.audio.trim import trim_silence
from doctor_dictation.config import get_settings
from doctor_dictation.core.hints import build_hints
from doctor_dictation.providers.stt.base import SttChainError
from doctor_dictation.providers.stt.factory import failure_response, make_stt, success_body

router = APIRouter()


def _doctor_top(limit: int) -> list[str]:
    """The doctor's most-used medicines; any database problem means no personalisation."""
    try:
        with closing(dbmod.get_conn()) as conn:
            return dbmod.top_medicines(conn, min(30, limit))
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


@router.post("/api/transcribe")
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
