"""Which recorded events a person may correct, and why the rest are refused (spec §9 "morning correction route").

A correction appends a new event that supersedes the old one, at the old one's time but at the END of the write
order. Anything read by position in the record (the theatre stay, the dose gaps) or by a gate (the swab hard stop,
the photo checks, the ward list) would then decide differently, so only a typed observation set and the theatre
drug lines (read in place, journey/placed.py) are correctable.
"""

from __future__ import annotations

from app.journey.placed import DRUG_KINDS

# Refused on both correction routes (the morning one keeps these three until Task 16 archives it).
COUNT = "A swab count is corrected on the count form, not here."
SURGERY = "A surgery step is recorded on the theatre steps, not corrected here."
MOVE = "A patient move is recorded as a new move, not corrected here."
# Refused on the care route only.
PHOTO = "A photo check is settled by a new photo or an override with a reason, not corrected here."
CAMERA = "The camera only advises; its output is not corrected into a person's record."
WARD = "The ward list and the prescription come from intake and Sync, not from a correction."
ORDERED = "This line is read in time order; record a new line instead of correcting this one."
OTHER = "Only an observation set or a theatre drug line can be corrected here."
CONFIRMED = "This heard line was confirmed. Correct the drug given instead."
DONE = "This line was already corrected. Correct the newer line."

OBS_FIELDS = ("sbp", "dbp", "hr", "spo2", "temp")
DRUG_FIELDS = ("strength", "amount", "unit", "route")  # never the name, `by`, draft_id or confirmed
# Drug lines are corrected in place (journey/placed.py): the theatre stay and the discharge draft read the
# correction where the original stood, so a drug corrected after the patient left theatre stays in that stay.
CORRECTABLE = {"obs.recorded": OBS_FIELDS, **{kind: DRUG_FIELDS for kind in DRUG_KINDS}}

PHOTO_KINDS = ("check.photo", "check.override", "photo.added", "proof.checked")  # the photo gate (U9) reads these
WARD_KINDS = ("patient.registered", "bed.changed", "rx.ordered")
ORDERED_KINDS = ("dose.given", "vitals.reading")  # dose-gap nudges and the strip read these in write order


def protected(event_type: str) -> str | None:
    """The three refusals the hard stop and the state machine need, on every correction route."""
    if event_type.startswith("count."):
        return COUNT
    if event_type.startswith("surgery."):
        return SURGERY
    if event_type == "patient.state":
        return MOVE
    return None


def refusal(event: dict, events: list[dict]) -> str | None:
    """Why the care app will not correct `event` (409), or None when it may."""
    kind = event["event_type"]
    if any(e.get("supersedes_id") == event["id"] for e in events):
        return DONE
    if kind == "druglog.parsed" and any(
        e["event_type"] == "drug.given" and e["payload"].get("draft_id") == event["id"] for e in events
    ):
        return CONFIRMED
    found = protected(kind)
    if found:
        return found
    if kind in PHOTO_KINDS:
        return PHOTO
    if kind.startswith("camera.") or kind == "swabs.counted":
        return CAMERA
    if kind in WARD_KINDS:
        return WARD
    if kind in ORDERED_KINDS:
        return ORDERED
    return None if kind in CORRECTABLE else OTHER


def unknown_fields(event_type: str, payload: dict) -> list[str]:
    """Keys a correction of this kind may not change (`by` comes from the request, never the payload)."""
    allowed = CORRECTABLE.get(event_type, ())
    return sorted(key for key in payload if key not in allowed)


def corrected(event_type: str, old: dict, values: dict, by: str) -> dict:
    """The new payload: the old one with the corrected values.

    An observation set takes the correcting person as `by`. A drug line keeps who gave (or said) it and names the
    correcting person as `corrected_by`, so the record still says who gave the drug.
    """
    if event_type in DRUG_KINDS:
        return {**old, **values, "corrected_by": by}
    return {**old, **values, "by": by}
