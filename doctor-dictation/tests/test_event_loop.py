"""Validation runs in a worker thread, so a slow call cannot stall other requests.

Run:  .venv/bin/python -m pytest tests/test_event_loop.py -q
"""
import asyncio
import time
import uuid

import httpx
import pytest

import doctor_dictation.api.format as format_api
import doctor_dictation.main as M
from doctor_dictation.config import override_settings


@pytest.mark.parametrize("slow_name", ["validate_structured", "normalize_transcript"])
def test_cpu_work_does_not_block_the_event_loop(monkeypatch, slow_name):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")  # rules path: no LLM, no network
    real = getattr(format_api, slow_name)

    def slow(*args, **kwargs):
        time.sleep(0.4)  # stands in for heavy CPU; a blocked loop stalls for this long
        return real(*args, **kwargs)

    monkeypatch.setattr(format_api, slow_name, slow)

    async def run():
        gaps, flag = [], {"stop": False}

        async def ticker():
            last = time.perf_counter()
            while not flag["stop"]:
                await asyncio.sleep(0.01)
                now = time.perf_counter()
                gaps.append(now - last)
                last = now

        task = asyncio.create_task(ticker())
        await asyncio.sleep(0.05)  # let the ticker start ticking first
        transport = httpx.ASGITransport(app=M.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r1 = await c.post("/api/v1/correct",
                              json={"transcript": "duration is 7 days", "current_form": {"rx": []}})
            r2 = await c.post("/api/format",
                              json={"transcript": "loop check " + uuid.uuid4().hex[:8]})
        await asyncio.sleep(0.05)  # let the ticker record the gap after the requests
        flag["stop"] = True
        await task
        return r1.status_code, r2.status_code, max(gaps)

    s1, s2, worst = asyncio.run(run())
    assert (s1, s2) == (200, 200)
    assert worst < 0.2, f"event loop stalled for {worst:.2f}s in {slow_name}"


def test_repair_message_does_not_block_the_event_loop(monkeypatch):
    # Review (ACC): build_repair_message does difflib work per unknown row; it must run off the loop.
    import json
    monkeypatch.setenv("ALLOW_STUB_PROVIDERS", "1")
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps({"rx": [{"form": "Tab.", "name": "Medalpha", "strength": "",
                                                           "dose": "1-0-0", "timing": "", "duration": "", "instructions": ""}]}))
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True)
    real = format_api.build_repair_message

    def slow(issues, transcript):
        time.sleep(0.4)
        return real(issues, transcript)

    monkeypatch.setattr(format_api, "build_repair_message", slow)

    async def run():
        gaps, flag = [], {"stop": False}

        async def ticker():
            last = time.perf_counter()
            while not flag["stop"]:
                await asyncio.sleep(0.01)
                now = time.perf_counter()
                gaps.append(now - last)
                last = now

        task = asyncio.create_task(ticker())
        await asyncio.sleep(0.05)
        transport = httpx.ASGITransport(app=M.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.post("/api/format", json={"transcript": "tablet medalpha " + uuid.uuid4().hex[:8]})
        await asyncio.sleep(0.05)
        flag["stop"] = True
        await task
        return r.status_code, max(gaps)

    status, worst = asyncio.run(run())
    assert status == 200
    assert worst < 0.2, f"event loop stalled for {worst:.2f}s in build_repair_message"
