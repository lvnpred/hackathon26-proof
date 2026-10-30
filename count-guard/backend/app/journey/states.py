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


def journey_path(events: list[dict]) -> list[str]:
    """Every state the patient has been in, in order, starting at clinic."""
    return ["clinic"] + [e["payload"]["to"] for e in events if e["event_type"] == "patient.state"]


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


YOU_DID = {
    "admitting": "admitted you",
    "clinic_done": "closed your visit",
    "ward": "moved you to the ward",
    "theatre": "sent you to theatre",
    "discharging": "signed your discharge",
    "home": "completed your discharge",
}


def _latest_happening(events: list[dict], you: bool = False) -> str | None:
    """The most recent of: order signed, order acknowledged, task began or done, state move.

    With `you`, the line is addressed to the patient, with short names and the dose that was given."""
    rows = visible_events(events)
    made = {e["id"]: e["payload"] for e in rows if e["event_type"] == "task.created"}
    best = None
    for index, e in enumerate(rows):
        p, kind, at = e["payload"], e["event_type"], clock(e["ts_ms"])
        who = short_name(p.get("by")) if you else p.get("by")
        if kind == "patient.state":
            if p.get("from") is None:  # any real event at the same time wins
                text = "You were admitted to the ward the day before." if you else f"{p['by']} admitted the patient to the ward the day before."
                rank = -1
            else:
                text = f"{who} {YOU_DID[p['to']]} at {at}." if you else f"{p['by']} {DID[p['to']]} at {at}."
                rank = 0
        elif kind == "order.signed":
            text, rank = (f"{who} signed new orders for you at {at}." if you else f"{who} signed new orders at {at}."), 0
        elif kind == "order.acknowledged":
            text, rank = (f"{who} acknowledged your orders at {at}." if you else f"{who} acknowledged the orders at {at}."), 0
        elif kind in ("task.began", "task.done"):
            task = made.get(p["task_id"], {})
            title = task.get("title", "a task")
            if you and kind == "task.done" and task.get("kind") == "dose":
                given = " ".join(part for part in (task.get("name") or title, task.get("amount")) if part)
                text = f"{who} gave {given} at {at}."
            else:
                verb = "began" if kind == "task.began" else "finished"
                text = f"{who} {verb} {title} at {at}."
            rank = 0
        elif kind == "question.asked" and p["to"] == "doctor":
            text = f"You sent a question to the doctor at {at}." if you else f"{short_name(p['by'])} sent a question to the doctor at {at}."
            rank = 0
        elif kind == "question.answered" and p.get("source") == "doctor":
            text, rank = (f"{who} answered your question at {at}." if you else f"{who} answered the question at {at}."), 0
        elif kind == "review.requested":
            text = f"You sent a healing photo at {at}." if you else f"{short_name(p['by'])} sent a healing photo at {at}."
            rank = 0
        elif kind == "review.answered":
            text = f"{who} reviewed {'your' if you else 'the'} healing photo at {at}: {p['label']}."
            rank = 0
        else:
            continue
        key = (e["ts_ms"], rank, index)
        if best is None or key >= best[0]:
            best = (key, text)
    return best[1] if best else None


NEXT_YOU = {
    "clinic": "The doctor admits you or closes the visit.",
    "clinic_done": "Your visit is closed. No further steps.",
    "admitting": "The nurse completes your admission.",
    "ward": "The doctor sends you to theatre or signs your discharge.",
    "theatre": "The nurse records the surgery and the count, then returns you to the ward.",
    "discharging": "The nurse completes your discharge.",
    "home": "You are home. No further steps.",
}

# The same steps addressed to the person who owns them (the "Next · for you" card).
NEXT_MINE = {
    "clinic": "Admit the patient or close the visit.",
    "clinic_done": NEXT["clinic_done"],
    "admitting": "Complete the admission.",
    "ward": "Send the patient to theatre or sign the discharge.",
    "theatre": "Record the surgery and the count, then return the patient to the ward.",
    "discharging": "Complete the discharge.",
    "home": NEXT["home"],
}


def _next_step(events: list[dict], state: str, you: bool = False, mine: bool = False) -> str:
    """The next step in staff words; `you` addresses the patient, `mine` the step's owner."""
    from app.journey.tasks import orders_list  # tasks imports this module

    next_ = (NEXT_YOU if you else NEXT_MINE if mine else NEXT)[state]
    own = "your" if you else "the"

    def say(subject: str, verb: str, rest: str) -> str:
        """`Nurse acknowledges the ...`, or for the owner `Acknowledge the ...`."""
        return f"{verb.capitalize()} {rest}" if mine else f"{subject} {verb}s {rest}"

    nurse = "The nurse" if you else "Nurse"
    fresh = [o for o in orders_list(events) if not o["acknowledged_by"]]
    if fresh and state in ("ward", "admitting"):
        ack = say(nurse, "acknowledge", f"the new orders from {fresh[-1]['by']}.")
        then = f"complete {own} admission" if mine else f"completes {own} admission"
        next_ = ack if state == "ward" else f"{ack[:-1]}, then {then}."
    if state == "theatre" and surgery_status(events) == "none":
        tray = tray_state(events)
        if tray["planned"] and not tray["latest"]:
            then = "record" if mine else "records"
            next_ = f"{say(nurse, 'check', 'the tray by video')}, then {then} the surgery and the count."
    if state in PHOTO_STATES:
        waiting = open_for_doctor(events)
        if waiting["reviews"]:
            next_ = say("The doctor", "review", f"{own} healing photo.")
        elif waiting["questions"]:
            next_ = say("The doctor", "answer", f"{own} question.")
    return next_


NEXT_ROLE = {
    "clinic": "doctor",
    "clinic_done": None,
    "admitting": "nurse",
    "ward": "doctor",
    "theatre": "nurse",
    "discharging": "nurse",
    "home": None,
}


def next_role(events: list[dict], state: str) -> str | None:
    """Who owns the next step. Same branches, same order as `_next_step`, so the two cannot drift."""
    from app.journey.tasks import orders_list  # tasks imports this module

    role = NEXT_ROLE[state]
    if state in ("ward", "admitting") and any(not o["acknowledged_by"] for o in orders_list(events)):
        role = "nurse"
    if state == "theatre" and surgery_status(events) == "none":
        tray = tray_state(events)
        if tray["planned"] and not tray["latest"]:
            role = "nurse"
    if state in PHOTO_STATES:
        waiting = open_for_doctor(events)
        if waiting["reviews"] or waiting["questions"]:
            role = "doctor"
    return role


def stay_events(events: list[dict]) -> list[dict]:
    """The visible events since the patient last changed state: this stay."""
    last = _last_state_event(events)
    return visible_events(events[events.index(last) + 1 :] if last else events)


def stay_latest(events: list[dict], kind: str) -> dict | None:
    return _latest(stay_events(events), kind)


def theatre_count(events: list[dict]) -> dict:
    """This theatre stay's swab count: the latest pack opened, the closing that still stands and the camera count."""
    stay = stay_events(events)
    opened, closing = _latest(stay, "count.pack_opened"), _latest(stay, "count.closing")
    camera = _latest(stay, "swabs.counted")
    newer = camera is not None and camera["payload"].get("count") is not None and (
        closing is None or stay.index(camera) > stay.index(closing))
    return {
        "opened": opened["payload"]["quantity"] if opened else None,
        "opened_by": opened["payload"].get("by") if opened else None,
        "opened_at_ms": opened["ts_ms"] if opened else None,
        "returned": closing["payload"]["returned"] if closing else None,
        "missing": closing["payload"]["unaccounted"] if closing else None,
        "read": closing["payload"].get("read") if closing else None,
        "saved": closing["payload"].get("saved") if closing else None,
        "closed_by": closing["payload"].get("by") if closing else None,
        "camera": {"count": camera["payload"]["count"], "evidence_id": camera["payload"].get("evidence_id"),
                   "at_ms": camera["ts_ms"]} if newer else None,
    }


def now_next(events: list[dict]) -> dict:
    state = current_state(events)
    now = _latest_happening(events) or "The patient is in clinic."
    you_now = _latest_happening(events, you=True) or "You are in clinic."
    return {
        "now": now,
        "next": _next_step(events, state),
        "next_mine": _next_step(events, state, mine=True),
        "next_role": next_role(events, state),
        "you_now": you_now,
        "you_next": _next_step(events, state, you=True),
    }


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
        "visited": journey_path(events),
        "count": theatre_count(events),
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
