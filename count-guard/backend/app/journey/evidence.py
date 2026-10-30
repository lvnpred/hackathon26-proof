"""The evidence sidecar: the boxes and raw output behind one model check, kept beside the episode's media (C4)."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from app.config import Settings

EVIDENCE_ID = re.compile(r"[0-9a-f]{32}")
MAX_RAW_CHARS = 200_000
RAW_CAPPED = {"note": "Raw output over 200 KB; not kept."}


def _path(settings: Settings, episode_id: str, evidence_id: str) -> Path:
    return settings.data_dir / "journey_media" / episode_id / f"{evidence_id}.evidence.json"


def save(settings: Settings, episode_id: str, body: dict) -> str:
    """Write a new sidecar and return its id. A raw output over 200 000 characters is replaced by a note (R12)."""
    evidence_id = uuid.uuid4().hex
    raw = body.get("raw")
    if raw is not None and len(json.dumps(raw)) > MAX_RAW_CHARS:
        raw = RAW_CAPPED
    path = _path(settings, episode_id, evidence_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**body, "raw": raw, "id": evidence_id}))
    return evidence_id


def load(settings: Settings, episode_id: str, evidence_id: str) -> dict | None:
    """The sidecar, or None when the id is malformed or the file is missing."""
    if not EVIDENCE_ID.fullmatch(evidence_id):
        return None
    path = _path(settings, episode_id, evidence_id)
    return json.loads(path.read_text()) if path.is_file() else None


def held_by(events: list[dict], evidence_id: str) -> list[dict]:
    """The events that cite this evidence, oldest first."""
    return [e for e in events if e["payload"].get("evidence_id") == evidence_id]
