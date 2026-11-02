"""The photo-check gate (U9): an admission or discharge move cannot complete while one of its photo checks is open.

Only admitting -> ward and discharging -> home are gated. Theatre-step and ward-task proofs never feed this gate,
and the surgery route never calls it, so U9 cannot reach the swab hard stop (spec §6.6).
"""

from __future__ import annotations

from app.journey import expected, verdict
from app.journey.states import CHECK_WORDS, current_state

GATED = {("admitting", "ward"): expected.ADMISSION, ("discharging", "home"): expected.DISCHARGE}
ERROR = "photo checks open"


def missing_checks(events: list[dict], to: str) -> list[str]:
    """The items of this move whose photo check is still open, e.g. ["admission:band"]; [] for any other move."""
    items = GATED.get((current_state(events), to), ())
    return [item for item in items if verdict.item_open(events, item)]


def refusal(events: list[dict], to: str) -> dict | None:
    """The 409 body for a move with open photo checks, or None. Items are staff words, never keys."""
    open_items = missing_checks(events, to)
    if not open_items:
        return None
    words = [CHECK_WORDS[item.partition(":")[2]] for item in open_items]
    detail = f"Photo checks still open: {', '.join(words)}. Take the photo again, or override it with a reason."
    return {"error": ERROR, "items": words, "detail": detail}
