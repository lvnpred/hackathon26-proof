"""The Ask section as a pure view of the ledger: questions, the doctor's answers, and healing-photo reviews.

Imports nothing from `app.journey`, so `states` and `stories` can both import it.
"""

from __future__ import annotations

DECISIONS = {"no_visit": "No visit needed", "come_in": "Come in to the clinic", "call": "The doctor will call you"}
PHOTO_STATES = ("clinic_done", "home")


def short_name(label: str | None) -> str:
    """'R. Kumar, 58 M (synthetic)' -> 'R. Kumar'; 'Dr. A. Rao (synthetic)' -> 'Dr. A. Rao'."""
    return (label or "").split(",")[0].replace(" (synthetic)", "").strip()


def _answer(p: dict, ts_ms: int) -> dict:
    return {
        "text": p.get("answer", ""),
        "by": p.get("by"),
        "at_ms": ts_ms,
        "via": p.get("via", ""),
        "heard_by": p.get("heard_by", ""),
        "sources": p.get("sources") or [],
        "found": bool(p.get("found")),
        "source": p.get("source", ""),
    }


def ask_view(events: list[dict]) -> dict:
    """Questions and reviews, oldest first, each with its first answer. Medicine photos and check-ins too."""
    answers, decisions = {}, {}
    for e in events:
        p = e["payload"]
        if e["event_type"] == "question.answered":
            answers.setdefault(p["question_id"], e)
        elif e["event_type"] == "review.answered":
            decisions.setdefault(p["review_id"], e)
    seen: dict[str, list[dict]] = {}
    for e in events:
        if e["event_type"] == "checkin.seen":
            by_list = seen.setdefault(e["payload"]["checkin_id"], [])
            if all(row["by"] != e["payload"]["by"] for row in by_list):
                by_list.append({"by": e["payload"]["by"], "at_ms": e["ts_ms"]})
    questions, reviews, medicines, checkins = [], [], [], []
    for e in events:
        p = e["payload"]
        if e["event_type"] == "question.asked":
            found = answers.get(e["id"])
            questions.append(
                {
                    "id": e["id"], "to": p["to"], "text": p["text"], "by": p["by"], "at_ms": e["ts_ms"],
                    "answer": _answer(found["payload"], found["ts_ms"]) if found else None,
                }
            )
        elif e["event_type"] == "review.requested":
            found = decisions.get(e["id"])
            reviews.append(
                {
                    "id": e["id"],
                    "photo": {"id": p["photo_id"], "url": f"/journey/episodes/{e['episode_id']}/photos/{p['photo_id']}"},
                    "note": p.get("note", ""), "by": p["by"], "at_ms": e["ts_ms"],
                    "answer": (
                        {
                            "decision": found["payload"]["decision"], "label": found["payload"]["label"],
                            "note": found["payload"].get("note", ""), "by": found["payload"]["by"], "at_ms": found["ts_ms"],
                        }
                        if found else None
                    ),
                }
            )
        elif e["event_type"] == "medicines.read":
            medicines.append(
                {
                    "id": e["id"],
                    "photo": {"id": p["photo_id"], "url": f"/journey/episodes/{e['episode_id']}/photos/{p['photo_id']}"},
                    "rows": p["rows"], "match": p["match"], "why": p["why"], "source": p["source"], "at_ms": e["ts_ms"],
                }
            )
        elif e["event_type"] == "checkin.recorded":
            checkins.append(
                {
                    "id": e["id"], "at_ms": e["ts_ms"], "day": p["day"], "feels": p["feels"],
                    "signs": p.get("signs") or [], "note": p.get("note", ""), "seen": seen.get(e["id"], []),
                }
            )
    return {"questions": questions, "reviews": reviews, "medicines": medicines, "checkins": checkins}


def open_for_doctor(events: list[dict]) -> dict:
    """How many questions to the doctor and healing photos still wait for the doctor."""
    view = ask_view(events)
    return {
        "questions": sum(q["to"] == "doctor" and q["answer"] is None for q in view["questions"]),
        "reviews": sum(r["answer"] is None for r in view["reviews"]),
    }
