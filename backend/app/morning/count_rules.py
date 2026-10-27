"""Bucket dwell and closing reconcile for the morning timeline.

A swab counts as out only after it sits in the bucket for DWELL frames.
A hand wave that leaves sooner does not count.
"""

from __future__ import annotations

DWELL = 3


def fresh_state() -> dict:
    return {"out": set(), "last": {}}


def observe(state: dict, frame: dict, *, dwell: int = DWELL) -> list[dict]:
    track_id = frame["track_id"]
    last = state["last"].setdefault(
        track_id,
        {"zone": None, "streak": 0, "frame_id": None, "t_ms": 0},
    )
    last["zone"] = frame["zone"]
    last["frame_id"] = frame["frame_id"]
    last["t_ms"] = frame["t_ms"]
    if frame["zone"] == "bucket":
        last["streak"] += 1
        if last["streak"] == dwell and track_id not in state["out"]:
            state["out"].add(track_id)
            return [
                {
                    "event_type": "count.item_out",
                    "ts_ms": frame["t_ms"],
                    "tier": "documentation",
                    "payload": {
                        "track_id": track_id,
                        "frame_id": frame["frame_id"],
                        "source": "replay",
                    },
                }
            ]
        return []
    last["streak"] = 0
    return []


def closing(state: dict, *, opened: int, item_type: str = "swab") -> dict:
    missing = [
        track_id
        for track_id, info in state["last"].items()
        if track_id not in state["out"] and info["zone"] != "bucket"
    ]
    named = missing[0] if missing else None
    frame_id = state["last"][named]["frame_id"] if named else None
    returned = len(state["out"])
    return {
        "event_type": "count.closing",
        "ts_ms": max((info["t_ms"] for info in state["last"].values()), default=0) + 1,
        "tier": "documentation",
        "payload": {
            "item_type": item_type,
            "opened": opened,
            "returned": returned,
            "unaccounted": opened - returned,
            "track_id": named,
            "frame_id": frame_id,
            "detail": (
                f"Unaccounted: {opened - returned} {item_type}."
                + (f" Last seen {named}, frame {frame_id}." if named else "")
            ),
        },
    }


def demo_frames() -> list[dict]:
    """20 swabs. 19 dwell in the bucket. swab-20 stays in the field."""
    frames: list[dict] = []
    clock = 0
    for number in range(1, 20):
        track_id = f"swab-{number}"
        frames.append(
            {"t_ms": clock, "track_id": track_id, "zone": "field", "frame_id": f"field-{track_id}"}
        )
        clock += 100
        for step in range(DWELL):
            frames.append(
                {
                    "t_ms": clock,
                    "track_id": track_id,
                    "zone": "bucket",
                    "frame_id": f"bucket-{track_id}-{step}",
                }
            )
            clock += 100
    frames.append(
        {"t_ms": clock, "track_id": "swab-20", "zone": "field", "frame_id": "field-swab-20"}
    )
    return frames


def replay(frames: list[dict], *, opened: int = 20, dwell: int = DWELL) -> list[dict]:
    state = fresh_state()
    events: list[dict] = []
    for frame in frames:
        events.extend(observe(state, frame, dwell=dwell))
    events.append(closing(state, opened=opened))
    return events
