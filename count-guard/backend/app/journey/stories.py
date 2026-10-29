"""Three stories on one timeline: the doctor's, the nurse's and the patient's. Plus the audit trail."""

from __future__ import annotations

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
            "Vomiting that does not stop",
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


def plain(event: dict) -> str:
    kind = event["event_type"]
    p = event.get("payload") or {}
    if kind == "rx.ordered":
        return f"Prescription from {p.get('by')}: {len(p.get('rows') or [])} medicines ({p.get('source')})."
    if kind == "ward.orders_set":
        return f"Ward orders from {p.get('by')}: {len(p.get('doses') or [])} doses, observations every {p.get('obs_every_h') or 0:g} h."
    if kind == "dose.given":
        return f"{p.get('by')} logged {p.get('name')} {p.get('amount') or ''}.".replace(" .", ".")
    if kind == "obs.recorded":
        return f"{p.get('by')} logged BP {p.get('sbp')}/{p.get('dbp')}, HR {p.get('hr')}, SpO2 {p.get('spo2')}, T {p.get('temp')}."
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
            return f"{p.get('by')} admitted the patient to the {p.get('to')}.{said}"
        return f"{p.get('by')} moved the patient from {p.get('from')} to {p.get('to')}.{said}"
    if kind == "order.signed":
        return f"{p.get('by')} signed {len(p.get('items') or [])} orders."
    if kind == "order.acknowledged":
        return f"{p.get('by')} acknowledged the orders."
    if kind == "task.created":
        return f"Task added: {p.get('title')}."
    if kind == "task.began":
        return f"{p.get('by')} began a task."
    if kind == "task.done":
        return f"{p.get('by')} finished a task."
    if kind == "discharge.signed":
        return f"{p.get('by')} signed the discharge."
    if kind in ("surgery.began", "surgery.ended"):
        return f"{p.get('by')} recorded that surgery {kind.split('.')[1]}."
    return explain_event(event)


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
