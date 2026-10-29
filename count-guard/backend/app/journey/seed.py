"""The ward demo seed: three synthetic patients on one shared demo clock (episode ms, 0 = Day 0 09:00).

Kumar and Das start empty, in clinic (the video builds their stories live). Iyer was admitted the
day before and is on the ward with a signed, acknowledged hourly-observation order and one reading
taken, so the rules in nudges.py raise her overdue round the first time the clock passes Day 0 10:00.
The seed writes through the same helpers the routes use, so it cannot drift from them.
"""

from __future__ import annotations

from typing import Callable

from app.journey import tasks
from app.journey.rx import IYER_DOCUMENT, from_document
from app.journey.schedule import build as build_schedule
from app.journey.stories import CARE_TEMPLATES

DOCTOR = "Dr. A. Rao (synthetic)"
NURSE = "Nurse Meena (synthetic)"
NURSE_THEATRE = "Nurse Asha (synthetic)"
BOARD_LABEL = "Ward staff board (synthetic)"  # holds the doctor's hand-set status; never a patient

PATIENTS = [
    ("4", "R. Kumar, 58 M (synthetic)"),
    ("7", "S. Iyer, 64 F (synthetic)"),
    ("9", "A. Das, 47 M (synthetic)"),
]


def card_payload(template_key: str, rx_payload: dict | None, by: str) -> dict:
    """The discharge.card payload. The /discharge-card route and the seed both build it here."""
    template = CARE_TEMPLATES[template_key]
    return {
        "template": template_key,
        "title": template["title"],
        "warning_signs": template["warning_signs"],
        "wound_care": template["wound_care"],
        "help_line": template["help_line"],
        "review": template["review"],
        "schedule": build_schedule(rx_payload) if rx_payload else [],
        "by": by,
    }


def seed_ward(store, raise_nudges: Callable) -> dict:
    """Create the three episodes and the staff board; Iyer gets her ward history.

    Returns {"patients": id, bed and name in bed order, "board": the staff board's episode id}.
    """
    made = []
    for bed, name in PATIENTS:
        episode_id = store.create_episode(name)["id"]
        made.append({"id": episode_id, "bed": bed, "name": name})
    board = store.create_episode(BOARD_LABEL)["id"]

    iyer = made[1]["id"]
    admitted = {"from": None, "to": "ward", "by": DOCTOR, "reason": "Admitted the day before (seed)"}
    store.append(iyer, "patient.state", admitted, ts_ms=0)
    store.append(iyer, "rx.ordered", from_document(IYER_DOCUMENT, source="demo"), ts_ms=0)
    obs = {
        "kind": "obs", "text": "BP and pulse every 1 h", "name": "", "amount": "", "every_h": 1,
        "mode": "tick", "proof": "none", "limits": {"sbp_min": 90},
    }
    tasks.sign_order(store, iyer, [obs], DOCTOR, 0)
    order = tasks.orders_list(store.events(iyer))[0]
    tasks.acknowledge_order(store, iyer, order["id"], NURSE, 0)
    task = tasks.task_list(store.events(iyer))[0]
    reading = {"sbp": 124, "dbp": 78, "hr": 80, "spo2": 98, "temp": 36.9}
    tasks.complete_task(store, iyer, task["id"], NURSE, 0, values=reading)
    raise_nudges(store, iyer, 0)
    return {"patients": made, "board": board}
