"""The app owner's review of the shipped lists (plan PQ-f, Task 9). Offline.

The owner proposes changes to the shipped medicine and investigation lists. They wait in one JSON file under the data
root (shared by every clinic) until the owner exports them; an operator command folds the export into the repo's JSON.
Every route answers 404 unless the caller is an owner in multi-clinic mode (the screen's existence is not revealed).
"""
import fcntl
import json
import logging
import sqlite3
import threading
from contextlib import closing, contextmanager
from datetime import date
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from doctor_dictation import db as dbmod
from doctor_dictation import policy
from doctor_dictation.api import authorship
from doctor_dictation.core import formulary, overlay
from doctor_dictation.promotion import write_atomic
from doctor_dictation.scope import data_root

router = APIRouter()
log = logging.getLogger(__name__)
_LOCK = threading.Lock()
NOT_FOUND = {"error": "not found"}


def pending_path():
    return data_root() / "owner" / "list-changes.json"


class OwnerChange(BaseModel):
    op: Literal["add", "edit", "drop"]
    entry_key: str = Field(min_length=1, max_length=60)
    data: dict = {}


class Refused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.body = status, {"error": message}


class Unreadable(Exception):
    """The pending file exists but cannot be read or parsed."""


def _read(strict: bool = False) -> dict:
    """The pending changes. A missing file is empty. An unreadable, malformed or wrongly shaped file is logged and
    treated as empty, or (``strict``, for a write) raises Unreadable so the file is never overwritten. Call under _LOCK."""
    empty = {k: [] for k in overlay.KINDS}
    path = pending_path()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            raise ValueError("not an object")
    except FileNotFoundError:
        return empty
    except (OSError, ValueError):
        log.warning("owner lists: %s is unreadable", path, exc_info=True)
        if strict:
            raise Unreadable(str(path))
        return empty
    out = {}
    for kind in overlay.KINDS:
        rows = doc.get(kind)
        out[kind] = [r for r in rows if isinstance(r, dict) and isinstance(r.get("entry_key"), str)
                     and r.get("action") in ("add", "edit") and isinstance(r.get("data"), dict)] \
            if isinstance(rows, list) else []
    return out


def _write(doc: dict) -> None:
    path = pending_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


@contextmanager
def _exclusive():
    """One writer at a time across threads (_LOCK) and across worker processes (flock on a sibling lock file)."""
    path = pending_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, open(path.with_name("list-changes.lock"), "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _gate(request: Request, kind: str):
    """The owner identity, or the response to return."""
    ident = authorship.identity(request)
    if ident is None or not policy.is_owner(ident):
        return None, JSONResponse(status_code=404, content=NOT_FOUND)
    if kind not in overlay.KINDS:
        return None, JSONResponse(status_code=404, content={"error": "no such list"})
    return ident, None


def _shipped_by_key(kind: str) -> dict:
    return {overlay.entry_key_of(e): e for e in overlay.shipped(kind) if isinstance(e, dict) and e.get("canonical")}


@router.get("/api/v1/owner/lists/{kind}")
def show(request: Request, kind: str):
    _ident, bad = _gate(request, kind)
    if bad:
        return bad
    with _LOCK:
        pending = {r["entry_key"]: r for r in _read()[kind]}
    shipped = _shipped_by_key(kind)
    return {"kind": kind,
            "items": [{"entry_key": k, "entry": e, "pending": pending.get(k)} for k, e in shipped.items()],
            "pending": sorted((r for k, r in pending.items() if k not in shipped), key=lambda r: r["entry_key"])}


def _apply(kind: str, ch: OwnerChange) -> tuple:
    """Update the pending file under the lock; returns (audit action, before, after)."""
    key, shipped = ch.entry_key, _shipped_by_key(kind)
    with _exclusive():
        doc = _read(strict=True)
        rows = [r for r in doc[kind] if r["entry_key"] != key]
        before = next((r for r in doc[kind] if r["entry_key"] == key), None)
        after = None
        if ch.op != "drop":
            if ch.op == "add":
                if key in shipped:
                    raise Refused(409, f"{key!r} is already in the shipped list: edit it")
                data = overlay.validate_data(kind, "add", ch.data, owner=True)
                if formulary.key(data["name"]) != key:
                    raise Refused(400, f"The entry key {key!r} does not match the name {data['name']!r}")
            else:
                if key not in shipped:
                    raise Refused(404, "no such entry")
                data = overlay.validate_data(kind, "edit", ch.data, owner=True)
            after = {"action": ch.op, "entry_key": key, "data": data}
            rows.append(after)
        elif len(rows) == len(doc[kind]):
            raise Refused(404, "no pending change for this entry")
        doc[kind] = sorted(rows, key=lambda r: r["entry_key"])
        _write(doc)
    return "owner-list." + ch.op, before, after


@router.post("/api/v1/owner/lists/{kind}/changes")
def change(request: Request, kind: str, body: OwnerChange):
    ident, bad = _gate(request, kind)
    if bad:
        return bad
    try:
        action, before, after = _apply(kind, body)
    except Refused as e:
        return JSONResponse(status_code=e.status, content=e.body)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Unreadable:
        return JSONResponse(status_code=503, content={"error": "try again"})
    except OSError:
        log.warning("owner lists: write failed", exc_info=True)
        return JSONResponse(status_code=503, content={"error": "try again"})
    try:
        with closing(dbmod.get_conn()) as conn:
            dbmod.log_audit(conn, action=action, entity="owner-list." + kind, entity_id=body.entry_key,
                            detail={"before": before, "after": after})
    except sqlite3.Error:
        log.warning("owner lists: audit row not written", exc_info=True)
    return {"change": after}


@router.get("/api/v1/owner/lists/{kind}/export")
def export(request: Request, kind: str):
    _ident, bad = _gate(request, kind)
    if bad:
        return bad
    with _LOCK:
        rows = _read()[kind]
    body = {"kind": kind, "changes": [{"action": r["action"], "entry_key": r["entry_key"], "data": r["data"]} for r in rows]}
    name = f"list-changes-{kind}-{date.today().isoformat()}.json"
    return JSONResponse(content=body, headers={"Content-Disposition": f'attachment; filename="{name}"'})
