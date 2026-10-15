"""Profile split (spec 8.1): clinic details live on ``clinic_profile``, a doctor's own details on their ``users`` row.

SQL only, like the rest of ``db``. Every getter returns plain dicts with "" for unset values.
"""
from doctor_dictation import db as dbmod

CLINIC_KEYS = ("clinic_name", "address", "phone")
DOCTOR_KEYS = ("doctor_name", "qualifications", "reg_no")


def clinic_details(conn) -> dict:
    row = dbmod.get_profile(conn)
    return {k: (row[k] if row is not None else "") or "" for k in CLINIC_KEYS}


def saved_doctor_details(conn) -> dict:
    """The doctor fields still stored on ``clinic_profile`` (single mode, and prescriptions with no author)."""
    row = dbmod.get_profile(conn)
    return {k: (row[k] if row is not None else "") or "" for k in DOCTOR_KEYS}


def my_details(conn, user_id) -> dict:
    row = conn.execute("SELECT doctor_name, qualifications, reg_no FROM users WHERE id = ?", (user_id,)).fetchone()
    return {k: (row[k] if row is not None else "") or "" for k in DOCTOR_KEYS}


def save_clinic_details(conn, clinic_name="", address="", phone="", updated_at=None) -> None:
    """Upsert the three clinic fields; the doctor columns of ``clinic_profile`` are left as they are."""
    conn.execute(
        "INSERT INTO clinic_profile(id, clinic_name, address, phone, updated_at) VALUES (1, ?, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET clinic_name = excluded.clinic_name, address = excluded.address,"
        " phone = excluded.phone, updated_at = excluded.updated_at",
        (clinic_name, address, phone, updated_at or dbmod._utcnow()))
    conn.commit()


def save_my_details(conn, user_id, doctor_name="", qualifications="", reg_no="") -> int:
    """Write the signed-in user's own doctor fields; returns rows changed (0 for an unknown user)."""
    cur = conn.execute("UPDATE users SET doctor_name = ?, qualifications = ?, reg_no = ? WHERE id = ?",
                       (doctor_name, qualifications, reg_no, user_id))
    conn.commit()
    return cur.rowcount
