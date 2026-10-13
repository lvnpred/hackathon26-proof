"""Clinic profile endpoints (the six fields printed on the sheet)."""
from fastapi import APIRouter
from pydantic import BaseModel

from doctor_dictation import db as dbmod

router = APIRouter()


class ProfileBody(BaseModel):
    doctor_name: str = ""
    qualifications: str = ""
    reg_no: str = ""
    clinic_name: str = ""
    address: str = ""
    phone: str = ""


def profile_dict(row) -> dict:
    """Serialise a clinic-profile row, defaulting every field to "" (unset)."""
    keys = ("doctor_name", "qualifications", "reg_no", "clinic_name", "address", "phone")
    if row is None:
        return {k: "" for k in keys}
    return {k: row[k] for k in keys}


@router.get("/api/v1/profile")
def get_profile():
    conn = dbmod.get_conn()
    try:
        return profile_dict(dbmod.get_profile(conn))
    finally:
        conn.close()


@router.put("/api/v1/profile")
def put_profile(req: ProfileBody):
    conn = dbmod.get_conn()
    try:
        dbmod.save_profile(
            conn,
            doctor_name=req.doctor_name,
            qualifications=req.qualifications,
            reg_no=req.reg_no,
            clinic_name=req.clinic_name,
            address=req.address,
            phone=req.phone,
        )
        return profile_dict(dbmod.get_profile(conn))
    finally:
        conn.close()
