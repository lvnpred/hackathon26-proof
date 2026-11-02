"""Corrections in place: a corrected line stands where the line it corrects stood (fix round 1, R23).

A correction is appended at the end of the record. A reader that slices by position (the theatre stay) would
otherwise find a drug corrected after the patient left theatre in the ward stay. Only the kinds passed in move;
every other superseding event keeps its own position, exactly as `visible_events` leaves it, so the swab count,
moves and the hard stop read the record as before.
"""

from __future__ import annotations

DRUG_KINDS = ("druglog.parsed", "drug.given", "druglog.given")


def in_place(events: list[dict], kinds: tuple[str, ...] = DRUG_KINDS) -> list[dict]:
    """The visible events, with each correction of `kinds` in its original's slot (following a chain of corrections)."""
    ids = {e["id"] for e in events}
    replaced_by = {e["supersedes_id"]: e for e in events if e.get("supersedes_id")}
    out = []
    for e in events:
        moved = e["event_type"] in kinds and e.get("supersedes_id") in ids
        if moved:
            continue  # it stands in its original's slot
        if e["id"] not in replaced_by:
            out.append(e)
            continue
        latest = e
        while latest["id"] in replaced_by and replaced_by[latest["id"]]["event_type"] in kinds:
            latest = replaced_by[latest["id"]]
        if latest is not e and latest["id"] not in replaced_by:
            out.append(latest)
    return out
