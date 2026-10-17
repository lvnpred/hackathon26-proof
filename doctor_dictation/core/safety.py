"""Safety gate for finalizing a document (Task 6).

Pure, offline, no I/O. The verify gate refuses to finalize a prescription while
any Rx row is not ``verified`` — unless the doctor explicitly confirmed that
row. Keeping this as a pure function makes the rule easy to test without a DB.
"""


import re

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

    Returns one ``{"index", "name", "status"}`` per blocking row, in rx order.
    """
    confirmed = set(confirmed_rows or [])
    rows = structured.get("rx") if isinstance(structured, dict) else None
    block = []
    for index, row in enumerate(rows if isinstance(rows, list) else []):
        if not isinstance(row, dict):
            continue
        status = row.get("status")
        if status == "verified" or index in confirmed:
            continue
        block.append({"index": index, "name": row.get("name") or "", "status": status})
    return block
