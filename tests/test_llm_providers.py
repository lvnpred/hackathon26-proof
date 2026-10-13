"""LLM providers, offline (httpx.AsyncClient is replaced). Run: pytest tests/test_llm_providers.py -q"""
import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from doctor_dictation.config import build_settings
from doctor_dictation.providers.llm.base import LlmError
from doctor_dictation.providers.llm.factory import make_llm
from doctor_dictation.providers.llm.stub import StubLlm

MSG = [{"role": "user", "content": "x"}]
run = asyncio.run


def _settings(**kw):
    base = dict(llm_provider="openai", openai_api_key="k", deepseek_api_key="",
                llm_model="gpt-6-luna", llm_vision_model="",
                openai_base_url="https://api.openai.com/v1", allow_stub_providers=False)
    return replace(build_settings(), **{**base, **kw})


def _resp(status, body):
    return SimpleNamespace(status_code=status, text=str(body), json=lambda: body)


def _chat(content=None, tool_calls=None, finish="stop"):
    msg = {"content": content, **({"tool_calls": tool_calls} if tool_calls else {})}
    return _resp(200, {"choices": [{"finish_reason": finish, "message": msg}]})


def _serve(monkeypatch, replies):
    """Replace httpx.AsyncClient; serve `replies` in order (the last repeats)."""
    seen = []

    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def post(self, url, headers=None, **kw):
            seen.append({"url": url, "headers": headers, "json": dict(kw["json"])})
            return replies[min(len(seen) - 1, len(replies) - 1)]

    monkeypatch.setattr("httpx.AsyncClient", Client)
    return seen


def test_complete_json_payload_retry_order_and_error_strings(monkeypatch):
    llm = make_llm(_settings(llm_seed=11))
    seen = _serve(monkeypatch, [
        _resp(400, "Unsupported value: 'temperature' does not support 0.0"),
        _resp(400, "Unsupported parameter: 'top_p'"),
        _resp(400, "Unsupported parameter: 'seed'"), _chat('{"ok": true}')])
    assert run(llm.complete_json(MSG)) == ({"ok": True}, "")
    assert (seen[0]["url"], seen[0]["headers"]["Authorization"]) == (
        "https://api.openai.com/v1/chat/completions", "Bearer k")
    assert seen[0]["json"] == {
        "model": "gpt-6-luna", "response_format": {"type": "json_object"},
        "temperature": 0.0, "top_p": 1.0, "seed": 11, "messages": MSG}
    assert [tuple(k in c["json"] for k in ("temperature", "top_p", "seed")) for c in seen] == [
        (True, True, True), (False, True, True), (False, False, True), (False, False, False)]
    for reply, want in [(_resp(500, "down"), (None, "openai 500: down")),
                        (_resp(400, "bad model"), (None, "openai 400: bad model"))]:
        _serve(monkeypatch, [reply])
        assert run(llm.complete_json(MSG)) == want
    _serve(monkeypatch, [_chat("not json at all")])
    data, err = run(llm.complete_json(MSG))
    assert data is None and err.startswith("JSON parse:")


def test_complete_parses_tool_calls_text_and_failures(monkeypatch):
    llm = make_llm(_settings())
    calls = [{"id": "c1", "function": {"name": "layout", "arguments": '{"top": 0.1}'}}]
    tools = [{"type": "function", "function": {"name": "layout", "parameters": {}}}]
    seen = _serve(monkeypatch, [_chat(None, calls, "tool_calls")])
    out = run(llm.complete(MSG, tools))
    assert (out.text, out.json, out.finish) == ("", None, "tool_calls")
    assert [(c.id, c.name, c.arguments) for c in out.tool_calls] == [("c1", "layout", {"top": 0.1})]
    assert seen[0]["json"]["tools"] == tools and "response_format" not in seen[0]["json"]
    _serve(monkeypatch, [_chat('{"a": 1}')])
    out = run(llm.complete(MSG))
    assert (out.text, out.json, out.tool_calls) == ('{"a": 1}', {"a": 1}, ())
    bad = [{"id": "c", "function": {"name": "f", "arguments": "{oops"}}]
    for reply, match in [(_resp(500, "down"), "openai 500"), (_chat(None, bad), "response parse")]:
        _serve(monkeypatch, [reply])
        with pytest.raises(LlmError, match=match):
            run(llm.complete(MSG))


def test_image_parts_reach_the_http_payload_unchanged(monkeypatch):
    seen = _serve(monkeypatch, [_chat('{"ok": 1}')])
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": "read this letterhead"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAAA"}}]}]
    expected = json.loads(json.dumps(msgs))
    llm = make_llm(_settings(), vision=True)
    run(llm.complete_json(msgs))
    run(llm.complete(msgs))
    assert [c["json"]["messages"] for c in seen] == [expected, expected]


def test_factory_vision_model_fallback_and_provider_fields(monkeypatch):
    assert make_llm(_settings(llm_vision_model="gpt-vis")).model == "gpt-6-luna"
    assert make_llm(_settings(llm_vision_model="gpt-vis"), vision=True).model == "gpt-vis"
    for blank in ("", "   "):
        assert make_llm(_settings(llm_vision_model=blank), vision=True).model == "gpt-6-luna"
    ds = _settings(llm_provider="deepseek", deepseek_api_key="d")
    assert make_llm(ds, vision=True).model == ds.deepseek_model
    assert make_llm(_settings(openai_api_key="")) is None
    assert make_llm(replace(ds, deepseek_api_key="")) is None
    assert make_llm(_settings(llm_provider="weird")).name == "openai"  # typo acts like openai
    monkeypatch.setenv("LLM_VISION_MODEL", "  gpt-vis  ")
    assert build_settings().llm_vision_model == "gpt-vis"
    monkeypatch.delenv("LLM_VISION_MODEL")
    assert build_settings().llm_vision_model == ""


def test_stub_gating_and_behaviour(monkeypatch):
    want = {"rx": [{"name": "Paracetamol"}]}
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(want))
    with pytest.raises(ValueError, match="ALLOW_STUB_PROVIDERS"):
        make_llm(_settings(llm_provider="stub", openai_api_key=""))
    llm = make_llm(_settings(llm_provider="stub", allow_stub_providers=True))
    assert isinstance(llm, StubLlm) and run(llm.complete_json([])) == (want, "")
    assert run(llm.complete([])).json == want


def _client(monkeypatch, **fields):
    from fastapi.testclient import TestClient

    import doctor_dictation.main as M
    from doctor_dictation.config import override_settings
    override_settings(monkeypatch, **fields)
    return TestClient(M.app)


def test_format_route_uses_the_stub_provider(monkeypatch):
    client = _client(monkeypatch, llm_provider="stub", allow_stub_providers=True)
    monkeypatch.setenv("STUB_LLM_JSON", '{"rx": []}')
    r = client.post("/api/format", json={"transcript": "b1d stub route 7731 fever two days"})
    assert r.status_code == 200, r.text
    assert r.json()["engine"].startswith("stub:stub+lexicon")
    assert r.json()["grounding"]["llm_calls"] == 1


def test_health_reports_the_stub_provider(monkeypatch):
    client = _client(monkeypatch, llm_provider="stub", allow_stub_providers=True)
    h = client.get("/api/health").json()
    assert (h["llm_provider"], h["llm_model"], h["llm_configured"]) == ("stub", "stub", True)


def test_llm_error_body_never_leaks_the_key(monkeypatch):
    # Review #2: same rule for the LLM provider (its error string lands in the cached engine field).
    llm = make_llm(_settings(openai_api_key="sk-secret-key-123"))
    _serve(monkeypatch, [_resp(401, "bad auth: Bearer sk-secret-key-123")])
    data, err = run(llm.complete_json(MSG))
    assert data is None and "sk-secret-key-123" not in err and "[redacted]" in err
    with pytest.raises(LlmError) as e:
        run(llm.complete(MSG))
    assert "sk-secret-key-123" not in str(e.value)
