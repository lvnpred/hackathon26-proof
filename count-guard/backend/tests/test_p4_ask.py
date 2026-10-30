"""P4 Task 2: the Ask routes. Bot, question to the doctor, voice answer heard not saved, healing photo decision."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters import spark as spark_mod
from app.journey import live
from app.journey.ask import DECISIONS, open_for_doctor
from app.journey.record import BOT, NOT_FOUND, record_lines
from app.main import create_app
from tests.test_care_demo import _client, _seed
from tests.test_flow_states import ADVICE, DISCHARGE_CHECKS, _move
from tests.test_flow_tasks import DOC, _url
from tests.test_p2_live import _keyed

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
GOOD = "Amlodipine 5 mg, 1 in the morning, after food, for 30 days."
NOT_PHOTO = "A healing photo is sent once the visit is closed or you are home."


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _patients(client):
    return {p["bed"]: p["id"] for p in _seed(client)}


def _events(client, eid):
    return client.app.state.morning.events(eid)


def _ask(client, eid, text, to="bot", at_ms=1000):
    return client.post(_url(eid, f"ask/{to}"), json={"text": text, "at_ms": at_ms})


def _home(client, eid):
    assert client.post(_url(eid, "rx/demo"), json={"at_ms": 0}).status_code == 200
    assert _move(client, eid, "admitting", reason="Hernia repair").status_code == 200
    checks = {"band": True, "allergies": True, "baseline_obs": True, "consent": True}
    assert _move(client, eid, "ward", checklist=checks).status_code == 200
    body = {"summary": "Right hernia repaired. Wound is clean.", "by": DOC, "at_ms": 0}
    assert client.post(_url(eid, "discharge/sign"), json=body).status_code == 200
    assert _move(client, eid, "home", checklist=DISCHARGE_CHECKS).status_code == 200


def _close_visit(client, eid):
    assert client.post(_url(eid, "rx/demo"), json={"at_ms": 0}).status_code == 200
    assert _move(client, eid, "clinic_done").status_code == 200


def _photo(client, eid, note="Day 3", content=PNG, kind="image/png"):
    return client.post(
        _url(eid, "ask/review"), files={"file": ("healing.png", content, kind)}, data={"note": note, "at_ms": "2000"}
    )


def _strings(view):
    ask = view["ask"]
    out = [view["now_next"]["now"], view["now_next"]["next"]]
    out += [q["answer"]["text"] for q in ask["questions"] if q["answer"] and q["answer"]["by"] == BOT]
    out += [r["answer"]["label"] for r in ask["reviews"] if r["answer"]]
    return out


def test_bot_answers_from_the_record_offline(tmp_path):
    client = _client(tmp_path)
    das = _patients(client)["9"]
    _close_visit(client, das)
    view = _ask(client, das, "When do I take amlodipine?").json()
    got = view["ask"]["questions"][-1]["answer"]
    assert got["found"] and got["source"] == "rules" and got["by"] == BOT
    assert len(got["sources"]) == 1 and "Amlodipine 5 mg" in got["sources"][0]["text"]
    rx = next(e for e in _events(client, das) if e["event_type"] == "rx.ordered")
    assert got["sources"][0]["event_id"] == rx["id"]
    kinds = [e["event_type"] for e in _events(client, das)][-2:]
    assert kinds == ["question.asked", "question.answered"]
    asked = view["ask"]["questions"][-1]
    assert asked["to"] == "bot" and asked["by"] == "A. Das, 47 M (synthetic)"


def test_bot_not_found_offers_the_doctor(tmp_path):
    client = _client(tmp_path)
    das = _patients(client)["9"]
    _close_visit(client, das)
    got = _ask(client, das, "Can I drive?").json()["ask"]["questions"][-1]["answer"]
    assert got["found"] is False and got["text"] == NOT_FOUND and got["sources"] == []


def test_bot_reads_only_this_patient(tmp_path):
    client = _client(tmp_path)
    ids = _patients(client)
    kumar, das = ids["4"], ids["9"]
    _home(client, kumar)
    _close_visit(client, das)
    own = _ask(client, kumar, "How is the wound?").json()["ask"]["questions"][-1]["answer"]
    assert own["found"] and any("Wound" in s["text"] for s in own["sources"])
    got = _ask(client, das, "How is the wound?").json()["ask"]["questions"][-1]["answer"]
    assert got["found"] is False
    both = _ask(client, das, "When do I take amlodipine?").json()["ask"]["questions"][-1]["answer"]
    mine = {e["id"] for e in _events(client, das)}
    kumars = {e["id"] for e in _events(client, kumar)}
    assert both["sources"] and all(s["event_id"] in mine and s["event_id"] not in kumars for s in both["sources"])
    for q in client.get(_url(das, "")[:-1]).json()["ask"]["questions"]:
        assert all(s["event_id"] in mine for s in (q["answer"] or {}).get("sources", []))


def test_bot_live_reply_used_and_rejected(tmp_path, monkeypatch):
    client = TestClient(create_app(_keyed(tmp_path)))
    das = _patients(client)["9"]
    _close_visit(client, das)
    lines = record_lines(_events(client, das))
    lid = next(line["id"] for line in lines if "Amlodipine" in line["text"])

    def ask(reply):
        if isinstance(reply, Exception):
            def write(self, prompt):
                raise reply
        else:
            def write(self, prompt):
                assert "Amlodipine 5 mg" in prompt and "Question: What is my prescription?" in prompt
                return reply
        monkeypatch.setattr(spark_mod.SparkAdapter, "write", write)
        return _ask(client, das, "What is my prescription?").json()["ask"]["questions"][-1]["answer"]

    used = ask(json.dumps({"answer": GOOD, "sources": [lid]}))
    assert used["source"] == "muse-spark-1.3" and used["text"] == GOOD and used["sources"][0]["id"] == lid
    for bad in (json.dumps({"answer": GOOD, "sources": ["L99"]}), httpx.ConnectError("down")):
        got = ask(bad)
        assert got["source"] == "rules (model reply not usable)" and got["found"]


def test_question_to_doctor_answered_by_text(tmp_path):
    client = _client(tmp_path)
    kumar = _patients(client)["4"]
    _home(client, kumar)
    view = _ask(client, kumar, "Is some redness at the wound normal?", "doctor").json()
    question = view["ask"]["questions"][-1]
    assert question["to"] == "doctor" and question["answer"] is None
    assert open_for_doctor(_events(client, kumar)) == {"questions": 1, "reviews": 0}
    assert view["now_next"]["next"] == "The doctor answers the question."
    assert view["now_next"]["now"] == "R. Kumar sent a question to the doctor at Day 0 09:00."
    body = {"text": "A little redness is expected. Send a photo.", "by": DOC, "at_ms": 5000}
    done = client.post(_url(kumar, f"questions/{question['id']}/answer"), json=body).json()
    answer = done["ask"]["questions"][-1]["answer"]
    assert answer["via"] == "text" and answer["by"] == DOC and answer["source"] == "doctor" and answer["found"]
    assert done["now_next"]["now"] == f"{DOC} answered the question at Day 0 09:00."
    assert done["now_next"]["next"] != "The doctor answers the question."
    assert any(
        line["kind"] == "answer" and line["text"] == f"{DOC} answered your question: {body['text']}"
        for line in record_lines(_events(client, kumar))
    )
    plain = [r["what"] for r in client.get(_url(kumar, "audit")).json()["rows"]]
    assert "R. Kumar sent a question to the doctor." in plain and f"{DOC} answered the question (typed)." in plain
    assert not any("redness" in line for line in plain)


def test_hear_writes_nothing(tmp_path):
    client = _client(tmp_path)
    kumar = _patients(client)["4"]
    before = len(_events(client, kumar))
    r = client.post(_url(kumar, "ask/hear"), data={"by": DOC}, files={"file": ("rao-answer.wav", b"RIFF", "audio/wav")})
    assert r.status_code == 200
    assert r.json() == {"text": live.prepared("rao-answer.wav")["transcript"], "heard_by": "prepared"}
    assert len(_events(client, kumar)) == before
    r = client.post(_url(kumar, "ask/hear"), data={"by": DOC}, files={"file": ("IMG_0001.webm", b"RIFF", "audio/webm")})
    assert r.status_code == 409 and len(_events(client, kumar)) == before


def test_answer_refusals(tmp_path):
    client = _client(tmp_path)
    ids = _patients(client)
    kumar, das = ids["4"], ids["9"]
    _home(client, kumar)
    q = _ask(client, kumar, "Is this normal?", "doctor").json()["ask"]["questions"][-1]["id"]
    bot = _ask(client, kumar, "When do I take amlodipine?").json()["ask"]["questions"][-1]["id"]
    body = {"text": "Yes.", "by": DOC}
    url = lambda eid, qid: _url(eid, f"questions/{qid}/answer")
    assert client.post(url(kumar, q), json=body).status_code == 200
    count = len(_events(client, kumar))
    other = len(_events(client, das))
    again = client.post(url(kumar, q), json=body)
    assert again.status_code == 409 and again.json()["detail"] == "This question is answered already."
    refused = client.post(url(kumar, bot), json=body)
    assert refused.status_code == 409 and refused.json()["detail"] == "The record bot answers this question."
    missing = client.post(url(kumar, "nope"), json=body)
    assert missing.status_code == 404 and missing.json()["detail"] == "Question not found"
    assert client.post(url(das, q), json=body).status_code == 404
    assert client.post(url(kumar, q), json={**body, "text": ""}).status_code == 422
    assert len(_events(client, kumar)) == count and len(_events(client, das)) == other


def test_healing_review_no_visit_needed(tmp_path):
    client = _client(tmp_path)
    kumar = _patients(client)["4"]
    _home(client, kumar)
    view = _photo(client, kumar).json()
    review = view["ask"]["reviews"][-1]
    assert review["note"] == "Day 3" and review["answer"] is None and review["by"] == "R. Kumar, 58 M (synthetic)"
    assert review["photo"]["url"].startswith(f"/journey/episodes/{kumar}/photos/")
    assert client.get(review["photo"]["url"]).content == PNG
    assert [p["purpose"] for p in view["photos"]] == ["healing"]
    assert view["now_next"]["next"] == "The doctor reviews the healing photo."
    assert view["now_next"]["now"] == "R. Kumar sent a healing photo at Day 0 09:00."
    assert view["now_next"]["you_now"] == "You sent a healing photo at Day 0 09:00."
    decided = client.post(
        _url(kumar, f"reviews/{review['id']}/answer"), json={"decision": "no_visit", "by": DOC, "at_ms": 9000}
    ).json()
    answer = decided["ask"]["reviews"][-1]["answer"]
    assert answer["label"] == "No visit needed" and answer["decision"] == "no_visit"
    assert decided["now_next"]["now"].startswith(f"{DOC} reviewed the healing photo at ")
    assert decided["now_next"]["now"].endswith(": No visit needed.")
    assert decided["now_next"]["next"] != "The doctor reviews the healing photo."
    assert decided["now_next"]["you_now"].startswith("Dr. A. Rao reviewed your healing photo at ")
    assert decided["now_next"]["you_now"].endswith(": No visit needed.")
    lines = record_lines(_events(client, kumar))
    assert any(l["kind"] == "review" and l["text"].startswith(f"{DOC} reviewed your healing photo at ") and l["text"].endswith(": No visit needed.") for l in lines)
    count = len(_events(client, kumar))
    second = client.post(_url(kumar, f"reviews/{review['id']}/answer"), json={"decision": "call", "by": DOC})
    assert second.status_code == 409 and second.json()["detail"] == "This photo is reviewed already."
    assert len(_events(client, kumar)) == count
    plain = [r["what"] for r in client.get(_url(kumar, "audit")).json()["rows"]]
    assert "R. Kumar sent a healing photo for review." in plain
    assert f"{DOC} reviewed the healing photo: No visit needed." in plain


def test_review_answer_is_404_for_another_episode(tmp_path):
    client = _client(tmp_path)
    ids = _patients(client)
    kumar, das = ids["4"], ids["9"]
    _home(client, kumar)
    review = _photo(client, kumar).json()["ask"]["reviews"][-1]["id"]
    count = len(_events(client, das))
    r = client.post(_url(das, f"reviews/{review}/answer"), json={"decision": "call", "by": DOC})
    assert r.status_code == 404 and r.json()["detail"] == "Review not found"
    assert client.post(_url(kumar, "reviews/nope/answer"), json={"decision": "call", "by": DOC}).status_code == 404
    assert len(_events(client, das)) == count


def test_healing_review_refusals(tmp_path):
    client = _client(tmp_path)
    kumar = _patients(client)["4"]
    before = len(_events(client, kumar))
    r = _photo(client, kumar)
    assert r.status_code == 409 and r.json()["detail"] == NOT_PHOTO
    _home(client, kumar)
    count = len(_events(client, kumar))
    assert _photo(client, kumar, content=b"GIF89a" + b"0" * 20, kind="image/gif").status_code == 400
    assert _photo(client, kumar, content=b"not a png at all").status_code == 400
    assert len(_events(client, kumar)) == count and before < count
    review = _photo(client, kumar).json()["ask"]["reviews"][-1]["id"]
    bad = client.post(_url(kumar, f"reviews/{review}/answer"), json={"decision": "maybe", "by": DOC})
    assert bad.status_code == 422


def test_report_field_less_lines_are_skipped():
    events = [
        {"id": "e1", "episode_id": "x", "event_type": "order.signed", "ts_ms": 0, "payload": {"items": [{"text": "BP"}]}},
        {"id": "e2", "episode_id": "x", "event_type": "discharge.card", "ts_ms": 0, "payload": {"warning_signs": ["Fever"]}},
        {"id": "e3", "episode_id": "x", "event_type": "review.answered", "ts_ms": 0, "payload": {"review_id": "r"}},
        {"id": "e4", "episode_id": "x", "event_type": "rx.ordered", "ts_ms": 0, "payload": {"rows": [], "advice": ["Rest"], "review": "Day 7"}},
    ]
    texts = [line["text"] for line in record_lines(events)]
    assert texts == ["Warning sign on your discharge card: Fever", "Follow-up on the prescription: Day 7"]
    assert not any("None" in t or not t.strip() for t in texts)


def test_ask_strings_have_no_advice(tmp_path):
    client = _client(tmp_path)
    kumar = _patients(client)["4"]
    _home(client, kumar)
    _ask(client, kumar, "Should I stop amlodipine?")
    _ask(client, kumar, "Can I drive?")
    review = _photo(client, kumar).json()["ask"]["reviews"][-1]["id"]
    seen = [DECISIONS[k] for k in DECISIONS] + [NOT_PHOTO, "This question is answered already.", "The record bot answers this question.", "This photo is reviewed already."]
    view = client.post(_url(kumar, f"reviews/{review}/answer"), json={"decision": "no_visit", "by": DOC}).json()
    seen += _strings(view)
    seen += [r["what"] for r in client.get(_url(kumar, "audit")).json()["rows"] if r["type"].startswith(("question.", "review."))]
    for text in seen:
        assert not ADVICE.search(text), text
