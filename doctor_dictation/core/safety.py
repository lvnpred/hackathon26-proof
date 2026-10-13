"""Safety gate for finalizing a document (Task 6).

Pure, offline, no I/O. The verify gate refuses to finalize a prescription while
any Rx row is not ``verified`` — unless the doctor explicitly confirmed that
row. Keeping this as a pure function makes the rule easy to test without a DB.
"""


def screen_unverified(structured: dict, confirmed_rows=None) -> list[dict]:
    """Rx rows that are not ``verified`` and were not explicitly confirmed.

    ``structured`` is a validated form; its ``rx`` rows carry a ``status`` field
    (``verified`` / ``unverified-name`` / ``unknown-medicine`` /
    ``unverified-strength``). ``confirmed_rows`` is the list of rx indices the
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
