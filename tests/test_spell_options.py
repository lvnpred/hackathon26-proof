"""Plan I2-c: check-row sends the Spell it list: a generic and a reason per name, capped at 40, with the total found."""
import contextvars
import time
from datetime import date

import pytest
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.core import formulary as F
from doctor_dictation.core import rowcheck

TODAY = date(2026, 10, 17)
URL = "/api/v1/rx/check-row"


@pytest.fixture(autouse=True)
def _no_layer_leaks():
    F.activate(F.ClinicLayer())
    yield
    F.activate(F.ClinicLayer())


def _db_row(name, count):
    return {"id": 0, "name": name, "generic": None, "confirm_count": count, "first_seen_at": "2026-10-17T00:00:00Z",
            "last_seen_at": "2026-10-17T00:00:00Z", "added_by": None}


def test_check_row_returns_options_with_a_generic_a_reason_and_a_total(frozen_lexicon):
    c = TestClient(M.app)
    j = c.post(URL, json={"row": {"name": "Citrizene", "strength": "10 mg"}, "transcript": "tab citrizene 10 mg at night"}).json()
    assert j["suggestions"] == ["Cetirizine", "Ceftriaxone"]                         # unchanged (I1-r1)
    assert j["options"] == [{"name": "Cetirizine", "generic": "Cetirizine", "reason": "sounds"},
                            {"name": "Ceftriaxone", "generic": "Ceftriaxone", "reason": "sounds"}] and j["total"] == 2
    p = c.post(URL, json={"row": {"name": "Prednisone", "strength": "10 mg"}, "transcript": "tab prednisone 10 mg"}).json()
    assert [(o["name"], o["reason"]) for o in p["options"][:2]] == [("Prednisone", "matched"), ("Prednisolone", "lookalike")]
    assert c.post(URL, json={"row": {"name": "x" * 61}}).status_code == 400   # the I1-d input rules stay


def test_options_are_capped_and_the_total_says_how_many_were_found(monkeypatch):
    monkeypatch.setattr(rowcheck, "scored_spellings", lambda name, k: [(f"Zorb{i:02d}x", f"Zorb{i:02d}x", 0.9) for i in range(60)][:k])
    opts, total = rowcheck.options({"name": "Zorbex", "lexicon_match": ""})
    assert (len(opts), total, opts[0]["name"], opts[-1]["name"]) == (40, 60, "Zorb00x", "Zorb39x")
    assert rowcheck.options({"name": "Zorbex", "lexicon_match": ""}, cap=8)[0][7]["name"] == "Zorb07x"


def test_the_response_is_small_and_the_input_rules_still_answer_error_400s(frozen_lexicon, monkeypatch):
    monkeypatch.setattr(rowcheck, "scored_spellings", lambda name, k: [(f"Zorb{i:02d}x", f"Zorb{i:02d}x", 0.9) for i in range(90)][:k])
    c = TestClient(M.app)
    j = c.post(URL, json={"row": {"name": "Zorbex", "strength": "5 mg"}, "transcript": "tab zorbex 5 mg"}).json()
    assert len(j["options"]) == 40 and j["total"] == 90 and len(c.post(URL, json={"row": {"name": "Zorbex"}}).content) < 12000
    for body in ({"row": {"name": "one two three four five six seven eight nine"}}, {"row": {"name": ""}}, {"row": "x"}):
        r = c.post(URL, json=body)
        assert r.status_code == 400 and list(r.json()) == ["error"]


def test_clinic_names_join_only_rows_without_a_lexicon_match_in_usage_order(frozen_lexicon):
    rows = [_db_row("Dolvexa", 2), _db_row("Dolvexi", 30), _db_row("Dolmexa", 500)]
    F.activate(F.ranked_layer(rows, TODAY))
    opts, total = rowcheck.options({"name": "Dolvex", "lexicon_match": ""})
    assert [(o["name"], o["reason"]) for o in opts] == [("Dolvexi", "clinic"), ("Dolvexa", "clinic"), ("Dolmexa", "clinic")]
    assert [o["name"] for o in opts] == rowcheck.suggestions({"name": "Dolvex", "lexicon_match": ""}) and total == 3
    F.activate(F.ranked_layer([_db_row("Prednisome", 900)], TODAY))                  # a matched row never lists clinic names
    got, _ = rowcheck.options({"name": "Prednisone", "lexicon_match": "Prednisone"})
    assert "Prednisome" not in [o["name"] for o in got] and got[0] == {"name": "Prednisone", "generic": "Prednisone", "reason": "matched"}


def test_options_never_leak_another_clinics_names():
    def ask(layer):
        def run():
            F.activate(layer)
            return [o["name"] for o in rowcheck.options({"name": "Dolvex", "lexicon_match": ""})[0]]
        return contextvars.copy_context().run(run)
    assert ask(F.ranked_layer([_db_row("Dolvexa", 5)], TODAY)) == ["Dolvexa"]
    assert ask(F.ranked_layer([_db_row("Dolvexi", 5)], TODAY)) == ["Dolvexi"]
    assert ask(F.ClinicLayer()) == []
    assert rowcheck.options({"name": "Dolvex", "lexicon_match": ""}) == ([], 0)      # the surrounding context has no layer


def test_options_stay_fast_with_a_thousand_clinic_names(frozen_lexicon):
    F.activate(F.ClinicLayer(tuple((f"Name{i:04d}x", "") for i in range(1000))))
    for name in ("Citrizene", "Croissin", "Pantop", "Azithro"):
        rowcheck.options({"name": name, "lexicon_match": ""})                        # warm
        t = time.perf_counter()
        for _ in range(5):
            rowcheck.options({"name": name, "lexicon_match": ""})
        assert (time.perf_counter() - t) / 5 < 0.25, name                              # plan 50 ms; generous for a loaded CI box
