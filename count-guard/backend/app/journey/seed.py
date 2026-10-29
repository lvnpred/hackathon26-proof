"""The ward demo seed: three synthetic patients on one shared demo clock (episode ms, 0 = Day 0 09:00).

Kumar starts empty (the video builds his story live). Iyer is on hourly observations, so the rules
in nudges.py raise her overdue round the first time the clock passes Day 0 10:00. Das is ready to go home.
"""

from __future__ import annotations

from typing import Callable

from app.journey.rx import DEMO_DOCUMENT, from_document, key_of
from app.journey.schedule import build as build_schedule
from app.journey.stories import CARE_TEMPLATES

DOCTOR = "Dr. A. Rao (synthetic)"
NURSE = "Nurse Meena (synthetic)"

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


def seed_ward(store, raise_nudges: Callable) -> list[dict]:
    """Create the three episodes and their opening events. Returns id, bed and name in bed order."""
    made = []
    for bed, name in PATIENTS:
        episode_id = store.create_episode(name)["id"]
        made.append({"id": episode_id, "bed": bed, "name": name})

    def put(index: int, kind: str, payload: dict) -> None:
        episode_id = made[index]["id"]
        store.append(episode_id, kind, payload, ts_ms=0)
        raise_nudges(store, episode_id, 0)

    doses: list[dict] = []  # Iyer has no scheduled doses; her round is the hourly observations
    put(1, "ward.orders_set", {
        "doses": [{**d, "key": key_of(d["name"])} for d in doses],
        "obs_every_h": 1,
        "limits": {"sbp_min": 90},
        "by": DOCTOR,
    })
    put(1, "obs.recorded", {"sbp": 124, "dbp": 78, "hr": 80, "spo2": 98, "temp": 36.9, "by": NURSE})

    rx = from_document(DEMO_DOCUMENT, source="demo")
    put(2, "rx.ordered", rx)
    put(2, "discharge.card", card_payload("hernia-repair", rx, DOCTOR))
    return made
