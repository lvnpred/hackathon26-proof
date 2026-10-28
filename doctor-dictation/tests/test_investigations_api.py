"""Plan PQ-h Task 4: investigations become items on /api/format (checked on the answer, cached unchecked), each request
uses the clinic's own list, POST /api/v1/investigations/lookup, and the offline demo note is labelled. Offline."""
import json

import pytest
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.config import override_settings
from doctor_dictation.core import investigations as I
from doctor_dictation.core.determinism import _FORMAT_CACHE, normalize_transcript, validate_structured
from doctor_dictation.core.fallback import DEMO_WARNING, fallback_format, is_demo
from test_determinism import _stub_llm
from test_rules_split import DEMO
from test_users_routes import H, _signed_in, world  # noqa: F401

CAT = [{"canonical": "Renal Function Test", "aliases": ["rft", "kft"], "category": "Blood", "print": "RFT"},
       {"canonical": "Ultrasound Kidneys Ureters and Bladder", "aliases": ["usg kub"], "category": "Imaging",
        "print": "USG KUB"}]


def activate_catalogue(monkeypatch, entries, tmp_path):
    """Serve ``entries`` as the shipped catalogue (investigations.json is not built yet: owner CSV review)."""
    p = tmp_path / "investigations.json"
    p.write_text(json.dumps({"version": "t", "entries": entries}))
    monkeypatch.setattr(I, "CATALOGUE_PATH", p)
    monkeypatch.setattr(I, "_shipped_cache", None)
    monkeypatch.setattr(I, "_active", I.ContextVar("t", default=None))


@pytest.fixture()
def cat(monkeypatch, tmp_path):
    activate_catalogue(monkeypatch, CAT, tmp_path)
    _FORMAT_CACHE.clear()
    yield
    _FORMAT_CACHE.clear()


def _offline(monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")


def test_format_returns_items_with_statuses_and_caches_them_unchecked(monkeypatch, cat):
    _stub_llm(monkeypatch, [{"investigations": ["RFT", "Brain impulses"], "rx": []}])
    j = TestClient(M.app).post("/api/format", json={"transcript": "fever, advise rft"}).json()
    assert [(i["text"], i["status"]) for i in j["structured"]["investigations"]] == [("RFT", "verified"),
                                                                                    ("Brain impulses", "not-dictated")]
    assert j["structured"]["investigations"][0]["canonical"] == "Renal Function Test"
    assert _FORMAT_CACHE and all(i["status"] == "" and i["canonical"] == "" for v in _FORMAT_CACHE.values()
                                 for i in v["structured"]["investigations"])
    again = TestClient(M.app).post("/api/format", json={"transcript": "fever, advise rft"}).json()
    assert again["cached"] is True and again["structured"]["investigations"] == j["structured"]["investigations"]


def test_an_llm_cannot_mark_its_own_test_verified_or_the_doctors(monkeypatch, cat):
    forged = {"text": "Brain impulses", "status": "verified", "source": "doctor", "canonical": "Renal Function Test"}
    _stub_llm(monkeypatch, [{"investigations": [forged], "rx": []}])
    j = TestClient(M.app).post("/api/format", json={"transcript": "fever"}).json()
    assert j["structured"]["investigations"] == [{"text": "Brain impulses", "canonical": "", "status": "not-dictated",
                                                  "source": "dictated"}]


def test_a_cached_test_the_catalogue_gains_later_shows_on_the_next_answer(monkeypatch, cat, tmp_path):
    _stub_llm(monkeypatch, [{"investigations": ["Uroflow"], "rx": []}])
    ask = lambda: TestClient(M.app).post("/api/format", json={"transcript": "advise uroflow"}).json()  # noqa: E731
    assert ask()["structured"]["investigations"][0]["status"] == "new"
    activate_catalogue(monkeypatch, CAT + [{"canonical": "Uroflowmetry", "aliases": ["uroflow"], "category": "Other",
                                            "print": ""}], tmp_path)
    j = ask()
    assert j["cached"] is True and j["structured"]["investigations"][0]["status"] == "verified"


def test_validate_caps_items_with_the_old_warning_and_keeps_item_fields():
    out, w = validate_structured({"investigations": [f"T{i}" for i in range(14)]}, "")
    assert len(out["investigations"]) == 12 and "investigations: truncated 2 rows beyond the 12-row limit" in w
    assert [i["text"] for i in out["investigations"]] == [f"T{i}" for i in range(12)]
    out, _ = validate_structured({"investigations": [{"text": "RFT", "status": "verified", "source": "doctor",
                                                      "canonical": "X"}]}, "")
    assert out["investigations"][0] == {"text": "RFT", "canonical": "X", "status": "verified", "source": "doctor"}
    out, _ = validate_structured({"investigations": ["  ", None, 3, "ECG"]}, "")
    assert out["investigations"] == [{"text": "ECG", "canonical": "", "status": "", "source": "dictated"}]


def test_the_demo_note_lists_only_dictated_tests_and_is_labelled(monkeypatch, cat):
    out = fallback_format(normalize_transcript(DEMO))
    assert out["investigations"] == ["Urine culture", "Serum creatinine"]       # the golden demo dictates exactly these
    assert is_demo(normalize_transcript(DEMO).lower()) and not is_demo("fever, advise rft")
    _offline(monkeypatch)
    j = TestClient(M.app).post("/api/format", json={"transcript": DEMO}).json()
    assert j["engine"].startswith("fallback-rules") and DEMO_WARNING in j["warnings"]
    assert [i["status"] for i in j["structured"]["investigations"]] == ["new", "new"]   # heard; not in this catalogue
    other = TestClient(M.app).post("/api/format", json={"transcript": "fever, advise rft"}).json()
    assert DEMO_WARNING not in other["warnings"]


def test_the_demo_is_labelled_on_the_fallback_after_an_llm_error(monkeypatch, cat):
    _stub_llm(monkeypatch, ["not a dict"])
    j = TestClient(M.app).post("/api/format", json={"transcript": DEMO}).json()
    assert j["engine"].startswith("fallback-after-error") and DEMO_WARNING in j["warnings"]


def test_lookup_endpoint_reads_the_list_and_caps_input(monkeypatch, cat):
    c = TestClient(M.app)
    assert c.post("/api/v1/investigations/lookup", json={"text": "kft"}).json() == {"canonical": "Renal Function Test",
                                                                                   "status": "verified"}
    assert c.post("/api/v1/investigations/lookup", json={"text": "Brain impulses"}).json() == {"canonical": "",
                                                                                              "status": "new"}
    assert c.post("/api/v1/investigations/lookup", json={"text": "x" * 200}).status_code == 200
    assert c.post("/api/v1/investigations/lookup", json={"text": "x" * 201}).status_code == 422
    assert c.post("/api/v1/investigations/lookup", json={}).status_code == 422


def _add(client, kind, op, key, data=None):
    body = {"op": op, "entry_key": key, **({"data": data} if data is not None else {})}
    r = client.post(f"/api/v1/lists/{kind}/changes", json=body, headers=H)
    assert r.status_code == 200, r.text


def _lookup(client, text):
    r = client.post("/api/v1/investigations/lookup", json={"text": text}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def test_lookup_needs_sign_in_and_reads_only_the_callers_clinic_list(world, cat):
    with TestClient(M.app) as anon:
        assert anon.post("/api/v1/investigations/lookup", json={"text": "kft"}, headers=H).status_code == 401
    with _signed_in("dr.rao", "dr.iyer") as (rao, iyer):
        assert _lookup(rao, "Uroflow at home")["status"] == "new"
        _add(rao, "investigation", "add", "uroflow at home", {"name": "Uroflow at home"})   # an admin row is live at once
        assert _lookup(rao, "Uroflow at home") == {"canonical": "Uroflow at home", "status": "verified"}
        assert _lookup(iyer, "Uroflow at home")["status"] == "new"                       # another clinic's add
        assert _lookup(iyer, "rft")["status"] == "verified"


def test_a_test_the_clinic_hides_is_never_verified(world, cat, monkeypatch):
    _stub_llm(monkeypatch, [{"investigations": ["RFT"], "rx": []}])
    with _signed_in("dr.rao", "dr.iyer") as (rao, iyer):
        _add(rao, "investigation", "hide", "renal function test")
        assert _lookup(rao, "RFT") == {"canonical": "", "status": "new"}
        assert _lookup(iyer, "RFT")["status"] == "verified"
        mine = rao.post("/api/format", json={"transcript": "fever, advise rft"}, headers=H).json()
        theirs = iyer.post("/api/format", json={"transcript": "fever, advise rft"}, headers=H).json()
    assert [(i["text"], i["status"]) for i in mine["structured"]["investigations"]] == [("RFT", "new")]   # heard, not listed
    assert [(i["text"], i["status"]) for i in theirs["structured"]["investigations"]] == [("RFT", "verified")]


FORM = {"investigations": [{"text": "RFT", "canonical": "Renal Function Test", "status": "verified", "source": "dictated"},
                           {"text": "ECG", "canonical": "Electrocardiogram", "status": "verified", "source": "doctor"},
                           "CBC"], "rx": []}


def test_a_correction_about_medicines_keeps_every_item(monkeypatch, cat):            # Review Focus 4
    _stub_llm(monkeypatch, [{"rx": [{"name": "Dolo 650", "dose": "1-0-1"}]}])
    j = TestClient(M.app).post("/api/v1/correct", json={"transcript": "dolo twice daily", "current_form": FORM}).json()
    assert j["structured"]["investigations"] == I.coerce_items(FORM["investigations"])   # CBC stays unchecked ("")


def test_a_kept_not_dictated_item_keeps_its_source_and_status(monkeypatch, cat):
    kept = {"text": "Brain impulses", "canonical": "", "status": "not-dictated", "source": "doctor"}
    _stub_llm(monkeypatch, [{"rx": [{"name": "Dolo 650", "dose": "1-0-1"}]}])
    j = TestClient(M.app).post("/api/v1/correct", json={"transcript": "dolo twice daily",
                                                        "current_form": {"investigations": [kept], "rx": []}}).json()
    assert j["structured"]["investigations"] == [kept]


def test_a_replaced_test_is_checked_against_the_correction(monkeypatch, cat):
    _stub_llm(monkeypatch, [{"replace": {"investigations": [{"from": "RFT", "to": "KFT"}]}}])
    j = TestClient(M.app).post("/api/v1/correct", json={"transcript": "not rft, kft", "current_form": FORM}).json()
    assert j["structured"]["investigations"][0]["text"] == "KFT" and j["structured"]["investigations"][0]["status"] == "verified"


def test_the_llm_sees_strings_not_items(monkeypatch, cat):
    calls = _stub_llm(monkeypatch, [{}])
    TestClient(M.app).post("/api/v1/correct", json={"transcript": "ok", "current_form": FORM})
    assert '"investigations": ["RFT", "ECG", "CBC"]' in calls["messages"][0][1]["content"]


def test_a_correction_cannot_add_a_test_marked_as_the_doctors(monkeypatch, cat):    # final review I1
    forged = {"text": "ECG", "source": "doctor", "status": "verified"}
    _stub_llm(monkeypatch, [{"investigations": ["RFT", forged]}])
    form = {"investigations": [FORM["investigations"][0]], "rx": []}
    j = TestClient(M.app).post("/api/v1/correct", json={"transcript": "change dolo to twice daily", "current_form": form}).json()
    assert j["structured"]["investigations"] == [form["investigations"][0], {"text": "ECG", "canonical": "",
                                                                              "status": "not-dictated", "source": "dictated"}]
    assert I.screen(j["structured"]) == [{"index": 1, "text": "ECG"}]
