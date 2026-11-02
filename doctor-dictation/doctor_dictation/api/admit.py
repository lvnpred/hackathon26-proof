"""Save & admit to ward: record the admission after the save commits, then push it to Count Guard (spec §6.1, §7.1).

The push runs in a background task with a 1 s connect / 3 s total timeout per attempt (up to 3 attempts for a
connection error or 5xx), so a slow or absent Count Guard never undoes or slows the save; a failure
is stored in ``admissions.last_error`` and Count Guard's Sync pulls the same
payload later through ``GET /api/v1/admissions`` (§7.3). Intake is single-clinic only (§7.4).

``COUNT_GUARD_URL`` and ``CG_SYNC_TOKEN`` are read from the environment at call time; the token is never logged.
"""
import hmac
import json
import logging
import os
import re
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, Request
from fastapi.responses import JSONResponse

from doctor_dictation import db as dbmod
from doctor_dictation.api.pastday import is_past, visit_day_iso
from doctor_dictation.db import authorship as adb
from doctor_dictation.scope import multi_clinic_enabled

log = logging.getLogger(__name__)
router = APIRouter()

SOURCE = "doctor-dictation"
TIMEOUT = httpx.Timeout(3.0, connect=1.0)
DEFAULT_COUNT_GUARD_URL = "http://127.0.0.1:8100"      # Count Guard's dev API port (count-guard/Makefile CG_API_PORT)
TOKEN_HEADER = "X-CG-Sync-Token"
BACKOFF = (0.5, 1.5)                                   # seconds before the 2nd and 3rd push attempt
_sleep = time.sleep                                    # tests replace this
# Hosts counted as this machine when CG_SYNC_TOKEN is unset. Tests pass client=("127.0.0.1", 50000) to TestClient,
# whose default host "testclient" is refused like any other.
LOOPBACK = frozenset({"127.0.0.1", "::1"})
_SINCE = re.compile(r"\d{4}-\d{2}-\d{2}([T ][0-9:.]+Z?)?")


def count_guard_url() -> str:
    return (os.getenv("COUNT_GUARD_URL", "").strip() or DEFAULT_COUNT_GUARD_URL).rstrip("/")


def sync_token() -> str:
    return os.getenv("CG_SYNC_TOKEN", "").strip()


def reason_refusal(admit: bool, reason: str):
    """422 when the doctor asks to admit with no reason; None otherwise. Runs before the verify gate."""
    if admit and not (reason or "").strip():
        return JSONResponse(status_code=422, content={"error": "admission reason required"})
    return None


def _document_body(conn, row) -> dict:
    """The body GET /api/v1/documents/{id} returns, plus the author's printed doctor fields (no viewer needed)."""
    author = adb.document_author(conn, row["id"]) or {}
    return {
        "document_id": row["id"],
        "structured": json.loads(row["structured_json"]) if row["structured_json"] else {},
        "engine": row["engine"] or "",
        "transcript_sha256": row["transcript_sha"],
        "created_at": row["created_at"],
        "visit_date": visit_day_iso(row),
        "past": is_past(row),
        "author": {"user_id": author.get("author_id"), "name": author.get("name", ""),
                   **{k: author.get(k, "") for k in ("doctor_name", "qualifications", "reg_no")}},
    }


def payload_for(conn, document_id: int) -> dict | None:
    """The spec §7.1 body for one admitted document (None when there is no admission or no document)."""
    adm = conn.execute("SELECT status, reason FROM admissions WHERE document_id = ?", (document_id,)).fetchone()
    row = dbmod.get_document(conn, document_id)
    if adm is None or row is None:
        return None
    return {
        "source": SOURCE,
        "document_id": row["id"],
        "status": adm["status"],
        "admit_reason": adm["reason"] or "",
        "finalized_at": row["finalized_at"],          # stored text, never reformatted: Count Guard compares it as text
        "document": _document_body(conn, row),
    }


def _record(conn, document_id: int, admit: bool, reason: str, resave: bool) -> bool:
    """Write the admission row; False when this save sends nothing (a never-admitted document, U12)."""
    if admit:
        conn.execute(
            "INSERT INTO admissions (document_id, status, reason, admitted_at) VALUES (?, 'admit', ?, ?)"
            " ON CONFLICT(document_id) DO UPDATE SET status = 'admit', reason = excluded.reason,"
            " pushed_at = NULL, last_error = NULL",
            (document_id, reason.strip(), dbmod._utcnow()))
    elif resave:
        cur = conn.execute("UPDATE admissions SET status = 'send_home', pushed_at = NULL, last_error = NULL"
                           " WHERE document_id = ?", (document_id,))
        if cur.rowcount == 0:
            return False
    else:
        return False
    conn.commit()
    return True


def after_save(request: Request | None, background_tasks: BackgroundTasks, *, document_id: int, admit: bool,
               reason: str, resave: bool) -> None:
    """After the save's commit: record the admission and queue the push. Never raises: the save already happened."""
    if multi_clinic_enabled():
        return
    try:
        db = dbmod.db_path()                          # resolved here, inside the request
        conn = dbmod.get_conn(db)
        try:
            if not _record(conn, document_id, admit, reason, resave):
                return
            payload = payload_for(conn, document_id)
        finally:
            conn.close()
        background_tasks.add_task(push, payload, count_guard_url(), sync_token(), db)
    except Exception:
        log.warning("admission for document %s not recorded", document_id, exc_info=True)


def push(payload: dict, url: str, token: str, db: Path) -> None:
    """POST the admission to Count Guard and store the outcome in ``db``. Never raises.

    Up to len(BACKOFF) + 1 attempts, each with TIMEOUT. Only a refused/timed-out connection or a 5xx is retried;
    a 4xx is final (a 422 send_home for a never-admitted patient will not change). ``last_error`` holds the last
    attempt's reason; ``pushed_at`` is set on the first 200/201."""
    pushed_at = last_error = None
    headers = {TOKEN_HEADER: token} if token else {}
    for attempt in range(len(BACKOFF) + 1):
        if attempt:
            _sleep(BACKOFF[attempt - 1])
        retry = False
        try:
            r = httpx.post(url.rstrip("/") + "/journey/intake", json=payload, headers=headers, timeout=TIMEOUT)
            if r.status_code in (200, 201):
                pushed_at, last_error = dbmod._utcnow(), None
                break
            last_error = f"Count Guard answered {r.status_code}"
            retry = r.status_code >= 500
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:   # refused, unreachable, DNS failure: retried
            last_error = f"Count Guard not reached ({type(exc).__name__})"
            retry = True
        except Exception as exc:                      # read timeout or anything else: final; the reason only, never the token
            last_error = f"Count Guard not reached ({type(exc).__name__})"
        if not retry:
            break
    try:
        conn = dbmod.get_conn(db)
        try:
            conn.execute("UPDATE admissions SET pushed_at = ?, last_error = ? WHERE document_id = ? AND status = ?",
                         (pushed_at, last_error, payload["document_id"], payload["status"]))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        log.warning("push outcome for document %s not stored", payload.get("document_id"), exc_info=True)


@router.get("/api/v1/documents/{document_id}/admission")
def admission_status(document_id: int):
    """What the page polls after Save & admit (same origin, no token). Single-clinic only, like the push."""
    if multi_clinic_enabled():
        return JSONResponse(status_code=404, content={"error": "not found"})
    conn = dbmod.get_conn()
    try:
        row = conn.execute("SELECT status, pushed_at, last_error FROM admissions WHERE document_id = ?",
                           (document_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return JSONResponse(status_code=404, content={"error": f"no admission for document_id {document_id}"})
    return {"status": row["status"], "pushed_at": row["pushed_at"], "last_error": row["last_error"]}


@router.get("/api/v1/admissions")
def list_admissions(request: Request, since: str | None = None, x_cg_sync_token: str | None = Header(default=None)):
    """Count Guard's Sync: every admission whose document was saved at or after ``since`` (all when absent).
    With CG_SYNC_TOKEN unset only this machine may ask; any other host gets 403."""
    if multi_clinic_enabled():
        return JSONResponse(status_code=404, content={"error": "not found"})
    expected = sync_token()
    if not expected and (request.client.host if request.client else "") not in LOOPBACK:
        return JSONResponse(status_code=403, content={"error": "set CG_SYNC_TOKEN to accept other hosts"})
    if expected and not hmac.compare_digest((x_cg_sync_token or "").encode(), expected.encode()):
        return JSONResponse(status_code=401, content={"error": "sync token missing or wrong"})
    if since is not None and not _SINCE.fullmatch(since.strip()):
        return JSONResponse(status_code=422, content={"error": "since must be an ISO date-time"})
    conn = dbmod.get_conn()
    try:
        ids = [r["document_id"] for r in conn.execute(
            "SELECT a.document_id FROM admissions a JOIN documents d ON d.id = a.document_id"
            " WHERE ? IS NULL OR d.finalized_at >= ? ORDER BY a.document_id",
            (since and since.strip(), since and since.strip()))]
        return {"admissions": [p for p in (payload_for(conn, i) for i in ids) if p is not None]}
    finally:
        conn.close()
