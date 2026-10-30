"""Patient states: where the patient is, which moves are allowed, and what the ledger says now and next.

A state is never stored on its own. It is read from the latest `patient.state` event, so the
ledger stays the single source of truth. A move that the table does not allow is refused with a
plain reason before anything is written.
"""

from __future__ import annotations

from app.journey.ask import PHOTO_STATES, ask_view, open_for_doctor, short_name
from app.journey.dictation import open_drafts
from app.journey.nudges import count_and_patient, in_theatre
from app.journey.procedures import PROCEDURE_TEMPLATES, tray_plan
from app.journey.stories import clock
from app.journey.video import checks_view, tray_state
from app.morning.discharge import visible_events

STATES = ("clinic", "clinic_done", "admitting", "ward", "theatre", "discharging", "home")
PROCEDURES = {k: t["title"] for k, t in PROCEDURE_TEMPLATES.items()}

ADMISSION_CHECKS = ("band", "allergies", "baseline_obs", "consent")
DISCHARGE_CHECKS = ("card_given", "medicines_handed", "reminders_set")

# from -> to -> (label, role, checklist keys needed)
MOVES = {
    "clinic": {
        "admitting": ("Admit", "doctor", ()),
        "clinic_done": ("Close visit", "doctor", ()),
    },
    "admitting": {"ward": ("Complete admission", "nurse", ADMISSION_CHECKS)},
    "ward": {
        "theatre": ("Send to theatre", "doctor", ()),
        "discharging": ("Sign discharge", "doctor", ()),
    },
    "theatre": {"ward": ("Back to ward", "nurse", ())},
    "discharging": {"home": ("Complete discharge", "nurse", DISCHARGE_CHECKS)},
}

NEXT = {
    "clinic": "Doctor admits the patient or closes the visit.",
    "clinic_done": "The visit is closed. No further steps.",
    "admitting": "Nurse completes the admission.",
    "ward": "Doctor sends the patient to theatre or signs the discharge.",
    "theatre": "Nurse records the surgery and the count, then returns the patient to the ward.",
    "discharging": "Nurse completes the discharge.",
    "home": "The patient is home. No further steps.",
}
DID = {
    "admitting": "admitted the patient",
    "clinic_done": "closed the visit",
    "ward": "moved the patient to the ward",
    "theatre": "sent the patient to theatre",
    "discharging": "signed the discharge",
    "home": "completed the discharge",
}
CHECK_WORDS = {
    "band": "wristband",
    "allergies": "allergies",
    "baseline_obs": "baseline observations",
    "consent": "consent",
    "card_given": "discharge card",
    "medicines_handed": "medicines handed over",
    "reminders_set": "dose reminders",
}


def _latest(events: list[dict], kind: str) -> dict | None:
    rows = [event for event in events if event["event_type"] == kind]
    return rows[-1] if rows else None


def _last_state_event(events: list[dict]) -> dict | None:
    return _latest(events, "patient.state")


def current_state(events: list[dict]) -> str:
    last = _last_state_event(events)
    return last["payload"]["to"] if last else "clinic"


def count_open(events: list[dict]) -> bool:
    """True when the latest closing count that still stands has swabs unaccounted for.

    This is the v1 nudge rule, read from `count_and_patient` so the two cannot drift apart.
    """
    return any(n["kind"] == "count_open" for n in count_and_patient(visible_events(events)))


def surgery_status(events: list[dict]) -> str:
    """'none', 'began' or 'ended' for the current stay in theatre."""
    last = _last_state_event(events)
    since = events.index(last) + 1 if last else 0
    kinds = [e["event_type"] for e in events[since:] if e["event_type"].startswith("surgery.")]
    if "surgery.ended" in kinds:
        return "ended"
    return "began" if "surgery.began" in kinds else "none"


def _missing(checklist: dict, keys: tuple[str, ...]) -> list[str]:
    return [key for key in keys if checklist.get(key) is not True]


def check_move(events: list[dict], to: str, body: dict) -> str | None:
    """None when the move is allowed, else the plain reason for a 409."""
    state = current_state(events)
    if to not in MOVES.get(state, {}):
        return f"The patient is in {state}. A move to {to} is not allowed from here."
    _, _, keys = MOVES[state][to]
    if keys:
        missing = _missing(body.get("checklist") or {}, keys)
        if missing:
            return "Still to tick: " + ", ".join(CHECK_WORDS[k] for k in missing) + "."
    reason = (body.get("reason") or "").strip()
    if state == "clinic" and to == "admitting" and not reason:
        return "A reason for the admission is needed."
    if state == "ward" and to == "theatre" and body.get("procedure") not in PROCEDURES:
        return "Choose the procedure before sending the patient to theatre."
    if state == "ward" and to == "discharging" and _latest(events, "discharge.signed") is None:
        return "The discharge is not signed yet."
    if state == "theatre":
        if surgery_status(events) != "ended":
            return "Surgery has not ended. Record the end of surgery first."
        if count_open(events) and not reason:
            return "The closing count is open. A reason is needed to move the patient back to the ward."
    return None


class MoveRefused(Exception):
    """A move the table does not allow. The message is the plain reason."""


def move_payload(events: list[dict], to: str, body: dict) -> dict:
    """The `patient.state` payload for a move, or `MoveRefused` with the reason. The one place a move is built."""
    refusal = check_move(events, to, body)
    if refusal:
        raise MoveRefused(refusal)
    payload = {"from": current_state(events), "to": to, "by": body["by"], "reason": (body.get("reason") or "").strip()}
    if body.get("procedure"):
        payload["procedure"] = body["procedure"]
    if body.get("checklist"):
        payload["checklist"] = body["checklist"]
    return payload


def allowed_moves(events: list[dict]) -> list[dict]:
    out = []
    for to, (label, role, keys) in MOVES.get(current_state(events), {}).items():
        if to == "discharging":
            continue  # only the signed discharge moves the patient here
        needs = [CHECK_WORDS[k] for k in keys]
        if to == "admitting":
            needs = ["reason"]
        elif to == "theatre":
            needs = ["procedure"]
        elif in_theatre(events):
            open_count = count_open(events)
            needs = ["surgery ended"] if surgery_status(events) != "ended" else []
            if open_count:
                needs.append("reason (count open)")
                role = "doctor"  # the surgeon records why the patient leaves with the count open (D14)
        out.append({"to": to, "label": label, "role": role, "needs": needs})
    return out


def _latest_happening(events: list[dict]) -> str | None:
    """The most recent of: order signed, order acknowledged, task began or done, state move."""
    rows = visible_events(events)
    titles = {e["id"]: e["payload"]["title"] for e in rows if e["event_type"] == "task.created"}
    best = None
    for index, e in enumerate(rows):
        p, kind = e["payload"], e["event_type"]
        if kind == "patient.state":
            if p.get("from") is None:
                text, rank = f"{p['by']} admitted the patient to the ward the day before.", 1
            else:
                text, rank = f"{p['by']} {DID[p['to']]} at {clock(e['ts_ms'])}.", 0
        elif kind == "order.signed":
            text, rank = f"{p['by']} signed new orders at {clock(e['ts_ms'])}.", 0
        elif kind == "order.acknowledged":
            text, rank = f"{p['by']} acknowledged the orders at {clock(e['ts_ms'])}.", 0
        elif kind in ("task.began", "task.done"):
            verb = "began" if kind == "task.began" else "finished"
            title = titles.get(p["task_id"], "a task")
            text, rank = f"{p['by']} {verb} {title} at {clock(e['ts_ms'])}.", 0
        elif kind == "question.asked" and p["to"] == "doctor":
            text, rank = f"{short_name(p['by'])} sent a question to the doctor at {clock(e['ts_ms'])}.", 0
        elif kind == "question.answered" and p.get("source") == "doctor":
            text, rank = f"{p['by']} answered the question at {clock(e['ts_ms'])}.", 0
        elif kind == "review.requested":
            text, rank = f"{short_name(p['by'])} sent a healing photo at {clock(e['ts_ms'])}.", 0
        elif kind == "review.answered":
            text, rank = f"{p['by']} reviewed the healing photo at {clock(e['ts_ms'])}: {p['label']}.", 0
        else:
            continue
        key = (e["ts_ms"], rank, index)
        if best is None or key >= best[0]:
            best = (key, text)
    return best[1] if best else None


def now_next(events: list[dict]) -> dict:
    from app.journey.tasks import orders_list  # tasks imports this module

    state = current_state(events)
    now = _latest_happening(events) or "The patient is in clinic."
    next_ = NEXT[state]
    fresh = [o for o in orders_list(events) if not o["acknowledged_by"]]
    if fresh and state in ("ward", "admitting"):
        ack = f"Nurse acknowledges the new orders from {fresh[-1]['by']}."
        next_ = ack if state == "ward" else f"{ack[:-1]}, then completes the admission."
    if state == "theatre" and surgery_status(events) == "none":
        tray = tray_state(events)
        if tray["planned"] and not tray["latest"]:
            next_ = "Nurse checks the tray by video, then records the surgery and the count."
    if state in PHOTO_STATES:
        waiting = open_for_doctor(events)
        if waiting["reviews"]:
            next_ = "The doctor reviews the healing photo."
        elif waiting["questions"]:
            next_ = "The doctor answers the question."
    return {"now": now, "next": next_}


def flow_view(events: list[dict]) -> dict:
    procedure = next(
        (e["payload"]["procedure"] for e in reversed(events) if e["event_type"] == "patient.state" and e["payload"].get("procedure")),
        None,
    )
    from app.journey.proof import photos_view
    from app.journey.tasks import orders_list, task_list  # tasks imports this module

    return {
        "order_list": orders_list(events),
        "tasks": task_list(events),
        "state": current_state(events),
        "now_next": now_next(events),
        "allowed": allowed_moves(events),
        "procedure": {"key": procedure, "title": PROCEDURES[procedure]} if procedure else None,
        "procedures": dict(PROCEDURES),
        "drafts": open_drafts(events),
        "photos": photos_view(visible_events(events)),
        "tray": tray_state(events),
        "video_checks": checks_view(events),
        "ask": ask_view(events),
        "tray_templates": {key: tray_plan(key) for key in PROCEDURE_TEMPLATES},
    }
