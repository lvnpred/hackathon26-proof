"""Stub provider for load tests and demos; the factory refuses it unless ALLOW_STUB_PROVIDERS."""
import asyncio
import os

from doctor_dictation.providers.stt.base import Transcript


class StubStt:
    name = "stub"

    def __init__(self, settings=None):
        ...

    def available(self) -> bool:
        return True

    async def transcribe(self, audio, filename, hints=()):
        delay = int(os.getenv("STUB_DELAY_MS") or 0)  # env read at call time
        if delay > 0:
            await asyncio.sleep(delay / 1000)
        return Transcript(text=os.getenv("STUB_TRANSCRIPT") or "stub transcript", engine="stub")
