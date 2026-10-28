"""Who wrote a prescription (spec 7.1): ``encounters.doctor_id`` is the author, ``documents.finalized_by`` the
last saver. SQL only. A document saved before authorship existed has no author (``author_id`` None)."""
from doctor_dictation.db.details import clinic_details, my_details, saved_doctor_details

UNKNOWN_AUTHOR = "another doctor"


def author_label(row) -> str:
    """How a user is named on screen: doctor name, else display name, else username."""
    if row is None:
        return UNKNOWN_AUTHOR
    return (row["doctor_name"] or "").strip() or (row["display_name"] or "").strip() or row["username"] or UNKNOWN_AUTHOR


def _user(conn, user_id):
    return conn.execute("SELECT id, username, display_name, doctor_name FROM users WHERE id = ?", (user_id,)).fetchone()


def encounter_author_id(conn, encounter_id):
    row = conn.execute("SELECT doctor_id FROM encounters WHERE id = ?", (encounter_id,)).fetchone()
    return row["doctor_id"] if row is not None else None


def print_profile(conn, encounter_id) -> dict:
    """The six fields a prescription prints: clinic fields from the clinic, doctor fields from the AUTHOR.

    No author (single-database mode, or a pre-authorship prescription): the doctor fields saved on the clinic
    profile, exactly as before. Never the viewer's details.
    """
    author_id = encounter_author_id(conn, encounter_id)
    doctor = my_details(conn, author_id) if author_id is not None else saved_doctor_details(conn)
    return {**doctor, **clinic_details(conn)}


def document_author(conn, document_id):
    """``{document_id, encounter_id, author_id, name, doctor_name, qualifications, reg_no}`` or None (no document).

    ``name`` is "" when there is no author; the three doctor fields are what the prescription prints.
    """
    doc = conn.execute("SELECT id, encounter_id FROM documents WHERE id = ?", (document_id,)).fetchone()
    if doc is None:
        return None
    author_id = encounter_author_id(conn, doc["encounter_id"])
    profile = print_profile(conn, doc["encounter_id"])
    return {"document_id": doc["id"], "encounter_id": doc["encounter_id"], "author_id": author_id,
            "name": author_label(_user(conn, author_id)) if author_id is not None else "",
            **{k: profile[k] for k in ("doctor_name", "qualifications", "reg_no")}}


def set_finalized_by(conn, document_id, user_id) -> int:
    cur = conn.execute("UPDATE documents SET finalized_by = ? WHERE id = ?", (user_id, document_id))
    conn.commit()
    return cur.rowcount


def list_today(conn, start_iso, end_iso, doctor_id=None):
    """The Today rows in ``[start_iso, end_iso)``, oldest first, with ``author_id`` and ``doctor_name``.

    ``doctor_id`` keeps one author's prescriptions ("mine"); None keeps the whole clinic. ``doctor_name`` is ""
    for a prescription with no author.
    """
    mine, args = ("", ()) if doctor_id is None else (" AND e.doctor_id = ?", (doctor_id,))
    rows = conn.execute(
        "SELECT d.id AS document_id, d.encounter_id AS encounter_id, p.name AS patient_name, e.op_no AS op_no,"
        " d.created_at AS created_at, e.doctor_id AS author_id,"
        " u.username AS username, u.display_name AS display_name, u.doctor_name AS doctor_name"
        " FROM documents d JOIN encounters e ON e.id = d.encounter_id JOIN patients p ON p.id = e.patient_id"
        " LEFT JOIN users u ON u.id = e.doctor_id"
        " WHERE d.created_at >= ? AND d.created_at < ?" + mine + " ORDER BY d.created_at, d.id",
        (start_iso, end_iso, *args)).fetchall()
    return [{"document_id": r["document_id"], "encounter_id": r["encounter_id"], "patient_name": r["patient_name"],
             "op_no": r["op_no"], "created_at": r["created_at"], "author_id": r["author_id"],
             "doctor_name": author_label(r) if r["author_id"] is not None else ""} for r in rows]
