"""The clinic's own drug list: learn it on save, serve it to name matching, list it, let an admin remove a name."""
import asyncio
import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse

from doctor_dictation import db as dbmod
from doctor_dictation import policy
from doctor_dictation.api import authorship
from doctor_dictation.core import formulary
from doctor_dictation.db import formulary as fdb
from doctor_dictation.scope import multi_clinic_enabled

router = APIRouter()
log = logging.getLogger(__name__)
DENIED = {"error": "You are not allowed to do that"}
EntryId = Annotated[int, Path(ge=1, le=2**63 - 1)]       # SQLite's INTEGER range; anything else is a 422


def _today():
    """The UTC date the usage ranking counts days from (one place, so a test can pin it)."""
    return datetime.now(timezone.utc).date()


def load_layer() -> formulary.ClinicLayer:
    """This clinic's active names (the scope picks the database). A database problem means an empty layer, logged:
    names then read as unknown (the safe direction) and the request still answers. A missing scope propagates."""
    try:
        with closing(dbmod.get_conn()) as conn:
            return formulary.ranked_layer(fdb.list_active(conn), _today())   # most used first (I1-r1)
    except sqlite3.Error:
        log.warning("clinic formulary unavailable; matching without it", exc_info=True)
        return formulary.ClinicLayer()


async def request_scoped() -> None:
    """App-wide dependency: marks the request so reading the layer without ``use_clinic_layer`` is reported."""
    formulary.mark_request_scoped()


async def use_clinic_layer() -> None:
    """Route dependency: make this clinic's layer the active one for the request.

    Async on purpose: the value is set in the request's own context, which a sync handler's threadpool hop and
    ``asyncio.to_thread`` copy. A bare Thread or ThreadPoolExecutor starts empty and would not see it.
    """
    formulary.activate(await asyncio.to_thread(load_layer))


def learn_from_save(conn, structured, confirmed_rows, document_id, user_id) -> None:
    """Count the doctor's confirmed, unknown names once per saved document. Never blocks the save.

    Only rows the doctor confirmed (``confirmed_rows``) teach anything; names that are words of this clinic's
    patients are skipped (the patients are read only when a name could be learned)."""
    try:
        if not formulary.learnable(structured, confirmed_rows):
            return
        for name, generic in formulary.learnable(structured, confirmed_rows, fdb.patient_words(conn)):
            fdb.record_confirmation(conn, formulary.key(name), name, generic, document_id, user_id)
    except Exception:  # noqa: BLE001 - learning is a convenience, the prescription is already saved
        log.warning("clinic formulary: could not record confirmations", exc_info=True)


def _busy() -> JSONResponse:
    return JSONResponse(status_code=503, content={"error": "try again"})


@router.get("/api/v1/formulary")
def list_formulary():
    try:
        with closing(dbmod.get_conn()) as conn:
            return {"items": fdb.list_active(conn)}
    except sqlite3.Error:
        log.warning("clinic formulary: list failed", exc_info=True)
        return _busy()


@router.delete("/api/v1/formulary/{entry_id}")
def remove_entry(request: Request, entry_id: EntryId):
    """Clinic admins only. An id from another clinic is not in this database, so it answers 404."""
    ident = authorship.identity(request)
    if ident is None and multi_clinic_enabled():
        return JSONResponse(status_code=401, content={"error": "sign in required"})
    if ident is not None and not policy.can(ident, "formulary.manage"):
        return JSONResponse(status_code=403, content=DENIED)
    try:
        with closing(dbmod.get_conn()) as conn:
            name = fdb.remove(conn, entry_id)
            if name is None:
                return JSONResponse(status_code=404, content={"error": "no such medicine"})
            dbmod.log_audit(conn, action="formulary.remove", entity="formulary", entity_id=str(entry_id),
                            detail={"name": name})
    except sqlite3.Error:
        log.warning("clinic formulary: remove failed", exc_info=True)
        return _busy()
    return {"removed": entry_id, "name": name}
