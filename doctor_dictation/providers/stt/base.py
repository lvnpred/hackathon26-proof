"""Speech-to-text provider interface (contract 4.2)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence


@dataclass(frozen=True)
class Transcript:
    text: str
    engine: str                      # e.g. "openai-whisper-api", "local:small.en"
    language: str = ""
    duration: float | None = None
    extra: dict = field(default_factory=dict)   # e.g. {"decode": {...}} for local


class SttError(Exception):
    """A provider failed; str(e) is safe to show (<= 300 chars)."""


class SttUnavailable(SttError):
    """Not installed or not configured; the chain moves on."""


class SttNotImplemented(SttError):
    "Configured but no decode loop yet (ONNX): the route answers 501."


class SttModelLoadError(SttError):
    "Local model failed to load: the route answers 500, no fallback key."


class SttChainError(SttError):
    def __init__(self, failures):  # [(provider name, SttError)] in chain order
        self.failures = failures
        super().__init__("; ".join(f"{n}: {e}" for n, e in failures)[:300])


class SttProvider(Protocol):
    name: str                        # "openai" | "faster-whisper" | "onnx" | "browser" | "stub"

    def available(self) -> bool: ...

    async def transcribe(self, audio: bytes, filename: str, hints: Sequence[str] = ()) -> Transcript: ...
