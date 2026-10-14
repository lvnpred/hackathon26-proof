"""Auth routes: login, logout, me, change-password, and the login page. 404 when MULTI_CLINIC is off."""
import asyncio
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from doctor_dictation import accounts, authn
from doctor_dictation import db as dbmod
from doctor_dictation.passwords import PasswordError
from doctor_dictation.scope import multi_clinic_enabled
from doctor_dictation.sessions import COOKIE_NAME, LIFETIME_SECONDS, sign

router = APIRouter()
_LOGIN_SLOTS = asyncio.Semaphore(4)       # a login flood must not starve the thread pool every signed-in request uses
LOGIN_PAGE = Path(__file__).resolve().parents[2] / "frontend" / "login.html"
OFF = {"error": "sign-in is not enabled"}
BAD_LOGIN = {"error": "Wrong username or password"}


class LoginBody(BaseModel):
    username: str = Field("", max_length=256)
    password: str = Field("", max_length=1024)


class ChangeBody(BaseModel):
    current_password: str = Field("", max_length=1024)
    new_password: str = Field("", max_length=1024)


def _is_https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or proto == "https"


def _set_cookie(response, request: Request, ident_or_parts) -> None:
    clinic, uid, version = ident_or_parts
    response.set_cookie(COOKIE_NAME, sign(clinic, uid, version), max_age=LIFETIME_SECONDS, httponly=True,
                        samesite="lax", path="/", secure=_is_https(request))


@router.get("/login")
def login_page():
    if not multi_clinic_enabled():
        return JSONResponse(status_code=404, content=OFF)
    return FileResponse(LOGIN_PAGE)


@router.post("/api/v1/auth/login")
async def login(request: Request, body: LoginBody):
    if not multi_clinic_enabled():
        return JSONResponse(status_code=404, content=OFF)
    ip = request.client.host if request.client else "unknown"
    failed = getattr(request.app.state, "failed_clinics", frozenset())
    try:
        async with _LOGIN_SLOTS:
            ident = await asyncio.to_thread(authn.authenticate, body.username, body.password, ip, None, failed)
    except sqlite3.Error:                                          # e.g. a locked clinic database: never a "wrong password"
        return JSONResponse(status_code=503, content={"error": "try again"})
    if ident is None:
        return JSONResponse(status_code=401, content=BAD_LOGIN)
    response = JSONResponse({"ok": True, "must_change_password": ident.must_change_password})
    _set_cookie(response, request, (ident.clinic_slug, ident.user_id, ident.session_version))
    return response


@router.post("/api/v1/auth/logout")
async def logout(request: Request):
    if not multi_clinic_enabled():
        return JSONResponse(status_code=404, content=OFF)
    ident = request.state.identity

    def _audit():
        with closing(dbmod.get_conn()) as conn:                    # scope set by the middleware
            dbmod.log_audit(conn, action="logout", entity="user", entity_id=str(ident.user_id))

    await asyncio.to_thread(_audit)
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/api/v1/auth/me")
async def me(request: Request):
    if not multi_clinic_enabled():
        return JSONResponse(status_code=404, content=OFF)
    i = request.state.identity
    name = await asyncio.to_thread(authn.clinic_name, i.clinic_slug)
    return {"clinic_slug": i.clinic_slug, "clinic_name": name, "username": i.username,
            "display_name": i.display_name, "role": i.role, "must_change_password": i.must_change_password}


@router.post("/api/v1/auth/change-password")
async def change_password(request: Request, body: ChangeBody):
    if not multi_clinic_enabled():
        return JSONResponse(status_code=404, content=OFF)
    i = request.state.identity
    try:
        version = await asyncio.to_thread(accounts.change_password, i, body.current_password, body.new_password)
    except (PasswordError, accounts.AccountError) as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except sqlite3.Error:
        return JSONResponse(status_code=503, content={"error": "try again"})
    response = JSONResponse({"ok": True})
    _set_cookie(response, request, (i.clinic_slug, i.user_id, version))       # the old cookie is now revoked
    return response
