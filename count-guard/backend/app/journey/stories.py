"""Three stories on one timeline: the doctor's, the nurse's and the patient's. Plus the audit trail."""

from __future__ import annotations

from app.journey.ask import short_name
from app.morning.guide import explain_event

DAY_MS = 24 * 3_600_000
START_MINUTES = 9 * 60  # ts_ms 0 is Day 0, 09:00

STORIES = (
    {
        "id": "doctor",
        "who": "Doctor",
        "title": "Prescribes, orders and signs",
        "steps": (
            ("rx", "Prescribe in Doctor Dictation", "rx.ordered", "/doctor"),
            ("orders", "Set ward orders and limits", "ward.orders_set", "/doctor"),
            ("theatre", "Confirm drugs in theatre", "druglog.given", "/ot"),
            ("discharge", "Sign the discharge card", "discharge.card", "/doctor"),
        ),
    },
    {
        "id": "nurse",
        "who": "Nurse",
        "title": "Counts, gives and watches",
        "steps": (
            ("count", "Close the swab count", "count.closing", "/ot"),
            ("doses", "Log each dose given", "dose.given", "/nurse"),
            ("obs", "Log observations", "obs.recorded", "/nurse"),
            ("nudges", "Answer the nudges", "nudge.seen", "/nurse"),
            ("handover", "Hand over the shift", "handover.accepted", "/nurse"),
        ),
    },
    {
        "id": "patient",
        "who": "Patient",
        "title": "Scans, follows and checks in",
        "steps": (
            ("strips", "Scan my medicine strips", "brownbag.med_found", "/patient"),
            ("reminders", "Add dose reminders", "reminders.added", "/patient"),
            ("card", "Read my discharge card", "discharge.card", "/patient"),
            ("checkin", "Check in from home", "checkin.recorded", "/patient"),
        ),
    },
)

# Written by the clinic, chosen by the doctor. Not generated. Synthetic demo text.
CARE_TEMPLATES = {
    "hernia-repair": {
        "title": "Day-care hernia repair (clinic template, synthetic)",
        "warning_signs": [
            "Fever above 38 °C",
            "Wound red, swollen or leaking",
            "Pain not eased by the prescribed medicine",
            "Cannot pass urine",
            "Vomiting that keeps going",
        ],
        "wound_care": "Keep the dressing dry for 48 hours.",
        "help_line": "Ward 4 nurses' desk, 044 0000 0000 (synthetic)",
        "review": "Wound check in the surgical clinic on day 7 (synthetic)",
    }
}


def clock(ts_ms: int) -> str:
    day, rest = divmod(int(ts_ms), DAY_MS)
    minutes = START_MINUTES + rest // 60_000
    day += minutes // (24 * 60)
    minutes %= 24 * 60
    return f"Day {day} {minutes // 60:02d}:{minutes % 60:02d}"


# Plain words for the patient states. Local on purpose: states.py imports this module.
STATE_WORDS = {
    "clinic": "the clinic", "clinic_done": "the end of the clinic visit", "admitting": "admission",
    "ward": "the ward", "theatre": "theatre", "discharging": "discharge", "home": "home",
}


def count_of(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def plain(event: dict) -> str:
    kind = event["event_type"]
    p = event.get("payload") or {}
    if kind == "rx.ordered":
        return f"Prescription from {p.get('by')}: {count_of(len(p.get('rows') or []), 'medicine')} ({p.get('source')})."
    if kind == "ward.orders_set":
        return f"Ward orders from {p.get('by')}: {count_of(len(p.get('doses') or []), 'dose')}, observations every {p.get('obs_every_h') or 0:g} h."
    if kind == "dose.given":
        return f"{p.get('by')} logged {p.get('name')} {p.get('amount') or ''}.".replace(" .", ".")
    if kind == "obs.recorded":
        bp = f"BP {p.get('sbp')}/{p.get('dbp')}" if p.get("sbp") is not None and p.get("dbp") is not None else None
        parts = [bp] + [f"{label} {p.get(key)}" for label, key in (("HR", "hr"), ("SpO2", "spo2"), ("T", "temp")) if p.get(key) is not None]
        return f"{p.get('by')} logged {', '.join(x for x in parts if x)}."
    if kind == "nudge.raised":
        return f"Nudge to {p.get('to')}: {p.get('says')}"
    if kind == "nudge.seen":
        return f"{p.get('by')} answered a nudge: {(p.get('note') or 'seen').rstrip('.')}."
    if kind == "handover.drafted":
        return f"Handover drafted by {p.get('from')} for {p.get('to')} ({p.get('wording')}, {len(p.get('lines') or [])} lines)."
    if kind == "handover.accepted":
        return f"{p.get('by')} accepted the handover."
    if kind == "reminders.added":
        return f"Dose reminders added for {p.get('count')} medicines."
    if kind == "discharge.card":
        return f"Discharge card signed by {p.get('by')}."
    if kind == "help.requested":
        return f"Patient pressed Need help: {p.get('says')}"
    if kind == "checkin.recorded":
        signs = ", ".join(p.get("signs") or []) or "no listed signs"
        return f"Day {p.get('day')} check-in: {p.get('feels')}; {signs}."
    if kind == "patient.state":
        said = f" Reason: {p.get('reason')}" if p.get("reason") else ""
        if p.get("from") is None:
            return f"{p.get('by')} admitted the patient to {STATE_WORDS.get(p.get('to'), p.get('to'))}.{said}"
        return f"{p.get('by')} moved the patient from {STATE_WORDS.get(p.get('from'), p.get('from'))} to {STATE_WORDS.get(p.get('to'), p.get('to'))}.{said}"
    if kind == "order.signed":
        return f"{p.get('by')} signed {count_of(len(p.get('items') or []), 'order')}."
    if kind == "order.drafted":
        return f"{p.get('by')} dictated {count_of(len(p.get('items') or []), 'order')} (draft, not signed)."
    if kind == "discharge.drafted":
        return f"{p.get('by')} dictated a discharge summary (draft, not signed)."
    if kind == "tray.planned":
        n = sum(i["qty"] for i in p["instruments"])
        return f"{p['by']} confirmed the tray plan for {p['title']}: {n} instruments, {p['swab_total']} swabs."
    if kind == "doctor.status":
        doctor = short_name(p.get("doctor"))
        if p.get("source") == "manual":
            said = {"available": "Available", "busy": f"Busy until {clock(p.get('until_ms') or 0)[-5:]}"}
            return f"{doctor} set the status: {said.get(p.get('status'), 'automatic')}."
        return f"{doctor} is in theatre with {p.get('patient')}, free about {clock(p.get('until_ms') or 0)[-5:]}."
    if kind == "medicines.read":
        return f"Medicines photo: {p.get('why')}"
    if kind == "tray.checked":
        return f"Tray check by {'photos' if p.get('media') == 'photos' else 'video'}: {p.get('why')}"
    if kind == "setup.checked":
        return f"Set-up check by {'photos' if p.get('media') == 'photos' else 'video'}: {p.get('why')}"
    if kind == "question.asked":
        if p.get("to") == "bot":
            return f"{short_name(p.get('by'))} asked the record bot a question."
        return f"{short_name(p.get('by'))} sent a question to the doctor."
    if kind == "question.answered":
        if p.get("source") == "doctor":
            return f"{p.get('by')} answered the question{ {'voice': ' (by voice)', 'text': ' (typed)'}.get(p.get('via'), '') }."
        if p.get("found"):
            return f"The record bot answered from {len(p.get('sources') or [])} lines of the record."
        return "The record bot found nothing in the record for this question."
    if kind == "review.requested":
        return f"{short_name(p.get('by'))} sent a healing photo for review."
    if kind == "review.answered":
        return f"{p.get('by')} reviewed the healing photo: {p.get('label')}."
    if kind == "photo.added" and p.get("purpose") == "frame":
        clip = "set-up" if p.get("video") == "setup" else p.get("video")
        if p.get("media") == "photos":
            return f"A photo from the {clip} check was kept as proof."
        return f"A frame from the {clip} clip was kept as proof."
    if kind == "photo.added":
        return f"{p.get('by')} added a {p.get('purpose')} photo."
    if kind == "proof.checked":
        return f"Photo check: {p.get('why')}"
    if kind == "order.acknowledged":
        return f"{p.get('by')} acknowledged the orders."
    if kind == "task.created":
        return f"Task added: {p.get('title')}."
    if kind == "task.began":
        return f"{p.get('by')} began a task."
    if kind == "task.done":
        how = {"voice": " by voice", "text": " (typed)"}.get(p.get("via"))
        if how:
            return f"{p.get('by')} finished a task{how}." + (" Photo flagged." if p.get("match") == "mismatch" else "")
        return f"{p.get('by')} finished a task."
    if kind == "discharge.signed":
        return f"{p.get('by')} signed the discharge."
    if kind in ("surgery.began", "surgery.ended"):
        return f"{p.get('by')} recorded that surgery {kind.split('.')[1]}."
    return explain_event(event)


PATIENT_STATE = {"admitting": "You were admitted.", "theatre": "You went to theatre.", "clinic_done": "Your clinic visit was closed.",
                 "discharging": "You are getting ready to go home.", "home": "You went home."}


STAFF_ONLY = ("order.drafted", "discharge.drafted")


def patient_line(event: dict, tasks: dict[str, dict], signed: bool = False) -> str:
    """The patient's wording of an event; events without one read as `plain`.

    A draft is staff work, and the card line repeats the signed line once the discharge is signed:
    both read "" and the timeline hides an empty line from the patient."""
    kind = event["event_type"]
    p = event.get("payload") or {}
    if kind in STAFF_ONLY or (kind == "discharge.card" and signed):
        return ""
    if kind == "patient.state":
        to, frm = p.get("to"), p.get("from")
        if frm is None:
            return PATIENT_STATE["admitting"]
        if to == "ward" and frm in ("admitting", "theatre"):
            return "You are on the ward." if frm == "admitting" else "You are back on the ward."
        if to in PATIENT_STATE:
            return PATIENT_STATE[to]
    elif kind == "nudge.raised":
        # A note for staff has no patient wording; the timeline hides an empty line from the patient.
        return f"A note for you: {p.get('says')}" if p.get("to") == "patient" else ""
    elif kind == "surgery.began":
        return "Your operation began."
    elif kind == "surgery.ended":
        return "Your operation finished."
    elif kind == "discharge.signed":
        return "The doctor signed your discharge."
    elif kind == "order.signed":
        return f"The doctor signed {count_of(len(p.get('items') or []), 'order')}."
    elif kind == "task.done" and p.get("task_id") in tasks:
        task, who = tasks[p["task_id"]], short_name(p.get("by"))
        if task.get("kind") == "dose":
            return f"{who} gave {(task.get('name') or task.get('title') or '').lower()}."
        if task.get("kind") == "obs":
            return f"{who} checked your observations."
        return f"{who} finished: {task.get('title')}."
    return plain(event)


def timeline_items(events: list[dict]) -> list[dict]:
    tasks = {e["id"]: e.get("payload") or {} for e in events if e["event_type"] == "task.created"}
    signed = any(e["event_type"] == "discharge.signed" for e in events)
    return [{"id": e["id"], "when": clock(e["ts_ms"]), "type": e["event_type"], "plain": plain(e), "patient": patient_line(e, tasks, signed)}
            for e in events]


def build_stories(events: list[dict]) -> list[dict]:
    seen = {event["event_type"] for event in events}
    out = []
    for story in STORIES:
        steps = []
        current_set = False
        for step_id, title, marker, href in story["steps"]:
            done = marker in seen
            current = not done and not current_set
            current_set = current_set or current
            steps.append({"id": step_id, "title": title, "href": href, "done": done, "current": current})
        out.append(
            {
                "id": story["id"],
                "who": story["who"],
                "title": story["title"],
                "done": sum(step["done"] for step in steps),
                "total": len(steps),
                "steps": steps,
            }
        )
    return out


def audit_rows(events: list[dict]) -> list[dict]:
    """Every line as written. A corrected line stays, marked with what replaced it."""
    replaced_by = {e["supersedes_id"]: e["id"] for e in events if e.get("supersedes_id")}
    rows = []
    for event in events:
        p = event.get("payload") or {}
        rows.append(
            {
                "id": event["id"],
                "when": clock(event["ts_ms"]),
                "written_at": event["wall_clock"],
                "who": p.get("by") or p.get("source") or "system",
                "what": plain(event),
                "type": event["event_type"],
                "tier": event["tier"],
                "supersedes": event.get("supersedes_id"),
                "replaced_by": replaced_by.get(event["id"]),
            }
        )
    return rows
