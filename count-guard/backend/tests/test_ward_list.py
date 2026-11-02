"""The server-owned ward list and demo clock (spec §8): beds, the shared clock and the at_ms clamp."""

from __future__ import annotations

from app.journey import clock, seed, ward_api
from tests.test_care_demo import _client

H = 3_600_000
M = 60_000


def _store(client):
    return client.app.state.morning


def _seed(client):
    res = client.post("/journey/demo/seed")
    assert res.status_code == 200, res.text
    return res.json()


def _new(store, label="T. Test, 40 F (synthetic)"):
    return store.create_episode(label)["id"]


def test_seed_registers_three_patients_with_beds(tmp_path):
    client = _client(tmp_path)
    _seed(client)
    ward = client.get("/journey/ward").json()
    assert [p["bed"] for p in ward["patients"]] == ["4", "7", "9"]
    assert [p["name"] for p in ward["patients"]] == [name for _, name in seed.PATIENTS]
    assert all(p["name"] != seed.BOARD_LABEL for p in ward["patients"])
    assert {"id", "name", "bed", "state", "source"} <= set(ward["patients"][0])
    assert ward["patients"][1]["state"] == "ward"  # Iyer was admitted the day before
    assert ward["patients"][0]["source"] == "seed"


def test_seed_again_gives_a_fresh_ward_and_clears_the_clock(tmp_path):
    client = _client(tmp_path)
    first = _seed(client)
    assert client.post("/journey/clock", json={"ms": H}).json() == {"now_ms": H}
    second = _seed(client)
    ward = client.get("/journey/ward").json()
    assert [p["bed"] for p in ward["patients"]] == ["4", "7", "9"]
    assert {p["id"] for p in ward["patients"]} == {p["id"] for p in second["patients"]}
    assert not {p["id"] for p in first["patients"]} & {p["id"] for p in ward["patients"]}
    assert ward["now_ms"] == 0
    assert _store(client).get_clock() is None


def test_ward_names_the_staff_board(tmp_path):
    client = _client(tmp_path)
    made = _seed(client)
    assert client.get("/journey/ward").json()["board"] == made["board"]


def test_next_bed_is_lowest_free(tmp_path):
    client = _client(tmp_path)
    _seed(client)
    store = _store(client)
    assert ward_api.next_bed(store) == "1"
    for bed in ("1", "2", "3"):
        ward_api.register(store, _new(store), bed=bed, source="test", document_id=None, ts_ms=0)
    assert ward_api.next_bed(store) == "5"


def test_register_writes_the_event(tmp_path):
    client = _client(tmp_path)
    store = _store(client)
    eid = _new(store)
    ward_api.register(store, eid, bed="12", source="dd", document_id=31, ts_ms=5 * M)
    event = store.events(eid)[-1]
    assert event["event_type"] == "patient.registered"
    assert event["payload"] == {"bed": "12", "source": "dd", "document_id": 31}
    assert event["ts_ms"] == 5 * M
    ward = client.get("/journey/ward").json()
    assert [(p["id"], p["bed"], p["source"]) for p in ward["patients"]] == [(eid, "12", "dd")]


def test_stamp_clamps_future_to_server_now(tmp_path):
    store = _store(_client(tmp_path))
    eid = _new(store)
    clock.set_ms(store, 600_000)
    assert clock.stamp(store, eid, 900_000) == 600_000


def test_stamp_clamps_behind_latest_event(tmp_path):
    store = _store(_client(tmp_path))
    eid = _new(store)
    store.append(eid, "note.added", {}, ts_ms=500_000)
    assert clock.stamp(store, eid, 100_000) == 500_000


def test_stamp_none_on_empty_episode_uses_server_now(tmp_path):
    store = _store(_client(tmp_path))
    eid = _new(store)
    clock.set_ms(store, 600_000)
    assert clock.stamp(store, eid, None) == 600_000


def test_stamp_none_after_events_steps_past_the_later_of_event_and_clock(tmp_path):
    store = _store(_client(tmp_path))
    eid = _new(store)
    store.append(eid, "note.added", {}, ts_ms=10_000)
    clock.set_ms(store, 600_000)
    assert clock.stamp(store, eid, None) == 601_000


def test_seed_then_future_at_ms_unchanged(tmp_path):
    client = _client(tmp_path)
    kumar = _seed(client)["patients"][0]["id"]
    res = client.post(f"/journey/episodes/{kumar}/rx/demo", json={"at_ms": 2 * H + 5 * M})
    assert res.status_code == 200, res.text
    assert _store(client).events(kumar)[-1]["ts_ms"] >= 2 * H + 5 * M
    assert any(e["ts_ms"] == 2 * H + 5 * M for e in _store(client).events(kumar))


def test_existing_at_ms_unchanged_when_clock_unset(tmp_path):
    store = _store(_client(tmp_path))
    eid = _new(store)
    assert store.get_clock() is None
    assert clock.stamp(store, eid, 120_000) == 120_000
    store.append(eid, "note.added", {}, ts_ms=120_000)
    assert clock.stamp(store, eid, None) == 121_000
    assert clock.now_ms(store) == 0


def test_clock_route_moves_time_for_all_patients(tmp_path):
    client = _client(tmp_path)
    _seed(client)
    assert client.post("/journey/clock", json={"ms": 3_600_000}).json() == {"now_ms": 3_600_000}
    assert client.get("/journey/ward").json()["now_ms"] == 3_600_000


def test_clock_route_refuses_bad_values(tmp_path):
    client = _client(tmp_path)
    assert client.post("/journey/clock", json={"ms": -1}).status_code == 422
    assert client.post("/journey/clock", json={"ms": "soon"}).status_code == 422
    assert client.post("/journey/clock", json={"ms": 5, "extra": 1}).status_code == 422
