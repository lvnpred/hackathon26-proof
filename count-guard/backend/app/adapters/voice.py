"""Muse Voice Transcribe.

Docs checked 27 Oct 2026: POST /v1/asr/transcribe returns turn-level
startMs and endMs. Word-level timestamps are not available. Turn times
are enough for the 30 second unannounced-add window.
Checked live 30 Oct 2026: the body is a JSON `request` part plus an `audio`
part (WAV), the same shape Doctor Dictation's Muse provider sends.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.config import Settings


def parse_voice_payload(payload: dict, offset_ms: int = 0) -> list[dict]:
    turns = payload.get("turns") or []
    parsed = []
    for turn in turns:
        text = (turn.get("transcript") or "").strip()
        if not text:
            continue
        parsed.append(
            {
                "text": text,
                "t0_ms": offset_ms + int(turn.get("startMs") or 0),
                "t1_ms": offset_ms + int(turn.get("endMs") or turn.get("startMs") or 0),
            }
        )
    if parsed:
        return parsed
    text = (payload.get("transcript") or "").strip()
    if not text:
        return []
    return [{"text": text, "t0_ms": offset_ms, "t1_ms": offset_ms}]


class VoiceAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def transcribe(self, path: Path, offset_ms: int = 0, content_type: str = "audio/wav"
    ) -> list[dict]:
        if not self.settings.voice_configured:
            raise RuntimeError("MODEL_API_KEY is not set")
        request = {"mode": "PUSH_TO_TALK", "model": self.settings.voice_model, "audioEncoding": "WAV", "languageBias": ["English"]}
        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"{self.settings.meta_base}/asr/transcribe",
                headers={"Authorization": f"Bearer {self.settings.meta_api_key}"},
                files={
                    "request": (None, json.dumps(request), "application/json"),
                    "audio": (path.name, path.read_bytes(), content_type),
                },
            )
            response.raise_for_status()
            return parse_voice_payload(response.json(), offset_ms)
