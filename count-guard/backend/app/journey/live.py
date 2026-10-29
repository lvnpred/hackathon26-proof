"""Model seam: a live call when a key is set, a prepared result when it is not. Nothing here decides."""

from __future__ import annotations

import base64
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

import httpx

from app.adapters.spark import SparkAdapter
from app.adapters.voice import VoiceAdapter
from app.config import Settings

PREPARED_DIR = Path(__file__).parent / "prepared"
_NAME = re.compile(r"^([a-z0-9-]{1,60})\.[a-z0-9]{1,5}$")
NO_KEY = "No model key, so recordings are not transcribed here. Type what was said in the box."
UNREACHABLE = "The transcriber did not answer. Type what was said in the box."


class NotHeard(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def safe_stem(filename: str | None) -> str | None:
    """The stem of a plain file name, or None. Slashes, spaces and dots in the stem never pass."""
    match = _NAME.match((filename or "").lower())
    return match.group(1) if match else None


def prepared(filename: str | None) -> dict | None:
    stem = safe_stem(filename)
    if stem is None:
        return None
    path = PREPARED_DIR / f"{stem}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def to_wav(raw: bytes, content_type: str) -> bytes:
    if content_type == "audio/wav":
        return raw
    done = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", "pipe:0", "-ac", "1", "-ar", "16000", "-f", "wav", "pipe:1"],
        input=raw, capture_output=True, check=True, timeout=60,
    )
    return done.stdout


def transcribe(settings: Settings, raw: bytes, filename: str, content_type: str) -> dict:
    if settings.voice_configured:
        try:
            wav = to_wav(raw, content_type)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "heard.wav"
                path.write_bytes(wav)
                turns = VoiceAdapter(settings).transcribe(path, 0, "audio/wav")
        except (httpx.HTTPError, subprocess.SubprocessError, OSError) as exc:
            raise NotHeard(502, UNREACHABLE) from exc
        return {"text": " ".join(t["text"] for t in turns), "source": "muse-voice-transcribe"}
    found = prepared(filename)
    if found and found.get("transcript"):
        return {"text": found["transcript"], "source": "prepared"}
    raise NotHeard(409, NO_KEY)


def spark_text(settings: Settings, prompt: str) -> str | None:
    if not settings.spark_configured:
        return None
    try:
        return SparkAdapter(settings).write(prompt)
    except (httpx.HTTPError, RuntimeError, ValueError):
        return None


def read_photo(
    settings: Settings,
    reader: Literal["strip", "monitor"],
    raw: bytes,
    filename: str,
    content_type: str,
) -> dict:
    if settings.spark_configured:
        kind = content_type if (content_type or "").startswith("image/") else "image/jpeg"
        data_url = f"data:{kind};base64,{base64.b64encode(raw).decode()}"
        adapter = SparkAdapter(settings)
        try:
            text = adapter.read_strips(data_url) if reader == "strip" else adapter.read_monitor(data_url)
        except (httpx.HTTPError, RuntimeError, ValueError):
            return {"text": None, "source": "failed"}
        return {"text": text, "source": "muse-spark-1.3"}
    found = prepared(filename)
    if found and found.get("text"):
        return {"text": found["text"], "source": "prepared"}
    return {"text": None, "source": "none"}
