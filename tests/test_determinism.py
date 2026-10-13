"""Determinism gate (P2): same input -> identical output, 5/5 runs.

Offline: forces the rules+lexicon fallback path (no LLM, no network) by
clearing DEEPSEEK_API_KEY, so this runs on any machine incl. CI.

Run:  ./.venv-arm64/Scripts/python -m pytest tests/ -q
"""
import json
from pathlib import Path

import doctor_dictation.main as M
from doctor_dictation.config import get_settings, override_settings
from doctor_dictation.providers.llm.factory import make_llm
from doctor_dictation.providers.stt import local as L
from doctor_dictation.providers.stt.base import SttError, Transcript
from doctor_dictation.providers.stt.factory import make_stt
from doctor_dictation.providers.stt.openai import OpenAiStt
from doctor_dictation.core.fallback import fallback_format
from doctor_dictation.core.determinism import (
    ALLOWED_DOSES,
    RX_UNKNOWN_MEDICINE,
    RX_UNVERIFIED_STRENGTH,
    RX_VERIFIED,
    build_repair_message,
    correct_drugs,
    ground_rx,
    loop_should_continue,
    normalize_numbers,
    normalize_transcript,
    open_issues,
    validate_structured,
)

GOLDEN = json.loads((Path(__file__).parent / "golden.json").read_text(encoding="utf-8"))


def run_pipeline(transcript: str) -> dict:
    norm = normalize_transcript(transcript)
    structured, warnings = validate_structured(fallback_format(norm), norm)
    return {"normalized": norm, "structured": structured, "warnings": warnings}


def test_normalize_numbers():
    assert normalize_numbers("for two weeks and five days") == "for 2 weeks and 5 days"


def test_correct_drugs_no_duplication_in_canonical():
    out = correct_drugs("syrup Potassium Magnesium Citrate 15 ml three times daily")
    assert "Potassium Potassium" not in out
    assert out.count("Potassium Magnesium Citrate") == 1
    assert correct_drugs("tablet tam sulosin 0.4 mg") == "tablet Tamsulosin 0.4 mg"


def test_correct_drugs_splits_and_misspellings():
    assert "Tamsulosin" in correct_drugs("tablet tam sulosin 0.4 mg")
    assert "Paracetamol" in correct_drugs("have paracetmol twice a day")
    assert "Ranitidine" in correct_drugs("rantidine 150 mg")
    assert "Azithromycin" in correct_drugs("tablet azithro 500 mg")


def test_alias_map_file_order_independent():
    import random
    import doctor_dictation.core.determinism as D
    base = D._alias_map()
    entries = list(D.load_lexicon())
    random.Random(42).shuffle(entries)
    D._lexicon_cache = entries
    try:
        assert D._alias_map() == base
    finally:
        D._lexicon_cache = None
        D.load_lexicon()
    assert base.get("crocin") == "Paracetamol"  # brand -> generic, always
    assert base.get("dolo") == "Paracetamol"


def test_golden_deterministic_5x():
    for case in GOLDEN:
        first = json.dumps(run_pipeline(case["transcript"]), sort_keys=True)
        for _ in range(4):
            assert json.dumps(run_pipeline(case["transcript"]), sort_keys=True) == first, case["id"]


def test_golden_expected_fields():
    for case in GOLDEN:
        out = run_pipeline(case["transcript"])["structured"]
        for want in case.get("diagnosis_contains", []):
            assert any(want.lower() in d.lower() for d in out["diagnosis"]), (case["id"], out)
        for rx in case.get("rx", []):
            match = [m for m in out["rx"] if m["name"].lower() == rx["name"].lower()]
            assert match, (case["id"], f"missing {rx['name']}", out["rx"])
            assert match[0]["dose"] == rx["dose"], (case["id"], match[0])
            assert match[0]["dose"] in ALLOWED_DOSES
        if "patientName" in case:
            assert out["patientName"] == case["patientName"], (case["id"], out)
        if "ageSex" in case:
            assert out["ageSex"] == case["ageSex"], (case["id"], out)
        if "review_contains" in case:
            assert case["review_contains"] in out["review"], (case["id"], out)


def test_no_hallucinated_rx():
    out = run_pipeline("patient complains of headache since one day advise rest review after three days")
    assert out["structured"]["rx"] == []


def test_validator_flags_unverified_drug():
    fake_llm = {"rx": [{"form": "Tab.", "name": "Atorvastatin", "strength": "20 mg",
                        "dose": "1-0-0", "timing": "After food", "duration": "30 days",
                        "instructions": ""}]}
    validated, warnings = validate_structured(fake_llm, "fever since two days, rest advised")
    assert validated["rx"][0]["instructions"].startswith("[unverified")
    assert warnings, "expected unverified warning"


def _client(monkeypatch):
    from fastapi.testclient import TestClient
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    return TestClient(M.app)


def test_api_format_deterministic_and_cached(monkeypatch):
    client = _client(monkeypatch)
    body = {"transcript": GOLDEN[1]["transcript"]}
    r1 = client.post("/api/format", json=body)
    assert r1.status_code == 200, r1.text
    r2 = client.post("/api/format", json=body)
    assert r2.status_code == 200, r2.text
    assert r1.json()["structured"] == r2.json()["structured"]
    assert r2.json()["cached"] is True
    assert r2.json()["transcript_sha256"] == r1.json()["transcript_sha256"]


def test_api_format_empty_400(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/api/format", json={"transcript": "   "})
    assert r.status_code == 400


def test_api_health_reports_lexicon(monkeypatch):
    client = _client(monkeypatch)
    h = client.get("/api/health").json()
    assert h["lexicon_entries"] >= 300
    assert h["lexicon_version"] == "1.1.0"
    assert h["stt_engine_requested"] == "auto"
    assert h["stt_engine_active"] in ("faster-whisper", "onnx",
                                      "openai-whisper-api", "browser-webspeech")
    assert "available" in h["onnx_stt"]
    assert h["llm_configured"] is False  # both keys cleared in _client
    assert h["llm_provider"] in ("openai", "deepseek")


def test_model_selection_endpoints_removed(monkeypatch):
    client = _client(monkeypatch)
    # GET /api/models: no app route, no static file at that path -> 404.
    assert client.get("/api/models").status_code == 404
    # POST /api/model is no longer a route. The SPA StaticFiles mount (GET/HEAD
    # only) answers a non-route POST with 405 when the frontend dir is present,
    # or the app replies 404 when it is not. Either way the model-switch
    # endpoint is gone (it used to return 200/400/503).
    assert client.post("/api/model", json={"model": "tiny.en"}).status_code in (404, 405)


def test_health_still_reports_engine(monkeypatch):
    h = _client(monkeypatch).get("/api/health").json()
    assert h["stt_engine_requested"] == "auto"
    assert "whisper_model" in h


def test_llm_config_default_openai(monkeypatch):
    override_settings(monkeypatch, llm_provider="openai", openai_api_key="k",
                      llm_model="gpt-6-luna", openai_base_url="https://api.openai.com/v1")
    llm = make_llm(get_settings())
    assert (llm.name, llm.model, llm.base_url) == ("openai", "gpt-6-luna", "https://api.openai.com/v1")


def test_llm_config_deepseek_and_missing_key(monkeypatch):
    override_settings(monkeypatch, llm_provider="deepseek", deepseek_api_key="")
    assert make_llm(get_settings()) is None
    override_settings(monkeypatch, deepseek_api_key="d")
    llm = make_llm(get_settings())
    assert (llm.name, llm.model) == ("deepseek", get_settings().deepseek_model)


def test_llm_config_openai_missing_key(monkeypatch):
    override_settings(monkeypatch, llm_provider="openai", openai_api_key="")
    assert make_llm(get_settings()) is None


def test_complete_drops_unsupported_param(monkeypatch):
    import asyncio
    from fastapi.testclient import TestClient
    override_settings(monkeypatch, llm_provider="openai", openai_api_key="k", llm_model="gpt-6-luna")

    draft = {"rx": [_rx("Paracetamol", strength="650 mg")]}
    seen = []

    class Resp:
        def __init__(self, status, body):
            self.status_code = status
            self._body = body
            self.text = json.dumps(body) if isinstance(body, dict) else body

        def json(self):
            if self.status_code != 200:
                raise ValueError("no json")
            return self._body

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, **kw):
            seen.append(dict(kw["json"]))
            if len(seen) == 1:
                return Resp(400, "Unsupported value: 'temperature' does not support 0.0")
            return Resp(200, {"choices": [{"message": {
                "content": json.dumps(draft)}}]})

    monkeypatch.setattr("httpx.AsyncClient", Client)
    r = TestClient(M.app).post("/api/format", json={
        "transcript": "tablet Paracetamol 650 mg twice daily"})
    assert r.status_code == 200, r.text
    assert len(seen) == 2
    assert "temperature" in seen[0] and "temperature" not in seen[1]
    assert r.json()["structured"]["rx"][0]["status"] == "verified"


def test_transcribe_onnx_unconfigured_503(monkeypatch):
    from fastapi.testclient import TestClient
    override_settings(monkeypatch, stt_engine="onnx", stt_chain=())
    r = TestClient(M.app).post("/api/transcribe",
                               files={"audio": ("t.webm", b"\x00\x01", "audio/webm")})
    assert r.status_code == 503
    assert r.json()["fallback"] == "browser"


def test_transcribe_explicit_faster_whisper_missing_503(monkeypatch):
    from fastapi.testclient import TestClient
    override_settings(monkeypatch, stt_engine="faster-whisper", stt_chain=())
    monkeypatch.setattr(L, "faster_whisper_available", lambda: False)
    r = TestClient(M.app).post("/api/transcribe",
                               files={"audio": ("t.webm", b"\x00\x01", "audio/webm")})
    assert r.status_code == 503


def _cloud_ok(transcript="hello world"):
    async def fake(self, audio_bytes, filename, hints=()):
        assert tuple(hints) == ()  # the route passes no hints until ACC2
        return Transcript(text=transcript, engine="openai-whisper-api")
    return fake


def _cloud_fail(msg="boom"):
    async def fake(self, audio_bytes, filename, hints=()):
        assert tuple(hints) == ()
        raise SttError(msg)
    return fake


def test_transcribe_cloud_default(monkeypatch):
    from fastapi.testclient import TestClient
    from doctor_dictation.core.determinism import normalize_transcript, transcript_sha
    override_settings(monkeypatch, stt_engine="auto", stt_chain=(), openai_api_key="k")
    monkeypatch.setattr(OpenAiStt, "transcribe", _cloud_ok("fever and cough"))
    r = TestClient(M.app).post("/api/transcribe",
                               files={"audio": ("t.webm", b"\x00\x01", "audio/webm")})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["engine"] == "openai-whisper-api"
    assert j["transcript"] == "fever and cough"
    assert j["transcript_sha256"] == transcript_sha(normalize_transcript("fever and cough"))


def test_transcribe_cloud_fail_falls_back_to_small(monkeypatch):
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    override_settings(monkeypatch, stt_engine="auto", stt_chain=(), openai_api_key="k",
                      whisper_model="large-v3-turbo")
    monkeypatch.setattr(OpenAiStt, "transcribe", _cloud_fail("down"))
    monkeypatch.setattr(L, "faster_whisper_available", lambda: True)
    monkeypatch.setattr(L, "_model", None)
    monkeypatch.setattr(L, "_pinned_name", None)

    class FakeModel:
        def transcribe(self, path, **kw):
            assert kw.get("temperature") == 0.0  # pinned decode preserved
            return ([SimpleNamespace(text="hello world")],
                    SimpleNamespace(language="en", duration=1.0))

    monkeypatch.setattr(L, "get_model", lambda: FakeModel())
    r = TestClient(M.app).post("/api/transcribe",
                               files={"audio": ("t.webm", b"\x00\x01", "audio/webm")})
    assert r.status_code == 200, r.text
    assert r.json()["engine"] == "local:small.en"
    assert L.whisper_model_name() == "small.en"  # turbo avoided in fallback


def test_transcribe_cloud_fail_no_local_502(monkeypatch):
    from fastapi.testclient import TestClient
    override_settings(monkeypatch, stt_engine="auto", stt_chain=(), openai_api_key="k")
    monkeypatch.setattr(OpenAiStt, "transcribe", _cloud_fail("down"))
    monkeypatch.setattr(L, "faster_whisper_available", lambda: False)
    r = TestClient(M.app).post("/api/transcribe",
                               files={"audio": ("t.webm", b"\x00\x01", "audio/webm")})
    assert r.status_code == 502
    assert "down" in r.json()["error"]


def _active():
    return make_stt(get_settings()).active_name()


def test_active_engine_prefers_cloud(monkeypatch):
    override_settings(monkeypatch, stt_engine="auto", stt_chain=(), openai_api_key="k")
    assert _active() == "openai-whisper-api"
    override_settings(monkeypatch, openai_api_key="")
    monkeypatch.setattr(L, "faster_whisper_available", lambda: False)
    assert _active() == "browser-webspeech"


# ---- Part A: agent-loop grounding ----

def test_ground_unknown_medicine_kept_and_flagged():
    draft = {"rx": [{"form": "Tab.", "name": "Medalpha", "strength": "10 mg",
                     "dose": "1-0-0", "timing": "After food", "duration": "",
                     "instructions": ""}]}
    validated, warnings = validate_structured(draft, "fever, rest advised")
    assert len(validated["rx"]) == 1  # kept, never silently dropped
    row = validated["rx"][0]
    assert row["status"] == RX_UNKNOWN_MEDICINE
    assert row["lexicon_match"] == ""
    assert "[unverified" in row["instructions"]
    assert warnings


def test_ground_unverified_strength():
    draft = {"rx": [{"form": "Tab.", "name": "Paracetamol", "strength": "999 mg",
                     "dose": "1-0-0", "timing": "", "duration": "",
                     "instructions": ""}]}
    validated, _ = validate_structured(
        draft, "tablet Paracetamol 999 mg once daily")
    row = validated["rx"][0]
    assert row["status"] == RX_UNVERIFIED_STRENGTH
    assert row["lexicon_match"] == "Paracetamol"
    assert "unverified strength" in row["instructions"]


def test_ground_verified_row():
    rows, issues = ground_rx(
        [{"name": "Paracetamol", "strength": "650 mg"}],
        "tablet Paracetamol 650 mg twice daily after food")
    assert issues == []
    assert rows[0]["status"] == RX_VERIFIED
    assert rows[0]["lexicon_match"] == "Paracetamol"


def test_repair_message_names_offenders():
    rows, issues = ground_rx(
        [{"name": "Atorvastatin", "strength": "20 mg"}], "fever, rest advised")
    msg = build_repair_message(issues, "fever, rest advised")
    assert "Atorvastatin" in msg
    assert "FULL corrected JSON" in msg


def test_loop_guard():
    assert loop_should_continue(2, 1, 1) is True
    assert loop_should_continue(1, 0, 1) is False  # nothing open
    assert loop_should_continue(1, 1, 1) is False  # no progress
    assert loop_should_continue(2, 1, 3) is False  # budget spent
    assert loop_should_continue(3, 2, 2) is True


def _stub_llm(monkeypatch, drafts):
    """Queue of draft dicts served as LLM outputs; records all message lists."""
    calls = {"n": 0, "messages": []}

    class Resp:
        def __init__(self, draft):
            self.status_code = 200
            self._draft = draft
            self.text = json.dumps(draft)

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(self._draft)}}]}

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, **kw):
            calls["messages"].append(kw["json"]["messages"])
            draft = drafts[min(calls["n"], len(drafts) - 1)]
            calls["n"] += 1
            return Resp(draft)

    monkeypatch.setattr("httpx.AsyncClient", Client)
    override_settings(monkeypatch, openai_api_key="dummy-key", llm_provider="openai")
    return calls


def _rx(name, **kw):
    row = {"form": "Tab.", "name": name, "strength": "", "dose": "1-0-0",
           "timing": "", "duration": "", "instructions": ""}
    row.update(kw)
    return row


def test_loop_repairs_to_verified(monkeypatch):
    from fastapi.testclient import TestClient
    bad = {"rx": [_rx("Atorvastatin", strength="20 mg"),
                  _rx("Paracetamol", strength="650 mg")]}
    fixed = {"rx": [_rx("Paracetamol", strength="650 mg")]}
    calls = _stub_llm(monkeypatch, [bad, fixed])
    r = TestClient(M.app).post("/api/format", json={
        "transcript": "fever, tablet Paracetamol 650 mg twice daily after food"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert calls["n"] == 2
    assert j["grounding"]["llm_calls"] == 2
    assert j["grounding"]["rounds"] == 1
    assert j["grounding"]["open_issues"] == []
    assert "+loop1" in j["engine"]
    assert [m["name"] for m in j["structured"]["rx"]] == ["Paracetamol"]
    # repair prompt named the offender and kept the original user message
    repair_msgs = calls["messages"][1]
    assert "Atorvastatin" in repair_msgs[-1]["content"]
    assert repair_msgs[0]["role"] == "system"


def test_loop_terminates_at_cap(monkeypatch):
    from fastapi.testclient import TestClient
    d3 = {"rx": [_rx("Medalpha"), _rx("Medbeta"), _rx("Medgamma")]}
    d2 = {"rx": [_rx("Medalpha"), _rx("Medbeta")]}
    d1 = {"rx": [_rx("Medalpha")]}
    calls = _stub_llm(monkeypatch, [d3, d2, d1, d1])
    r = TestClient(M.app).post("/api/format", json={
        "transcript": "fever, rest advised, review next week"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert calls["n"] == 3  # extract + 2 repairs = cap, then finalize
    assert j["grounding"]["llm_calls"] == 3
    assert j["grounding"]["rounds"] == 2
    assert len(j["structured"]["rx"]) == 1  # best draft (fewest issues) kept
    assert j["structured"]["rx"][0]["status"] == RX_UNKNOWN_MEDICINE
    assert len(j["grounding"]["open_issues"]) == 1


def test_loop_best_draft_wins_on_regression(monkeypatch):
    from fastapi.testclient import TestClient
    one_issue = {"rx": [_rx("Atorvastatin", strength="20 mg")]}
    three_issues = {"rx": [_rx("Atorvastatin", strength="20 mg"),
                           _rx("Medalpha"), _rx("Medbeta")]}
    calls = _stub_llm(monkeypatch, [one_issue, three_issues])
    r = TestClient(M.app).post("/api/format", json={
        "transcript": "fever, rest advised"})
    j = r.json()
    assert calls["n"] == 2  # repair made things worse -> stop, keep best
    assert j["grounding"]["llm_calls"] == 2
    assert [m["name"] for m in j["structured"]["rx"]] == ["Atorvastatin"]
    assert len(j["grounding"]["open_issues"]) == 1


def test_grounding_status_schema():
    valid = {"verified", "unverified-name", "unknown-medicine",
             "unverified-strength"}
    for case in GOLDEN:
        out = run_pipeline(case["transcript"])["structured"]
        for m in out["rx"]:
            assert m.get("status") in valid, (case["id"], m)
            assert "lexicon_match" in m, (case["id"], m)
    assert open_issues(run_pipeline(GOLDEN[0]["transcript"])["structured"]) == []


def test_seeded_shortcut_rows_get_flagged():
    # The flank-pain seeded fallback emits the classic 4-drug prescription;
    # drugs not literally dictated (Deflazacort here) must be flagged, not
    # silently presented as verified.
    out = run_pipeline(GOLDEN[1]["transcript"])["structured"]
    by_name = {m["name"]: m for m in out["rx"]}
    assert by_name["Tamsulosin"]["status"] == "verified"
    assert by_name["Deflazacort"]["status"] == "unverified-name"


# ---- Dictated OP number (registration no.), additive to the schema ----

def test_validator_carries_op_no():
    out, _ = validate_structured({"opNo": "OP-1234"}, "")
    assert out["opNo"] == "OP-1234"


def test_fallback_extracts_op_no():
    out = fallback_format("patient name Anita 45 year old female OP 1234 right flank pain")
    assert out["opNo"].upper().endswith("1234")


# ---- Truncation caps must never silently drop dictated medicines ----------


def test_validator_keeps_rx_beyond_old_eight_row_cap():
    """12 dictated rows all survive (the old rx[:8] cap silently dropped rows 9-12)."""
    draft = {"rx": [
        {"name": f"Med{i}", "strength": "10 mg", "dose": "1-0-0",
         "timing": "After food", "duration": ""}
        for i in range(12)
    ]}
    validated, warnings = validate_structured(draft, "")
    assert len(validated["rx"]) == 12
    assert [r["name"] for r in validated["rx"]] == [f"Med{i}" for i in range(12)]
    assert not any("truncat" in w.lower() for w in warnings)


def test_validator_truncates_beyond_twenty_rows_with_warning():
    """25 rows -> 20 kept, and truncation is announced, never silent."""
    draft = {"rx": [
        {"name": f"Med{i}", "strength": "10 mg", "dose": "1-0-0",
         "timing": "After food", "duration": ""}
        for i in range(25)
    ]}
    validated, warnings = validate_structured(draft, "")
    assert len(validated["rx"]) == 20
    assert any("truncat" in w.lower() for w in warnings)
