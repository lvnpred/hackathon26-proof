"""Team (Users) routes, spec 8.2: list, add, disable, enable and reset the password of users in the signed-in
user's own clinic. Every action asks ``policy.can`` first and is audited by ``accounts``. An id from another
clinic is simply not in this clinic's database, so it answers 404. Everything is 404 when MULTI_CLINIC is off."""
import asyncio
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from doctor_dictation import accounts, policy
from doctor_dictation.directory import DirectoryError
from doctor_dictation.textclean import clean_text
from doctor_dictation.scope import multi_clinic_enabled

router = APIRouter()
OFF = {"error": "sign-in is not enabled"}
DENIED = {"error": "You are not allowed to do that"}
NO_STORE = {"Cache-Control": "no-store"}           # responses carrying a temporary password are never cached
UserId = Annotated[int, Path(ge=1, le=2**63 - 1)]  # SQLite's INTEGER range; anything else is a 422


class NewUserBody(BaseModel):
    username: str = Field("", max_length=64)
    display_name: str = Field("", max_length=120)
    doctor_name: str = Field("", max_length=120)
    qualifications: str = Field("", max_length=120)
    reg_no: str = Field("", max_length=120)


def _gate(request: Request, action: str, resource=None):
    """``(identity, None)`` when the call may go ahead, else ``(None, error response)``."""
    if not multi_clinic_enabled():
        return None, JSONResponse(status_code=404, content=OFF)
    identity = request.state.identity                  # set by SessionMiddleware for every non-public path
    if not policy.can(identity, action, resource):
        return None, JSONResponse(status_code=403, content=DENIED)
    return identity, None


async def _call(fn, *args):
    """Run an accounts call off the event loop (the clinic scope follows ``to_thread``).
    Returns ``(result, None)`` or ``(None, error response)``."""
    try:
        return await asyncio.to_thread(fn, *args), None
    except accounts.StaleSession:
        return None, JSONResponse(status_code=401, content={"error": "sign in required"})
    except accounts.NoSuchUser:                        # before AccountError: it is a subclass
        return None, JSONResponse(status_code=404, content={"error": "no such user"})
    except (accounts.AccountError, DirectoryError) as exc:
        return None, JSONResponse(status_code=400, content={"error": str(exc)})
    except OverflowError:
        return None, JSONResponse(status_code=400, content={"error": "number out of range"})
    except sqlite3.Error:
        return None, JSONResponse(status_code=503, content={"error": "try again"})


@router.get("/api/v1/users")
async def list_users(request: Request):
    identity, refused = _gate(request, "user.view")
    if refused is not None:
        return refused
    users, failed = await _call(accounts.list_users, identity.clinic_slug)
    if failed is not None:
        return failed
    return {"users": users, "me": identity.user_id}


@router.post("/api/v1/users", status_code=201)
async def create_user(request: Request, body: NewUserBody):
    identity, refused = _gate(request, "user.create")
    if refused is not None:
        return refused
    fields = {k: clean_text(v) for k, v in body.model_dump().items() if k != "username"}

    def _create():
        uid, secret = accounts.create_user(identity.clinic_slug, body.username, **fields)   # audit actor from the scope
        return accounts.get_user(identity.clinic_slug, uid), secret

    created, failed = await _call(_create)
    if failed is not None:
        return failed
    user, secret = created
    return JSONResponse(status_code=201, content={"user": user, "temporary_password": secret}, headers=NO_STORE)


async def _set_active(request: Request, user_id: int, active: bool):
    identity, refused = _gate(request, "user.disable", {"user_id": user_id})   # one permission covers both directions
    if refused is not None:
        return refused
    user, failed = await _call(accounts.set_active, identity, user_id, active)
    if failed is not None:
        return failed
    return {"user": user}


@router.post("/api/v1/users/{user_id}/disable")
async def disable_user(request: Request, user_id: UserId):
    return await _set_active(request, user_id, False)


@router.post("/api/v1/users/{user_id}/enable")
async def enable_user(request: Request, user_id: UserId):
    return await _set_active(request, user_id, True)


@router.post("/api/v1/users/{user_id}/reset-password")
async def reset_password(request: Request, user_id: UserId):
    identity, refused = _gate(request, "user.reset_password", {"user_id": user_id})
    if refused is not None:
        return refused
    secret, failed = await _call(accounts.reset_user_password, identity, user_id)
    if failed is not None:
        return failed
    return JSONResponse({"ok": True, "temporary_password": secret}, headers=NO_STORE)
