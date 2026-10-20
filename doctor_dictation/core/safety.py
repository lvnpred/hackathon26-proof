"""Safety gate for finalizing a document (Task 6).

Pure, offline, no I/O. The verify gate refuses to finalize a prescription while
any Rx row is not ``verified`` — unless the doctor explicitly confirmed that
row. Keeping this as a pure function makes the rule easy to test without a DB.
"""


import re

from .doctor_generic import DOCTOR, clean_generic

# The two texts check-row adds to Instructions (core/correction.GROUNDING_MARKERS): exactly these, in brackets, case as written.
_GROUNDING_MARKER = re.compile(r" ?\[unverified(?: strength)?: confirm with doctor\]")


def strip_grounding_markers(structured: dict) -> dict:
    """Remove the two grounding markers (and one space before each) from every rx row's Instructions; mutates and returns it.

    For a form that passed the Save gate: every row is verified or doctor-confirmed, so the marker no longer says anything true
    and must not print. Only the exact marker goes; the doctor's own words ("unverified", "confirm with doctor") stay."""
    rows = structured.get("rx") if isinstance(structured, dict) else None
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and isinstance(row.get("instructions"), str):
            row["instructions"] = _GROUNDING_MARKER.sub("", row["instructions"]).strip()
    return structured


def screen_unverified(structured: dict, confirmed_rows=None) -> list[dict]:
    """Rx rows that are not ``verified`` and were not explicitly confirmed.

    ``structured`` is a validated form; its ``rx`` rows carry a ``status`` field
    (``verified`` / ``unverified-name`` / ``unknown-medicine`` /
    ``unverified-strength`` / ``lookalike-check``; any status but ``verified``
    blocks). ``confirmed_rows`` is the list of rx indices the
    doctor explicitly confirmed, so a confirmed row does not block the save.

    A doctor generic (``generic_source == "doctor"``) also blocks: ``"generic": "pending"`` while it is pending and the
    row is not confirmed, ``"generic": "invalid"`` when it fails ``clean_generic`` (confirmed or not).

    Returns one ``{"index", "name", "status"}`` per blocking row, in rx order, plus ``"generic"`` when the doctor
    generic blocks (on the same entry when the status blocks too).
    """
    confirmed = set(confirmed_rows or [])
    rows = structured.get("rx") if isinstance(structured, dict) else None
    block = []
    for index, row in enumerate(rows if isinstance(rows, list) else []):
        if not isinstance(row, dict):
            continue
        status = row.get("status")
        entry = {"index": index, "name": row.get("name") or "", "status": status}
        if status != "verified" and index not in confirmed:
            block.append(entry)
        problem = _generic_block(row, index in confirmed)
        if problem:
            if not block or block[-1] is not entry:
                block.append(entry)
            entry["generic"] = problem
    return block


def _generic_block(row: dict, confirmed: bool) -> str:
    """"invalid" / "pending" / "" for a row's doctor generic (a row without one never blocks here)."""
    if row.get("generic_source") != DOCTOR:
        return ""
    if not clean_generic(row.get("generic")):
        return "invalid"
    return "pending" if row.get("generic_pending") is True and not confirmed else ""
