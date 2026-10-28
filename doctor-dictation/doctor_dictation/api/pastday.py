"""A document's visit day, and the past-day rule (UI-A Task 1): a prescription from an earlier clinic day is view and
reprint only. The page locks it (``past`` on GET /api/v1/documents/{id}); the server refuses its re-save (409)."""
from datetime import datetime

from fastapi.responses import JSONResponse

from doctor_dictation import db as dbmod
from doctor_dictation.api import visit


def visit_day(row):
    """The document's visit day: the clinic-zone day of its created_at (fixed at first save). None when absent or unreadable."""
    try:
        return visit.to_clinic(datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))).date()
    except (ValueError, TypeError, KeyError, IndexError):
        return None


def visit_day_iso(row) -> str:
    day = visit_day(row)
    return day.isoformat() if day else ""


def is_past(row) -> bool:
    """True when the document's visit day is before the clinic's today; an unknown visit day is not past."""
    day = visit_day(row)
    return day is not None and day < visit.today()


def past_refusal(document_id):
    """A re-save of an earlier day's prescription: 409, nothing written (past prescriptions are view and reprint
    only). None for today's, and for a missing document (the 404 further on says so)."""
    conn = dbmod.get_conn()
    try:
        row = dbmod.get_document(conn, document_id)
    finally:
        conn.close()
    if row is None or not is_past(row):
        return None
    return JSONResponse(status_code=409, content={"error": "past prescription", "hint": (
        f"This prescription is from {visit.date_text(visit_day(row))}. Past prescriptions are view and reprint only; "
        "start a new visit to change the treatment.")})
