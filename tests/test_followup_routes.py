"""Plan I2-b: review_date on /api/format (never cached), /api/v1/correct, Save and the page's route. Offline."""
import json
from datetime import date

from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation import db as dbmod
from doctor_dictation.api import visit
from doctor_dictation.config import override_settings
from doctor_dictation.core.determinism import _FORMAT_CACHE
from doctor_dictation.pdf import build_sheet_html

def test_format_stamps_the_review_date_on_a_copy_so_the_cache_never_keeps_a_day(monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    _FORMAT_CACHE.clear()
    monkeypatch.setattr(visit, "today", lambda: date(2026, 10, 17))
    client, body = TestClient(M.app), {"transcript": "patient complains of headache since one day advise rest review after one week"}
    first = client.post("/api/format", json=body).json()
    assert (first["structured"]["review"], first["structured"]["review_date"]) == ("Review after 1 week", "2026-10-24")
    monkeypatch.setattr(visit, "today", lambda: date(2026, 10, 31))                 # the same words on another day: a cache hit
    again = client.post("/api/format", json=body).json()
    assert again["cached"] is True and again["structured"]["review_date"] == "2026-11-07"
    assert all("review_date" not in v["structured"] for v in _FORMAT_CACHE.values())

def test_correct_recomputes_and_save_stores_the_review_date_and_ignores_a_sent_one(tmp_path, monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "f.db"))
    conn = dbmod.get_conn()
    dbmod.migrate(conn)                                                            # TestClient runs no lifespan: migrate by hand
    conn.close()
    monkeypatch.setattr(visit, "today", lambda: date(2026, 10, 31))
    client = TestClient(M.app)
    form = {"patientName": "Anita", "opNo": "OP-5", "review": "after 2 months", "review_date": "1999-01-01", "rx": []}
    out = client.post("/api/v1/correct", json={"transcript": "", "current_form": form}).json()
    assert out["structured"]["review_date"] == "2026-12-31"                         # 31 Oct + 2 months
    r = client.post("/api/v1/documents", json={"structured": form, "confirmed_rows": []})
    assert r.status_code == 200, r.text
    conn = dbmod.get_conn(tmp_path / "f.db")
    saved = json.loads(dbmod.get_document(conn, r.json()["document_id"])["structured_json"])
    conn.close()
    assert (saved["review"], saved["review_date"]) == ("after 2 months", "2026-12-31")

def test_the_review_date_route_answers_the_page(monkeypatch):
    monkeypatch.setattr(visit, "today", lambda: date(2026, 10, 17))
    c = TestClient(M.app)
    assert c.post("/api/v1/review-date", json={"review": "1 week"}).json() == {"review_date": "2026-10-24", "label": "Sat 24 Oct 2026"}
    assert c.post("/api/v1/review-date", json={"review": "SOS"}).json() == {"review_date": "", "label": ""}
    assert c.post("/api/v1/review-date", json={}).json() == {"review_date": "", "label": ""}
    assert [c.post("/api/v1/review-date", json={"review": v}).status_code for v in ("x" * 1001, 7, None, ["1 week"])] == [400] * 4

def test_a_document_saved_before_this_change_opens_and_prints_as_before(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "o.db"))
    conn = dbmod.get_conn()
    dbmod.migrate(conn)
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "Old", "40 / M", None))
    old = {"patientName": "Old", "diagnosis": ["Gastritis"], "complaints": ["epigastric pain", "nausea"], "review": "after 1 week", "rx": []}
    doc = dbmod.save_document(conn, eid, "sha-old", old)
    conn.close()
    got = TestClient(M.app).get(f"/api/v1/documents/{doc}").json()["structured"]
    assert got == old                                                              # no migration, no new key
    html = build_sheet_html(got, {"date": "2026-10-01"})
    assert '<span class="inl-label">Review:</span> after 1 week</div>' in html and 'class="rev-date"' not in html    # no date until it is re-saved (Q8)


def test_the_visit_day_is_the_clinic_zone_day_and_save_prints_that_same_day(tmp_path, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from doctor_dictation.api import persistence
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    ist = ZoneInfo("Asia/Kolkata")
    before = datetime.now(ist).date()
    assert before <= visit.today() <= datetime.now(ist).date()          # the clinic zone, whatever the host clock zone is
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "v.db"))
    conn = dbmod.get_conn()
    dbmod.migrate(conn)
    conn.close()
    monkeypatch.setattr(visit, "today", lambda: date(2031, 3, 4))
    seen = []
    real = persistence._pdf_inputs
    monkeypatch.setattr(persistence, "_pdf_inputs", lambda conn, v, day, eid: (seen.append(day), real(conn, v, day, eid))[1])
    form = {"patientName": "Anita", "opNo": "OP-6", "review": "1 week", "rx": []}
    assert TestClient(M.app).post("/api/v1/documents", json={"structured": form, "confirmed_rows": []}).status_code == 200
    assert seen == [date(2031, 3, 4)]
