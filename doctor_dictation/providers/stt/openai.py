"""OpenAI Whisper API provider (cloud default), plus the shared OpenAI-compatible request."""
import httpx

from doctor_dictation.providers.stt.base import SttError, SttUnavailable, Transcript

URL = "https://api.openai.com/v1/audio/transcriptions"


class OpenAiCompatibleStt:
    """One POST to an OpenAI-style /audio/transcriptions endpoint; subclasses set the vendor."""
    name = label = engine = key_env = url = ""

    def __init__(self, key: str, model: str):
        self._key, self._model = key, model

    def available(self) -> bool:
        return bool(self._key)

    async def transcribe(self, audio, filename, hints=()):
        if not self._key:
            raise SttUnavailable(f"{self.key_env} is not set")
        data = {"model": self._model, "language": "en"}
        if hints:
            data["prompt"] = ", ".join(hints)
        files = {"file": (filename or "dictation.webm", audio, "audio/webm")}
        try:  # httpx.AsyncClient is looked up at call time so tests can patch it
            async with httpx.AsyncClient(timeout=90) as client:
                r = await client.post(self.url, headers={"Authorization": f"Bearer {self._key}"},
                                      files=files, data=data)
        except Exception as e:  # network, timeout, TLS: all mean "cloud failed"
            raise SttError(str(e)[:300]) from e
        if r.status_code != 200:
            body = r.text.replace(self._key, "[redacted]")  # a proxy may echo our Authorization header
            raise SttError(f"{self.label} STT {r.status_code}: {body[:300]}"[:300])
        try:
            text = r.json().get("text", "")
        except Exception as e:  # e.g. a captive portal answering 200 with HTML
            raise SttError(f"{self.label} STT returned a non-JSON reply: {e}"[:300]) from e
        return Transcript(text=text, engine=self.engine)


class OpenAiStt(OpenAiCompatibleStt):
    name, label, engine, key_env, url = "openai", "OpenAI", "openai-whisper-api", "OPENAI_API_KEY", URL

    def __init__(self, settings):
        super().__init__(settings.openai_api_key, "whisper-1")
