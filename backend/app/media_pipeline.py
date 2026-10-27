"""Recorded-video path. SAM sees one uploaded clip, not a live socket."""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.adapters.sam import SamAdapter
from app.adapters.voice import VoiceAdapter
from app.config import SAM_CONCEPTS
from app.core.tracker import Tracker
from app.engine import Engine


def run_recorded_video(engine: Engine, case_id: str, source: Path, concepts: list[str] | None = None) -> dict:
    settings = engine.settings
    if not settings.sam_configured:
        raise RuntimeError(
            "SAM 3.1 needs MODEL_API_KEY. Upload ?scenario=demo to run the count rules "
            "on scripted perception. A live frame socket is not part of the SAM 3.1 API."
        )
    zones = engine.store.zones(case_id)
    if set(zones) != {"tray", "field", "bucket"}:
        raise RuntimeError("Save tray, field, and bucket zones before uploading video.")
    work = settings.data_dir / "video" / case_id
    work.mkdir(parents=True, exist_ok=True)
    clip = work / "clip-2fps.mp4"
    audio = work / "speech.wav"
    _ffmpeg(
        ["-y", "-i", str(source), "-vf", f"fps={settings.sam_fps},scale=-2:720", "-an", str(clip)]
    )
    _ffmpeg(["-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", str(audio)])
    names = concepts or list(SAM_CONCEPTS)
    records = SamAdapter(settings).segment_video(clip, names)
    engine.store.log_model_call(
        settings.sam_model,
        "app/adapters/sam.py",
        f"{len(records)} records, {len(names)} concepts",
        case_id,
    )
    by_frame: dict[int, list[dict]] = {}
    for record in records:
        by_frame.setdefault(int(record["frame_index"]), []).append(
            {
                "track_id": str(record["object_id"]),
                "label": record["label"],
                "bbox": record["bbox"],
                "score": record["score"],
                "mask_ref": None,
            }
        )
    tracker = Tracker(
        lost_after_frames=settings.lost_after_frames,
        low_confidence=settings.low_confidence,
    )
    width, height = _video_size(clip)
    for index in sorted(by_frame):
        media_ts = int(index * 1000 / settings.sam_fps)
        engine._ingest_detections(
            case_id,
            tracker,
            zones,
            by_frame[index],
            media_ts_ms=media_ts,
            width=width,
            height=height,
            source="sam-3.1",
            chunk_id="upload",
            relink=False,
            external_ids=True,
        )
    if settings.voice_configured and audio.exists() and audio.stat().st_size:
        try:
            turns = VoiceAdapter(settings).transcribe(audio)
            engine.store.log_model_call(
                settings.voice_model,
                "app/adapters/voice.py",
                f"{len(turns)} turns",
                case_id,
            )
            for turn in turns:
                engine.add_utterance(
                    case_id,
                    turn["text"],
                    t0_ms=turn["t0_ms"],
                    t1_ms=turn["t1_ms"],
                    source="muse-voice-transcribe",
                )
        except Exception as exc:
            engine.store.log_model_call(
                settings.voice_model,
                "app/adapters/voice.py",
                f"transcribe failed: {exc}",
                case_id,
            )
    last = max(by_frame) if by_frame else 0
    engine.apply_rules(case_id, now_ms=int(last * 1000 / settings.sam_fps), finalize=True)
    engine._cache_tracks(case_id, tracker)
    return engine.snapshot(case_id, perception="sam-3.1")


def _ffmpeg(args: list[str]) -> None:
    completed = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr[-500:] or "ffmpeg failed")


def _video_size(path: Path) -> tuple[int, int]:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    width, height = completed.stdout.strip().split("x")
    return int(width), int(height)
