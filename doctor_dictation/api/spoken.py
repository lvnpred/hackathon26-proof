"""The save hook for the doctor's spoken terms (plan SH-H1). The prescription is already saved when this runs."""
import json
import logging

from doctor_dictation.core import spoken
from doctor_dictation.db import formulary as fdb
from doctor_dictation.db import spoken as sdb

log = logging.getLogger(__name__)


def _form(raw):
    """A saved form: the dict itself, or read from its stored JSON; None when unreadable."""
    if isinstance(raw, (str, bytes)):
        try:
            raw = json.loads(raw)
        except ValueError:
            return None
    return raw if isinstance(raw, dict) else None


def record_from_save(conn, structured, document_id, doctor_id, patient_words=None, previous=None) -> int:
    """What one saved form teaches, counted once per document for ``doctor_id``. Returns the terms counted now.

    The one place a save teaches spoken terms (contract 5.5): the save hook and the backfill both call it, and H2/H3
    add theirs here. ``previous`` (a re-save: the form saved before, a dict or its JSON) is taken back first.
    ``patient_words`` is read from the clinic's patients when not given, and only when a form has a term at all.
    COMMITS (``record_terms`` does) and RAISES on a database error, after rolling its own writes back."""
    previous = _form(previous)
    if not (spoken.terms_from_save(structured, ()) or spoken.terms_from_save(previous, ())):
        return 0
    words = fdb.patient_words(conn) if patient_words is None else patient_words
    return sdb.record_terms(conn, doctor_id, spoken.terms_from_save(structured, words), document_id,
                            previous=spoken.terms_from_save(previous, words))


def learn_spoken_terms(conn, structured, document_id, user_id, patient_words=None, previous=None) -> None:
    """``record_from_save`` for this doctor (``user_id or 0``), called by every save.

    Never raises, so it never blocks the save (S4): any error is logged and the connection rolled back."""
    try:
        record_from_save(conn, structured, document_id, user_id or 0, patient_words=patient_words, previous=previous)
    except Exception:  # noqa: BLE001 - learning is a convenience, the prescription is already saved
        log.warning("spoken terms: could not record terms", exc_info=True)
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001 - a failing rollback must not raise either
            log.warning("spoken terms: rollback failed", exc_info=True)


def replay_saved(conn, by_doctor: bool) -> tuple[int, int]:
    """Count every finalized document's terms (the backfill). Returns (documents read, new term uses).

    ``by_doctor`` credits each document's author (its encounter's doctor, NULL is 0); otherwise doctor 0.
    A document with unreadable JSON is skipped. The ledger makes a second run count nothing. Unlike the save hook
    this RAISES on a database error (``record_from_save`` rolls its own document back), so the operator sees it."""
    words = fdb.patient_words(conn)
    uses = "SELECT COALESCE(SUM(uses), 0) FROM spoken_terms"
    before = conn.execute(uses).fetchone()[0]
    rows = conn.execute("SELECT d.id, d.structured_json, e.doctor_id FROM documents d JOIN encounters e ON e.id = d.encounter_id"
                        " WHERE d.finalized_at IS NOT NULL AND d.structured_json IS NOT NULL ORDER BY d.id").fetchall()
    read = 0
    for doc_id, raw, doctor_id in rows:
        structured = _form(raw)
        if structured is None:
            continue
        read += 1
        record_from_save(conn, structured, doc_id, (doctor_id if by_doctor else None) or 0, patient_words=words)
    return read, conn.execute(uses).fetchone()[0] - before
