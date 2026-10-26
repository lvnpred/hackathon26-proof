"""The doctor's spoken terms (plan SH-H1). SQL only; what a term is, and how it is phrased and ranked, lives in core/spoken.py."""
import json
from collections import defaultdict
from collections.abc import Sequence
from datetime import date

from doctor_dictation.core.formulary import THRESHOLD, usage_score
from doctor_dictation.core.spoken import CONTEXT_LINES, LINK_MIN, HintTerm, Term, key, phrase, terms_from_save, usual_strength
from doctor_dictation.db import _utcnow

# A pair is active (its term is lifted to tier 1) when counted by enough documents and neither it nor its term was
# removed, and its term still has uses (``doctor_hint_terms`` skips a term with none). Bind :threshold.
ACTIVE = "m.removed_at IS NULL AND m.confirm_count >= :threshold AND t.removed_at IS NULL AND t.uses > 0"


def record_terms(conn, doctor_id, terms: list[Term], document_id, previous: Sequence[Term] = ()) -> int:
    """Count one saved DOCUMENT for each term. The same document again changes nothing unless ``previous`` took it back.

    ``previous`` is what this document taught before (a re-save): it is taken back first (``unrecord_terms``), so a
    corrected name loses this document's use, a changed strength moves, and a name still there is counted once again.
    A use is dated by its document, so a backfill or an out-of-order save keeps the real first and last dates.
    Returns how many terms were counted now.

    COMMITS what the caller has open first, then all of its own writes or none of them (a failure rolls back and raises)."""
    if conn.in_transaction:                       # so the rollback below can only undo this call's own writes
        conn.commit()
    row = conn.execute("SELECT COALESCE(finalized_at, created_at) FROM documents WHERE id = ?", (document_id,)).fetchone()
    at = row[0] if row and row[0] else _utcnow()
    try:
        unrecord_terms(conn, previous, document_id)
        counted = sum(_record_term(conn, doctor_id, t, document_id, at) for t in terms)
        conn.commit()
        return counted
    except BaseException:
        conn.rollback()
        raise


def unrecord_terms(conn, terms: Sequence[Term], document_id) -> int:
    """Take back the use each term (a document's earlier form) gave this document, whichever doctor it was credited to.

    Only a use the ledger holds is taken back, with its strength. Returns how many. Does NOT commit: ``record_terms``
    runs it inside its own all-or-nothing transaction."""
    taken = 0
    for t in terms:
        for (tid,) in conn.execute("SELECT t.id FROM spoken_terms t JOIN spoken_term_docs d ON d.term_id = t.id"
                                   " WHERE d.document_id = ? AND t.kind = ? AND t.term_key = ?",
                                   (document_id, t.kind, t.key)).fetchall():
            conn.execute("DELETE FROM spoken_term_docs WHERE term_id = ? AND document_id = ?", (tid, document_id))
            conn.execute("UPDATE spoken_terms SET uses = MAX(uses - 1, 0) WHERE id = ?", (tid,))
            if t.kind == "medicine":
                conn.execute("UPDATE spoken_term_strengths SET uses = MAX(uses - 1, 0) WHERE term_id = ? AND strength = ?",
                             (tid, t.strength))
            taken += 1
    return taken


def _record_term(conn, doctor_id, t: Term, document_id, at) -> int:
    """Count one term for one document; 1 when counted, 0 when this document already counted it."""
    conn.execute(
        "INSERT INTO spoken_terms(doctor_id, kind, term_key, spoken, form, generic, first_used_at, last_used_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(doctor_id, kind, term_key) DO NOTHING",
        (doctor_id, t.kind, t.key, t.spoken, t.form, t.generic, at, at))
    tid = conn.execute("SELECT id FROM spoken_terms WHERE doctor_id = ? AND kind = ? AND term_key = ?",
                       (doctor_id, t.kind, t.key)).fetchone()[0]
    if not conn.execute("INSERT OR IGNORE INTO spoken_term_docs(term_id, document_id) VALUES (?, ?)",
                        (tid, document_id)).rowcount:
        return 0
    conn.execute(
        "UPDATE spoken_terms SET uses = uses + 1, first_used_at = MIN(first_used_at, ?), last_used_at = MAX(last_used_at, ?),"
        " spoken = CASE WHEN ? >= last_used_at THEN ? ELSE spoken END,"
        " form = CASE WHEN ? >= last_used_at AND ? != '' THEN ? ELSE form END,"
        " generic = CASE WHEN ? >= last_used_at AND ? != '' THEN ? ELSE generic END WHERE id = ?",
        (at, at, at, t.spoken, at, t.form, t.form, at, t.generic, t.generic, tid))
    if t.kind == "medicine":                      # "" too: the "no strength said" use
        conn.execute("INSERT INTO spoken_term_strengths(term_id, strength, uses) VALUES (?, ?, 1)"
                     " ON CONFLICT(term_id, strength) DO UPDATE SET uses = uses + 1", (tid, t.strength))
    return 1


def doctor_hint_terms(conn, doctor_id, today: date) -> list[HintTerm]:
    """Every live term of this doctor (a use left, not removed), uncapped and unranked, with ``term_id`` and ``key`` set."""
    strengths = defaultdict(dict)
    for r in conn.execute("SELECT s.term_id, s.strength, s.uses FROM spoken_term_strengths s JOIN spoken_terms t ON t.id = s.term_id"
                          " WHERE t.doctor_id = ? AND t.removed_at IS NULL AND s.uses > 0", (doctor_id,)):
        strengths[r["term_id"]][r["strength"]] = r["uses"]
    rows = conn.execute("SELECT id, term_key, spoken, uses, last_used_at FROM spoken_terms"
                        " WHERE doctor_id = ? AND removed_at IS NULL AND uses > 0 ORDER BY id", (doctor_id,)).fetchall()
    return [HintTerm(phrase(r["spoken"], usual_strength(strengths[r["id"]])), usage_score(r["uses"], r["last_used_at"], today),
                     term_id=r["id"], key=r["term_key"]) for r in rows]


def record_mishearings(conn, doctor_id, pairs: Sequence[tuple[str, str]], document_id) -> int:
    """Count one saved DOCUMENT for each (term key, heard) pair of this doctor. The same document again changes nothing.

    A pair whose medicine term the doctor has not recorded is skipped. Pairs are never taken back on a re-save.
    Returns how many pairs were counted now.

    COMMITS what the caller has open first, then all of its own writes or none of them (a failure rolls back and raises)."""
    if conn.in_transaction:                       # so the rollback below can only undo this call's own writes
        conn.commit()
    try:
        counted = sum(_record_mishearing(conn, doctor_id, term_key, heard, document_id) for term_key, heard in pairs)
        conn.commit()
        return counted
    except BaseException:
        conn.rollback()
        raise


def _record_mishearing(conn, doctor_id, term_key, heard, document_id) -> int:
    """Count one pair for one document; 1 when counted, 0 when skipped or this document already counted it."""
    row = conn.execute("SELECT id FROM spoken_terms WHERE doctor_id = ? AND kind = 'medicine' AND term_key = ?",
                       (doctor_id, term_key)).fetchone()
    if row is None:
        return 0
    now = _utcnow()
    heard_key = key(heard)
    conn.execute("INSERT OR IGNORE INTO spoken_mishearings(term_id, heard_key, heard, first_seen_at, last_seen_at)"
                 " VALUES (?, ?, ?, ?, ?)", (row["id"], heard_key, heard, now, now))
    mid = conn.execute("SELECT id FROM spoken_mishearings WHERE term_id = ? AND heard_key = ?",
                       (row["id"], heard_key)).fetchone()[0]
    if not conn.execute("INSERT OR IGNORE INTO spoken_mishearing_docs(mishearing_id, document_id) VALUES (?, ?)",
                        (mid, document_id)).rowcount:
        return 0
    conn.execute("UPDATE spoken_mishearings SET confirm_count = confirm_count + 1, last_seen_at = ?,"
                 " removed_at = CASE WHEN confirm_count + 1 >= ? THEN NULL ELSE removed_at END WHERE id = ?",
                 (now, THRESHOLD, mid))
    return 1


def active_mishearing_term_ids(conn, doctor_id) -> set[int]:
    """The ids of this doctor's terms that have an active corrected mishearing."""
    return {r[0] for r in conn.execute(
        f"SELECT DISTINCT m.term_id FROM spoken_mishearings m JOIN spoken_terms t ON t.id = m.term_id"
        f" WHERE t.doctor_id = :doctor_id AND {ACTIVE}", {"doctor_id": doctor_id, "threshold": THRESHOLD})}


def list_active_mishearings(conn) -> list[dict]:
    """Active corrected mishearings of every doctor in this clinic, most recently seen first."""
    rows = conn.execute(
        "SELECT m.id, t.spoken, m.heard, m.confirm_count, m.first_seen_at, m.last_seen_at, t.doctor_id,"
        " COALESCE(NULLIF(u.display_name, ''), u.username, '') AS doctor"
        " FROM spoken_mishearings m JOIN spoken_terms t ON t.id = m.term_id LEFT JOIN users u ON u.id = t.doctor_id"
        f" WHERE {ACTIVE} ORDER BY m.last_seen_at DESC, m.id DESC", {"threshold": THRESHOLD}).fetchall()
    return [dict(r) for r in rows]


def remove_mishearing(conn, entry_id) -> dict | None:
    """Soft-remove an ACTIVE pair: returns its spoken and heard words, or None when there is no such active pair.

    Only documents saved after this count toward bringing it back (the count restarts at 0)."""
    row = conn.execute("SELECT t.spoken, m.heard FROM spoken_mishearings m JOIN spoken_terms t ON t.id = m.term_id"
                       f" WHERE m.id = :id AND {ACTIVE}", {"id": entry_id, "threshold": THRESHOLD}).fetchone()
    if row is None:
        return None
    conn.execute("UPDATE spoken_mishearings SET removed_at = ?, confirm_count = 0 WHERE id = ?", (_utcnow(), entry_id))
    conn.commit()
    return {"spoken": row["spoken"], "heard": row["heard"]}


def record_links(conn, doctor_id, diagnosis_keys: Sequence[str], term_refs: Sequence[tuple[str, str]], document_id) -> int:
    """Make this DOCUMENT's diagnosis-term links exactly ``diagnosis_keys`` x ``term_refs`` (``[(kind, term_key)]``).

    What the document counted before is taken back first (its ``term_link_docs`` rows go, each link's count drops, to 0
    at least), so a re-save replaces its links. A term this doctor has not recorded is skipped. Returns the pairs
    counted now that this document had not counted before: the same set again gives 0.

    COMMITS what the caller has open first, then all of its own writes or none of them (a failure rolls back and raises)."""
    if conn.in_transaction:                       # so the rollback below can only undo this call's own writes
        conn.commit()
    try:
        before = {r[0] for r in conn.execute("SELECT link_id FROM term_link_docs WHERE document_id = ?", (document_id,))}
        for lid in before:
            conn.execute("DELETE FROM term_link_docs WHERE link_id = ? AND document_id = ?", (lid, document_id))
            conn.execute("UPDATE term_links SET count = MAX(count - 1, 0) WHERE id = ?", (lid,))
        now, fresh = _utcnow(), 0
        tids = []
        for kind, term_key in dict.fromkeys(term_refs):
            row = conn.execute("SELECT id FROM spoken_terms WHERE doctor_id = ? AND kind = ? AND term_key = ?",
                               (doctor_id, kind, term_key)).fetchone()
            if row is not None:
                tids.append(row[0])
        for dkey in dict.fromkeys(k for k in diagnosis_keys if k):
            for tid in tids:
                conn.execute("INSERT OR IGNORE INTO term_links(doctor_id, diagnosis_key, term_id, last_seen_at)"
                             " VALUES (?, ?, ?, ?)", (doctor_id, dkey, tid, now))
                lid = conn.execute("SELECT id FROM term_links WHERE doctor_id = ? AND diagnosis_key = ? AND term_id = ?",
                                   (doctor_id, dkey, tid)).fetchone()[0]
                conn.execute("INSERT INTO term_link_docs(link_id, document_id) VALUES (?, ?)", (lid, document_id))
                conn.execute("UPDATE term_links SET count = count + 1, last_seen_at = ? WHERE id = ?", (now, lid))
                fresh += lid not in before
        conn.commit()
        return fresh
    except BaseException:
        conn.rollback()
        raise


def linked_term_ids(conn, doctor_id, diagnosis_keys: Sequence[str]) -> set[int]:
    """The ids of this doctor's live terms (a use left, not removed) linked to any of the keys by LINK_MIN documents."""
    keys = list(dict.fromkeys(diagnosis_keys))[:CONTEXT_LINES]
    if not keys:
        return set()
    marks = ", ".join("?" * len(keys))
    return {r[0] for r in conn.execute(
        "SELECT DISTINCT l.term_id FROM term_links l JOIN spoken_terms t ON t.id = l.term_id"
        f" WHERE l.doctor_id = ? AND l.count >= ? AND t.removed_at IS NULL AND t.uses > 0 AND l.diagnosis_key IN ({marks})",
        (doctor_id, LINK_MIN, *keys))}


def patient_candidates(conn, doctor_id: int) -> list:
    """Rows (id, name, age_sex, op_no) of the patients this doctor has seen, by id. ``doctor_id`` 0 (single-database
    mode) has no doctor filter: every patient."""
    if doctor_id > 0:
        return conn.execute("SELECT id, name, age_sex, op_no FROM patients WHERE id IN "
                            "(SELECT patient_id FROM encounters WHERE doctor_id = ?) ORDER BY id", (doctor_id,)).fetchall()
    return conn.execute("SELECT id, name, age_sex, op_no FROM patients ORDER BY id").fetchall()


def patient_term_keys(conn, patient_ids, doctor_id: int, visits: int = 3) -> set[str]:
    """Keys of the terms in a patient's last ``visits`` finalized documents (``patient_ids``: one id or a person's rows).

    Only this doctor's visits count; ``doctor_id`` 0 (single-database mode) has no doctor filter. A document whose JSON
    does not parse to a dict adds nothing."""
    ids = (patient_ids,) if isinstance(patient_ids, int) else tuple(patient_ids)
    if not ids:
        return set()
    sql = ("SELECT d.structured_json FROM documents d JOIN encounters e ON e.id = d.encounter_id "
           f"WHERE e.patient_id IN ({','.join('?' * len(ids))}) AND d.finalized_at IS NOT NULL")
    args = list(ids)
    if doctor_id > 0:
        sql += " AND e.doctor_id = ?"
        args.append(doctor_id)
    rows = conn.execute(sql + " ORDER BY d.created_at DESC, d.id DESC LIMIT ?", (*args, max(0, int(visits)))).fetchall()
    keys: set[str] = set()
    for (raw,) in rows:
        try:
            form = json.loads(raw)
            if isinstance(form, dict):
                keys |= {t.key for t in terms_from_save(form, frozenset())}
        except (TypeError, ValueError):
            continue
    return keys
