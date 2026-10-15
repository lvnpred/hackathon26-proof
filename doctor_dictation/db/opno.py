"""Generated OP numbers: ``<PREFIX>-YYYYMMDD-NNN`` (clinic prefix, local clinic date, per-day sequence).

SQL + string work only. The prefix is the clinic's own: ``clinic_profile.op_prefix``, a copy of the directory's
``clinics.op_prefix``; ``OP`` when unset or invalid. The sequence continues from the largest number already used
that day under the same prefix in ``patients.op_no`` or ``encounters.op_no``; values that do not match the exact
day prefix and digits are ignored. NNN is zero-padded to three digits and simply grows (1000, 1001, ...) past 999.
Only 1-9 ASCII digits count as a sequence, so overlong or non-ASCII stored values are ignored. Changing the prefix
never rewrites a number already issued.

The day is the SERVER's local calendar day (a server in UTC rolls the sequence at 05:30 IST).
"""
import re
from datetime import datetime

from doctor_dictation.db import _utcnow, create_patient
from doctor_dictation.directory import PREFIX_RE

DEFAULT_PREFIX = "OP"


def check_op_prefix(value) -> str:
    """The prefix trimmed and upper-cased, or ValueError: 2 to 6 letters or digits."""
    text = value.strip() if isinstance(value, str) and value.isascii() else ""   # before upper(): 'ß' folds to 'SS'
    text = text.upper()
    if PREFIX_RE.fullmatch(text) is None:
        raise ValueError("OP prefix must be 2 to 6 letters or digits")
    return text


def get_op_prefix(conn) -> str:
    """The clinic's prefix from its profile row; ``OP`` when unset or invalid (single mode, older databases)."""
    row = conn.execute("SELECT op_prefix FROM clinic_profile WHERE id = 1").fetchone()
    value = row[0] if row is not None else None
    return value if isinstance(value, str) and PREFIX_RE.fullmatch(value) else DEFAULT_PREFIX


def set_op_prefix(conn, prefix) -> str:
    """Store the prefix on the single profile row (created blank when missing); returns the stored value.
    New numbers use it; numbers already issued are never rewritten."""
    prefix = check_op_prefix(prefix)
    conn.execute("INSERT INTO clinic_profile(id, updated_at, op_prefix) VALUES (1, ?, ?)"
                 " ON CONFLICT(id) DO UPDATE SET op_prefix = excluded.op_prefix", (_utcnow(), prefix))
    conn.commit()
    return prefix


def _day_prefix(now=None, prefix=DEFAULT_PREFIX) -> str:
    now = now or datetime.now().astimezone()
    return f"{prefix}-{now:%Y%m%d}-"


def next_op_no(conn, now=None, prefix=None) -> str:
    """Next free OP number for ``now``'s local calendar day (default: today) under the clinic's prefix."""
    day = _day_prefix(now, prefix or get_op_prefix(conn))
    pat = re.compile(re.escape(day) + r"([0-9]{1,9})$")
    top = 0
    for table in ("patients", "encounters"):
        rows = conn.execute(
            f"SELECT op_no FROM {table} WHERE op_no LIKE ?", (day + "%",)
        ).fetchall()
        for (op_no,) in rows:
            m = pat.match(op_no or "")
            if m:
                top = max(top, int(m.group(1)))
    return f"{day}{top + 1:03d}"


def create_patient_with_new_op(conn, name, age_sex="", now=None):
    """Create a patient carrying a freshly generated OP number; return ``(id, op_no)``.

    Never merges into an existing patient. ``BEGIN IMMEDIATE`` takes SQLite's
    write lock *before* the prefix and number are read, and :func:`create_patient`'s
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
