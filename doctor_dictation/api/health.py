"""Health endpoints. Settings are read per request, never at import."""
from fastapi import APIRouter

from doctor_dictation.api import visit
from doctor_dictation.config import get_settings, secret_presence
from doctor_dictation.core.determinism import lexicon_size, lexicon_version
from doctor_dictation.core.dosing import dosing_version
from doctor_dictation.providers.llm.factory import make_llm
from doctor_dictation.providers.stt.factory import make_stt
from doctor_dictation.providers.stt.local import STT_DECODE, whisper_model_name
from doctor_dictation.providers.stt.onnx import status as onnx_stt_status

router = APIRouter()


@router.get("/api/health")
@router.get("/health")
def health():
    settings = get_settings()
    try:
        active = make_stt(settings).active_name()
    except ValueError:  # bad STT_CHAIN, or stub without ALLOW_STUB_PROVIDERS
        active = "misconfigured"
    stt = {
        "faster-whisper": f"local:{whisper_model_name()}",
        "onnx": "onnx-whisper",
        "openai-whisper-api": "openai-whisper-api (cloud default)",
        "groq-whisper-api": f"groq-whisper-api ({settings.groq_stt_model})",
        "muse-api": f"muse-api ({settings.muse_stt_model})",
        "assemblyai-api": f"assemblyai-api ({settings.assemblyai_model}"
                          f"{', medical' if settings.assemblyai_medical else ''})",
        "browser-webspeech": "browser-webspeech (no server STT installed)",
    }.get(active, active)
    onnx_ok, onnx_detail = onnx_stt_status()
    llm = make_llm(settings)
    # Presence only -- booleans from the resolved settings snapshot, never values.
    presence = secret_presence(
        ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GROQ_API_KEY", "ASSEMBLYAI_API_KEY", "META_API_KEY"),
        overrides={"OPENAI_API_KEY": settings.openai_api_key,
                   "DEEPSEEK_API_KEY": settings.deepseek_api_key,
                   "GROQ_API_KEY": settings.groq_api_key,
                   "ASSEMBLYAI_API_KEY": settings.assemblyai_api_key,
                   "META_API_KEY": settings.meta_api_key},
    )
    return {
        "ok": True,
        "whisper_model": whisper_model_name(),
        "stt_engine": stt,
        "stt_engine_requested": settings.stt_engine,
        "stt_engine_active": active,
        "onnx_stt": {"available": onnx_ok, "detail": onnx_detail},
        "openai_configured": presence["OPENAI_API_KEY"],
        "deepseek_configured": presence["DEEPSEEK_API_KEY"],
        "groq_configured": presence["GROQ_API_KEY"],
        "assemblyai_configured": presence["ASSEMBLYAI_API_KEY"],
        "meta_configured": presence["META_API_KEY"],
        "llm_provider": llm.name if llm else settings.llm_provider,
        "llm_model": llm.model if llm else "",
        "llm_configured": llm is not None,
        "lexicon_version": lexicon_version(),
        "lexicon_entries": lexicon_size(),
        "dosing_version": dosing_version(),
        "date_locale": visit.locale(),           # the page formats dates and times with these two (frontend/dates.js)
        "timezone": visit.effective_zone_name(),   # the zone the server uses, so page and print agree
        "stt_decode": {k: v for k, v in STT_DECODE.items() if k != "initial_prompt"},
    }
