"""Patient states: where the patient is, which moves are allowed, and what the ledger says now and next.

A state is never stored on its own. It is read from the latest `patient.state` event, so the
ledger stays the single source of truth. A move that the table does not allow is refused with a
plain reason before anything is written.
"""

from __future__ import annotations

from app.journey.nudges import count_and_patient
from app.journey.stories import clock
from app.morning.discharge import visible_events

STATES = ("clinic", "clinic_done", "admitting", "ward", "theatre", "discharging", "home")
PROCEDURES = {"hernia-repair": "Open inguinal hernia repair"}

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
        elif current_state(events) == "theatre":
            needs = ["surgery ended"] + (["reason (count open)"] if count_open(events) else [])
        out.append({"to": to, "label": label, "role": role, "needs": needs})
    return out


def now_next(events: list[dict]) -> dict:
    last = _last_state_event(events)
    state = current_state(events)
    if last is None:
        now = "The patient is in clinic."
    else:
        p = last["payload"]
        now = f"{p['by']} {DID[state]} at {clock(last['ts_ms'])}."
    return {"now": now, "next": NEXT[state]}


def flow_view(events: list[dict]) -> dict:
    procedure = next(
        (e["payload"]["procedure"] for e in reversed(events) if e["event_type"] == "patient.state" and e["payload"].get("procedure")),
        None,
    )
    return {
        "state": current_state(events),
        "now_next": now_next(events),
        "allowed": allowed_moves(events),
        "procedure": {"key": procedure, "title": PROCEDURES[procedure]} if procedure else None,
        "procedures": dict(PROCEDURES),
    }
