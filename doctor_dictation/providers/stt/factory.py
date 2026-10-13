"""Builds the STT provider chain from settings; one chain serves the route and /api/health."""
from typing import Sequence

from doctor_dictation.core.determinism import normalize_transcript, transcript_sha
from doctor_dictation.providers.stt.base import (
    SttChainError, SttError, SttModelLoadError, SttNotImplemented, SttUnavailable, Transcript)
from doctor_dictation.providers.stt.browser import BrowserStt
from doctor_dictation.providers.stt.local import LocalWhisperStt
from doctor_dictation.providers.stt.onnx import OnnxStt
from doctor_dictation.providers.stt.openai import OpenAiStt
from doctor_dictation.providers.stt.stub import StubStt

STT_REGISTRY = {"openai": OpenAiStt, "faster-whisper": LocalWhisperStt, "onnx": OnnxStt,
                "browser": BrowserStt, "stub": StubStt}
DISPLAY = {"openai": "openai-whisper-api", "faster-whisper": "faster-whisper",
           "onnx": "onnx", "stub": "stub"}


def derive_chain(s) -> tuple[str, ...]:
    # STT_CHAIN when set, else implied by STT_ENGINE (unknown values act as auto)
    return s.stt_chain or {"faster-whisper": ("faster-whisper",), "onnx": ("onnx",),
                           "stub": ("stub",)}.get(s.stt_engine, ("openai", "faster-whisper"))


class FallbackStt:
    name = "chain"  # tries providers in order; route and /api/health share it

    def __init__(self, providers):
        self.providers = tuple(providers)

    @property
    def chain_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.providers)

    def available(self) -> bool:
        return any(p.available() for p in self.providers)

    def active_name(self) -> str:
        for p in self.providers:
            if p.available():
                return DISPLAY[p.name]
        if len(self.providers) == 1 and self.providers[0].name != "browser":
            return f"unavailable:{self.providers[0].name}"
        return "browser-webspeech"

    async def transcribe(self, audio: bytes, filename: str, hints: Sequence[str] = ()) -> Transcript:
        failures, really_failed = [], False
        for p in self.providers:
            if really_failed and hasattr(p, "after_earlier_failure"):
                p.after_earlier_failure()  # local pins small.en after a cloud failure
            try:
                return await p.transcribe(audio, filename, hints)
            except SttError as e:
                failures.append((p.name, e))
                if not isinstance(e, SttUnavailable):
                    really_failed = True
                    print(f"STT provider {p.name} failed: {e}", flush=True)
        raise SttChainError(failures)


def make_stt(settings) -> FallbackStt:
    providers = []
    for name in derive_chain(settings):
        if name not in STT_REGISTRY:
            raise ValueError(f"unknown STT provider '{name}' (known: {', '.join(STT_REGISTRY)})")
        if name == "stub" and not settings.allow_stub_providers:
            raise ValueError("the stub STT provider needs ALLOW_STUB_PROVIDERS=1")
        providers.append(STT_REGISTRY[name](settings))
    return FallbackStt(providers)


def success_body(t: Transcript) -> dict:
    """The 200 body, with the key set each engine always returned."""
    body: dict = {"transcript": t.text}
    if t.language or t.duration is not None:
        body.update(language=t.language, duration=t.duration)
    body["engine"] = t.engine
    body["transcript_sha256"] = transcript_sha(normalize_transcript(t.text))
    body.update(t.extra)
    return body


def failure_response(err: SttChainError, chain: Sequence[str]) -> tuple[int, dict]:
    """(status, JSON) exactly as the old if-chain in /api/transcribe returned."""
    for _, e in err.failures:
        if isinstance(e, SttNotImplemented):
            return 501, {"error": str(e), "fallback": "browser"}
    real = [(n, e) for n, e in err.failures if not isinstance(e, SttUnavailable)]
    local = [e for n, e in real if n != "openai"]
    if local:  # a local engine really failed: never loop back to the cloud
        body = {"error": str(local[-1])[:500]}
        if not isinstance(local[-1], SttModelLoadError):
            body["fallback"] = "browser"
        return 500, body
    if real:  # only the cloud failed and nothing else could answer
        return 502, {"error": f"Cloud STT failed and no local STT available: {real[0][1]}",
                     "fallback": "browser"}
    if tuple(chain) == ("onnx",):
        return 503, {"error": f"ONNX STT not configured: {err.failures[0][1]}",
                     "fallback": "browser",
                     "hint": "See doctor_dictation/requirements-onnx.txt (ARM64 py3.11 venv + QNN SDK + model export)."}
    if tuple(chain) == ("faster-whisper",):
        return 503, {"error": "STT_ENGINE=faster-whisper but faster-whisper is not installed here.",
                     "fallback": "browser",
                     "hint": "Run the server from .venv-stt (Python 3.11/3.12 x64) or set STT_ENGINE=auto."}
    return 503, {
        "error": "No server STT installed — run the server from .venv-stt (faster-whisper needs Python 3.11/3.12 x64).",
        "fallback": "browser",
        "hint": "Chrome/Edge: the page will auto-retry with free on-device Web Speech recognition — just allow mic and speak again. Or set OPENAI_API_KEY for cloud Whisper.",
    }
