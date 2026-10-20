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
from doctor_dictation.core import determinism, doctor_generic, formulary, overlay
from doctor_dictation.db import formulary as fdb
from doctor_dictation.db import overlay as odb
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


def load_overlay() -> overlay.OverlayState:
    """This clinic's ACTIVE overlay rows of both lists (pending rows never reach the effective list). A database problem
    means the empty overlay, logged: the shipped lists then answer and the request still does. A missing scope
    propagates."""
    try:
        with closing(dbmod.get_conn()) as conn:
            return overlay.state_from_rows([r for kind in overlay.KINDS for r in odb.list_rows(conn, kind)])
    except sqlite3.Error:
        log.warning("clinic overlay unavailable; matching against the shipped lists", exc_info=True)
        return overlay.OverlayState()


def _load_clinic() -> tuple:
    return load_layer(), load_overlay()


async def request_scoped() -> None:
    """App-wide dependency: marks the request so reading the layer without ``use_clinic_layer`` is reported."""
    formulary.mark_request_scoped()


async def use_clinic_layer() -> None:
    """Route dependency: make this clinic's layer AND list overlay the active ones for the request (one thread hop).

    Async on purpose: the values are set in the request's own context, which a sync handler's threadpool hop and
    ``asyncio.to_thread`` copy. A sync dependency runs in a copied context, so its activation would be lost silently;
    a bare Thread or ThreadPoolExecutor starts empty and would not see it either.
    """
    layer, state = await asyncio.to_thread(_load_clinic)
    formulary.activate(layer)
    overlay.activate(state)


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


def learn_doctor_generics(conn, structured, confirmed_rows, remember_generics, document_id, user_id) -> None:
    """Count each confirmed, pending doctor generic toward the clinic's medicine list (plan PQ-g), one audit row each.

    Never ``upsert``: ``record_confirmation`` keeps the row pending until ``formulary.THRESHOLD`` documents confirm the
    same generic. It COMMITS, so this runs after the document is saved. The row is an ``add`` keyed by the name: on the
    read path an add takes the name off any shipped entry (Crocin leaves Paracetamol), while an ``edit`` keyed by a brand
    would be refused there (``validate_data`` takes no ``name`` on an edit, and a brand is no entry key). For a shipped
    brand or alias ``base_sha`` records the entry it overrides, so the list screen flags the row "shipped-changed" when
    that entry changes. A name a live admin row owns (count 0) is logged, not audited. A row the read path would refuse (``overlay.conflicts``)
    is logged and not counted. Never blocks the save: any error is logged and swallowed, like ``learn_from_save``."""
    try:
        rows = structured.get("rx") or []
        for index, name, generic in doctor_generic.new_doctor_generics(structured, confirmed_rows, remember_generics):
            entry_key, data = formulary.key(name), {"name": name, "generic": generic}
            base_sha = overlay.claimant_sha(determinism.shipped_lexicon(), name)   # the shipped entry it overrides, or ""
            why = overlay.conflicts("medicine", determinism.shipped_lexicon(), odb.list_rows(conn, "medicine"),
                                    {"entry_key": entry_key, "action": "add", "data": data, "base_sha": base_sha})
            if why:
                log.info("clinic overlay: doctor generic for %r not counted: %s", name, why[0])
                continue
            count = odb.record_confirmation(conn, "medicine", entry_key, "add", data, base_sha, document_id, user_id)
            if count == 0:                              # a live admin row for this name wins: nothing was counted
                log.info("clinic overlay: doctor generic for %r not counted: the clinic's own entry wins", name)
                continue
            suggestion = str(rows[index].get("generic_suggestion") or "")
            dbmod.log_audit(conn, action="generic.doctor", entity="clinic_overlay", entity_id=entry_key,
                            detail={"name": name, "generic": generic, "action": "add", "document_id": document_id,
                                    "count": count, "from_suggestion": generic.casefold() == suggestion.casefold()})
    except Exception:  # noqa: BLE001 - learning is a convenience, the prescription is already saved
        log.warning("clinic overlay: could not record doctor generics", exc_info=True)


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
