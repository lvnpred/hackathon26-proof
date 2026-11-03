"""Recordings kept for playback (care-app clarity §4.2): the audio a model heard, saved beside the episode's photos in
the data dir (git-ignored, never the repo) and served back only to that episode.

No event is written for a recording: the event that used it (a drafted order, a heard drug) names it by `audio_id`.
Beside each recording, `<id>.heard.json` keeps what Muse Voice heard (transcript, hearer, calls), so an answer
confirmed in a later request can show the words heard next to the words the person confirmed.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.journey.api import _require

audio_router = APIRouter(prefix="/journey/episodes/{episode_id}")

AUDIO_ID = re.compile(r"[0-9a-f]{32}")
# The content type a recording is served with, by the suffix it was kept under.
SUFFIXES = {".wav": "audio/wav", ".webm": "audio/webm", ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
            ".aac": "audio/aac", ".flac": "audio/flac", ".bin": "application/octet-stream"}
_BY_TYPE = {"audio/wav": ".wav", "audio/x-wav": ".wav", "audio/wave": ".wav", "audio/webm": ".webm", "video/webm": ".webm",
            "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a",
            "audio/aac": ".aac", "audio/flac": ".flac"}
NOT_FOUND = "Recording not found"


def _folder(settings, episode_id: str) -> Path:
    return settings.data_dir / "journey_media" / episode_id


def save(settings, episode_id: str, raw: bytes, content_type: str, heard: dict) -> str:
    """Keep the recording under journey_media/<episode>/<id>.audio<suffix>, and what was heard beside it. Its id."""
    audio_id = uuid.uuid4().hex
    folder = _folder(settings, episode_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{audio_id}.audio{_BY_TYPE.get(content_type, '.bin')}").write_bytes(raw)
    kept = {"transcript": heard["text"], "heard_by": heard["source"], "calls": heard["calls"]}
    (folder / f"{audio_id}.heard.json").write_text(json.dumps(kept))
    return audio_id


def heard_of(settings, episode_id: str, audio_id: str) -> dict | None:
    """What was heard on this episode's recording ({transcript, heard_by, calls}), or None."""
    if find(settings, episode_id, audio_id) is None:
        return None
    path = _folder(settings, episode_id) / f"{audio_id}.heard.json"
    return json.loads(path.read_text()) if path.is_file() else None


def find(settings, episode_id: str, audio_id: str) -> Path | None:
    """This episode's recording with that id, or None (a malformed id, another episode's id, or no file)."""
    if not AUDIO_ID.fullmatch(audio_id or ""):
        return None
    for suffix in SUFFIXES:
        path = _folder(settings, episode_id) / f"{audio_id}.audio{suffix}"
        if path.is_file():
            return path
    return None


@audio_router.get("/audio/{audio_id}")
def get_audio(episode_id: str, audio_id: str, request: Request) -> FileResponse:
    _require(request, episode_id)
    path = find(request.app.state.settings, episode_id, audio_id)
    if path is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return FileResponse(path, media_type=SUFFIXES[path.suffix], headers={"X-Content-Type-Options": "nosniff"})
