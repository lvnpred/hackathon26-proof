"""What each proof photo should show (spec §6.6): one expected-content line per check, and its staff label.

Items are keyed `<step>:<key>`. Ward tasks are keyed `task:<task_id>` on the record; their expected line is
looked up by `task:<kind>`.
"""

from __future__ import annotations

from app.journey.states import ADMISSION_CHECKS, CHECK_WORDS, DISCHARGE_CHECKS

EXPECT: dict[str, str] = {
    "admission:band": "a patient wristband with the patient's name printed on it",
    "admission:allergies": "an allergy label, or a card that says no allergies are known",
    "admission:baseline_obs": "a patient monitor screen showing the readings",
    "admission:consent": "a signed consent form",
    "discharge:card_given": "the discharge card in the patient's hand",
    "discharge:medicines_handed": "a medicine bag with labels",
    "discharge:reminders_set": "a phone screen showing a dose reminder",
    "theatre:swab_tray": "the swab tray before incision, with the swabs laid apart so they can be counted",
    "theatre:closing_tray": "the swab tray at closing, with the swabs laid apart so they can be counted",
    "task:dose": "the medicine strip or packet, with the medicine name readable",
    "task:obs": "a patient monitor screen showing the readings",
    "task:procedure": "the set-up with its label visible, for example a saline bag and giving set",
    "task:check": "the thing that was checked, clearly in view",
    "task:other": "the finished task, clearly in view",
}

THEATRE_WORDS = {"swab_tray": "swab tray before incision", "closing_tray": "swab tray at closing"}
ADMISSION = tuple(f"admission:{k}" for k in ADMISSION_CHECKS)
DISCHARGE = tuple(f"discharge:{k}" for k in DISCHARGE_CHECKS)
THEATRE = tuple(f"theatre:{k}" for k in THEATRE_WORDS)
# The step each fixed item belongs to, and the state the patient is in while its photo is taken.
STEP_STATE = {"admission": "admitting", "discharge": "discharging", "theatre": "theatre"}


def label(item: str) -> str:
    """The staff word for an item: "wristband", "swab tray before incision", "task proof"."""
    step, _, key = item.partition(":")
    if step in ("admission", "discharge"):
        return CHECK_WORDS.get(key, key)
    if step == "theatre":
        return THEATRE_WORDS.get(key, key)
    return "task proof"


def fixed(item: str) -> bool:
    """True for an admission, discharge or theatre item (not a ward task)."""
    return item in ADMISSION or item in DISCHARGE or item in THEATRE


def expect_for(item: str, task_kind: str | None = None) -> str:
    if item.startswith("task:"):
        return EXPECT.get(f"task:{task_kind}", EXPECT["task:other"])
    return EXPECT[item]
