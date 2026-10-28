"""Plan SH-B2/SH-B4: check-row answers with the doctor's context groups; the patient comes from the saved sheet only."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api.app import create_app
from doctor_dictation.db import spoken as spoken_db

H = {"X-DD-Client": "1"}
URL = "/api/v1/rx/check-row"
REQ = SimpleNamespace(state=SimpleNamespace())            # single-database mode: no identity
NO_PATIENT = {"name": "", "age_sex": "", "op_no": ""}


def _fake_pdf(structured, meta, out_path, layout=None):
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(b"%PDF-fake")
    return Path(out_path)


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))                       # never the real dev database
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", _fake_pdf)
    with TestClient(create_app()) as c:
        yield c


def _save(c, diagnosis, name, strength, patient="Asha Verma", age_sex="40 / F", document_id=None, op=""):
    row = {"form": "Tab.", "name": name, "strength": strength, "dose": "1-0-1", "status": "verified"}
    body = {"structured": {"patientName": patient, "ageSex": age_sex, "opNo": op, "diagnosis": diagnosis, "rx": [row]},
            "confirmed_rows": [0], **({"document_id": document_id} if document_id else {})}
    r = c.post("/api/v1/documents", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def _post(c, name, **extra):
    return c.post(URL, json={"row": {"name": name}, "transcript": f"tab {name.lower()}", **extra})


def _patient_names(j):
    return [i["name"] for g in j["context"] if g["kind"] == "patient" for i in g["items"]]


def test_the_load_answer_carries_the_diagnosis_group_and_search_answers_stay_plain(app_client):
    c = app_client
    for _ in range(2):
        _save(c, ["BPH"], "Urimax", "0.4 mg")
    ctx = {"diagnosis": ["BPH"], "patient": NO_PATIENT}
    j = _post(c, "Yurimacks", context=ctx).json()
    g = j["context"][0]
    assert g["kind"] == "diagnosis" and g["for"] == "BPH"
    assert [i["name"] for i in g["items"]] == ["Urimax"] and isinstance(g["items"][0]["generic"], str)
    plain = _post(c, "Yurimacks").json()
    assert plain["context"] == [] and plain["options"] == j["options"] and plain["row"] == j["row"]   # S1: row untouched


def test_a_saved_sheet_uses_its_encounter_not_the_typed_patient(app_client):
    c = app_client
    _save(c, [], "Urimax", "0.4 mg")
    _save(c, [], "Urimax", "0.4 mg")                                   # no OP number: each save is a new patient row
    _save(c, [], "Montelukast", "10 mg", patient="Ravi Kumar", age_sex="45 / M")
    d = _save(c, [], "Dutas", "0.5 mg")
    ctx = {"diagnosis": [], "patient": {"name": "Ravi Kumar", "age_sex": "45 / M", "op_no": ""}}
    j = _post(c, "Dutaz", context=ctx, document_id=d).json()
    assert _patient_names(j) == ["Urimax"]            # Asha's earlier visits; Dutas is this document, excluded; Ravi ignored


def test_document_patient_ids_returns_every_row_of_the_person(app_client):
    from doctor_dictation.api.spellctx import document_patient_ids
    c = app_client
    ids = [_save(c, [], "Urimax", "0.4 mg") for _ in range(3)]
    conn = dbmod.get_conn()
    try:
        got = document_patient_ids(conn, REQ, ids[-1], 0)
        assert len(got) == 3 and got == tuple(sorted(got))
        assert document_patient_ids(conn, REQ, 999999, 0) == ()
    finally:
        conn.close()


def test_bad_context_and_bad_document_id_are_ignored_never_a_400(app_client):
    c = app_client
    for extra in ({"context": "x"}, {"context": {"diagnosis": "BPH"}}, {"document_id": "7"}, {"document_id": True},
                  {"document_id": 999999}, {"context": {"diagnosis": ["x" * 201]}}):
        r = _post(c, "Zorbex", **extra)
        assert r.status_code == 200 and r.json()["context"] == [], extra
    r = c.post(URL, json={"row": {"name": "x" * 61}, "context": {"diagnosis": ["BPH"], "patient": NO_PATIENT}})
    assert r.status_code == 400                                         # the old rules still answer first


def test_an_unsaved_draft_never_gets_a_patient_group(app_client):
    c = app_client
    _save(c, [], "Urimax", "0.4 mg")
    _save(c, [], "Urimax", "0.4 mg")
    ctx = {"diagnosis": [], "patient": {"name": "Asha Verma", "age_sex": "40 / F", "op_no": ""}}
    j = _post(c, "Dutaz", context=ctx).json()
    assert not any(g["kind"] == "patient" for g in j["context"])        # owner Q6: only after the first save


def test_a_failing_lookup_logs_the_type_only_and_still_answers(app_client, monkeypatch, capsys):
    import sqlite3

    def boom(*a, **k):
        raise sqlite3.OperationalError("no such table: Asha Verma OP-1 BPH Urimax")
    monkeypatch.setattr(spoken_db, "doctor_medicine_names", boom)
    ctx = {"diagnosis": ["BPH"], "patient": {"name": "Asha Verma", "age_sex": "40 / F", "op_no": "OP-1"}}
    r = _post(c := app_client, "Yurimacks", context=ctx)
    out = capsys.readouterr().out
    assert r.status_code == 200 and r.json()["context"] == [] and "OperationalError" in out
    assert not any(s in out for s in ("Asha", "OP-1", "BPH", "Urimax"))


def test_a_removed_clinic_name_in_the_patients_history_never_appears(app_client):
    from doctor_dictation.core import formulary
    c = app_client
    _save(c, ["BPH"], "Urimax", "0.4 mg"); _save(c, ["BPH"], "Dutas", "0.5 mg")
    d = _save(c, [], "Uromax", "0.4 mg")
    ctx = {"diagnosis": ["BPH"], "patient": NO_PATIENT}
    before = _post(c, "Yurimacks", context=ctx, document_id=d).json()
    assert "Urimax" in _patient_names(before) + [i["name"] for g in before["context"] for i in g["items"]]
    conn = dbmod.get_conn()
    try:
        n = conn.execute("UPDATE clinic_formulary SET removed_at = '2026-10-28T00:00:00Z' WHERE name_key = ?", (formulary.key("Urimax"),)).rowcount
        assert n == 1
        conn.commit()
    finally:
        conn.close()
    after = _post(c, "Yurimacks", context=ctx, document_id=d).json()
    assert "Urimax" not in [i["name"] for g in after["context"] for i in g["items"]]
