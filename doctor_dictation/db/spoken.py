"""The doctor's spoken terms (plan SH-H1). SQL only; what a term is, and how it is phrased and ranked, lives in core/spoken.py."""
from collections import defaultdict
from collections.abc import Sequence
from datetime import date

from doctor_dictation.core.formulary import usage_score
from doctor_dictation.core.spoken import HintTerm, Term, phrase, usual_strength
from doctor_dictation.db import _utcnow


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
