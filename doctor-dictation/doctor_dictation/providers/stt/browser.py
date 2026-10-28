"""Marker provider: speech recognition runs in the browser, never on the server."""
from doctor_dictation.providers.stt.base import SttUnavailable


class BrowserStt:
    name = "browser"

    def __init__(self, settings=None):
        ...

    def available(self) -> bool:
        return False

    async def transcribe(self, audio, filename, hints=()):
        raise SttUnavailable("speech recognition runs in the browser")
