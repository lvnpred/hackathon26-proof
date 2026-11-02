"""Count extras on the swab camera (spec §6.4, §9): the replay of recorded detections, the bucket-dwell counter and
what the care view shows of them, of a resolve and of a closed camera case.

Reuses only the pure counter in `morning/count_rules.py` (`fresh_state`, `observe`, `demo_frames`, `closing`). Its
`replay` is not used: that writes a closing. Everything here is written as `camera.*` by CAMERA_BY and is advice;
`count_gate` and `stay_opened` read none of it (U10).
"""

from __future__ import annotations

from app.journey import advice, states
from app.journey.stories import CAMERA_BY
from app.morning.count_rules import closing, demo_frames, fresh_state, observe

REPLAY_OPENED = 20  # the recorded detections: twenty swabs, nineteen dwell in the bucket
DWELL_BAG = "camera_dwell"


def replay_summary() -> dict:
    """The recorded detections run through the dwell counter. A summary only, never a `count.closing`."""
    state = fresh_state()
    for frame in demo_frames():
        observe(state, frame)
    summary = closing(state, opened=REPLAY_OPENED)["payload"]  # pure: read the figures, write none of it
    missing = sorted(t for t, info in state["last"].items() if t not in state["out"] and info["zone"] != "bucket")
    last_zone = state["last"][missing[0]]["zone"] if missing else None
    return {"source": "prepared", "opened": REPLAY_OPENED, "returned": summary["returned"], "missing": missing,
            "last_zone": last_zone}


def replay_advice(summary: dict) -> list[dict]:
    """One advice row per swab the replay did not see back. No camera frame stands behind a replay."""
    where = advice.PLACE.get(summary.get("last_zone") or "", "the field")
    return [{"rule": "R3", "item": track, "item_type": "swab", "frame_id": None, "key": f"replay:{track}",
             "text": f"In the recorded replay one swab was not seen back. It was last seen on {where}."}
            for track in summary["missing"]]


def dwell_state(store, episode_id: str, events: list[dict]) -> dict:
    """The dwell counter for this theatre stay, kept on the sim bag. A new stay starts a fresh counter."""
    last = next((e for e in reversed(events) if e["event_type"] == "patient.state"), None)
    stay = last["id"] if last else None
    bag = store.sim_state(episode_id)
    held = bag.get(DWELL_BAG)
    if not held or held["stay"] != stay:
        held = bag[DWELL_BAG] = {"stay": stay, "state": fresh_state()}
    return held["state"]


def dwell_frame(store, episode_id: str, events: list[dict], frame: dict, ts: int) -> list[dict]:
    """One camera frame through the dwell counter. A swab counted back is written as `camera.item_out`."""
    state = dwell_state(store, episode_id, events)
    written = []
    for out in observe(state, frame):
        payload = {**out["payload"], "source": "camera", "t_ms": out["ts_ms"], "by": CAMERA_BY}
        written.append(store.append(episode_id, "camera.item_out", payload, ts_ms=ts))
    return written


def returned(events: list[dict]) -> list[str]:
    """Swabs the dwell counter saw back this stay, in the order seen."""
    return [e["payload"]["track_id"] for e in states.stay_events(events) if e["event_type"] == "camera.item_out"]


def latest_closed(events: list[dict], *, stay_only: bool = True) -> dict | None:
    pool = states.stay_events(events) if stay_only else events
    rows = [e for e in pool if e["event_type"] == "camera.closed"]
    return rows[-1] if rows else None


def closed_view(episode_id: str, event: dict | None) -> dict | None:
    if event is None:
        return None
    p = event["payload"]
    return {"text": p["text"], "source": p["source"], "by": p["closed_by"], "case_id": p["case_id"],
            "count_sheet_url": f"/journey/episodes/{episode_id}/camera/count-sheet.pdf"}


def view(episode_id: str, events: list[dict]) -> dict:
    """The extras on the care view of the camera."""
    replay = states.stay_latest(events, "camera.replayed")
    return {
        "replay": {k: replay["payload"][k] for k in ("source", "opened", "returned", "missing")} if replay else None,
        "dwell": {"returned": len(returned(events))},
        "closed": closed_view(episode_id, latest_closed(events)),
    }
