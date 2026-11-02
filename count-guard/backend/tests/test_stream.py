"""The live stream moved into the care app (spec §8, §9 "morning SSE stream"): ward list and one chart."""

from __future__ import annotations

import threading
import time

from test_care_demo import _client


def _patient(client, name="K. Nair (synthetic)") -> str:
    res = client.post("/journey/patients", json={"name": name, "age_sex": "35 M", "reason": "Lump"})
    assert res.status_code == 201, res.text
    return res.json()["episode_id"]


def _ids(text: str) -> list[str]:
    return [line[4:] for line in text.splitlines() if line.startswith("id: ")]


def _first_arrival(client, url: str, write) -> tuple[float, float]:
    """Open the stream, write one event 0.2 s later, return (written_at, received_at) for that event's id."""
    written: dict = {}

    def later():
        time.sleep(0.2)
        written["at"] = time.monotonic()
        written["event"] = write()

    received = None
    with client.stream("GET", url) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        threading.Thread(target=later, daemon=True).start()
        for line in response.iter_lines():
            if line.startswith("id: ") and line[4:] == written.get("event", {}).get("id"):
                received = time.monotonic()
                break
    assert received is not None, "the stream never sent the new event"
    return written["at"], received


def test_stream_emits_new_event_within_1s(tmp_path):
    client = _client(tmp_path)
    eid = _patient(client)
    store = client.app.state.morning
    write = lambda: store.append(eid, "obs.recorded", {"sbp": 120, "dbp": 80, "hr": 70, "by": "Nurse A"}, ts_ms=5)
    at, got = _first_arrival(client, "/journey/ward/stream?timeout_s=2", write)
    assert got - at < 1.0
    at, got = _first_arrival(client, f"/journey/episodes/{eid}/stream?timeout_s=2", write)
    assert got - at < 1.0


def test_ward_stream_sends_a_registration(tmp_path):
    client = _client(tmp_path)
    store = client.app.state.morning
    from app.journey import intake

    def register():
        intake.new_patient(store, name="L. Rao (synthetic)", age_sex="", reason="", now_ms=0)
        return next(e for e in store.timeline_after(None) if e["event_type"] == "patient.registered")

    at, got = _first_arrival(client, "/journey/ward/stream?timeout_s=2", register)
    assert got - at < 1.0


def test_stream_resumes_from_last_event_id(tmp_path):
    client = _client(tmp_path)
    eid = _patient(client)
    store = client.app.state.morning
    first = store.append(eid, "obs.recorded", {"sbp": 120, "dbp": 80, "hr": 70, "by": "Nurse A"}, ts_ms=5)
    second = store.append(eid, "obs.recorded", {"sbp": 121, "dbp": 80, "hr": 70, "by": "Nurse A"}, ts_ms=6)
    for url in (f"/journey/episodes/{eid}/stream?timeout_s=0.3", "/journey/ward/stream?timeout_s=0.3"):
        resumed = client.get(url, headers={"Last-Event-ID": first["id"]})
        assert resumed.status_code == 200
        ids = _ids(resumed.text)
        assert second["id"] in ids and first["id"] not in ids, url


def test_episode_stream_without_an_id_sends_the_whole_record(tmp_path):
    client = _client(tmp_path)
    eid = _patient(client)
    ids = _ids(client.get(f"/journey/episodes/{eid}/stream?timeout_s=0.3").text)
    assert ids == [e["id"] for e in client.app.state.morning.events(eid)]


def test_ward_stream_without_an_id_starts_at_the_tail(tmp_path):
    """A fresh ward stream sends no history, only where it stands, so a reconnect resumes from there."""
    client = _client(tmp_path)
    eid = _patient(client)
    tail = client.app.state.morning.events(eid)[-1]["id"]
    text = client.get("/journey/ward/stream?timeout_s=0.3").text
    assert "event: ready" in text and _ids(text) == [tail]
    assert "retry: " in text


def test_ward_stream_leaves_out_episodes_without_a_bed(tmp_path):
    client = _client(tmp_path)
    eid = _patient(client)
    store = client.app.state.morning
    start = store.events(eid)[-1]["id"]
    board = store.create_episode("Staff board")
    hidden = store.append(board["id"], "doctor.status", {"status": "in theatre"}, ts_ms=1)
    shown = store.append(eid, "obs.recorded", {"sbp": 120, "dbp": 80, "hr": 70, "by": "Nurse A"}, ts_ms=5)
    ids = _ids(client.get("/journey/ward/stream?timeout_s=0.3", headers={"Last-Event-ID": start}).text)
    assert ids == [shown["id"]] and hidden["id"] not in ids


def test_ward_stream_sends_a_clock_change(tmp_path):
    client = _client(tmp_path)
    _patient(client)
    store = client.app.state.morning

    def later():
        time.sleep(0.2)
        store.set_clock(7_200_000)

    with client.stream("GET", "/journey/ward/stream?timeout_s=2") as response:
        threading.Thread(target=later, daemon=True).start()
        lines = []
        for line in response.iter_lines():
            lines.append(line)
            if line.startswith("data: ") and "7200000" in line:
                break
    assert "event: clock" in lines


def test_stream_of_an_unknown_episode_is_404(tmp_path):
    assert _client(tmp_path).get("/journey/episodes/nope/stream?timeout_s=0.3").status_code == 404


def test_stream_timeout_is_bounded(tmp_path):
    client = _client(tmp_path)
    assert client.get("/journey/ward/stream?timeout_s=0").status_code == 422
    assert client.get("/journey/ward/stream?timeout_s=31").status_code == 422
