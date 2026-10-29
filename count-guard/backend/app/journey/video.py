"""Planned vs seen for a video clip. Pure: no I/O, no model call."""

from __future__ import annotations

from app.journey.procedures import SETUP_TEMPLATES

NOT_CHECKED = "The clip was not checked: no model key and no prepared result for this clip."
NO_ANSWER = "The clip was not checked: the video model did not answer."
UNREADABLE = "The clip could not be read."
NO_FRAMES = " No frames could be cut from the clip."
OK_WHY = "Every planned item was seen in the clip."
MAX_FRAMES = 6


def _group(items: list[dict]) -> list[dict]:
    """Rows by concept in first-seen order. Items with no concept are left out."""
    rows: dict[str, dict] = {}
    for item in items:
        concept = item.get("concept")
        if concept is None:
            continue
        row = rows.setdefault(concept, {"concept": concept, "names": [], "planned": 0})
        row["names"].append(item["name"])
        row["planned"] += item["qty"]
    return list(rows.values())


def expected_for_tray(plan: dict) -> list[dict]:
    return _group(plan["instruments"])


def unchecked_for_tray(plan: dict) -> list[str]:
    return [i["name"] for i in plan["instruments"] if i.get("concept") is None]


def expected_for_setup(key: str) -> list[dict]:
    return _group(SETUP_TEMPLATES[key]["items"])


def summarize(records: list[dict], fps: int, min_score: float, concepts: list[str]) -> dict[str, dict]:
    """Per concept: the most distinct ids in one frame, so an id switch does not double count."""
    frames: dict[str, dict[int, set]] = {c: {} for c in concepts}
    for record in records:
        label = record.get("label")
        score = record.get("score")
        if label not in frames or (score is not None and score < min_score):
            continue
        frames[label].setdefault(int(record["frame_index"]), set()).add(record["object_id"])
    out: dict[str, dict] = {}
    for concept in concepts:
        per_frame = frames[concept]
        if not per_frame:
            out[concept] = {"count": 0, "at_s": None}
            continue
        best = max(len(ids) for ids in per_frame.values())
        first = min(f for f, ids in per_frame.items() if len(ids) == best)
        out[concept] = {"count": best, "at_s": round(first / fps, 3)}
    return out


def compare(expected: list[dict], detections: dict | None, source: str = "none") -> dict:
    if detections is None:
        rows = [{**e, "seen": None, "at_s": None} for e in expected]
        why = {"failed": NO_ANSWER, "unreadable": UNREADABLE}.get(source, NOT_CHECKED)
        return {"rows": rows, "missing": [], "match": "none", "why": why}
    rows = []
    for e in expected:
        cell = detections.get(e["concept"]) or {}
        rows.append({**e, "seen": cell.get("count", 0), "at_s": cell.get("at_s")})
    short = [r for r in rows if r["seen"] < r["planned"]]
    if not short:
        return {"rows": rows, "missing": [], "match": "ok", "why": OK_WHY}
    parts = "; ".join(f"{r['concept']} (planned {r['planned']}, seen {r['seen']})" for r in short)
    return {"rows": rows, "missing": [r["concept"] for r in short], "match": "mismatch",
            "why": f"Not seen in the clip: {parts}."}


def frame_times(rows: list[dict]) -> list[float]:
    """Seconds into the clip worth keeping as proof frames. Empty when nothing was checked."""
    if rows and all(r["seen"] is None for r in rows):
        return []
    times = sorted({r["at_s"] for r in rows if r["seen"] and r["at_s"] is not None})
    return times[:MAX_FRAMES] if times else [0.0]


def _frames(episode_id: str, ids: list[str]) -> list[dict]:
    return [{"id": i, "url": f"/journey/episodes/{episode_id}/photos/{i}"} for i in ids]


def checks_view(events: list[dict]) -> list[dict]:
    """Every tray and set-up check, oldest first, with its kept frames."""
    out = []
    for e in events:
        if e["event_type"] not in ("tray.checked", "setup.checked"):
            continue
        p = e["payload"]
        out.append(
            {
                "id": e["id"],
                "check": e["event_type"].split(".")[0],
                "task_id": p.get("task_id"),
                "at_ms": e["ts_ms"],
                "by": p["by"],
                "media": p.get("media", "video"),
                **{k: p[k] for k in ("rows", "missing", "match", "why", "source")},
                "unchecked": p.get("unchecked", []),
                "frames": _frames(e["episode_id"], p["frame_ids"]),
            }
        )
    return out


def tray_state(events: list[dict]) -> dict:
    """The latest tray plan, and the latest tray check written after it."""
    planned = next((i for i in range(len(events) - 1, -1, -1) if events[i]["event_type"] == "tray.planned"), None)
    if planned is None:
        return {"planned": None, "latest": None}
    checks = checks_view(events[planned + 1 :])
    latest = [c for c in checks if c["check"] == "tray"]
    return {"planned": events[planned]["payload"], "latest": latest[-1] if latest else None}
