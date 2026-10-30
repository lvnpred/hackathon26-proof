"""Model seam: a live call when a key is set, a prepared result when it is not. Nothing here decides."""

from __future__ import annotations

import base64
import json
import logging
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Literal

import httpx

from app.adapters.spark import SparkAdapter
from app.adapters.voice import VoiceAdapter
from app.adapters.sam import SamAdapter
from app.config import Settings
from app.journey.proof import parse_monitor_text
from app.journey.regions import READER_CONCEPTS, monitor_values, pair_regions, strip_values, strips_from
from app.journey.video import frames_from, summarize
from app.media_pipeline import to_sam_clip
from app.spend import clip_seconds

PREPARED_DIR = Path(__file__).parent / "prepared"
log = logging.getLogger(__name__)
_NAME = re.compile(r"^([a-z0-9-]{1,60})\.[a-z0-9]{1,5}$")
NO_KEY = "No model key, so recordings are not transcribed here. Type what was said in the box."
NO_SPEECH = "Nothing was heard in the recording. Type what was said in the box."
FALLBACK = "prepared (live call failed)"
MAX_LIVE_SECONDS = 120
LONG_CLIP = "The clip is longer than 2 minutes. Trim it, then upload it again."
UNREACHABLE = "The transcriber did not answer. Type what was said in the box."


MODEL_IDS = {"voice": "voice_model", "spark": "spark_model", "sam": "sam_model", "spark-open": "spark_open_model"}
_LIVE = ("muse-voice-transcribe", "muse-spark-1.3", "sam-3.1")
_FAILED = (FALLBACK, "failed", "unreadable", "rules (model reply not usable)")


def call_of(model: str, settings: Settings, source: str, ms: int | None) -> dict:
    """One model call as the record keeps it: the card key, the model id, the source word and the time."""
    return {"model": model, "model_id": getattr(settings, MODEL_IDS[model]), "source": source, "ms": ms}


def mode_of(source: str) -> str | None:
    """live, prepared or failed for a source word; None when no model was asked (rules, typed, none)."""
    if source in _LIVE:
        return "live"
    if source == "prepared":
        return "prepared"
    return "failed" if source in _FAILED else None


HEARERS = ("prepared", "muse-voice-transcribe", "prepared (live call failed)")


def spoken_calls(settings: Settings, via: str, heard_by: str) -> list[dict]:
    """The voice call of a spoken confirmation made in a later request: the hearer the server named, no time (R4)."""
    if via == "voice" and heard_by in HEARERS:
        return [call_of("voice", settings, heard_by, None)]
    return []


def _since(start: float) -> int:
    return round((time.monotonic() - start) * 1000)


def _calls(model: str, settings: Settings, source: str, ms: int | None) -> list[dict]:
    """The calls of a result: none when nothing was read, else the one model asked."""
    return [] if source == "none" else [call_of(model, settings, source, ms)]


def _prepared_ms(found: dict | None) -> int | None:
    return found.get("ms") if found else None


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


def _reason(exc: Exception, key: str) -> str:
    """Why a call failed, with the response body when there is one. The key never appears."""
    body = exc.response.text if isinstance(exc, httpx.HTTPStatusError) else ""
    text = f"{type(exc).__name__}: {exc} {body}"
    return (text.replace(key, "[redacted]") if key else text)[:400]


def transcribe(settings: Settings, raw: bytes, filename: str, content_type: str) -> dict:
    if settings.voice_configured:
        start = time.monotonic()
        try:
            wav = to_wav(raw, content_type)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "heard.wav"
                path.write_bytes(wav)
                start = time.monotonic()
                turns = VoiceAdapter(settings).transcribe(path, 0, "audio/wav")
        except (httpx.HTTPError, subprocess.SubprocessError, OSError, ValueError) as exc:
            log.warning("Voice transcription failed: %s", _reason(exc, settings.meta_api_key))
            found = prepared(filename)
            if found and found.get("transcript"):
                return {"text": found["transcript"], "source": FALLBACK, "calls": [call_of("voice", settings, FALLBACK, _since(start))]}
            raise NotHeard(502, UNREACHABLE) from exc
        ms = _since(start)
        text = " ".join(t["text"] for t in turns).strip()
        if not text:
            raise NotHeard(409, NO_SPEECH)
        return {"text": text, "source": "muse-voice-transcribe", "calls": [call_of("voice", settings, "muse-voice-transcribe", ms)]}
    found = prepared(filename)
    if found and found.get("transcript"):
        return {"text": found["transcript"], "source": "prepared", "calls": [call_of("voice", settings, "prepared", _prepared_ms(found))]}
    raise NotHeard(409, NO_KEY)


def spark_text(settings: Settings, prompt: str) -> str | None:
    if not settings.spark_configured:
        return None
    try:
        return SparkAdapter(settings).write(prompt)
    except (httpx.HTTPError, RuntimeError, ValueError):
        return None


def _boxes(settings: Settings, reader: str, data_url: str) -> tuple[list[dict], list[dict], dict]:
    """SAM's boxes for a photo: (boxes, parsed records, the sam call). A SAM error gives no boxes and a failed call."""
    start = time.monotonic()
    try:
        records = SamAdapter(settings).segment_images([data_url], READER_CONCEPTS[reader])
    except (httpx.HTTPError, RuntimeError, OSError, ValueError, KeyError, TypeError):
        return [], [], call_of("sam", settings, "failed", _since(start))
    call = call_of("sam", settings, "sam-3.1", _since(start))
    parsed = [{k: v for k, v in r.items() if k != "mask_token"} for r in records]
    boxes = [
        {"bbox": [round(v, 4) for v in r["bbox"]], "score": r.get("score")}
        for r in records
        if r.get("frame_index", 0) == 0 and (r.get("score") is None or r["score"] >= settings.low_confidence)
    ]
    return boxes, parsed, call


def _values(reader: str, text: str | None) -> list[dict]:
    """What Spark read, in reading order; none when it read nothing."""
    if not text:
        return []
    if reader == "monitor":
        return monitor_values(parse_monitor_text(text))
    return strip_values(strips_from(text))


def _photo(text, source, regions, calls, raw, handmade) -> dict:
    return {"text": text, "source": source, "regions": regions, "calls": calls, "raw": raw, "handmade": handmade}


def read_photo(
    settings: Settings,
    reader: Literal["strip", "monitor"],
    raw: bytes,
    filename: str,
    content_type: str,
    live_ok: bool = True,
) -> dict:
    """A photo read is two calls: SAM boxes each region, Spark reads the values, `pair_regions` joins them (D1(b))."""
    found = prepared(filename)
    if settings.spark_configured and live_ok:
        kind = content_type if (content_type or "").startswith("image/") else "image/jpeg"
        data_url = f"data:{kind};base64,{base64.b64encode(raw).decode()}"
        boxes, parsed, sam_call = _boxes(settings, reader, data_url)
        adapter = SparkAdapter(settings)
        start = time.monotonic()
        try:
            text = adapter.read_strips(data_url) if reader == "strip" else adapter.read_monitor(data_url)
        except (httpx.HTTPError, RuntimeError, ValueError):
            ms = _since(start)
            if found and found.get("text"):
                text, source, handmade = found["text"], FALLBACK, bool(found.get("handmade"))
            else:
                text, source, handmade = None, "failed", False
            spark_call = call_of("spark", settings, source, ms)
        else:
            source, handmade = "muse-spark-1.3", False
            spark_call = call_of("spark", settings, source, _since(start))
        regions = pair_regions(boxes, _values(reader, text))
        return _photo(text, source, regions, [sam_call, spark_call], {"sam": parsed, "spark": text}, handmade)
    if found and found.get("text"):
        values = _values(reader, found["text"])
        stored = found.get("regions")
        calls = ([call_of("sam", settings, "prepared", _prepared_ms(found))] if stored else []) + [
            call_of("spark", settings, "prepared", _prepared_ms(found))]
        return _photo(found["text"], "prepared", stored or pair_regions([], values), calls,
                      found.get("raw"), bool(found.get("handmade")))
    return _photo(None, "none", [], [], None, False)


def _stored(found: dict | None, key: str) -> dict:
    """The fixture's frames (`key` is frames or stills) and raw output, else None (R10)."""
    found = found or {}
    return {"frames": found.get(key), "raw": found.get("raw"), "handmade": bool(found.get("handmade"))}


def _live_evidence(records: list[dict], fps: int, settings: Settings, photos: bool) -> dict:
    """The boxes of a live SAM answer, and its parsed records without the mask tokens (R12)."""
    frames = frames_from(records, fps, settings.low_confidence, photos=photos)
    parsed = [{k: v for k, v in r.items() if k != "mask_token"} for r in records]
    return {"frames": frames, "raw": {"sam": parsed}, "handmade": False}


def _stored_or(settings: Settings, found: dict | None, failed: str, ms: int | None, key: str) -> dict:
    """A live call did not work: the prepared detections under the fallback label, else `failed`."""
    stored = found.get("detections") if found else None
    source = FALLBACK if stored else failed
    return {"detections": stored or None, "source": source, "calls": _calls("sam", settings, source, ms),
            **(_stored(found, key) if stored else _stored(None, key))}


def _prepared_or_none(settings: Settings, found: dict | None, key: str) -> dict:
    stored = found.get("detections") if found else None
    if stored:
        return {"detections": stored, "source": "prepared", "calls": _calls("sam", settings, "prepared", _prepared_ms(found)),
                **_stored(found, key)}
    return {"detections": None, "source": "none", "calls": [], **_stored(None, key)}


def segment_clip(
    settings: Settings, clip: Path, filename: str, concepts: list[str], live_ok: bool = True
) -> dict:
    """Detections by concept for one clip: live SAM 3.1 with a key (and live_ok), else the prepared result."""
    found = prepared(filename)
    if settings.sam_configured and live_ok:
        try:
            seconds = clip_seconds(clip)
        except (SystemExit, OSError, ValueError):  # no ffprobe, ffprobe fails or prints N/A
            return {"detections": None, "source": "unreadable", "calls": _calls("sam", settings, "unreadable", None),
                    **_stored(None, "frames")}
        if seconds > MAX_LIVE_SECONDS:
            raise NotHeard(400, LONG_CLIP)
        start = time.monotonic()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "clip.mp4"
                to_sam_clip(clip, out, settings.sam_fps)
                start = time.monotonic()
                records = SamAdapter(settings).segment_video(out, concepts)
            ms = _since(start)
            detections = summarize(records, settings.sam_fps, settings.low_confidence, concepts)
            evidence = _live_evidence(records, settings.sam_fps, settings, photos=False)
        except (httpx.HTTPError, RuntimeError, OSError, ValueError, KeyError, TypeError):
            return _stored_or(settings, found, "failed", _since(start), "frames")
        return {"detections": detections, "source": "sam-3.1", "calls": _calls("sam", settings, "sam-3.1", ms), **evidence}
    return _prepared_or_none(settings, found, "frames")


_IMAGE_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def segment_photos(
    settings: Settings, paths: list[Path], concepts: list[str], filename: str, live_ok: bool = True
) -> dict:
    """Detections by concept for 1-6 photos: per concept the most seen in any one photo (as for frames)."""
    found = prepared(filename)
    if settings.sam_configured and live_ok:
        start = time.monotonic()
        try:
            urls = [
                f"data:{_IMAGE_TYPES.get(p.suffix, 'image/jpeg')};base64,{base64.b64encode(p.read_bytes()).decode()}"
                for p in paths
            ]
            start = time.monotonic()
            records = SamAdapter(settings).segment_images(urls, concepts)
            ms = _since(start)
            detections = summarize(records, 1, settings.low_confidence, concepts)
            evidence = _live_evidence(records, 1, settings, photos=True)
        except (httpx.HTTPError, RuntimeError, OSError, ValueError, KeyError, TypeError):
            return _stored_or(settings, found, "failed", _since(start), "stills")
        for cell in detections.values():
            cell["at_s"] = None  # a photo has no time
        return {"detections": detections, "source": "sam-3.1", "calls": _calls("sam", settings, "sam-3.1", ms), **evidence}
    return _prepared_or_none(settings, found, "stills")
