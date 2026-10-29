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
from app.adapters.sam import SamAdapter
from app.config import Settings
from app.journey.video import summarize
from app.media_pipeline import to_sam_clip
from app.spend import clip_seconds

PREPARED_DIR = Path(__file__).parent / "prepared"
_NAME = re.compile(r"^([a-z0-9-]{1,60})\.[a-z0-9]{1,5}$")
NO_KEY = "No model key, so recordings are not transcribed here. Type what was said in the box."
NO_SPEECH = "Nothing was heard in the recording. Type what was said in the box."
FALLBACK = "prepared (live call failed)"
MAX_LIVE_SECONDS = 120
LONG_CLIP = "The clip is longer than 2 minutes. Trim it, then upload it again."
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
        except (httpx.HTTPError, subprocess.SubprocessError, OSError, ValueError) as exc:
            found = prepared(filename)
            if found and found.get("transcript"):
                return {"text": found["transcript"], "source": FALLBACK}
            raise NotHeard(502, UNREACHABLE) from exc
        text = " ".join(t["text"] for t in turns).strip()
        if not text:
            raise NotHeard(409, NO_SPEECH)
        return {"text": text, "source": "muse-voice-transcribe"}
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
    live_ok: bool = True,
) -> dict:
    if settings.spark_configured and live_ok:
        kind = content_type if (content_type or "").startswith("image/") else "image/jpeg"
        data_url = f"data:{kind};base64,{base64.b64encode(raw).decode()}"
        adapter = SparkAdapter(settings)
        try:
            text = adapter.read_strips(data_url) if reader == "strip" else adapter.read_monitor(data_url)
        except (httpx.HTTPError, RuntimeError, ValueError):
            found = prepared(filename)
            if found and found.get("text"):
                return {"text": found["text"], "source": FALLBACK}
            return {"text": None, "source": "failed"}
        return {"text": text, "source": "muse-spark-1.3"}
    found = prepared(filename)
    if found and found.get("text"):
        return {"text": found["text"], "source": "prepared"}
    return {"text": None, "source": "none"}


def _stored_or(stored: dict | None, failed: str) -> dict:
    """A live call did not work: the prepared detections under the fallback label, else `failed`."""
    if stored:
        return {"detections": stored, "source": FALLBACK}
    return {"detections": None, "source": failed}


def _prepared_or_none(stored: dict | None) -> dict:
    if stored:
        return {"detections": stored, "source": "prepared"}
    return {"detections": None, "source": "none"}


def segment_clip(
    settings: Settings, clip: Path, filename: str, concepts: list[str], live_ok: bool = True
) -> dict:
    """Detections by concept for one clip: live SAM 3.1 with a key (and live_ok), else the prepared result."""
    found = prepared(filename)
    stored = found.get("detections") if found else None
    if settings.sam_configured and live_ok:
        try:
            seconds = clip_seconds(clip)
        except (SystemExit, OSError, ValueError):  # no ffprobe, ffprobe fails or prints N/A
            return {"detections": None, "source": "unreadable"}
        if seconds > MAX_LIVE_SECONDS:
            raise NotHeard(400, LONG_CLIP)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "clip.mp4"
                to_sam_clip(clip, out, settings.sam_fps)
                records = SamAdapter(settings).segment_video(out, concepts)
            detections = summarize(records, settings.sam_fps, settings.low_confidence, concepts)
        except (httpx.HTTPError, RuntimeError, OSError, ValueError, KeyError, TypeError):
            return _stored_or(stored, "failed")
        return {"detections": detections, "source": "sam-3.1"}
    return _prepared_or_none(stored)


_IMAGE_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def segment_photos(
    settings: Settings, paths: list[Path], concepts: list[str], filename: str, live_ok: bool = True
) -> dict:
    """Detections by concept for 1-6 photos: per concept the most seen in any one photo (as for frames)."""
    found = prepared(filename)
    stored = found.get("detections") if found else None
    if settings.sam_configured and live_ok:
        try:
            urls = [
                f"data:{_IMAGE_TYPES.get(p.suffix, 'image/jpeg')};base64,{base64.b64encode(p.read_bytes()).decode()}"
                for p in paths
            ]
            records = SamAdapter(settings).segment_images(urls, concepts)
            detections = summarize(records, 1, settings.low_confidence, concepts)
        except (httpx.HTTPError, RuntimeError, OSError, ValueError, KeyError, TypeError):
            return _stored_or(stored, "failed")
        for cell in detections.values():
            cell["at_s"] = None  # a photo has no time
        return {"detections": detections, "source": "sam-3.1"}
    return _prepared_or_none(stored)
