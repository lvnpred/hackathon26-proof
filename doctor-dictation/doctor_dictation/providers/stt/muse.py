"""Meta Muse Voice Transcribe (cloud), file endpoint: one multipart POST, WAV only.

Hints go out as `keywords` (vocabulary biasing: a nudge, not a guaranteed spelling).
MUSE_LANGUAGE_BIAS sets `languageBias`, e.g. "English,Hindi" for mixed dictation.
Browser webm is converted to 16 kHz WAV with ffmpeg first; no ffmpeg = unavailable.
Docs: dev.meta.ai/docs/speech-to-text (checked 2026-10-19).
"""
import asyncio
import json

import httpx

from doctor_dictation.audio.wav import WavConvertError, ffmpeg_path, to_wav16k
from doctor_dictation.providers.stt.base import SttError, SttUnavailable, Transcript

URL = "https://api.meta.ai/v1/asr/transcribe"


class MuseStt:
    name = "muse"

    def __init__(self, settings):
        self._key = settings.meta_api_key
        self._model = settings.muse_stt_model
        self._languages = settings.muse_language_bias

    def available(self) -> bool:
        return bool(self._key) and ffmpeg_path() is not None

    def _request(self, hints) -> dict:
        req = {"mode": "PUSH_TO_TALK", "model": self._model, "audioEncoding": "WAV"}
        if self._languages:
            req["languageBias"] = list(self._languages)
        if hints:
            req["keywords"] = [h for h in hints if h]
        return req

    async def transcribe(self, audio, filename, hints=()):
        if not self._key:
            raise SttUnavailable("META_API_KEY is not set")
        exe = ffmpeg_path()
        if exe is None:
            raise SttUnavailable("Muse needs WAV audio and ffmpeg is not installed")
        try:
            wav = await asyncio.to_thread(to_wav16k, audio, exe)
        except WavConvertError as e:
            raise SttError(f"Muse STT audio conversion failed: {e}"[:300]) from e
        files = {"request": (None, json.dumps(self._request(hints)), "application/json"),
                 "audio": ("dictation.wav", wav, "audio/wav")}
        try:  # httpx.AsyncClient is looked up at call time so tests can patch it
            async with httpx.AsyncClient(timeout=90) as client:
                r = await client.post(URL, headers={"Authorization": f"Bearer {self._key}"}, files=files)
        except Exception as e:  # network, timeout, TLS: all mean "cloud failed"
            raise SttError(str(e)[:300]) from e
        if r.status_code != 200:
            body = r.text.replace(self._key, "[redacted]")  # a proxy may echo our Authorization header
            raise SttError(f"Muse STT {r.status_code}: {body[:300]}"[:300])
        try:
            text = r.json().get("transcript", "")
        except Exception as e:  # e.g. a captive portal answering 200 with HTML
            raise SttError(f"Muse STT returned a non-JSON reply: {e}"[:300]) from e
        return Transcript(text=text, engine=f"muse:{self._model}")
