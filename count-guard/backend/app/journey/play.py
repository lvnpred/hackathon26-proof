"""The three-act demo for R. Kumar: the doctor prescribes, the nurse cares, the patient goes home.

Every nudge below is raised by the rules in nudges.py, not written by this script.
"""

from __future__ import annotations

from typing import Callable

from app.journey.rx import DEMO_DOCUMENT, from_document, key_of
from app.journey.schedule import build as build_schedule
from app.journey.stories import CARE_TEMPLATES
from app.morning.brownbag import read_strip
from app.morning.druglog import parse_drug_phrase

H = 3_600_000
M = 60_000

DOCTOR = "Dr. A. Rao (synthetic)"
SCRUB = "Nurse Priya (synthetic)"
WARD = "Nurse Meena (synthetic)"
RELIEF = "Nurse Joseph (synthetic)"

ORDERS = {
    "doses": [
        {"name": "Paracetamol", "amount": "1 g IV", "every_h": 6},
        {"name": "Ondansetron", "amount": "4 mg IV", "every_h": 8},
    ],
    "obs_every_h": 1,
    "limits": {"sbp_min": 90, "sbp_max": 160, "hr_max": 110, "spo2_min": 94, "temp_max": 38.0},
    "by": DOCTOR,
}


def play_journey(store, episode_id: str, raise_nudges: Callable) -> None:
    def put(kind: str, payload: dict, at: int, **extra) -> dict:
        event = store.append(episode_id, kind, payload, ts_ms=at, **extra)
        raise_nudges(store, episode_id, at)
        return event

    def answer(kind: str, by: str, note: str, at: int) -> None:
        for event in store.events(episode_id):
            if event["event_type"] == "nudge.raised" and event["payload"]["kind"] == kind:
                seen = {e["payload"]["nudge_id"] for e in store.events(episode_id) if e["event_type"] == "nudge.seen"}
                if event["id"] not in seen:
                    put("nudge.seen", {"nudge_id": event["id"], "by": by, "note": note}, at)

    def dose(name: str, amount: str, by: str, at: int) -> None:
        put("dose.given", {"key": key_of(name), "name": name, "amount": amount, "by": by, "source": "spoken"}, at)

    def obs(sbp: int, dbp: int, hr: int, spo2: int, temp: float, at: int) -> None:
        put("obs.recorded", {"sbp": sbp, "dbp": dbp, "hr": hr, "spo2": spo2, "temp": temp, "by": WARD}, at)

    # Act 1, Day 0: the doctor prescribes in Doctor Dictation; the patient scans strips at home.
    put("rx.ordered", from_document(DEMO_DOCUMENT, source="demo"), 0)
    put("brownbag.med_found", {**read_strip("metoprolol", "25 mg"), "by": "patient", "source": "typed"}, 10 * H)
    wrong = put("brownbag.med_found", {**read_strip("amlodipine", "10 mg"), "by": "patient", "source": "typed"}, 10 * H + M)
    put("reminders.added", {"count": 3, "by": "patient"}, 10 * H + 5 * M)
    answer("strip_strength_differs", "patient", "Pharmacist swapped the strip for amlodipine 5 mg.", 11 * H)
    put(
        "brownbag.med_found",
        {**read_strip("amlodipine", "5 mg"), "by": "patient", "source": "typed"},
        11 * H + M,
        supersedes_id=wrong["id"],
    )

    # Act 2, Day 1: admission orders, theatre, then the ward.
    put("ward.orders_set", {**ORDERS, "doses": [{**d, "key": key_of(d["name"])} for d in ORDERS["doses"]]}, 22 * H)
    put("count.pack_opened", {"item_type": "swab", "quantity": 20, "source": "spoken", "by": SCRUB}, 24 * H)
    given = {**parse_drug_phrase("lignocaine two percent, five ml, local infiltration"), "confirmed": True, "by": DOCTOR}
    put("druglog.given", given, 24 * H + 10 * M)
    short = put(
        "count.closing",
        {"opened": 20, "returned": 19, "unaccounted": 1, "detail": "1 swab unaccounted at closing.", "by": SCRUB},
        24 * H + 50 * M,
    )
    put(
        "count.closing",
        {"opened": 20, "returned": 20, "unaccounted": 0, "detail": "Swab found in the drape fold.", "by": SCRUB},
        24 * H + 54 * M,
        supersedes_id=short["id"],
    )
    answer("count_open", SCRUB, "Found in the drape fold. Count 20 of 20.", 24 * H + 55 * M)

    obs(128, 80, 84, 98, 36.8, 26 * H)
    dose("Paracetamol", "1 g IV", WARD, 26 * H + 5 * M)
    obs(112, 70, 90, 97, 36.9, 27 * H)
    obs(86, 54, 96, 97, 37.0, 28 * H)
    answer("obs_past_limit", WARD, "Told Dr. Rao at 13:05. Doctor reviewed at the bedside.", 28 * H + 5 * M)
    dose("Ondansetron", "4 mg IV", WARD, 28 * H + 30 * M)
    dose("Ondansetron", "4 mg IV", RELIEF, 29 * H)
    obs(108, 68, 88, 97, 37.1, 29 * H)
    answer("dose_logged_early", WARD, "Checked with Nurse Joseph and told Dr. Rao.", 29 * H + 10 * M)
    raise_nudges(store, episode_id, 33 * H + 30 * M)  # the ward screen's clock check at 18:30
    dose("Paracetamol", "1 g IV", WARD, 33 * H + 35 * M)
    answer("dose_overdue", WARD, "Dose given and logged at 18:35.", 33 * H + 35 * M)
    obs(124, 78, 82, 98, 37.2, 33 * H + 36 * M)
    answer("obs_overdue", WARD, "Set taken at 18:36.", 33 * H + 36 * M)

    # Act 3, Day 1 evening to Day 3: the discharge card, then home (post-op day 2).
    template = CARE_TEMPLATES["hernia-repair"]
    rx = from_document(DEMO_DOCUMENT, source="demo")
    put(
        "discharge.card",
        {
            "template": "hernia-repair",
            "title": template["title"],
            "warning_signs": template["warning_signs"],
            "wound_care": template["wound_care"],
            "help_line": template["help_line"],
            "review": template["review"],
            "schedule": build_schedule(rx),
            "by": DOCTOR,
        },
        35 * H,
    )
    put(
        "checkin.recorded",
        {"day": 2, "feels": "Sore and warm", "signs": ["Fever above 38 °C"], "note": "", "by": "patient"},
        73 * H,
    )
    put("help.requested", {"says": "The dressing is wet.", "by": "patient"}, 73 * H + 30 * M)
