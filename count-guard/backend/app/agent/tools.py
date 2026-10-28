"""Tools the reconciler may call. They read the ledger. They change nothing."""

from __future__ import annotations

from app.core.ledger import ledger_rows, open_discrepancies
from app.engine import track_path
from app.store import Store


def schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "get_ledger",
                "description": "Counts per item type: opened, tray, field, bucket, unaccounted.",
                "parameters": {
                    "type": "object",
                    "properties": {"item_type": {"type": "string"}},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_track",
                "description": "One item's zone path.",
                "parameters": {
                    "type": "object",
                    "properties": {"track_id": {"type": "string"}},
                    "required": ["track_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_frames",
                "description": "Frames for one track around a video time in milliseconds.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "track_id": {"type": "string"},
                        "around_ts": {"type": "integer"},
                    },
                    "required": ["track_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_transcript",
                "description": "Transcript lines between t0 and t1 milliseconds.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "t0": {"type": "integer"},
                        "t1": {"type": "integer"},
                    },
                    "required": ["t0", "t1"],
                },
            },
        },
    ]


def dispatch(store: Store, case_id: str, name: str, arguments: dict) -> dict:
    events = store.events(case_id)
    if name == "get_ledger":
        rows = ledger_rows(events)
        item_type = arguments.get("item_type")
        if item_type:
            rows = [row for row in rows if row["item_type"] == item_type]
        return {"ledger": rows, "discrepancies": open_discrepancies(events)}
    if name == "get_track":
        track_id = arguments["track_id"]
        return {"track_id": track_id, "path": track_path(events, track_id), "cached": store.track(case_id, track_id)}
    if name == "get_frames":
        track_id = arguments["track_id"]
        around = arguments.get("around_ts")
        points = track_path(events, track_id)
        frames = []
        for point in points:
            if around is not None and point.get("media_ts_ms") is not None:
                if abs(point["media_ts_ms"] - int(around)) > 120_000:
                    continue
            if point.get("frame_id"):
                frames.append(
                    {
                        "frame_id": point["frame_id"],
                        "evidence_id": f"frame:{point['frame_id']}",
                        "media_ts_ms": point["media_ts_ms"],
                        "zone": point["zone"],
                    }
                )
        return {"frames": frames}
    if name == "get_transcript":
        segments = store.transcripts(case_id, int(arguments["t0"]), int(arguments["t1"]))
        return {
            "transcript": [
                {
                    "id": segment["id"],
                    "evidence_id": f"transcript:{segment['id']}",
                    "t0_ms": segment["t0_ms"],
                    "t1_ms": segment["t1_ms"],
                    "text": segment["text"],
                }
                for segment in segments
            ]
        }
    return {"error": f"unknown tool {name}"}
