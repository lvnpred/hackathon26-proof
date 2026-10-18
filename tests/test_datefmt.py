"""Iteration 3: date formatting (core/datefmt.py, api/visit.py, health, the PDF header). Offline."""
import json
import logging
import shutil
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation import db as dbmod
from doctor_dictation.api import persistence, visit
from doctor_dictation.config import override_settings
from doctor_dictation.core import datefmt
from doctor_dictation.core.followup import date_label
from doctor_dictation.pdf.sheet import build_sheet_html

TABLE = json.loads((Path(__file__).parent / "data" / "date_formats.json").read_text(encoding="utf-8"))


def _utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@pytest.fixture(autouse=True)
def _fresh_warnings():
    datefmt._warned.clear()
    visit._warned.clear()


@pytest.mark.parametrize("case", TABLE["date"], ids=lambda c: c["in"])
def test_format_date_table(case):
    assert datefmt.format_date(date.fromisoformat(case["in"]), case["locale"]) == case["out"]
    assert datefmt.format_date(case["in"], case["locale"]) == case["out"]


@pytest.mark.parametrize("case", TABLE["label"], ids=lambda c: c["in"])
def test_format_label_table_and_date_label_is_the_same_text(case):
    assert datefmt.format_label(date.fromisoformat(case["in"]), case["locale"]) == case["out"]
    assert date_label(case["in"]) == case["out"]            # core/followup.date_label keeps its name and its text


@pytest.mark.parametrize("case", TABLE["time"], ids=lambda c: c["in"] + c["tz"])
def test_format_time_table(case):
    assert datefmt.format_time(visit.to_clinic(_utc(case["in"]), case["tz"]), case["locale"]) == case["out"]


@pytest.mark.parametrize("case", TABLE["datetime"], ids=lambda c: c["in"] + c["tz"])
def test_format_datetime_table(case):
    assert datefmt.format_datetime(visit.to_clinic(_utc(case["in"]), case["tz"]), case["locale"]) == case["out"]


def test_invalid_input_gives_an_empty_string_never_an_error():
    for v in TABLE["invalid"]["date"]:
        assert datefmt.format_date(v, "en-IN") == "", v
    for v in TABLE["invalid"]["label"]:
        assert datefmt.format_label(v, "en-IN") == "" and date_label(v) == "", v
    for v in TABLE["invalid"]["instant"]:
        assert datefmt.format_time(v, "en-IN") == "" and datefmt.format_datetime(v, "en-IN") == "", v


def test_a_time_is_lower_case_am_pm_with_no_leading_zero_and_no_seconds():
    out = datefmt.format_time(datetime(2026, 10, 17, 9, 5, 59))
    assert out == "9:05 am" and "AM" not in out and not out.startswith("0")


def test_resolve_locale_known_unknown_and_one_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="doctor_dictation.core.datefmt"):
        assert datefmt.resolve_locale("en-IN") == "en-IN" and datefmt.resolve_locale(" en-IN ") == "en-IN"
        assert datefmt.resolve_locale(None) == "en-IN" and datefmt.resolve_locale("") == "en-IN"
        assert not caplog.records                                      # known or blank: silent
        for _ in range(3):
            assert datefmt.resolve_locale("fr-FR") == "en-IN"          # unknown: the default, never an error
    assert len(caplog.records) == 1 and "fr-FR" in caplog.text
    assert datefmt.format_date("2026-10-17", "xx") == "17 Oct 2026"    # a bad locale in a formatter falls back too


def test_the_setting_is_read_through_config(monkeypatch):
    from doctor_dictation import config
    monkeypatch.delenv("DATE_LOCALE", raising=False)
    assert config.build_settings().date_locale == "en-IN"
    monkeypatch.setenv("DATE_LOCALE", "en-GB")
    assert config.build_settings().date_locale == "en-GB"


def test_health_reports_the_locale_and_the_zone(monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    h = TestClient(M.app).get("/api/health").json()
    assert h["date_locale"] == "en-IN" and h["timezone"] == "Asia/Kolkata"
    override_settings(monkeypatch, date_locale="zz-ZZ")
    assert TestClient(M.app).get("/health").json()["date_locale"] == "en-IN"      # the RESOLVED locale reaches the page
    monkeypatch.delenv("TZ")
    assert TestClient(M.app).get("/health").json()["timezone"] == "Asia/Kolkata"  # unset: the clinic default


# --- the visit day follows the clinic zone, not the container clock ---------------------------------------------

def test_today_is_the_ist_date_between_midnight_and_0530(monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    assert visit.today(now=datetime(2026, 10, 16, 18, 30, tzinfo=timezone.utc)) == date(2026, 10, 17)   # 00:00 IST
    assert visit.today(now=datetime(2026, 10, 16, 23, 59, tzinfo=timezone.utc)) == date(2026, 10, 17)   # 05:29 IST, UTC says the 16th
    assert visit.today(now=datetime(2026, 10, 17, 0, 1, tzinfo=timezone.utc)) == date(2026, 10, 17)
    assert visit.today(now=datetime(2026, 10, 16, 18, 29, tzinfo=timezone.utc)) == date(2026, 10, 16)   # 23:59 IST the day before
    assert visit.today(now=datetime(2026, 10, 17, 18, 30, tzinfo=timezone.utc)) == date(2026, 10, 18)   # across midnight
    assert visit.today(now=datetime(2026, 12, 31, 20, 0, tzinfo=timezone.utc)) == date(2027, 1, 1)


def test_today_uses_the_default_zone_when_tz_is_unset_and_follows_another_zone(monkeypatch):
    monkeypatch.delenv("TZ", raising=False)
    assert visit.today(now=datetime(2026, 10, 16, 20, 0, tzinfo=timezone.utc)) == date(2026, 10, 17)
    monkeypatch.setenv("TZ", "UTC")
    assert visit.today(now=datetime(2026, 10, 16, 20, 0, tzinfo=timezone.utc)) == date(2026, 10, 16)
    monkeypatch.setenv("TZ", "America/New_York")
    assert visit.today(now=datetime(2026, 10, 17, 3, 0, tzinfo=timezone.utc)) == date(2026, 10, 16)


def test_a_zone_with_no_data_falls_back_to_the_server_date_and_logs_once(monkeypatch, caplog):
    monkeypatch.setenv("TZ", "Not/AZone")
    with caplog.at_level(logging.WARNING, logger="doctor_dictation.api.visit"):
        a, b = visit.today(), visit.today()
    assert a == b == datetime.now().astimezone().date()
    assert len(caplog.records) == 1 and "Not/AZone" in caplog.text
    assert visit.zone_name() == "Not/AZone"                          # named as set; only the date maths fell back


def test_the_real_clock_is_used_without_an_injected_one(monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    from zoneinfo import ZoneInfo
    before = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    assert visit.today() in (before, datetime.now(ZoneInfo("Asia/Kolkata")).date())


# --- print: the PDF header --------------------------------------------------------------------------------------

def test_the_pdf_header_prints_the_new_format_not_iso(monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    conn, eid = _conn()
    meta, _ = persistence._pdf_inputs(conn, {"opNo": "OP-1", "patientName": "A"}, date(2026, 10, 17), eid)
    assert meta["date"] == "17 Oct 2026"
    html = build_sheet_html({"patientName": "A", "opNo": "OP-1", "rx": []}, meta)
    assert "17 Oct 2026 &nbsp;|&nbsp; OP/IP No: OP-1" in html and "2026-10-17" not in html


def _conn():
    conn = dbmod.get_conn()
    dbmod.migrate(conn)
    return conn, dbmod.create_encounter(conn, dbmod.create_patient(conn, "A", "40 / M", None))


def test_save_prints_the_visit_day_in_the_new_format_and_the_reprint_uses_it_too(tmp_path, monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "v.db"))
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    conn = dbmod.get_conn()
    dbmod.migrate(conn)
    conn.close()
    seen = []

    def fake(structured, meta, out_path, layout=None):
        seen.append(meta["date"])
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-x")
        return Path(out_path)
    monkeypatch.setattr(persistence, "render_prescription", fake)
    monkeypatch.setattr(visit, "today", lambda *a, **k: date(2026, 10, 17))
    c = TestClient(M.app)
    r = c.post("/api/v1/documents", json={"structured": {"patientName": "Anita", "opNo": "OP-9", "rx": []}, "confirmed_rows": []})
    assert r.status_code == 200 and seen == ["17 Oct 2026"]
    # an old document with no stored PDF: re-rendered on demand from created_at, in the clinic zone (00:30 IST on the 18th)
    conn = dbmod.get_conn()
    conn.execute("UPDATE documents SET pdf_path = NULL, created_at = ? WHERE id = ?", ("2026-10-17T19:00:00Z", r.json()["document_id"]))
    conn.commit()
    conn.close()
    assert c.get(f"/api/v1/documents/{r.json()['document_id']}/pdf").status_code == 200
    assert seen[-1] == "18 Oct 2026"


def test_the_review_label_on_the_page_of_the_pdf_is_unchanged():
    html = build_sheet_html({"patientName": "A", "review": "1 week", "review_date": "2026-10-24", "rx": []}, {"date": "17 Oct 2026"})
    assert '<span class="rev-date">(Sat 24 Oct 2026)</span>' in html


def test_real_offline_render_prints_the_header_date(tmp_path):
    pytest.importorskip("playwright.sync_api")
    pdftotext = shutil.which("pdftotext")
    if pdftotext is None:
        pytest.skip("pdftotext is not installed")
    from doctor_dictation.pdf import PdfUnavailable, render_prescription
    out = tmp_path / "a.pdf"
    try:
        render_prescription({"patientName": "Anita", "opNo": "OP-1", "rx": []}, {"date": "17 Oct 2026", "opNo": "OP-1", "patientName": "Anita"}, out)
    except (PdfUnavailable, Exception) as exc:                      # no Chromium here: nothing to check
        pytest.skip(f"no offline render: {exc}")
    text = subprocess.run([pdftotext, str(out), "-"], capture_output=True, text=True, timeout=30).stdout
    assert "17 Oct 2026" in text and "2026-10-17" not in text


# --- the visit day is fixed at first save (I3 fix batch) --------------------------------------------------------

def _setup(tmp_path, monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "v.db"))
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    conn = dbmod.get_conn()
    dbmod.migrate(conn)
    conn.close()
    seen = []

    def fake(structured, meta, out_path, layout=None):
        seen.append((meta["date"], structured.get("review_date")))
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-x")
        return Path(out_path)
    monkeypatch.setattr(persistence, "render_prescription", fake)
    return TestClient(M.app), seen


def _set_created(doc_id, created):
    conn = dbmod.get_conn()
    conn.execute("UPDATE documents SET created_at = ? WHERE id = ?", (created, doc_id))
    conn.commit()
    conn.close()


def test_a_resave_on_a_later_day_keeps_the_first_visit_day_everywhere(tmp_path, monkeypatch):
    c, seen = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(visit, "today", lambda *a, **k: date(2026, 10, 17))                 # day 1
    form = {"patientName": "Anita", "opNo": "OP-9", "review": "1 week", "rx": []}
    r = c.post("/api/v1/documents", json={"structured": form, "confirmed_rows": []})
    doc = r.json()["document_id"]
    assert r.json()["visit_date"] == "2026-10-17" and seen[-1] == ("17 Oct 2026", "2026-10-24")   # a first save uses visit.today()
    _set_created(doc, "2026-10-17T05:00:00Z")                                              # created_at as a real day-1 save stores it
    monkeypatch.setattr(visit, "today", lambda *a, **k: date(2026, 10, 19))                 # day 3
    r2 = c.post("/api/v1/documents", json={"structured": form, "document_id": doc, "confirmed_rows": []})
    assert r2.status_code == 200 and r2.json()["visit_date"] == "2026-10-17"
    assert seen[-1] == ("17 Oct 2026", "2026-10-24")                                       # header AND review date: still day 1 (+7)
    assert c.get(f"/api/v1/documents/{doc}").json()["visit_date"] == "2026-10-17"          # the screen: day 1
    # a changed review text recomputes from the SAME visit day
    r3 = c.post("/api/v1/documents", json={"structured": {**form, "review": "2 weeks"}, "document_id": doc, "confirmed_rows": []})
    assert seen[-1] == ("17 Oct 2026", "2026-10-31") and r3.json()["visit_date"] == "2026-10-17"
    stored = json.loads(dbmod.get_document(dbmod.get_conn(), doc)["structured_json"])
    assert stored["review_date"] == "2026-10-31"


def test_visit_day_is_the_clinic_zone_day_of_created_at_and_old_rows_derive_it(tmp_path, monkeypatch):
    c, seen = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(visit, "today", lambda *a, **k: date(2030, 1, 1))
    form = {"patientName": "Old", "opNo": "OP-3", "review": "1 week", "rx": []}
    doc = c.post("/api/v1/documents", json={"structured": form, "confirmed_rows": []}).json()["document_id"]
    _set_created(doc, "2026-10-17T19:00:00Z")                                              # 00:30 IST on the 18th (UTC says the 17th)
    assert c.get(f"/api/v1/documents/{doc}").json()["visit_date"] == "2026-10-18"
    c.post("/api/v1/documents", json={"structured": form, "document_id": doc, "confirmed_rows": []})
    assert seen[-1] == ("18 Oct 2026", "2026-10-25")                                       # an old document: derived from created_at, not today
    for bad in ("", "garbage"):
        _set_created(doc, bad)
        assert c.get(f"/api/v1/documents/{doc}").json()["visit_date"] == ""               # no created_at: ''


def test_health_reports_the_effective_zone_when_the_tz_name_has_no_data(monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    monkeypatch.setenv("TZ", "Mars/Base")
    got = TestClient(M.app).get("/api/health").json()["timezone"]
    assert got != "Mars/Base" and got == (datetime.now().astimezone().tzname() or "UTC")   # what to_clinic really falls back to
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    assert TestClient(M.app).get("/api/health").json()["timezone"] == "Asia/Kolkata"
