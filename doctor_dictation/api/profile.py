"""Profile endpoints: the six fields printed on the sheet, plus the clinic's OP-number prefix.

Signed in (multi-clinic mode) they come from two places (spec 8.1): the clinic details (clinic name, address,
phone) are shared on ``clinic_profile``; "my details" (doctor name, qualifications, registration no.) are the
signed-in user's own ``users`` row. GET and PUT keep the same six flat keys in both modes. Single-database mode
(no one signs in) keeps the one shared row, exactly as before. ``op_prefix`` (spec 10) is a clinic detail: the
directory row is the record, ``clinic_profile.op_prefix`` the copy OP numbers read.
"""
from contextlib import closing  # M4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse  # M4
from pydantic import BaseModel, Field

from doctor_dictation import db as dbmod
from doctor_dictation.api.authorship import identity
from doctor_dictation.db import details, opno  # M4: opno
from doctor_dictation.directory import open_directory, set_clinic_op_prefix  # M4
from doctor_dictation.scope import multi_clinic_enabled, require_scope  # M4
from doctor_dictation.textclean import clean_text

router = APIRouter()
MAX_FIELD = 600


class ProfileBody(BaseModel):
    doctor_name: str = Field("", max_length=MAX_FIELD)
    qualifications: str = Field("", max_length=MAX_FIELD)
    reg_no: str = Field("", max_length=MAX_FIELD)
    clinic_name: str = Field("", max_length=MAX_FIELD)
    address: str = Field("", max_length=MAX_FIELD)
    phone: str = Field("", max_length=MAX_FIELD)
    op_prefix: str | None = Field(None, max_length=MAX_FIELD)  # M4: absent = unchanged, so an older page never resets it


def profile_dict(row) -> dict:
    """Serialise a clinic-profile row, defaulting every field to "" (unset)."""
    keys = ("doctor_name", "qualifications", "reg_no", "clinic_name", "address", "phone")
    if row is None:
        return {k: "" for k in keys}
    return {k: row[k] for k in keys}


def _split(conn, user_id) -> dict:
    return {**details.my_details(conn, user_id), **details.clinic_details(conn)}


def profile_response(conn, ident) -> dict:  # M4
    """GET's body (also PUT's and the letterhead use-details answer): the six fields, then the OP prefix."""  # M4
    six = profile_dict(dbmod.get_profile(conn)) if ident is None else _split(conn, ident.user_id)  # M4
    return {**six, "op_prefix": opno.get_op_prefix(conn)}  # M4


def _save_op_prefix(conn, prefix: str) -> bool:  # M4
    """Directory first (the record), then the clinic's copy that OP numbers read. Issued numbers never change.
    False (clinic copy untouched) when the directory does not know the clinic."""  # M4
    if multi_clinic_enabled():  # M4
        with closing(open_directory()) as d:  # M4
            if not set_clinic_op_prefix(d, require_scope().clinic_slug, prefix):  # M4
                return False  # M4
    opno.set_op_prefix(conn, prefix)  # M4
    return True  # M4


@router.get("/api/v1/profile")
def get_profile(request: Request):
    ident = identity(request)
    conn = dbmod.get_conn()
    try:
        return profile_response(conn, ident)  # M4
    finally:
        conn.close()


@router.put("/api/v1/profile")
def put_profile(req: ProfileBody, request: Request):
    ident = identity(request)
    try:  # M4: validate before anything is saved, so a bad prefix changes nothing
        prefix = None if req.op_prefix is None else opno.check_op_prefix(req.op_prefix)  # M4
    except ValueError as exc:  # M4
        return JSONResponse(status_code=400, content={"error": str(exc)})  # M4
    req = req.model_copy(update={k: clean_text(getattr(req, k)) for k in (
        "doctor_name", "qualifications", "reg_no", "clinic_name", "address", "phone")})
    conn = dbmod.get_conn()
    try:
        if ident is None:
            dbmod.save_profile(
                conn,
                doctor_name=req.doctor_name,
                qualifications=req.qualifications,
                reg_no=req.reg_no,
                clinic_name=req.clinic_name,
                address=req.address,
                phone=req.phone,
            )
        else:  # M4: the two signed-in saves are M3's, now in an else branch
            details.save_clinic_details(conn, req.clinic_name, req.address, req.phone)
            details.save_my_details(conn, ident.user_id, req.doctor_name, req.qualifications, req.reg_no)
        if prefix is not None and not _save_op_prefix(conn, prefix):  # M4
            return JSONResponse(status_code=404, content={"error": "clinic not found"})  # M4
        return profile_response(conn, ident)  # M4
    finally:
        conn.close()
