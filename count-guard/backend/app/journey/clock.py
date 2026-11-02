"""The shared demo clock (spec §8). Episode ms, 0 = Day 0 09:00, the same zero every journey route uses.

The clock row is unset until POST /journey/clock sets it; the seed clears it. While it is unset, stamp()
gives exactly the times the routes gave before the clock moved to the server.
"""

from __future__ import annotations

STEP_MS = 1000  # an action sent without a time lands one second after the episode's latest event
# Putting a patient on the ward list is bookkeeping, not care: a just-registered episode still counts as
# empty, so its first action without a time lands at the clock time (0 on a fresh seed), as before.
NOT_CARE = ("patient.registered",)


def now_ms(store) -> int:
    """The server's demo time, or 0 while the clock is unset."""
    return store.get_clock() or 0


def set_ms(store, ms: int) -> int:
    return store.set_clock(ms)


def stamp(store, episode_id: str, at_ms: int | None) -> int:
    """The ts_ms an action on this episode is written at.

    Without at_ms: one step after the later of the latest event and the clock, or the clock time when the
    episode has no events. The ward-list registration does not count as an event here. With at_ms: never before the episode's latest event, and never past the
    clock when the clock is set.
    """
    clock = store.get_clock()
    latest = store.latest_ts(episode_id, skip=NOT_CARE)
    if at_ms is None:
        if latest is None:
            return clock or 0
        return max(latest, clock or 0) + STEP_MS
    stamped = int(at_ms)
    if clock is not None:
        stamped = min(stamped, clock)
    if latest is not None:
        stamped = max(stamped, latest)
    return stamped
