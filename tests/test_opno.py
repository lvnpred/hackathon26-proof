"""Generated OP numbers: helper (db) + Save route behaviour. Offline."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

from doctor_dictation import db as dbmod
from doctor_dictation.db.opno import next_op_no
from template_fixtures import tclient, tconn  # noqa: F401

NOW = datetime(2026, 10, 14, 9, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
DAY = "OP-20261014-"


def _pat(conn, op):
    return dbmod.create_patient(conn, "P", op_no=op)


def test_first_of_day_is_001(tconn):
    assert next_op_no(tconn, now=NOW) == DAY + "001"


def test_increments_past_max_and_ignores_garbage_and_other_days(tconn):
    for op in (DAY + "001", DAY + "007", DAY + "abc", DAY + "", "OP-20261013-099", "OP-9", None, "X" + DAY + "050"):
        _pat(tconn, op)
    assert next_op_no(tconn, now=NOW) == DAY + "008"


def test_uses_encounters_too(tconn):
    pid = _pat(tconn, None)
    dbmod.create_encounter(tconn, pid, op_no=DAY + "012")
    assert next_op_no(tconn, now=NOW) == DAY + "013"


def test_day_rollover_resets(tconn):
    _pat(tconn, DAY + "005")
    assert next_op_no(tconn, now=NOW + timedelta(days=1)) == "OP-20261015-001"


def test_four_digit_growth(tconn):
    _pat(tconn, DAY + "999")
    assert next_op_no(tconn, now=NOW) == DAY + "1000"
    _pat(tconn, DAY + "1000")
    assert next_op_no(tconn, now=NOW) == DAY + "1001"


def test_default_now_uses_local_date(tconn):
    assert re.fullmatch(r"OP-\d{8}-001", next_op_no(tconn))


# ---- route ---------------------------------------------------------------

def _capture(monkeypatch):
    seen = {"metas": []}

    def fake(structured, meta, out_path, layout=None):
        seen["metas"].append(dict(meta))
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-1.4 fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)
    return seen


def _body(name, op="", doc=None):
    b = {"structured": {"patientName": name, "opNo": op, "rx": [{"name": "Tamsulosin", "status": "verified"}]},
         "confirmed_rows": []}
    if doc is not None:
        b["document_id"] = doc
    return b


def _db():
    return dbmod.get_conn()


def test_blank_op_generates_and_stores_everywhere(tclient, monkeypatch):
    seen = _capture(monkeypatch)
    r = tclient.post("/api/v1/documents", json=_body("Anita"))
    assert r.status_code == 200, r.text
    j = r.json()
    assert re.fullmatch(r"OP-\d{8}-001", j["op_no"])
    conn = _db()
    try:
        assert dbmod.get_patient(conn, j["patient_id"])["op_no"] == j["op_no"]
        assert dbmod.get_encounter(conn, j["encounter_id"])["op_no"] == j["op_no"]
        doc = dbmod.get_document(conn, j["document_id"])
        assert json.loads(doc["structured_json"])["opNo"] == j["op_no"]
    finally:
        conn.close()
    assert seen["metas"][-1]["opNo"] == j["op_no"]


def test_two_blank_op_patients_get_distinct_numbers_no_rename(tclient, monkeypatch):
    _capture(monkeypatch)
    a = tclient.post("/api/v1/documents", json=_body("Anita")).json()
    b = tclient.post("/api/v1/documents", json=_body("Bhaskar")).json()
    assert a["op_no"] != b["op_no"] and a["op_no"].endswith("001") and b["op_no"].endswith("002")
    assert a["patient_id"] != b["patient_id"]
    conn = _db()
    try:
        assert dbmod.get_patient(conn, a["patient_id"])["name"] == "Anita"
        assert len(dbmod.list_patients(conn)) == 2
    finally:
        conn.close()


def test_dictated_op_still_merges(tclient, monkeypatch):
    _capture(monkeypatch)
    a = tclient.post("/api/v1/documents", json=_body("Anita", "OP-5")).json()
    b = tclient.post("/api/v1/documents", json=_body("Anita Rao", "OP-5")).json()
    assert a["patient_id"] == b["patient_id"] and a["op_no"] == b["op_no"] == "OP-5"


def test_resave_blank_keeps_number_no_new_rows(tclient, monkeypatch):
    seen = _capture(monkeypatch)
    a = tclient.post("/api/v1/documents", json=_body("Anita")).json()
    b = tclient.post("/api/v1/documents", json=_body("Anita", doc=a["document_id"])).json()
    assert b["op_no"] == a["op_no"] and b["patient_id"] == a["patient_id"] and b["encounter_id"] == a["encounter_id"]
    assert seen["metas"][-1]["opNo"] == a["op_no"]
    conn = _db()
    try:
        assert len(dbmod.list_patients(conn)) == 1
        assert len(dbmod.list_encounters(conn)) == 1
        doc = dbmod.get_document(conn, a["document_id"])
        assert json.loads(doc["structured_json"])["opNo"] == a["op_no"]
    finally:
        conn.close()


def test_resave_with_different_typed_op_leaves_patient_and_encounter(tclient, monkeypatch):
    _capture(monkeypatch)
    a = tclient.post("/api/v1/documents", json=_body("Anita")).json()
    b = tclient.post("/api/v1/documents", json=_body("Anita", "OP-77", doc=a["document_id"])).json()
    assert b["op_no"] == a["op_no"]
    conn = _db()
    try:
        assert dbmod.get_patient(conn, a["patient_id"])["op_no"] == a["op_no"]
        assert dbmod.get_encounter(conn, a["encounter_id"])["op_no"] == a["op_no"]
    finally:
        conn.close()


def test_eight_concurrent_first_saves_get_distinct_numbers(tclient, monkeypatch):
    _capture(monkeypatch)
    with ThreadPoolExecutor(8) as ex:
        rs = list(ex.map(lambda i: tclient.post("/api/v1/documents", json=_body(f"Pat{i}")), range(8)))
    assert all(r.status_code == 200 for r in rs), [r.text for r in rs]
    ops = {r.json()["op_no"] for r in rs}
    assert len(ops) == 8
    conn = _db()
    try:
        assert len(dbmod.list_patients(conn)) == 8
    finally:
        conn.close()


# ---- fix round 1 ---------------------------------------------------------

def _today_prefix():
    return f"OP-{datetime.now().astimezone():%Y%m%d}-"


def test_overlong_and_non_ascii_digit_sequences_are_ignored(tconn):
    _pat(tconn, DAY + "9" * 5000)
    _pat(tconn, DAY + "١٢٣")  # Arabic-Indic digits
    assert next_op_no(tconn, now=NOW) == DAY + "001"


def test_route_survives_overlong_stored_op(tclient, monkeypatch):
    _capture(monkeypatch)
    conn = _db()
    try:
        dbmod.create_patient(conn, "X", op_no=_today_prefix() + "9" * 5000)
        dbmod.create_patient(conn, "Y", op_no=_today_prefix() + "١٢")
    finally:
        conn.close()
    r = tclient.post("/api/v1/documents", json=_body("Anita"))
    assert r.status_code == 200, r.text
    assert r.json()["op_no"] == _today_prefix() + "001"


def test_blank_op_same_name_as_typed_op_patient_is_new_patient(tclient, monkeypatch):
    _capture(monkeypatch)
    a = tclient.post("/api/v1/documents", json=_body("Asha", "OP-X")).json()
    b = tclient.post("/api/v1/documents", json=_body("Asha")).json()
    assert a["patient_id"] != b["patient_id"]
    assert b["op_no"].startswith("OP-2") and b["op_no"] != "OP-X"
    conn = _db()
    try:
        assert dbmod.get_patient(conn, a["patient_id"])["op_no"] == "OP-X"
        assert len(dbmod.list_patients(conn)) == 2
    finally:
        conn.close()


def test_blank_op_same_name_as_no_op_patient_is_new_patient(tclient, monkeypatch):
    _capture(monkeypatch)
    conn = _db()
    try:
        old = dbmod.create_patient(conn, "Asha")
    finally:
        conn.close()
    b = tclient.post("/api/v1/documents", json=_body("Asha")).json()
    assert b["patient_id"] != old and b["op_no"]
    conn = _db()
    try:
        assert dbmod.get_patient(conn, old)["op_no"] is None
        assert len(dbmod.list_patients(conn)) == 2
    finally:
        conn.close()
