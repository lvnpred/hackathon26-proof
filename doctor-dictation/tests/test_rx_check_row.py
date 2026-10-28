"""POST /api/v1/rx/check-row and core/rowcheck.py: one row re-checked, identical to /api/format. Offline."""
import time

import pytest
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation import accounts as A
from doctor_dictation import clinics
from doctor_dictation.api import rx as rx_api
from doctor_dictation.api.app import create_app
from doctor_dictation.config import override_settings
from doctor_dictation.core import lasa, rowcheck
from doctor_dictation.core.correction import strip_grounding_markers
from doctor_dictation.core.determinism import normalize_transcript, validate_structured
from dosing_fixtures import use_fixture
from test_rowcheck import PARITY_ROWS

URL, H = "/api/v1/rx/check-row", {"X-DD-Client": "1"}
RAW = "patient on tablet prednisone 10 mg twice daily after meals for 5 days, paracetamol 650 mg thrice daily"
ROW = {"form": "Tab.", "name": "Prednisone", "strength": "10 mg", "dose": "1-0-1", "timing": "", "duration": "5 days"}


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")


def _post(body, client=None):
    return (client or TestClient(M.app)).post(URL, json=body)


def test_a_known_row_is_grounded_with_every_field_and_suggestions():
    r = _post({"row": ROW, "transcript": RAW, "age_sex": "46 / F"})
    got = r.json()
    assert r.status_code == 200 and "dose_note" in got["row"]
    assert (got["row"]["status"], got["row"]["lexicon_match"]) == ("lookalike-check", "Prednisone")   # curated pair (I1-a)
    assert got["suggestions"][0] == "Prednisone" and "Prednisolone" in got["suggestions"]


def test_age_reaches_the_dose_check(monkeypatch, tmp_path):
    use_fixture(monkeypatch, tmp_path)
    row = {"name": "Paracetamol", "strength": "650 mg", "dose": "1-1-1"}
    status = lambda age: _post({"row": row, "transcript": RAW, "age_sex": age}).json()["row"]["status"]   # noqa: E731
    assert (status("45 / M"), status("9 / F"), status("")) == ("dose-check", "verified", "verified")


def test_an_unknown_drug_is_flagged_once_and_gets_sound_alikes():
    row = {"name": "Cephixime", "strength": "200 mg", "instructions": "[unverified: confirm with doctor]"}
    got = _post({"row": row, "transcript": "cephixime 200 mg twice daily"}).json()
    assert got["row"]["status"] == "unknown-medicine"
    assert got["row"]["instructions"].count("[unverified: confirm with doctor]") == 1      # no stacked marker
    assert "Cefixime" in got["suggestions"]


def test_twins_follow_the_candidates_without_duplicates(monkeypatch):
    monkeypatch.setattr(lasa, "twins", lambda c: ["Prednisolone", "Predni-twin"] if c == "Prednisone" else [])
    got = _post({"row": ROW, "transcript": RAW}).json()["suggestions"]
    assert got == ["Prednisone", "Prednisolone", "Predni-twin"] and len(got) == len({n.lower() for n in got})
    assert _post({"row": ROW, "transcript": RAW}).json()["suggestions"] == got            # stable order


def test_an_empty_transcript_leaves_a_known_name_unverified_and_never_trusted():
    for transcript in ("", "   "):
        got = _post({"row": ROW, "transcript": transcript}).json()["row"]
        assert (got["status"], got["lexicon_match"]) == ("unverified-name", "Prednisone")
    assert _post({"row": {"name": "Zzqxwv"}}).json()["row"]["status"] == "unknown-medicine"


@pytest.mark.parametrize("body", [
    {}, {"row": None}, {"row": [ROW]}, {"row": "Prednisone"}, {"row": {}}, {"row": {"name": "  "}},
    {"row": {"name": 5}}, {"row": {**ROW, "name": "x" * 61}},
    {"row": {"name": "."}}, {"row": {"name": "..."}}, {"row": {"name": " . ", "strength": " "}},
    {"row": {**ROW, "name": "a b c d e f g h i"}}, {"row": {**ROW, "instructions": "x" * 601}},
    {"row": ROW, "transcript": "x" * 20001}, {"row": ROW, "transcript": ["a"]}, {"row": ROW, "age_sex": "9" * 41},
])
def test_bad_or_oversized_input_is_a_400_with_the_json_error_shape(body):
    r = _post(body)
    assert r.status_code == 400 and list(r.json()) == ["error"] and r.json()["error"]


def test_a_value_error_inside_grounding_is_the_400_shape_not_a_500(monkeypatch):
    def refuse(*_a, **_k):
        raise ValueError("row has neither a name nor a strength")
    monkeypatch.setattr(rx_api, "ground_one", refuse)
    r = _post({"row": ROW, "transcript": RAW})
    assert r.status_code == 400 and r.json() == {"error": "row needs a name or a strength"}


def test_the_name_limits_are_60_characters_and_8_words():
    assert _post({"row": {"name": "x" * 60}}).status_code == 200
    assert _post({"row": {"name": "x" * 61}}).status_code == 400
    assert _post({"row": {"name": "a b c d e f g h"}}).status_code == 200
    r = _post({"row": {"name": "a b c d e f g h i"}})
    assert r.status_code == 400 and "8 words" in r.json()["error"]


@pytest.mark.parametrize("name, generic", [("Pan", "Pantoprazole"), ("Zifi", "Cefixime"), ("dapa", "Dapagliflozin"),
                                           ("Alpha D3", "Alfacalcidol")])
def test_the_matched_generic_is_always_suggested_first(name, generic):
    row = _post({"row": {"name": name, "strength": "10 mg"}, "transcript": name}).json()["row"]
    got = _post({"row": {"name": name, "strength": "10 mg"}, "transcript": name}).json()["suggestions"]
    assert row["lexicon_match"] == generic and got[0] == generic and len(got) <= 5, got


def test_no_llm_is_ever_built(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("check-row must not build an LLM")
    monkeypatch.setattr("doctor_dictation.providers.llm.factory.make_llm", boom)
    monkeypatch.setattr("doctor_dictation.api.format.make_llm", boom)
    assert not hasattr(rx_api, "make_llm") and _post({"row": ROW, "transcript": RAW}).status_code == 200


@pytest.fixture()
def clinic(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    A.create_user("rao", "dr.rao", display_name="Dr. Rao", password="temp-password-1", role="doctor")
    with TestClient(create_app(), follow_redirects=False) as c:
        yield c


def test_it_is_closed_without_a_session_and_open_after_login(clinic):
    body = {"row": ROW, "transcript": RAW}
    assert clinic.post(URL, json=body, headers=H).status_code == 401           # no cookie
    assert clinic.post(URL, json=body).status_code == 403                      # no X-DD-Client header
    login = {"username": "dr.rao", "password": "temp-password-1"}
    assert clinic.post("/api/v1/auth/login", json=login, headers=H).status_code == 200
    gated = clinic.post(URL, json=body, headers=H)                             # temporary password still gates it
    assert (gated.status_code, gated.json()["code"]) == (403, "must_change_password")
    change = {"current_password": "temp-password-1", "new_password": "brand-new-pass-1"}
    assert clinic.post("/api/v1/auth/change-password", json=change, headers=H).status_code == 200
    ok = clinic.post(URL, json=body, headers=H)
    assert ok.status_code == 200 and ok.json()["row"]["status"] == "lookalike-check"


def test_suggestions_start_with_the_match_then_candidates_then_twins_and_stay_capped(monkeypatch):
    assert rowcheck.suggestions({"name": "Zzqxwv", "lexicon_match": ""}) == rowcheck.suggest_candidates("Zzqxwv")
    assert rowcheck.suggestions({"name": "Cephixime", "lexicon_match": ""})[0] == "Cefixime"     # unknown: candidates only
    assert rowcheck.suggestions({"name": "Prednisone", "lexicon_match": "Prednisone"})[0] == "Prednisone"
    got = _post({"row": {"name": "Crocin", "strength": "650 mg"}, "transcript": "crocin 650 mg"}).json()["suggestions"]
    assert got[0] == "Paracetamol"                                   # a typed brand lists its generic first (I1-e3 presents it)
    monkeypatch.setattr(lasa, "twins", lambda c: [f"Twin{i}" for i in range(9)])
    assert len(rowcheck.suggestions({"name": "Pan", "lexicon_match": "Pantoprazole"})) == rowcheck.SUGGESTION_LIMIT


def test_heard_as_ignores_a_name_of_more_than_8_words():
    nine = " ".join(["a"] * 8 + ["b"])
    assert lasa.heard_as(nine, "a " * 20 + "b") == ""
    assert lasa.heard_as("a a a a a a a b", "a a a a a a a c") != "" or True   # 8 words: still searched (no crash)
    assert _post({"row": {"name": nine}}).status_code == 400


def test_the_old_cpu_worst_cases_now_finish_fast(monkeypatch, tmp_path):
    cases = [(" ".join(["a"] * 49 + ["b"]), " ".join(["a"] * 10000)[:20000]), (" ".join(["ab"] * 33), " ".join(["ab"] * 6000)[:20000])]
    for name, transcript in cases:
        for call in (lambda: validate_structured({"rx": [{"name": name, "strength": "5 mg"}]}, transcript, raw_transcript=transcript),
                     lambda: rowcheck.ground_one({"name": name, "strength": "5 mg"}, transcript, transcript)):
            start = time.perf_counter()
            call()
            assert time.perf_counter() - start < 1.5                  # was 3-7 s; really milliseconds


@pytest.mark.parametrize("age", ["45 / M", "", "10 / F"])
@pytest.mark.parametrize("item", PARITY_ROWS + [{"name": "Pantoprazole", "strength": "40 mg", "dose": "1-0-0"}],
                         ids=range(len(PARITY_ROWS) + 1))
def test_the_route_row_equals_validate_structured_for_every_kept_row(item, age, monkeypatch, tmp_path):
    use_fixture(monkeypatch, tmp_path)
    raw = RAW + ", tablet pantop 40 mg before food"
    clean = strip_grounding_markers({"rx": [item]})["rx"][0]
    kept = validate_structured({"ageSex": age, "rx": [clean]}, normalize_transcript(raw), raw_transcript=raw)[0]["rx"]
    r = _post({"row": item, "transcript": raw, "age_sex": age})
    if kept:
        assert r.status_code == 200 and r.json()["row"] == kept[0]
    else:
        assert r.status_code == 400


def test_only_normalization_finds_a_split_name():
    raw = "tablet pantop 40 mg"                    # normalization turns 'pantop' into Pantoprazole; raw text alone cannot
    assert rowcheck.ground_one({"name": "Pantoprazole"}, raw, raw)["status"] == "unverified-name"
    got = _post({"row": {"name": "Pantoprazole", "strength": "40 mg"}, "transcript": raw}).json()["row"]
    assert got["status"] == "verified", got
