"""AssemblyAI (cloud): upload, submit, then poll until the transcript is done.

Unlike OpenAI and Groq this is a job API, so one dictation is three or more requests.
Hints go out as keyterms_prompt (billed as an add-on); ASSEMBLYAI_MEDICAL=1 adds
Medical Mode (domain "medical-v1"), which is also billed per hour on top.
"""
import asyncio
import time

import httpx

from doctor_dictation.providers.stt.base import SttError, SttUnavailable, Transcript

BASE = "https://api.assemblyai.com/v2"
POLL_SECONDS = 1.0     # module-level so tests can set 0
DEADLINE_SECONDS = 90  # same budget as the single OpenAI request
MAX_KEYTERM_WORDS = 6  # AssemblyAI rejects longer phrases


class AssemblyAiStt:
    name = "assemblyai"

    def __init__(self, settings):
        self._key = settings.assemblyai_api_key
        self._model = settings.assemblyai_model
        self._medical = settings.assemblyai_medical

    def available(self) -> bool:
        return bool(self._key)

    def _fail(self, what: str, r) -> SttError:
        body = r.text.replace(self._key, "[redacted]")  # a proxy may echo our authorization header
        return SttError(f"AssemblyAI STT {what} {r.status_code}: {body[:300]}"[:300])

    def _job(self, upload_url: str, hints) -> dict:
        job = {"audio_url": upload_url, "speech_models": [self._model], "language_code": "en"}
        terms = [h for h in hints if h and len(h.split()) <= MAX_KEYTERM_WORDS]
        if terms:
            job["keyterms_prompt"] = terms
        if self._medical:
            job["domain"] = "medical-v1"
        return job

    async def transcribe(self, audio, filename, hints=()):
        if not self._key:
            raise SttUnavailable("ASSEMBLYAI_API_KEY is not set")
        auth = {"authorization": self._key}  # raw key, no "Bearer"
        try:  # httpx.AsyncClient is looked up at call time so tests can patch it
            async with httpx.AsyncClient(timeout=90) as client:
                r = await client.post(f"{BASE}/upload", headers=auth, content=audio)
                if r.status_code != 200:
                    raise self._fail("upload", r)
                r = await client.post(f"{BASE}/transcript", headers=auth,
                                      json=self._job(r.json()["upload_url"], hints))
                if r.status_code != 200:
                    raise self._fail("submit", r)
                job_id, end = r.json()["id"], time.monotonic() + DEADLINE_SECONDS
                while True:
                    r = await client.get(f"{BASE}/transcript/{job_id}", headers=auth)
                    if r.status_code != 200:
                        raise self._fail("poll", r)
                    job = r.json()
                    if job.get("status") == "completed":
                        return Transcript(text=job.get("text") or "", engine=f"assemblyai:{self._model}")
                    if job.get("status") == "error":
                        raise SttError(f"AssemblyAI STT job failed: {job.get('error', '')}"[:300])
                    if time.monotonic() > end:
                        raise SttError(f"AssemblyAI STT timed out after {DEADLINE_SECONDS}s")
                    await asyncio.sleep(POLL_SECONDS)
        except SttError:
            raise
        except Exception as e:  # network, timeout, TLS, a non-JSON reply: all mean "cloud failed"
            raise SttError(str(e).replace(self._key, "[redacted]")[:300]) from e
