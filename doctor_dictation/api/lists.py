"""The clinic's list screen: read the shipped lists with the clinic's changes, and let a clinic admin change them (plan PQ-f).

Every write is checked by ``overlay.conflicts`` first (the read path runs the same procedure, so a write it would refuse
there is refused here with the reason), needs ``formulary.manage`` and leaves one ``audit_log`` row. Data stays in the
clinic's own database (the request scope picks it); the lists a request matches against are loaded per request
(``use_clinic_layer``), so the next request sees the change.
"""
import logging
import sqlite3
from contextlib import closing
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from doctor_dictation import db as dbmod
from doctor_dictation import policy
from doctor_dictation.api import authorship
from doctor_dictation.api.formulary import DENIED
from doctor_dictation.core import formulary, overlay
from doctor_dictation.db import formulary as fdb
from doctor_dictation.db import overlay as odb
from doctor_dictation.scope import multi_clinic_enabled

router = APIRouter()
log = logging.getLogger(__name__)


class Change(BaseModel):
    op: Literal["add", "edit", "hide", "reset", "keep-mine", "take-new", "approve"]
    entry_key: str = Field(min_length=1, max_length=60)
    data: dict = {}


class Refused(Exception):
    def __init__(self, status: int, message: str, reasons: list | None = None):
        super().__init__(message)
        self.status, self.body = status, {"error": message, **({"reasons": reasons} if reasons else {})}


def _busy() -> JSONResponse:
    return JSONResponse(status_code=503, content={"error": "try again"})


def _screen(conn, kind: str) -> list:
    learned = fdb.list_active(conn) if kind == "medicine" else []
    return overlay.screen_rows(kind, overlay.shipped(kind), odb.list_rows(conn, kind), learned,
                               odb.list_rows(conn, kind, pending=True))


@router.get("/api/v1/lists/{kind}")
def show(kind: str):
    if kind not in overlay.KINDS:
        return JSONResponse(status_code=404, content={"error": "no such list"})
    try:
        with closing(dbmod.get_conn()) as conn:
            items = _screen(conn, kind)
    except sqlite3.Error:
        log.warning("clinic list: read failed", exc_info=True)
        return _busy()
    return {"kind": kind, "items": items, "flags": sum(1 for i in items if i["flag"]),
            "pending": sum(1 for i in items if i["pending"])}


def _check(kind, shipped, active, row) -> None:
    why = overlay.conflicts(kind, shipped, active, row)
    if why:
        raise Refused(409, why[0], why)


def _write(conn, kind, key, action, data, base_sha, user_id, active, shipped) -> None:
    clean = overlay.validate_data(kind, action, data)          # ValueError -> 400
    _check(kind, shipped, active, {"entry_key": key, "action": action, "data": clean, "base_sha": base_sha})
    odb.upsert(conn, kind, key, action, clean, base_sha, "admin", user_id, commit=False)


def _flag(kind, shipped, active, key) -> tuple:
    """(flag, inert): the row's flag as the screen shows it; ``inert`` when the read path sets the row aside (a later
    shipped list conflicts with it), which the screen flags "shipped-changed" too."""
    if key in overlay.refused_rows(kind, shipped, active):
        return overlay.SHIPPED_CHANGED, True
    return next((f["reason"] for f in overlay.effective_entries(kind, shipped, active)[1] if f["entry_key"] == key), ""), False


def _apply(conn, kind, ch: Change, user_id):
    """Do the change; returns (audit action, row before, data after). Raises Refused / ValueError."""
    key, data, shipped = ch.entry_key, ch.data, overlay.shipped(kind)
    active = odb.list_rows(conn, kind)
    by_key = {overlay.entry_key_of(e): e for e in shipped if isinstance(e, dict) and e.get("canonical")}
    mine = {r["entry_key"]: r for r in active}
    pending = {r["entry_key"]: r for r in odb.list_rows(conn, kind, pending=True)}
    before, base = mine.get(key) or pending.get(key), by_key.get(key)
    own_add = next((r for r in (mine.get(key), pending.get(key)) if r and r["action"] == "add"), None)
    op = ch.op
    if op == "add":
        clean = overlay.validate_data(kind, "add", data)
        if formulary.key(clean["name"]) != key:
            raise Refused(400, f"The entry key {key!r} does not match the name {clean['name']!r}")
        if base is not None:
            hidden = key in mine and mine[key]["action"] == "hide"
            raise Refused(409, f"'{clean['name']}' is hidden from the shared list: use Reset to bring it back" if hidden
                          else f"'{clean['name']}' is already in the shared list: edit it")
        _write(conn, kind, key, "add", clean, "", user_id, active, shipped)
        return "list.add", before, clean
    if op == "edit":
        if base is None and own_add is None:
            raise Refused(404, "no such entry")
        action, sha = ("edit", overlay.entry_sha(base)) if base is not None else ("add", "")
        _write(conn, kind, key, action, data, sha, user_id, active, shipped)
        return "list.edit", before, overlay.validate_data(kind, action, data)
    if op == "hide":
        if own_add is not None and base is None:
            raise Refused(409, "This is your own addition \u2014 use Reset to remove it")
        if base is None:
            raise Refused(404, "no such entry")
        _write(conn, kind, key, "hide", ch.data, overlay.entry_sha(base) if base is not None else "", user_id, active, shipped)
        return "list.hide", before, {}
    if op == "approve":
        row = pending.get(key)
        if row is None:
            raise Refused(404, "no pending suggestion for this entry")
        _check(kind, shipped, active, row)
        if not odb.approve(conn, kind, key, user_id, commit=False):
            raise Refused(404, "no pending suggestion for this entry")
        return "list.approve", row, row["data"]
    if op == "reset":
        if before is None:
            raise Refused(404, "nothing to reset")
        if not odb.reset(conn, kind, key, commit=False):
            raise Refused(404, "nothing to reset")
        return "list.reset", before, None
    if key not in mine:                                      # keep-mine / take-new act on a stored row
        raise Refused(404, "nothing to change for this entry")
    flag, inert = _flag(kind, shipped, active, key)
    if op == "take-new":
        if not flag:
            raise Refused(409, "This entry has no shared change to take")
        if not odb.reset(conn, kind, key, commit=False):
            raise Refused(404, "nothing to reset")
        return "list.take-new", before, None
    if flag != overlay.SHIPPED_CHANGED:                      # keep-mine
        raise Refused(409, "This entry has no shared change to keep your version over")
    row = mine[key]
    over = row["action"] == "add" and bool(row.get("base_sha"))     # an add over a shipped name: re-stamp its sha
    if base is None and not (inert and row["action"] == "add") and not over:
        raise Refused(409, "The shared entry is gone: use Reset")
    sha = overlay.claimant_sha(shipped, row["data"].get("name", "")) if over else \
        overlay.entry_sha(base) if base is not None else ""
    # re-checked like any write: a row that still conflicts is refused (409) with the reason
    _write(conn, kind, key, row["action"], row["data"], sha, user_id, active, shipped)
    return "list.keep-mine", before, row["data"]


def _locked_change(conn, kind, body: Change, user_id):
    """Read, check, write and audit under one write lock and one commit: two admins cannot both pass a check against the
    same rows, and a failed audit row leaves no change behind (the pattern of ``odb.record_confirmation``)."""
    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        action, before, after = _apply(conn, kind, body, user_id)
        dbmod.log_audit(conn, action=action, entity="list." + kind, entity_id=body.entry_key,
                        detail={"before": before, "after": after}, commit=False)
        item = next((i for i in _screen(conn, kind) if i["entry_key"] == body.entry_key), None)
        conn.commit()
        return item
    except BaseException:
        conn.rollback()
        raise


@router.post("/api/v1/lists/{kind}/changes")
def change(request: Request, kind: str, body: Change):
    """Clinic admins only. Answers the changed item (None when the change removed it)."""
    ident = authorship.identity(request)
    if ident is None and multi_clinic_enabled():
        return JSONResponse(status_code=401, content={"error": "sign in required"})
    if ident is not None and not policy.can(ident, "formulary.manage"):
        return JSONResponse(status_code=403, content=DENIED)
    if kind not in overlay.KINDS:
        return JSONResponse(status_code=404, content={"error": "no such list"})
    try:
        with closing(dbmod.get_conn()) as conn:
            item = _locked_change(conn, kind, body, ident.user_id if ident else None)
    except Refused as e:
        return JSONResponse(status_code=e.status, content=e.body)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except sqlite3.Error:
        log.warning("clinic list: write failed", exc_info=True)
        return _busy()
    return {"item": item}
