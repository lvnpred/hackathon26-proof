"""The clinic's overlay on the shipped lists (plan PQ-f). SQL only; the merge rules live outside db/."""
import json

from doctor_dictation.core.formulary import THRESHOLD
from doctor_dictation.db import _utcnow

COLUMNS = "id, kind, entry_key, action, data, base_sha, source, confirm_count, created_by, created_at, updated_at"
_ACTIVE = "removed_at IS NULL AND (source = 'admin' OR confirm_count >= ?)"


def _dump(data: dict) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


def upsert(conn, kind, entry_key, action, data: dict, base_sha, source, user_id, *, commit: bool = True) -> int:
    """The ADMIN path: insert or replace one row, live at once. The first writer stays in created_by.

    Doctor saves go through record_confirmation, so a non-admin source here would downgrade a live admin row."""
    if source != "admin":
        raise ValueError("upsert is the admin path: source must be 'admin'")
    now = _utcnow()
    conn.execute(
        "INSERT INTO clinic_overlay(kind, entry_key, action, data, base_sha, source, created_by, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(kind, entry_key) DO UPDATE SET action = excluded.action, data = excluded.data,"
        " base_sha = excluded.base_sha, source = excluded.source, updated_at = excluded.updated_at, removed_at = NULL",
        (kind, entry_key, action, _dump(data), base_sha, source, user_id, now, now))
    if commit:
        conn.commit()
    return conn.execute("SELECT id FROM clinic_overlay WHERE kind = ? AND entry_key = ?", (kind, entry_key)).fetchone()[0]


def list_rows(conn, kind, *, pending: bool = False) -> list[dict]:
    """Active rows, or with pending=True the live rows that are not active yet. Ordered by entry_key."""
    where = f"NOT ({_ACTIVE})" if pending else _ACTIVE
    rows = conn.execute(f"SELECT {COLUMNS} FROM clinic_overlay WHERE kind = ? AND "
                        + ("removed_at IS NULL AND " if pending else "") + f"{where} ORDER BY entry_key",
                        (kind, THRESHOLD)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["data"] = json.loads(d["data"])
        out.append(d)
    return out


def reset(conn, kind, entry_key, *, commit: bool = True) -> bool:
    """Soft-remove a live row. False when there is none."""
    done = conn.execute("UPDATE clinic_overlay SET removed_at = ?, updated_at = ? WHERE kind = ? AND entry_key = ?"
                        " AND removed_at IS NULL", (_utcnow(), _utcnow(), kind, entry_key)).rowcount
    if commit:
        conn.commit()
    return bool(done)


def record_confirmation(conn, kind, entry_key, action, data: dict, base_sha, document_id, user_id) -> int:
    """Count one saved DOCUMENT for an entry. Returns the count (0 when a live admin row wins).

    BEGIN IMMEDIATE takes the write lock before the row is read, so concurrent saves queue up (busy timeout).
    The count is the ledger size, so it heals itself.

    It COMMITS any transaction the caller has open on ``conn`` first (and commits its own): call it after your own
    commit, never inside a transaction you may still want to roll back.
    """
    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        count = _confirm(conn, kind, entry_key, action, _dump(data), base_sha, document_id, user_id)
        conn.commit()
        return count
    except BaseException:
        conn.rollback()
        raise


def _confirm(conn, kind, entry_key, action, text, base_sha, document_id, user_id) -> int:
    now = _utcnow()
    row = conn.execute("SELECT id, data, source, removed_at FROM clinic_overlay WHERE kind = ? AND entry_key = ?",
                       (kind, entry_key)).fetchone()
    if row is None:
        oid = conn.execute(
            "INSERT INTO clinic_overlay(kind, entry_key, action, data, base_sha, source, created_by, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, 'doctor', ?, ?, ?)", (kind, entry_key, action, text, base_sha, user_id, now, now)).lastrowid
    elif row["source"] == "admin" and row["removed_at"] is None:
        return 0
    else:
        oid = row["id"]
        if row["removed_at"] is not None or row["data"] != text:
            conn.execute("DELETE FROM clinic_overlay_docs WHERE overlay_id = ?", (oid,))
            conn.execute("UPDATE clinic_overlay SET action = ?, data = ?, base_sha = ?, source = 'doctor',"
                         " removed_at = NULL WHERE id = ?", (action, text, base_sha, oid))
    conn.execute("INSERT OR IGNORE INTO clinic_overlay_docs(overlay_id, document_id) VALUES (?, ?)", (oid, document_id))
    count = conn.execute("SELECT COUNT(*) FROM clinic_overlay_docs WHERE overlay_id = ?", (oid,)).fetchone()[0]
    conn.execute("UPDATE clinic_overlay SET confirm_count = ?, updated_at = ? WHERE id = ?", (count, now, oid))
    return count


def approve(conn, kind, entry_key, user_id, *, commit: bool = True) -> bool:
    """Make a pending row active by setting its source to 'admin'. The caller writes the audit row."""
    done = conn.execute("UPDATE clinic_overlay SET source = 'admin', updated_at = ? WHERE kind = ? AND entry_key = ?"
                        " AND removed_at IS NULL AND source != 'admin'", (_utcnow(), kind, entry_key)).rowcount
    if commit:
        conn.commit()
    return bool(done)
