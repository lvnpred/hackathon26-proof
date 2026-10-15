"""Authorship and profile-split SQL (M3 Task 1): migration 006, print profile, author lookup, Today rows,
per-doctor hints. Offline; each test uses its own temp database file."""
import shutil

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation.db import authorship as adb
from doctor_dictation.db import details


@pytest.fixture()
def conn(tmp_path):
    c = dbmod.get_conn(tmp_path / "m3.db")
    dbmod.migrate(c)
    yield c
    c.close()


def _user(conn, username, doctor_name="", display_name="", qualifications="", reg_no=""):
    uid = dbmod.create_user(conn, username, "x")
    conn.execute("UPDATE users SET doctor_name = ?, display_name = ?, qualifications = ?, reg_no = ? WHERE id = ?",
                 (doctor_name, display_name, qualifications, reg_no, uid))
    conn.commit()
    return uid


def _doc(conn, author_id, names=("Tamsulosin",), created_at="2026-10-14T05:00:00Z", patient="P"):
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, patient, "40 / M", None), doctor_id=author_id,
                                 op_no="OP-" + patient)
    return dbmod.save_document(conn, eid, "sha", {"rx": [{"name": n} for n in names]},
                               finalized_by=author_id, finalized_at=created_at, created_at=created_at)


def _db_before_006(tmp_path):
    old = tmp_path / "old_migrations"
    old.mkdir()
    for version, path in dbmod.discover_migrations():
        if version < "006":
            shutil.copy(path, old / version)
    c = dbmod.get_conn(tmp_path / "adopted.db")
    dbmod.migrate(c, old)
    return c


def test_migration_006_copies_the_saved_doctor_fields_to_the_first_user_only(tmp_path):
    c = _db_before_006(tmp_path)
    try:
        dbmod.save_profile(c, doctor_name="Dr. Rao", qualifications="MBBS", reg_no="R-111", clinic_name="Rao Clinic")
        first, second = dbmod.create_user(c, "dr.rao", "x"), dbmod.create_user(c, "dr.mehta", "x")
        assert dbmod.migrate(c) == ["006_doctor_details_to_users.sql", "007_templates_scope.sql",
                                    "008_clinic_profile_prefix.sql"]
        assert details.my_details(c, first) == {"doctor_name": "Dr. Rao", "qualifications": "MBBS", "reg_no": "R-111"}
        assert details.my_details(c, second) == {"doctor_name": "", "qualifications": "", "reg_no": ""}
        assert details.saved_doctor_details(c)["doctor_name"] == "Dr. Rao"     # the shared row keeps its copy
    finally:
        c.close()


def test_migration_006_never_overwrites_details_and_is_a_no_op_without_users_or_profile(tmp_path):
    c = _db_before_006(tmp_path)
    try:
        dbmod.save_profile(c, doctor_name="Dr. Old")
        uid = dbmod.create_user(c, "dr.rao", "x")
        c.execute("UPDATE users SET reg_no = 'MINE' WHERE id = ?", (uid,))
        c.commit()
        dbmod.migrate(c)
        assert details.my_details(c, uid) == {"doctor_name": "", "qualifications": "", "reg_no": "MINE"}
    finally:
        c.close()
    bare = dbmod.get_conn(tmp_path / "bare.db")
    try:
        assert "006_doctor_details_to_users.sql" in dbmod.migrate(bare)   # no users, no profile: applies cleanly
        assert dbmod.migrate(bare) == []
    finally:
        bare.close()


def test_author_label_prefers_doctor_name_then_display_name_then_username(conn):
    a = _user(conn, "dr.a", doctor_name="  Dr. A  ", display_name="Alpha")
    b = _user(conn, "dr.b", display_name="Beta")
    c = _user(conn, "dr.c")
    rows = {r["id"]: r for r in conn.execute("SELECT * FROM users")}
    assert [adb.author_label(rows[i]) for i in (a, b, c)] == ["Dr. A", "Beta", "dr.c"]
    assert adb.author_label(None) == adb.UNKNOWN_AUTHOR == "another doctor"


def test_print_profile_takes_doctor_fields_from_the_author_and_clinic_fields_from_the_clinic(conn):
    dbmod.save_profile(conn, doctor_name="Old Shared", qualifications="OLD", reg_no="OLD-1",
                       clinic_name="Rao Clinic", address="1 Main Road", phone="040 111")
    rao = _user(conn, "dr.rao", doctor_name="Dr. Rao", qualifications="MBBS", reg_no="R-111")
    authored = dbmod.get_document(conn, _doc(conn, rao))["encounter_id"]
    legacy = dbmod.get_document(conn, _doc(conn, None))["encounter_id"]
    clinic = {"clinic_name": "Rao Clinic", "address": "1 Main Road", "phone": "040 111"}
    assert adb.print_profile(conn, authored) == {"doctor_name": "Dr. Rao", "qualifications": "MBBS", "reg_no": "R-111", **clinic}
    assert adb.print_profile(conn, legacy) == {"doctor_name": "Old Shared", "qualifications": "OLD", "reg_no": "OLD-1", **clinic}


def test_document_author_names_the_author_and_handles_legacy_and_missing_documents(conn):
    dbmod.save_profile(conn, doctor_name="Old Shared")
    mehta = _user(conn, "dr.mehta", doctor_name="Dr. Mehta", qualifications="MD", reg_no="M-222")
    doc = _doc(conn, mehta)
    a = adb.document_author(conn, doc)
    assert (a["document_id"], a["author_id"], a["name"]) == (doc, mehta, "Dr. Mehta")
    assert (a["doctor_name"], a["qualifications"], a["reg_no"]) == ("Dr. Mehta", "MD", "M-222")
    old = adb.document_author(conn, _doc(conn, None))
    assert (old["author_id"], old["name"], old["doctor_name"]) == (None, "", "Old Shared")
    assert adb.document_author(conn, 999) is None


def test_set_finalized_by_records_the_saver(conn):
    rao, mehta = _user(conn, "dr.rao"), _user(conn, "dr.mehta")
    doc = _doc(conn, rao)
    assert adb.set_finalized_by(conn, doc, mehta) == 1
    assert dbmod.get_document(conn, doc)["finalized_by"] == mehta
    assert dbmod.get_encounter(conn, dbmod.get_document(conn, doc)["encounter_id"])["doctor_id"] == rao   # author unchanged
    assert adb.set_finalized_by(conn, 999, mehta) == 0


def test_a_colleagues_save_does_not_move_the_prescription_to_the_saver(conn):
    dbmod.save_profile(conn, clinic_name="Rao Clinic")
    rao = _user(conn, "dr.rao", doctor_name="Dr. Rao", reg_no="R-111")
    mehta = _user(conn, "dr.mehta", doctor_name="Dr. Mehta", reg_no="M-222")
    doc = _doc(conn, rao, ["Tamsulosin"], patient="Asha")
    adb.set_finalized_by(conn, doc, mehta)                       # finalized_by (mehta) now differs from the author (rao)
    start, end = "2026-10-14T00:00:00Z", "2026-10-15T00:00:00Z"
    assert [r["patient_name"] for r in adb.list_today(conn, start, end, rao)] == ["Asha"]
    assert adb.list_today(conn, start, end, mehta) == []
    assert dbmod.top_medicines(conn, doctor_id=rao) == ["Tamsulosin"] and dbmod.top_medicines(conn, doctor_id=mehta) == []
    assert adb.print_profile(conn, dbmod.get_document(conn, doc)["encounter_id"])["reg_no"] == "R-111"


def test_list_today_mine_versus_clinic_with_doctor_names(conn):
    rao = _user(conn, "dr.rao", doctor_name="Dr. Rao")
    mehta = _user(conn, "dr.mehta", display_name="Mehta")
    _doc(conn, rao, patient="Asha", created_at="2026-10-14T05:00:00Z")
    _doc(conn, mehta, patient="Bala", created_at="2026-10-14T06:00:00Z")
    _doc(conn, None, patient="Chitra", created_at="2026-10-14T07:00:00Z")
    _doc(conn, rao, patient="Yesterday", created_at="2026-10-13T05:00:00Z")
    start, end = "2026-10-14T00:00:00Z", "2026-10-15T00:00:00Z"
    mine = adb.list_today(conn, start, end, rao)
    assert [(r["patient_name"], r["author_id"], r["doctor_name"]) for r in mine] == [("Asha", rao, "Dr. Rao")]
    clinic = adb.list_today(conn, start, end)
    assert [(r["patient_name"], r["doctor_name"]) for r in clinic] == [("Asha", "Dr. Rao"), ("Bala", "Mehta"), ("Chitra", "")]
    assert set(clinic[0]) == {"document_id", "encounter_id", "patient_name", "op_no", "created_at", "author_id", "doctor_name"}


def test_top_medicines_for_one_doctor_ignores_colleagues(conn):
    rao, mehta = _user(conn, "dr.rao"), _user(conn, "dr.mehta")
    _doc(conn, rao, ["Tamsulosin", "Tamsulosin"])
    _doc(conn, mehta, ["Paracetamol"])
    _doc(conn, None, ["Zincovit"])
    assert dbmod.top_medicines(conn, doctor_id=rao) == ["Tamsulosin"]
    assert dbmod.top_medicines(conn, doctor_id=mehta) == ["Paracetamol"]
    assert dbmod.top_medicines(conn) == ["Tamsulosin", "Zincovit", "Paracetamol"]
    assert dbmod.top_medicines(conn, doctor_id=999) == []


def test_clinic_details_save_keeps_the_doctor_columns_and_my_details_round_trip(conn):
    dbmod.save_profile(conn, doctor_name="Old Shared", qualifications="OLD", reg_no="OLD-1", clinic_name="Before")
    details.save_clinic_details(conn, "Rao Clinic", "1 Main Road", "040 111")
    assert details.clinic_details(conn) == {"clinic_name": "Rao Clinic", "address": "1 Main Road", "phone": "040 111"}
    assert details.saved_doctor_details(conn) == {"doctor_name": "Old Shared", "qualifications": "OLD", "reg_no": "OLD-1"}
    uid = _user(conn, "dr.rao")
    assert details.save_my_details(conn, uid, "Dr. Rao", "MBBS", "R-111") == 1
    assert details.my_details(conn, uid) == {"doctor_name": "Dr. Rao", "qualifications": "MBBS", "reg_no": "R-111"}
    assert details.save_my_details(conn, 999, "x", "y", "z") == 0
    assert details.my_details(conn, 999) == {"doctor_name": "", "qualifications": "", "reg_no": ""}
