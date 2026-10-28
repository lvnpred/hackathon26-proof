from fastapi.testclient import TestClient
from test_correction import _stub_llm

import doctor_dictation.main as M
from doctor_dictation.api.format import SYSTEM_PROMPT
from doctor_dictation.config import override_settings
from doctor_dictation.core import doctor_generic


def test_prompt_keeps_the_brand_rule_and_asks_for_a_separate_suggestion():
    assert "never replace a brand with its generic" in SYSTEM_PROMPT
    assert '"generic_suggestion"' in SYSTEM_PROMPT and "Never put it in \"name\"" in SYSTEM_PROMPT


def test_suggestion_reaches_the_row_only_without_an_exact_match(monkeypatch):
    _stub_llm(monkeypatch, {"rx": [{"name": "Zerodol-P", "generic_suggestion": "Aceclofenac + Paracetamol", "dose": "1-0-1"},
                                   {"name": "Crocin", "generic_suggestion": "Paracetamol", "dose": "SOS"}]})
    rows = TestClient(M.app).post("/api/format", json={"transcript": "tab zerodol-p twice daily, crocin as needed"}).json()["structured"]["rx"]
    assert [r["generic_suggestion"] for r in rows] == ["Aceclofenac + Paracetamol", ""]
    assert [r["generic"] for r in rows][0] == "" and all(r["generic_source"] != "doctor" for r in rows)


def test_a_doctor_source_from_the_llm_is_ignored(monkeypatch):
    _stub_llm(monkeypatch, {"rx": [{"name": "Zerodol-P", "generic": "Aceclofenac", "generic_source": "doctor"}]})
    row = TestClient(M.app).post("/api/format", json={"transcript": "zerodol-p"}).json()["structured"]["rx"][0]
    assert row["generic_source"] != "doctor" and row["generic"] == ""


def test_the_rules_only_fallback_has_no_suggestion(monkeypatch):
    from doctor_dictation.config import get_settings
    keys = [k for k in ("openai_api_key", "deepseek_api_key", "groq_api_key", "meta_api_key") if hasattr(get_settings(), k)]
    override_settings(monkeypatch, llm_provider="openai", **{k: "" for k in keys})   # every LLM key this build knows
    rows = TestClient(M.app).post("/api/format", json={"transcript": "tab zerodol-p 1-0-1 for 5 days"}).json()["structured"]["rx"]
    assert all(r["generic_suggestion"] == "" for r in rows)


def test_strip_llm_fields_never_mutates_its_input():
    draft = {"rx": [{"name": "A", "generic": "x", "generic_source": "doctor", "generic_pending": True, "dose": "SOS"}]}
    out = doctor_generic.strip_llm_fields(draft)
    assert out["rx"] == [{"name": "A", "dose": "SOS"}]
    assert draft["rx"][0]["generic_source"] == "doctor"
