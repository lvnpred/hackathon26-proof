"""Browse earlier days in the Today list (UI-A Task 2). Offline; the clinic day is frozen with monkeypatch.

``GET /api/v1/encounters/today`` lists the clinic-zone day (default ``visit.today()``), or ``?date=YYYY-MM-DD``.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api import visit
from authorship_fixtures import SAVE, as_user, clinic_conn, save, team  # noqa: F401

TODAY = date(2026, 10, 13)
LATE_12TH = "2026-10-12T18:00:00Z"     # 23:30 IST on the 12th
EARLY_13TH = "2026-10-12T19:00:00Z"    # 00:30 IST on the 13th (UTC still says the 12th)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "days.db"))
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    monkeypatch.setattr(visit, "today", lambda now=None: TODAY)
    from doctor_dictation.api.app import create_app
    with TestClient(create_app()) as c:
        conn = dbmod.get_conn()
        for name, at in (("Late", LATE_12TH), ("Early", EARLY_13TH)):
            eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, name, "", None))
            dbmod.save_document(conn, eid, "sha", {"rx": []}, created_at=at)
        conn.close()
        yield c


def _names(r):
    assert r.status_code == 200, r.text
    return [row["patient_name"] for row in r.json()]


def test_day_bounds_are_the_clinic_zone_midnights_in_utc(monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    assert visit.day_bounds_utc(date(2026, 10, 13)) == ("2026-10-12T18:30:00Z", "2026-10-13T18:30:00Z")
    monkeypatch.setenv("TZ", "America/New_York")                       # 23 hours on the day the clocks go back
    assert visit.day_bounds_utc(date(2026, 11, 1)) == ("2026-11-01T04:00:00Z", "2026-11-02T05:00:00Z")


def test_day_bounds_without_zone_data_fall_back_to_the_server_zone(monkeypatch):
    monkeypatch.setenv("TZ", "Not/AZone")
    start, end = visit.day_bounds_utc(date(2026, 10, 13))
    assert start < end and start.endswith("Z") and end.endswith("Z")


def test_the_default_day_is_the_clinic_zone_today(client):
    assert _names(client.get("/api/v1/encounters/today")) == ["Early"]


def test_a_date_lists_that_clinic_day(client):
    assert _names(client.get("/api/v1/encounters/today?date=2026-10-12")) == ["Late"]
    assert _names(client.get("/api/v1/encounters/today?date=2026-10-13")) == ["Early"]
    assert _names(client.get("/api/v1/encounters/today?date=2026-10-01")) == []
    rows = client.get("/api/v1/encounters/today?date=2026-10-12").json()
    assert set(rows[0]) == {"document_id", "encounter_id", "patient_name", "op_no", "created_at"}   # the shape is unchanged


def test_a_future_day_is_refused(client):
    r = client.get("/api/v1/encounters/today?date=2026-10-14")
    assert (r.status_code, r.json()) == (400, {"error": "date is in the future"})


@pytest.mark.parametrize("bad", ["2026-1-5", "13-10-2026", "2026-02-30", "x", "2026-10-13T00:00", " 2026-10-13", "０２０２-10-13"])
def test_a_malformed_date_is_refused(client, bad):
    r = client.get("/api/v1/encounters/today", params={"date": bad})
    assert (r.status_code, r.json()) == (400, {"error": "date must be YYYY-MM-DD"})


def test_scope_and_date_work_together_signed_in(team, monkeypatch):
    c = as_user(team.client, team.rao)
    mine = save(c, {**SAVE, "structured": {**SAVE["structured"], "patientName": "Asha", "opNo": ""}})
    theirs = save(as_user(c, team.mehta), {**SAVE, "structured": {**SAVE["structured"], "patientName": "Bala", "opNo": ""}})
    today_only = save(c, {**SAVE, "structured": {**SAVE["structured"], "patientName": "Chitra", "opNo": ""}})
    with clinic_conn() as conn:
        conn.executemany("UPDATE documents SET created_at = ? WHERE id = ?",
                         [(LATE_12TH, mine), (LATE_12TH, theirs), (EARLY_13TH, today_only)])
        conn.commit()
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    monkeypatch.setattr(visit, "today", lambda now=None: TODAY)
    as_user(c, team.rao)
    assert _names(c.get("/api/v1/encounters/today?scope=mine&date=2026-10-12")) == ["Asha"]
    assert _names(c.get("/api/v1/encounters/today?scope=clinic&date=2026-10-12")) == ["Asha", "Bala"]
    assert _names(c.get("/api/v1/encounters/today?scope=clinic")) == ["Chitra"]
    assert c.get("/api/v1/encounters/today?scope=clinic&date=2026-10-14").status_code == 400
