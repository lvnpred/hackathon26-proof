"""Local faster-whisper provider (offline fallback)."""
import asyncio
import os
import tempfile
import threading
from pathlib import Path

from doctor_dictation.config import get_settings
from doctor_dictation.core.hints import prompt_text
from doctor_dictation.providers.stt.base import (
    SttError, SttModelLoadError, SttUnavailable, Transcript)

# Pinned deterministic STT decode params (P0.1). temperature=0.0 disables the
# faster-whisper temperature-fallback chain; condition_on_previous_text=False
# stops cross-segment drift.
STT_DECODE = {
    "language": "en",
    "beam_size": 5,
    "patience": 1.0,
    "temperature": 0.0,
    "condition_on_previous_text": False,
    "compression_ratio_threshold": 2.4,
    "log_prob_threshold": -1.0,
    "no_speech_threshold": 0.6,
    "vad_filter": True,
    "vad_parameters": {"min_silence_duration_ms": 500},
    "initial_prompt": "medical prescription, dosage OD BD TDS HS SOS, after food before food",
}


def faster_whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


_pinned_name = None  # set by pin_small_model(); wins over settings
_model = None
_lock = threading.Lock()


def whisper_model_name() -> str:
    return _pinned_name or get_settings().whisper_model


def pin_small_model() -> None:  # small.en: fast, no turbo; drop the cached model
    global _pinned_name, _model
    if whisper_model_name() != "small.en":
        print(f"STT: pinning local fallback to small.en (was {whisper_model_name()})", flush=True)
        _pinned_name, _model = "small.en", None


def get_model():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel
            s = get_settings()
            _model = WhisperModel(whisper_model_name(), device=s.whisper_device,
                                  compute_type=s.whisper_compute_type)
    return _model


class LocalWhisperStt:
    name = "faster-whisper"

    def __init__(self, settings=None):
        ...

    def available(self) -> bool:
        return faster_whisper_available()

    def after_earlier_failure(self) -> None:
        pin_small_model()  # a cloud provider really failed

    async def transcribe(self, audio, filename, hints=()):
        if not faster_whisper_available():
            raise SttUnavailable("faster-whisper is not installed")
        try:
            model = await asyncio.to_thread(get_model)
        except Exception as e:
            raise SttModelLoadError(
                f"STT model failed to load ({whisper_model_name()}): {e}".strip()[:500]) from e
        decode = dict(STT_DECODE)
        if hints:
            decode["initial_prompt"] += ". " + prompt_text(hints)
        suffix = Path(filename or "audio.webm").suffix or ".webm"

        def _run():
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(audio)
            try:
                segments, info = model.transcribe(tmp.name, **decode)
                return " ".join(s.text.strip() for s in segments).strip(), info.language, info.duration
            finally:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass

        try:
            text, lang, dur = await asyncio.to_thread(_run)
        except Exception as e:
            raise SttError(f"Server STT failed: {e}".strip()[:500]) from e
        used = {"temperature": 0.0, "beam_size": 5, "patience": 1.0, "condition_on_previous_text": False}
        return Transcript(text=text, engine=f"local:{whisper_model_name()}", language=lang,
                          duration=dur, extra={"decode": used})
