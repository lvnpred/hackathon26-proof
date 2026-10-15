"""Doctor level inside Clinic A (spec 7, 13.1): Mehta views and reprints Rao's prescription with Rao's details,
cannot re-save or correct it, and hints and Today are per doctor. Offline."""
from contextlib import closing

from doctor_dictation import admin_demo
from doctor_dictation import db as dbmod
from doctor_dictation.config import override_settings
from doctor_dictation.scope import clinic_dir
from isolation_fixtures import (A, H, correct_body, owner_refusal, reprint, save_body, sql, today, user_id,
                                world)  # noqa: F401

RAO, MEHTA = admin_demo.doctor("dr.rao"), admin_demo.doctor("dr.mehta")


def _medicines(username):
    return {m for (_c, author, _p, _a, _d, meds) in admin_demo.PRESCRIPTIONS if author == username for m in meds}


def _doc_row(doc_id):
    return [tuple(r) for r in sql(A, "SELECT d.*, e.doctor_id FROM documents d"
                                     " JOIN encounters e ON e.id = d.encounter_id WHERE d.id = ?", doc_id)]


def test_a_colleague_can_view_the_prescription(world):
    r = world.mehta.get("/api/v1/documents/1")
    assert r.status_code == 200 and r.json()["structured"]["patientName"] == "Asha Verma"
    assert (r.json()["author"]["user_id"], r.json()["can_edit"]) == (user_id(world, "dr.rao"), False)   # A4
    assert world.rao.get("/api/v1/documents/1").json()["can_edit"] is True


def test_a_colleague_reprint_prints_the_authors_details(world):
    sql(A, "UPDATE templates SET status = 'archived' WHERE status = 'active'")    # built-in layout: author fields only
    html = reprint(world.mehta, A, 1)
    for value in (RAO["doctor_name"], RAO["qualifications"], RAO["reg_no"], "Rao Clinic"):
        assert value in html, value
    assert MEHTA["doctor_name"] not in html and MEHTA["reg_no"] not in html


def test_a_colleague_resave_is_403_and_changes_nothing(world):
    before = _doc_row(1)
    r = world.mehta.post("/api/v1/documents", json=save_body("Asha Verma", document_id=1), headers=H)
    assert (r.status_code, r.json()) == (403, owner_refusal(RAO["doctor_name"]))
    assert _doc_row(1) == before


def test_a_colleague_correction_is_403(world):
    r = world.mehta.post("/api/v1/correct", json=correct_body(1, "Asha Verma"), headers=H)
    assert (r.status_code, r.json()) == (403, owner_refusal(RAO["doctor_name"]))


def test_the_author_can_still_resave_and_keeps_authorship(world):
    r = world.rao.post("/api/v1/documents", json=save_body("Asha Verma", document_id=1), headers=H)
    assert r.status_code == 200, r.text
    row = sql(A, "SELECT d.finalized_by, e.doctor_id FROM documents d JOIN encounters e ON e.id = d.encounter_id"
                 " WHERE d.id = 1")[0]
    rao = user_id(world, "dr.rao")
    assert (row["finalized_by"], row["doctor_id"]) == (rao, rao)


def test_a_prescription_with_no_recorded_author_stays_editable_by_anyone_in_the_clinic(world):
    with closing(dbmod.get_conn(clinic_dir(A) / "app.db")) as conn:
        pid = dbmod.create_patient(conn, "Legacy Patient", "50 / M", "OLD-1")
        eid = dbmod.create_encounter(conn, pid, op_no="OLD-1", status="finalized")
        doc = dbmod.save_document(conn, eid, "legacy-sha", save_body("Legacy Patient", "OLD-1")["structured"],
                                  finalized_at=dbmod._utcnow())
    r = world.mehta.post("/api/v1/documents", json=save_body("Legacy Patient", document_id=doc), headers=H)
    assert r.status_code == 200, r.text
    assert sql(A, "SELECT finalized_by FROM documents WHERE id = ?", doc)[0]["finalized_by"] == user_id(world, "dr.mehta")


def test_an_encounter_cannot_be_created_in_a_colleagues_name(world):
    # F2: fixed; the server ignores a body doctor_id when signed in (ruling R1)
    rao, mehta = user_id(world, "dr.rao"), user_id(world, "dr.mehta")
    count = lambda: sql(A, "SELECT COUNT(*) FROM encounters WHERE doctor_id = ?", rao)[0][0]
    before = count()
    r = world.mehta.post("/api/v1/encounters", json={"patient_id": 1, "doctor_id": rao}, headers=H)
    assert r.status_code == 201, r.text
    assert r.json()["doctor_id"] == mehta
    assert sql(A, "SELECT doctor_id FROM encounters WHERE id = ?", r.json()["id"])[0][0] == mehta
    assert count() == before


def test_a_colleague_resave_is_403_before_the_verify_gate(world):
    unverified = save_body("Asha Verma", document_id=1)
    unverified["structured"]["rx"] = [{"name": "Tamsulosin", "status": "unverified-name"}]
    assert world.rao.post("/api/v1/documents", json=unverified, headers=H).status_code == 409   # the gate really fires
    r = world.mehta.post("/api/v1/documents", json=unverified, headers=H)
    assert (r.status_code, r.json()) == (403, owner_refusal(RAO["doctor_name"]))


def test_the_authors_own_reprint_prints_only_their_details(world):
    sql(A, "UPDATE templates SET status = 'archived' WHERE status = 'active'")
    html = reprint(world.mehta, A, 2)
    for value in (MEHTA["doctor_name"], MEHTA["qualifications"], MEHTA["reg_no"]):
        assert value in html, value
    assert RAO["reg_no"] not in html


def test_hints_come_from_the_signed_in_doctors_own_prescriptions(world, monkeypatch):
    override_settings(monkeypatch, stt_use_hints=True)
    seen = []
    monkeypatch.setattr("doctor_dictation.api.stt.build_hints", lambda top, limit: seen.append(set(top)) or [])
    for who in ("rao", "mehta", "iyer"):
        r = getattr(world, who).post("/api/transcribe", files={"audio": ("d.webm", b"fake audio", "audio/webm")},
                                     headers=H)
        assert r.status_code == 200, r.text
    assert seen == [_medicines("dr.rao"), _medicines("dr.mehta"), _medicines("dr.iyer")]


def test_today_mine_and_whole_clinic_differ(world):
    assert [r["document_id"] for r in today(world.mehta)] == [2]
    clinic = today(world.mehta, "clinic")
    assert [r["document_id"] for r in clinic] == [1, 2, 3]
    names = {r["document_id"]: r["doctor_name"] for r in clinic}
    assert names[1] == RAO["doctor_name"]
    assert names[2] == MEHTA["doctor_name"]
    assert [r["document_id"] for r in today(world.rao)] == [1, 3]
    assert [r["document_id"] for r in today(world.iyer, "clinic")] == [1, 2]
