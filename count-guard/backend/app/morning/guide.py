"""Plain-language status for one morning. The screen renders this. It does not invent steps."""

from __future__ import annotations

STEPS = (
    {
        "id": "medicines",
        "title": "Read the medicine strips",
        "place": "Before the operation",
        "href": "/opd",
        "does": "Write down each strip the person brought. A known name is grounded. An unknown name stays as read.",
        "marker": "brownbag.med_found",
    },
    {
        "id": "pack",
        "title": "Say what was opened",
        "place": "In the room",
        "href": "/ot",
        "does": "Say a line such as \"opening twenty swabs\". That sets the number to count back.",
        "marker": "count.pack_opened",
    },
    {
        "id": "count",
        "title": "Count what came back",
        "place": "In the room",
        "href": "/ot",
        "does": "Replay the tray, or add one by hand. A swab counts as back only after it stays in the bucket.",
        "marker": "count.closing",
    },
    {
        "id": "drugs",
        "title": "Record what was given",
        "place": "In the room",
        "href": "/ot",
        "does": "Hear a drug line, then confirm it. Nothing is on the sheet until you confirm.",
        "marker": "druglog.given",
    },
    {
        "id": "pressure",
        "title": "Record the blood pressure",
        "place": "In the room",
        "href": "/ot",
        "does": "Step through the recorded trace. The numbers are a log. The fact card stays off unless you turn it on.",
        "marker": "vitals.reading",
    },
    {
        "id": "sheet",
        "title": "Write the discharge sheet",
        "place": "After the room",
        "href": "/ward",
        "does": "The sheet lists only what was recorded. It does not say what to do next medically.",
        "marker": "discharge.drafted",
    },
)


def explain_event(event: dict) -> str:
    kind = event["event_type"]
    payload = event.get("payload") or {}
    if kind == "brownbag.med_found":
        name = payload.get("generic") or payload.get("name_as_read") or "a strip"
        strength = payload.get("strength") or ""
        how = payload.get("drug_class") if payload.get("grounded") else "as read"
        return f"Strip: {name} {strength} ({how}).".replace("  ", " ")
    if kind == "brownbag.same_drug_twice":
        return f"Same drug recorded twice: {payload.get('generic')}."
    if kind == "count.pack_opened":
        return f"Opened {payload.get('quantity')} {payload.get('item_type')}."
    if kind == "count.item_out":
        return f"{payload.get('track_id')} counted back ({payload.get('source') or 'seen'})."
    if kind == "count.closing":
        prefix = "Camera count filed" if payload.get("source") == "camera" else "Closing count"
        return (
            f"{prefix}: opened {payload.get('opened')}, "
            f"back {payload.get('returned')}, unaccounted {payload.get('unaccounted')}."
        )
    if kind == "druglog.parsed":
        name = payload.get("generic") or payload.get("name_as_heard")
        return f"Heard {name}. Not confirmed yet."
    if kind == "druglog.given":
        name = payload.get("generic") or payload.get("name_as_heard")
        return f"Confirmed {name} {payload.get('amount') or ''} {payload.get('unit') or ''} {payload.get('route') or ''}".strip() + "."
    if kind == "drug.given":
        name = payload.get("generic") or payload.get("name_as_heard")
        said = " ".join(str(x) for x in (name, payload.get("strength"), payload.get("amount"), payload.get("unit"),
                                          payload.get("route")) if x)
        return f"{payload.get('by')} confirmed {said} given."
    if kind == "count.pack_heard":
        return f"Heard: {payload.get('text')}. Not counted until a person confirms the pack."
    if kind == "vitals.reading":
        simulated = " (simulated)" if payload.get("source") == "simulated" else ""
        return f"Blood pressure {payload.get('systolic')}/{payload.get('diastolic')}, heart rate {payload.get('hr')}{simulated}."
    if kind == "vitals.card":
        return payload.get("text") or "Fact card."
    if kind == "discharge.drafted":
        return "Discharge sheet written from the timeline."
    if kind == "camera.linked":
        return "Swab camera started for this theatre stay. It advises; the count a person saves decides."
    if kind == "camera.ran":
        return "Swab camera read the clip" + (" · Prepared." if payload.get("source") == "prepared" else ".")
    if kind == "camera.advice":
        return f"Camera advice: {payload.get('text')}"
    if kind == "camera.ack":
        reason = (payload.get("reason") or "").strip()
        return f"{payload.get('by')} acknowledged the camera advice." + (f" Reason: {reason}" if reason else "")
    return kind.replace(".", " ").replace("_", " ")


PATIENT_RULE = (
    "These six steps are for this patient only. "
    "The next patient starts a new morning. Records are not mixed."
)


def build_guide(events: list[dict], patient: str = "This patient") -> dict:
    seen = {event["event_type"] for event in events}
    steps = []
    current_set = False
    done_count = 0
    for spec in STEPS:
        done = spec["marker"] in seen
        current = not done and not current_set
        if current:
            current_set = True
        if done:
            done_count += 1
        steps.append(
            {
                "id": spec["id"],
                "title": spec["title"],
                "place": spec["place"],
                "href": spec["href"],
                "does": spec["does"],
                "done": done,
                "current": current,
            }
        )
    current = next((step for step in steps if step["current"]), None)
    if current is None:
        summary = f"Every step for {patient} is recorded. Open the discharge sheet to read it back."
        nxt = steps[-1]["href"]
    else:
        summary = f"For {patient}: {current['does']}"
        nxt = current["href"]
    return {
        "patient": patient,
        "rule": PATIENT_RULE,
        "summary": summary,
        "next_href": nxt,
        "done": done_count,
        "total": len(steps),
        "steps": steps,
        "lines": [explain_event(event) for event in events],
    }
