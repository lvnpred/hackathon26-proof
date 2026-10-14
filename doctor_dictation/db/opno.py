"""Generated OP numbers: ``OP-YYYYMMDD-NNN`` (local clinic date, per-day sequence).

SQL + string work only. The sequence continues from the largest number already
used that day in ``patients.op_no`` or ``encounters.op_no``; values that do not
match the exact day prefix and digits are ignored. NNN is zero-padded to three
digits and simply grows (1000, 1001, ...) past 999. Only 1-9 ASCII digits count
as a sequence, so overlong or non-ASCII stored values are ignored.

The day is the SERVER's local calendar day (a server in UTC rolls the sequence
at 05:30 IST).
"""
import re
from datetime import datetime

from doctor_dictation.db import create_patient


def _day_prefix(now=None) -> str:
    now = now or datetime.now().astimezone()
    return f"OP-{now:%Y%m%d}-"


def next_op_no(conn, now=None) -> str:
    """Next free OP number for ``now``'s local calendar day (default: today)."""
    prefix = _day_prefix(now)
    pat = re.compile(re.escape(prefix) + r"([0-9]{1,9})$")
    top = 0
    for table in ("patients", "encounters"):
        rows = conn.execute(
            f"SELECT op_no FROM {table} WHERE op_no LIKE ?", (prefix + "%",)
        ).fetchall()
        for (op_no,) in rows:
            m = pat.match(op_no or "")
            if m:
                top = max(top, int(m.group(1)))
    return f"{prefix}{top + 1:03d}"


def create_patient_with_new_op(conn, name, age_sex="", now=None):
    """Create a patient carrying a freshly generated OP number; return ``(id, op_no)``.

    Never merges into an existing patient. ``BEGIN IMMEDIATE`` takes SQLite's
    write lock *before* the number is computed, and :func:`create_patient`'s
    commit publishes the new row before the lock is released, so a concurrent
    first save blocks (default 5 s busy timeout) and then sees this number.
    """
    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        op_no = next_op_no(conn, now)
        return create_patient(conn, name, age_sex, op_no), op_no
    except BaseException:
        conn.rollback()
        raise
