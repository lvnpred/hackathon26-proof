"""Final-fix I2: two rows with the same name keep their OWN status, lexicon match, instructions and dose note: the prior row is
paired by name AND occurrence (first with first, second with second), never "the last row of that name". Offline."""
import json

from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation import db as dbmod
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.safety import screen_unverified

STR = "[unverified strength: confirm with doctor]"
NAME = "[unverified: confirm with doctor]"


def _prior(name, status, strength, instructions="", **kw):
    return {"form": "Tab.", "name": name, "strength": strength, "dose": "1-0-0", "timing": "", "duration": "",
            "instructions": instructions, "status": status, "lexicon_match": kw.pop("lex", name), **kw}


def _fresh(name, strength="", **kw):                      # what validate_structured produced: every row regraded the same way
    return {"name": name, "strength": strength, "dose": "1-0-0", "status": "x", "lexicon_match": "x", "instructions": "", **kw}


def _view(rows):
    return [(r["strength"], r["status"], r["instructions"]) for r in rows]


def test_two_same_name_rows_of_different_status_keep_their_own_state_in_both_orders():
    weak = _prior("Amlodipine", "unverified-strength", "250 mg", f"after food {STR}")
    good = _prior("Amlodipine", "verified", "5 mg", "")
    for cur, want in (([weak, good], [("250 mg", "unverified-strength", f"after food {STR}"), ("5 mg", "verified", "")]),
                      ([good, weak], [("5 mg", "verified", ""), ("250 mg", "unverified-strength", f"after food {STR}")])):
        out = preserve_untouched_rx_status({"rx": cur}, {}, {"rx": [_fresh("Amlodipine", r["strength"]) for r in cur]})["rx"]
        assert _view(out) == want
        assert [r["lexicon_match"] for r in out] == ["Amlodipine", "Amlodipine"]


def test_a_dose_check_row_and_a_verified_twin_do_not_swap_state():
    dose = _prior("Metformin", "dose-check", "3000 mg", "", dose_note="3000 mg a day is high")
    good = _prior("Metformin", "verified", "500 mg", "")
    for cur in ([dose, good], [good, dose]):
        out = preserve_untouched_rx_status({"rx": cur}, {}, {"rx": [_fresh("Metformin", r["strength"]) for r in cur]})["rx"]
        assert [(r["strength"], r["status"]) for r in out] == [(r["strength"], r["status"]) for r in cur]
        assert [bool(r.get("dose_note")) for r in out] == [r["status"] == "dose-check" for r in cur]


def test_three_rows_a_b_a_pair_by_occurrence():
    a1 = _prior("Amlodipine", "unverified-strength", "250 mg", STR)
    b = _prior("Cetirizine", "verified", "10 mg")
    a2 = _prior("amlodipine ", "verified", "5 mg")               # same name after the usual trim and case fold
    out = preserve_untouched_rx_status({"rx": [a1, b, a2]}, {}, {"rx": [_fresh("Amlodipine", "250 mg"), _fresh("Cetirizine", "10 mg"), _fresh("Amlodipine", "5 mg")]})["rx"]
    assert [(r["name"], r["status"], r["instructions"]) for r in out] == [
        ("Amlodipine", "unverified-strength", STR), ("Cetirizine", "verified", ""), ("Amlodipine", "verified", "")]


def test_the_doctor_deleted_the_first_of_two_same_name_rows():
    # the page sends the rows that are left; the survivor keeps ITS state, not the deleted row's
    survivor = _prior("Amlodipine", "verified", "5 mg")
    out = preserve_untouched_rx_status({"rx": [survivor]}, {}, {"rx": [_fresh("Amlodipine", "5 mg")]})["rx"]
    assert _view(out) == [("5 mg", "verified", "")]
    weak = _prior("Amlodipine", "unverified-strength", "250 mg", STR)
    out = preserve_untouched_rx_status({"rx": [weak]}, {}, {"rx": [_fresh("Amlodipine", "250 mg")]})["rx"]
    assert _view(out) == [("250 mg", "unverified-strength", STR)]


def test_unique_renamed_patch_named_and_status_less_rows_behave_as_before():
    named = _prior("Amlodipine", "verified", "5 mg")
    out = preserve_untouched_rx_status({"rx": [named]}, {"rx": [{"name": "Amlodipine", "dose": "0-0-1"}]}, {"rx": [_fresh("Amlodipine", "5 mg", dose="0-0-1")]})["rx"]
    assert (out[0]["status"], out[0]["lexicon_match"]) == ("x", "x")            # patch-named: keeps the fresh grounding
    renamed = preserve_untouched_rx_status({"rx": [_prior("Amlodipine", "verified", "5 mg")]}, {}, {"rx": [_fresh("Nifedipine", "5 mg")]})["rx"]
    assert renamed[0]["status"] == "x"                                          # no prior row of that name: untouched
    bare = {"name": "Amlodipine", "strength": "5 mg"}                           # a prior row without a status
    out = preserve_untouched_rx_status({"rx": [bare, _prior("Amlodipine", "verified", "5 mg")]}, {}, {"rx": [_fresh("Amlodipine"), _fresh("Amlodipine")]})["rx"]
    assert ("status" in out[0], out[1]["status"]) == (False, "verified")


def test_a_patch_named_name_still_uses_up_its_occurrence_slot():
    cur = [_prior("Amlodipine", "verified", "5 mg"), _prior("Cetirizine", "unverified-strength", "99 mg", STR), _prior("Cetirizine", "verified", "10 mg")]
    out = preserve_untouched_rx_status({"rx": cur}, {}, {"rx": [_fresh("Amlodipine"), _fresh("Cetirizine"), _fresh("Cetirizine")]}, extra_named=["amlodipine"])["rx"]
    assert [r["status"] for r in out] == ["x", "unverified-strength", "verified"]


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "s.db"))
    conn = dbmod.get_conn(tmp_path / "s.db")
    dbmod.migrate(conn)
    return TestClient(M.app), conn


def _page(rows):                                          # what readRx sends: no generic, no derived fields
    return [{k: r[k] for k in ("form", "name", "strength", "dose", "timing", "duration", "instructions", "status", "lexicon_match")} for r in rows]


def test_correct_keeps_each_same_name_row_state(tmp_path, monkeypatch):
    client, conn = _client(tmp_path, monkeypatch)
    weak = _prior("Amlodipine", "unverified-strength", "250 mg", f"after food {STR}")
    good = _prior("Amlodipine", "verified", "5 mg", "")
    for cur in ([weak, good], [good, weak]):
        out = client.post("/api/v1/correct", json={"transcript": "", "current_form": {"rx": _page(cur)}}).json()["structured"]["rx"]
        assert [(r["strength"], r["status"], r["instructions"]) for r in out] == [(r["strength"], r["status"], r["instructions"]) for r in cur]
    conn.close()


def test_save_keeps_each_same_name_row_state_and_blocks_by_index(tmp_path, monkeypatch):
    client, conn = _client(tmp_path, monkeypatch)
    weak = _prior("Amlodipine", "unverified-strength", "250 mg", f"after food {STR}")
    good = _prior("Amlodipine", "verified", "5 mg", "")
    rows = _page([good, weak])
    blocked = client.post("/api/v1/documents", json={"structured": {"patientName": "Anita", "opNo": "OP-11", "rx": rows}, "confirmed_rows": []})
    assert blocked.status_code == 409 and [b["index"] for b in blocked.json()["block"]] == [1]
    r = client.post("/api/v1/documents", json={"structured": {"patientName": "Anita", "opNo": "OP-11", "rx": rows}, "confirmed_rows": [1]})
    assert r.status_code == 200, r.text
    saved = json.loads(dbmod.get_document(conn, r.json()["document_id"])["structured_json"])["rx"]
    assert [(s["strength"], s["status"], s["instructions"]) for s in saved] == [("5 mg", "verified", ""), ("250 mg", "unverified-strength", "after food")]
    r2 = client.post("/api/v1/documents", json={"structured": {"patientName": "Bina", "opNo": "OP-12", "rx": _page([weak, good])}, "confirmed_rows": [0]})
    saved = json.loads(dbmod.get_document(conn, r2.json()["document_id"])["structured_json"])["rx"]
    assert [(s["strength"], s["status"]) for s in saved] == [("250 mg", "unverified-strength"), ("5 mg", "verified")]
    conn.close()
