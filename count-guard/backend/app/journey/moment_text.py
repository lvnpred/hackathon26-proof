"""Fixed wording for AI moments (contract C5). Numbers and record fields only, never model text."""

from __future__ import annotations

from app.journey.stories import count_of

TITLE = {
    "orders": "Order dictation", "discharge": "Discharge dictation", "task_voice": "Task by voice",
    "answer_voice": "Doctor's spoken answer", "monitor": "Monitor photo", "dose_strip": "Strip photo",
    "medicines": "Medicines photo", "strips": "Photo of strips", "tray": "Tray check", "setup": "Set-up check",
    "swabs": "Swab camera count", "healing_photo": "Healing photo", "photo": "Photo", "typed_orders": "Orders",
    "record_bot": "Record bot answer", "nudge": "Alert", "handover": "Shift handover",
    "discharge_card": "Discharge card", "day_plan": "Day plan",
}
PHOTO_TITLE = {"reference": "Reference photo", "wound": "Wound photo"}

FILTER = {
    "orders": "voice", "discharge": "voice", "task_voice": "voice", "answer_voice": "voice",
    "monitor": "photos", "dose_strip": "photos", "medicines": "photos", "strips": "photos",
    "tray": "video", "setup": "video", "swabs": "video", "healing_photo": "photos", "photo": "photos",
    "typed_orders": None, "record_bot": "answers", "nudge": "alerts", "handover": None,
    "discharge_card": None, "day_plan": None,
}

KIND = {
    "orders": "voice", "discharge": "voice", "task_voice": "voice", "answer_voice": "voice",
    "monitor": "photo_read", "dose_strip": "photo_read", "medicines": "photo_read", "strips": "photo_read",
    "tray": "visual", "setup": "visual", "swabs": "visual", "healing_photo": "record", "photo": "record",
    "typed_orders": "record", "record_bot": "answer", "nudge": "rule", "handover": "draft",
    "discharge_card": "draft", "day_plan": "draft",
}

# Who owns the moment while it is open or flagged. A nudge uses its own `to`.
OWNER = {
    "orders": "doctor", "discharge": "doctor", "monitor": "nurse", "dose_strip": "nurse", "medicines": "doctor",
    "tray": "doctor", "setup": "nurse", "swabs": "nurse", "healing_photo": "doctor", "handover": "nurse",
}

PATIENT_TEXT = {
    "tray": "The tray was checked by camera before your surgery.",
    "swabs": "The swabs were counted by camera.",
    "setup": "The set-up was checked by camera.",
    "monitor": "Your observations were read from a monitor photo.",
    "dose_strip": "Your dose was checked against a strip photo.",
    "answer_voice": "Dr. Rao answered by voice.",
    "discharge_card": "Your discharge card.",
}

RULE_TEXT = {
    "strip_strength_differs": "The strength read from a strip is compared with the prescription row for the same medicine.",
    "strip_not_prescribed": "Each strip read is looked up in the prescription.",
    "dose_overdue": "An ordered dose is due every set number of hours, with 30 minutes' grace.",
    "dose_logged_early": "A dose logged sooner than its ordered interval, less 30 minutes, is flagged.",
    "dose_not_ordered": "A logged dose is looked up in the ward orders.",
    "obs_past_limit": "Each reading is compared with the limits the doctor set.",
    "obs_overdue": "Observations are due at the ordered interval, with 30 minutes' grace.",
    "count_open": "The closing swab count is compared with the pack opened.",
    "help_requested": "A Need-help press from the patient is always shown.",
    "warning_sign_ticked": "A ticked check-in sign is compared with the discharge list.",
}

NOTHING_SEEN = "Nothing seen in the clip."


def plural_of(concept: str, n: int) -> str:
    return concept if n == 1 or concept.endswith("s") else f"{concept}s"


def words(text: str | None) -> int:
    return len((text or "").split())


def order_text(n: int, w: int) -> str:
    return f"{count_of(n, 'order')} drafted from {count_of(w, 'word')}."


def discharge_text(n: int, w: int) -> str:
    return f"{count_of(n, 'section')} drafted from {count_of(w, 'word')}."


def task_voice_text(w: int) -> str:
    return f"Task recorded by voice from {count_of(w, 'word')}."


def answer_voice_text(w: int) -> str:
    return f"Answer recorded by voice from {count_of(w, 'word')}."


def bot_text(n: int, found: bool, patient: bool = False) -> str:
    if not found:
        return "Not found in your record." if patient else "Not found in the record."
    if patient:
        return f"Answered from {n} {'line' if n == 1 else 'lines'} of your record."
    return f"Answered from {count_of(n, 'record line')}."


def medicines_text(n: int, k: int, f: int) -> str:
    return f"Read {count_of(n, 'strip')}: {k} on the prescription, {f} flagged."


def strips_text(n: int, differ: int, unlisted: int) -> str:
    parts = []
    if differ:
        parts.append(f"{differ} differ{'s' if differ == 1 else ''} from the prescription")
    if unlisted:
        parts.append(f"{unlisted} not on the prescription")
    return f"Read {count_of(n, 'strip')}: {', '.join(parts) or 'all match the prescription'}."


def handover_text(n: int, e: int) -> str:
    return f"Handover of {count_of(n, 'line')} from {count_of(e, 'recorded event')}."


def card_text(s: int, r: int) -> str:
    return f"Discharge card with {count_of(s, 'warning sign')} and {count_of(r, 'schedule row')}."


def day_plan_text(k: int, c: int) -> str:
    return f"Day plan of {count_of(k, 'medicine')}; {c} matched to the medicines photo."
