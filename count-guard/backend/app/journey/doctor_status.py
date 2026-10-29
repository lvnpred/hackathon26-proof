"""The doctor's status chip. Pure: read from the ledgers, never stored as a result.

A hand-set Available or Busy (written on the staff board) wins until it expires. Otherwise the status is
read from where the doctor is: in theatre when an episode is in theatre, with "free about" set when the
patient was sent (the template's minutes, rounded up to the next quarter hour).
"""

from __future__ import annotations

from app.journey.ask import short_name
from app.journey.states import current_state
from app.journey.stories import clock

QUARTER = 15 * 60_000


def free_about(ts_ms: int, minutes: int) -> int:
    """ts + minutes, rounded up to the next quarter hour."""
    end = ts_ms + minutes * 60_000
    return -(-end // QUARTER) * QUARTER


def theatre_payload(doctor: str, patient_label: str, ts_ms: int, minutes: int) -> dict:
    return {
        "doctor": doctor,
        "status": "in_theatre",
        "patient": short_name(patient_label),
        "until_ms": free_about(ts_ms, minutes),
        "source": "auto",
    }


def _hhmm(ts_ms: int) -> str:
    return clock(ts_ms)[-5:]


def _status_events(events: list[dict], doctor: str, now_ms: int) -> list[dict]:
    return [
        e for e in events
        if e["event_type"] == "doctor.status" and e["ts_ms"] <= now_ms and e["payload"].get("doctor") == doctor
    ]


def _manual(doctor: str, board: list[dict], now_ms: int) -> dict | None:
    rows = _status_events(board, doctor, now_ms)
    if not rows:
        return None
    last = max(enumerate(rows), key=lambda pair: (pair[1]["ts_ms"], pair[0]))[1]["payload"]
    until = last.get("until_ms")
    if last.get("status") in ("available", "busy") and until is not None and now_ms < until:
        return last
    return None


def _auto(doctor: str, episodes: list[list[dict]], now_ms: int) -> dict | None:
    best = None
    for events in episodes:
        seen = [e for e in events if e["ts_ms"] <= now_ms]
        if current_state(seen) != "theatre":
            continue
        moved = max(i for i, e in enumerate(seen) if e["event_type"] == "patient.state")
        rows = _status_events(seen[moved:], doctor, now_ms)
        rows = [e for e in rows if e["payload"].get("source") == "auto" and e["payload"].get("status") == "in_theatre"]
        if rows and (best is None or rows[-1]["ts_ms"] >= best["ts_ms"]):
            best = rows[-1]
    return best["payload"] if best else None


def current(doctor: str, episodes: list[list[dict]], board: list[dict], now_ms: int) -> dict:
    name = short_name(doctor)
    manual = _manual(doctor, board, now_ms)
    if manual:
        status, until = manual["status"], manual["until_ms"]
        text = f"{name}: Busy until {_hhmm(until)}" if status == "busy" else f"{name}: Available"
        return {"doctor": doctor, "status": status, "text": text, "until_ms": until, "source": "manual", "patient": None}
    auto = _auto(doctor, episodes, now_ms)
    if auto:
        text = f"{name}: In theatre with {auto['patient']}, free about {_hhmm(auto['until_ms'])}"
        return {"doctor": doctor, "status": "in_theatre", "text": text, "until_ms": auto["until_ms"],
                "source": "auto", "patient": auto["patient"]}
    return {"doctor": doctor, "status": "available", "text": f"{name}: Available", "until_ms": None,
            "source": "auto", "patient": None}
