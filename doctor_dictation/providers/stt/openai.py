"""OpenAI Whisper API provider (cloud default)."""
import httpx

from doctor_dictation.providers.stt.base import SttError, SttUnavailable, Transcript

URL = "https://api.openai.com/v1/audio/transcriptions"


class OpenAiStt:
    name = "openai"

    def __init__(self, settings):
        self._key = settings.openai_api_key

    def available(self) -> bool:
        return bool(self._key)

    async def transcribe(self, audio, filename, hints=()):
        if not self._key:
            raise SttUnavailable("OPENAI_API_KEY is not set")
        data = {"model": "whisper-1", "language": "en"}
        if hints:
            data["prompt"] = ", ".join(hints)
        files = {"file": (filename or "dictation.webm", audio, "audio/webm")}
        try:  # httpx.AsyncClient is looked up at call time so tests can patch it
            async with httpx.AsyncClient(timeout=90) as client:
                r = await client.post(URL, headers={"Authorization": f"Bearer {self._key}"},
                                      files=files, data=data)
        except Exception as e:  # network, timeout, TLS: all mean "cloud failed"
            raise SttError(str(e)[:300]) from e
        if r.status_code != 200:
            body = r.text.replace(self._key, "[redacted]")  # a proxy may echo our Authorization header
            raise SttError(f"OpenAI STT {r.status_code}: {body[:300]}"[:300])
        try:
            text = r.json().get("text", "")
        except Exception as e:  # e.g. a captive portal answering 200 with HTML
            raise SttError(f"OpenAI STT returned a non-JSON reply: {e}"[:300]) from e
        return Transcript(text=text, engine="openai-whisper-api")
