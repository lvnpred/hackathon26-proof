"""Plan I2-a: every row the lexicon knows carries its generic: first authoring, /correct and Save. Offline."""
import json

from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation import db as dbmod
from doctor_dictation.config import override_settings
from doctor_dictation.core.determinism import _FORMAT_CACHE, ground_rx, validate_structured

T = "tab cetirizine 10 mg once daily, tab crocin 500 mg sos, cap omeprazole 20 mg before food, tab citrizene 10 mg, tab amlo 5 mg"

def test_every_row_the_lexicon_knows_carries_its_generic():
    s, _w = validate_structured({"rx": [{"form": "Tab.", "name": n} for n in ("Cetirizine", "Crocin", "Omeprazole", "Citrizene", "Amlo")]}, T)
    assert [(r["name"], r["lexicon_match"], r["generic"]) for r in s["rx"]] == [
        ("Cetirizine", "Cetirizine", "Cetirizine"),      # a generic-named row: itself (was "")
        ("Crocin", "Paracetamol", "Paracetamol"),        # a brand: its generic (unchanged)
        ("Omeprazole", "Omeprazole", "Omeprazole"),
        ("Citrizene", "", ""),                           # unknown: no generic (Task 2 adds a Did you mean)
        ("Amlo", "Amlodipine", "Amlodipine")]            # a short alias kept as dictated: its generic
    rows, _issues = ground_rx([{"name": "Cetirizine"}, {"name": ""}], "cetirizine")
    assert [r["generic"] for r in rows] == ["Cetirizine", ""]

def test_first_authoring_shows_the_generic_on_every_known_row(monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")          # the rules path: no provider
    _FORMAT_CACHE.clear()
    j = TestClient(M.app).post("/api/format", json={"transcript": "tab cetirizine 10 mg once daily. tab crocin 650 mg sos"}).json()
    assert [(r["name"], r["generic"]) for r in j["structured"]["rx"]] == [("Cetirizine", "Cetirizine"), ("Crocin", "Paracetamol")]

def test_the_generic_survives_correct_and_save(tmp_path, monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "a.db"))
    conn = dbmod.get_conn(tmp_path / "a.db")
    dbmod.migrate(conn)                                                                  # the schema (the plan omitted it)
    client = TestClient(M.app)
    row = {"form": "Tab.", "name": "Cetirizine", "strength": "10 mg", "dose": "1-0-0", "timing": "", "duration": "",
           "instructions": "", "status": "verified", "lexicon_match": "Cetirizine"}          # what readRx sends: no generic
    out = client.post("/api/v1/correct", json={"transcript": "", "current_form": {"rx": [row]}}).json()
    assert out["structured"]["rx"][0]["generic"] == "Cetirizine"
    r = client.post("/api/v1/documents", json={"structured": {"patientName": "Anita", "opNo": "OP-9", "rx": [row]}, "confirmed_rows": []})
    assert r.status_code == 200, r.text
    saved = json.loads(dbmod.get_document(conn, r.json()["document_id"])["structured_json"])["rx"][0]
    conn.close()
    assert (saved["name"], saved["generic"]) == ("Cetirizine", "Cetirizine")


def test_check_row_sends_the_generic_for_a_resolved_name_whatever_its_status(monkeypatch):
    """After a Did you mean tap the row is unverified-name (nobody dictated it) but its name resolves: the generic stays."""
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    client = TestClient(M.app)
    for transcript in ("", "tab citrizene 10 mg at night. tab croissin 500 mg"):
        got = {}
        for name in ("Cetirizine", "Crocin", "Citrizene"):
            row = client.post("/api/v1/rx/check-row", json={"row": {"form": "Tab.", "name": name, "strength": "10 mg", "dose": "0-0-1"},
                                                              "transcript": transcript}).json()["row"]
            got[name] = (row["status"], row["lexicon_match"], row["generic"])
        assert got["Cetirizine"] == ("unverified-name", "Cetirizine", "Cetirizine")
        assert got["Crocin"] == ("unverified-name", "Paracetamol", "Paracetamol")
        assert got["Citrizene"][2] == ""                                                    # an unresolved name never gets one


def _client(tmp_path, monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "a.db"))
    conn = dbmod.get_conn(tmp_path / "a.db")
    dbmod.migrate(conn)
    return TestClient(M.app), conn


def test_untouched_combination_row_keeps_its_blank_generic_after_a_correction(tmp_path, monkeypatch):
    client, conn = _client(tmp_path, monkeypatch)
    conn.close()
    row = {"form": "Tab.", "name": "Zerodol-P", "strength": "", "dose": "1-0-1", "timing": "", "duration": "",
           "instructions": "", "status": "unknown-medicine", "lexicon_match": ""}
    out = client.post("/api/v1/correct", json={"transcript": "", "current_form": {"rx": [row]}}).json()["structured"]["rx"][0]
    assert (out["generic"], out["generic_source"], out["combo_base"], out["did_you_mean"]) == ("", "", "Zerodol", "")


def test_a_stale_match_on_a_fuzzy_name_saves_no_generic(tmp_path, monkeypatch):
    client, conn = _client(tmp_path, monkeypatch)
    base = {"form": "Tab.", "strength": "500 mg", "dose": "1-0-1", "timing": "", "duration": "", "instructions": "",
            "status": "verified", "lexicon_match": "Paracetamol"}
    rows = [{**base, "name": "Crocinn"}, {**base, "name": "Crocin"}]
    r = client.post("/api/v1/documents", json={"structured": {"patientName": "Anita", "opNo": "OP-9", "rx": rows}, "confirmed_rows": [0]})
    assert r.status_code == 200, r.text
    saved = json.loads(dbmod.get_document(conn, r.json()["document_id"])["structured_json"])["rx"]
    conn.close()
    assert [(x["name"], x["generic"], x["generic_source"]) for x in saved] == [
        ("Crocinn", "", ""), ("Crocin", "Paracetamol", "lexicon")]


def test_restored_rows_recompute_the_three_generic_fields():
    from doctor_dictation.core.correction import preserve_untouched_rx_status
    prev = [{"name": n, "status": "verified", "lexicon_match": "Paracetamol"} for n in ("Crocinn", "Crocin")]
    fresh = [{"name": n, "status": "verified", "lexicon_match": "Paracetamol", "generic": "X", "generic_source": "X", "combo_base": "X"}
             for n in ("Crocinn", "Crocin")]
    out = preserve_untouched_rx_status({"rx": prev}, {}, {"rx": fresh})["rx"]
    assert [(r["generic"], r["generic_source"], r["combo_base"]) for r in out] == [("", "", ""), ("Paracetamol", "lexicon", "")]
