"""The doctor's usual medicines for a diagnosis (plan SH-B6). Read-only; the doctor comes only from the session.

A POST, so the diagnosis text stays out of the URL (and the proxy's access log); it is never logged either."""
import asyncio
import logging
import sqlite3
from contextlib import closing
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from doctor_dictation import db as dbmod
from doctor_dictation.api import authorship
from doctor_dictation.api.formulary import _busy, use_clinic_layer
from doctor_dictation.core import formulary, spoken
from doctor_dictation.core.determinism import is_blocked
from doctor_dictation.core.your_usual import MAX_PER_LINE, USUAL_DOCS, pick, usual_row
from doctor_dictation.db import formulary as fdb
from doctor_dictation.db import spoken as sdb
from doctor_dictation.scope import multi_clinic_enabled

router = APIRouter()
log = logging.getLogger(__name__)


class UsualRequest(BaseModel):
    diagnosis: Any = None      # validated by hand so every failure is the same 400 {"error": ...}


def _problem(req: UsualRequest):
    lines = req.diagnosis
    if not (isinstance(lines, list) and len(lines) <= spoken.CONTEXT_LINES
            and all(isinstance(x, str) and len(x) <= spoken.CONTEXT_CHARS for x in lines)):
        return (f"diagnosis must be a list of at most {spoken.CONTEXT_LINES} lines of text, "
                f"each at most {spoken.CONTEXT_CHARS} characters")
    return None


def _lookup(lines: list[str], doctor_id: int) -> list[dict]:
    seen: set[str] = set()
    found = []
    with closing(dbmod.get_conn()) as conn:
        removed = fdb.removed_keys(conn)
        for index, line in enumerate(lines):
            dkey = spoken.diagnosis_key(line)
            if not dkey or dkey in seen:
                continue
            seen.add(dkey)
            rows = []
            for link in sdb.diagnosis_medicine_links(conn, doctor_id, dkey, 2 * MAX_PER_LINE):
                name = link["spoken"]
                if is_blocked(name) or formulary.key(name) in removed:
                    continue
                row = usual_row(link["term_key"], name, link["generic"], link["count"],
                                sdb.link_document_forms(conn, link["link_id"], USUAL_DOCS))
                if row is not None:
                    rows.append(row)
                if len(rows) >= MAX_PER_LINE:
                    break
            found.append((index, rows))
    return pick(found)


@router.post("/api/v1/spoken/usual", dependencies=[Depends(use_clinic_layer)])
async def usual(request: Request, req: UsualRequest):
    ident = authorship.identity(request)
    if ident is None and multi_clinic_enabled():
        return JSONResponse(status_code=401, content={"error": "sign in required"})
    problem = _problem(req)
    if problem:
        return JSONResponse(status_code=400, content={"error": problem})
    try:
        return {"groups": await asyncio.to_thread(_lookup, req.diagnosis, ident.user_id if ident else 0)}
    except sqlite3.Error:
        log.warning("your usual: lookup failed", exc_info=True)        # never the diagnosis
        return _busy()
