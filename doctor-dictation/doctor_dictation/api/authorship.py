"""The ownership answer every document route gives (spec 7.1). Routes call ``policy.can`` through ``check``.

Single-database mode has no signed-in user (``request.state.identity`` is absent), so nothing is checked
and every response keeps its old shape.
"""
from contextlib import closing

from fastapi import Request
from fastapi.responses import JSONResponse

from doctor_dictation import db as dbmod
from doctor_dictation import policy
from doctor_dictation.db import authorship as adb
from doctor_dictation.scope import multi_clinic_enabled


def identity(request: Request):
    """The signed-in ``sessions.Identity`` (multi-clinic mode), or None (single-database mode)."""
    return getattr(request.state, "identity", None)


def forbidden(author_name: str) -> JSONResponse:
    return JSONResponse(status_code=403, content={
        "error": f"This prescription belongs to {author_name}. You can view and reprint it."})


def _signed_out(request: Request):
    """No identity on the request: None in single-database mode (nothing to check). Multi-clinic mode has the
    session middleware set one on every request, so its absence fails closed with the NoScope handler's 401."""
    if multi_clinic_enabled():
        return JSONResponse(status_code=401, content={"error": "sign in required"})
    return None


def check(conn, request: Request, action: str, document_id: int):
    """None when ``action`` is allowed on the document (or there is no such document: the caller answers 404,
    or single-database mode); otherwise the 403 response to return (the 401 in multi-clinic mode with no identity)."""
    ident = identity(request)
    if ident is None:
        return _signed_out(request)
    author = adb.document_author(conn, document_id)
    if author is None or policy.can(ident, action, author):
        return None
    return forbidden(author["name"])


def check_document(request: Request, action: str, document_id: int):
    """``check`` with its own connection (sync routes, or ``asyncio.to_thread`` from async ones)."""
    if identity(request) is None:
        return _signed_out(request)
    with closing(dbmod.get_conn()) as conn:
        return check(conn, request, action, document_id)


def author_view(conn, request: Request, document_id: int) -> dict:
    """The extra keys GET /documents/{id} returns when someone is signed in: who wrote it, and may I edit it."""
    ident = identity(request)
    if ident is None:
        return {}
    author = adb.document_author(conn, document_id)
    shown = {k: author[k] for k in ("doctor_name", "qualifications", "reg_no")}
    return {"author": {"user_id": author["author_id"], "name": author["name"], **shown},
            "can_edit": policy.can(ident, "document.edit", author)}
