"""The clinic's learned drug list (spec I1-h). SQL only; the rules (names, threshold) live in core/formulary.py."""
from doctor_dictation.core.formulary import THRESHOLD
from doctor_dictation.db import _utcnow

COLUMNS = "id, name, generic, confirm_count, first_seen_at, last_seen_at, added_by"


def record_confirmation(conn, key, name, generic, document_id, user_id) -> int:
    """Count one saved DOCUMENT for a name. The same document again (a re-save) changes nothing. Returns the count."""
    now = _utcnow()
    row = conn.execute("SELECT id FROM clinic_formulary WHERE name_key = ?", (key,)).fetchone()
    fid = row["id"] if row else conn.execute(
        "INSERT INTO clinic_formulary(name_key, name, generic, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
        (key, name, generic or None, now, now)).lastrowid
    if conn.execute("INSERT OR IGNORE INTO clinic_formulary_docs(formulary_id, document_id) VALUES (?, ?)",
                    (fid, document_id)).rowcount:
        conn.execute(
            "UPDATE clinic_formulary SET confirm_count = confirm_count + 1, last_seen_at = ?,"
            " removed_at = CASE WHEN confirm_count + 1 >= ? THEN NULL ELSE removed_at END,"
            " added_by = CASE WHEN confirm_count + 1 = ? THEN ? ELSE added_by END WHERE id = ?",
            (now, THRESHOLD, THRESHOLD, user_id, fid))
    conn.commit()
    return conn.execute("SELECT confirm_count FROM clinic_formulary WHERE id = ?", (fid,)).fetchone()[0]


def list_active(conn) -> list[dict]:
    """Active names, most recently seen first."""
    rows = conn.execute(f"SELECT {COLUMNS} FROM clinic_formulary WHERE removed_at IS NULL AND confirm_count >= ?"
                        " ORDER BY last_seen_at DESC, id DESC", (THRESHOLD,)).fetchall()
    return [dict(r) for r in rows]


def remove(conn, entry_id) -> str | None:
    """Soft-remove an ACTIVE entry: returns its name, or None when this clinic has no such active entry."""
    row = conn.execute("SELECT name FROM clinic_formulary WHERE id = ? AND removed_at IS NULL AND confirm_count >= ?",
                       (entry_id, THRESHOLD)).fetchone()
    if row is None:
        return None
    conn.execute("UPDATE clinic_formulary SET removed_at = ?, confirm_count = 0 WHERE id = ?", (_utcnow(), entry_id))
    conn.commit()
    return row["name"]


def patient_words(conn) -> frozenset:
    """Casefolded words of 3+ letters in this clinic's patient names: a patient typed into a medicine cell is not a drug."""
    words = set()
    for (name,) in conn.execute("SELECT name FROM patients WHERE name IS NOT NULL"):
        words.update(w for w in str(name).casefold().split() if len(w) >= 3)
    return frozenset(words)
