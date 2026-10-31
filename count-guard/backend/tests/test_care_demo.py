"""Demo clock: journey POSTs take an explicit at_ms (episode clock ms, 0 = Day 0 09:00)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

H = 3_600_000
ORDERS = {
    "doses": [{"name": "Paracetamol", "amount": "1 g IV", "every_h": 6}],
    "obs_every_h": 1,
    "limits": {"sbp_min": 90, "hr_max": 110},
    "by": "Dr. Test",
}


def _client(tmp_path, *, dd_base="http://127.0.0.1:9"):
    settings = Settings(
        data_dir=tmp_path,
        meta_api_key="",
        meta_base="https://api.meta.ai/v1",
        sam_model="sam-3.1",
        voice_model="muse-voice-transcribe-1.0",
        spark_model="muse-spark-1.3",
        baseten_api_key="",
        spark_open_base="https://inference.baseten.co/v1",
        spark_open_model="meta-models/muse-spark-open-1026",
        low_confidence=0.45,
        unannounced_window_ms=30_000,
        lost_after_frames=4,
        sam_fps=2,
        dd_base=dd_base,
    )
    return TestClient(create_app(settings))


def _episode_with_orders(tmp_path):
    client = _client(tmp_path)
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]
    base = f"/journey/episodes/{eid}"
    client.post(f"{base}/orders", json={**ORDERS, "at_ms": 0})
    client.post(f"{base}/obs", json={"sbp": 120, "dbp": 80, "hr": 70, "by": "Nurse A", "at_ms": 0})
    return client, eid


def _rows(client, eid, kind):
    rows = client.get(f"/journey/episodes/{eid}/audit").json()["rows"]
    return [r for r in rows if r["type"] == kind]


def _overdue(client, eid):
    view = client.post(f"/journey/episodes/{eid}/tick", json={"at_ms": 2 * H}).json()
    return next(n for n in view["nudges"] if n["kind"] == "obs_overdue")


def test_seen_takes_demo_time(tmp_path):
    client, eid = _episode_with_orders(tmp_path)
    nudge = _overdue(client, eid)
    r = client.post(f"/journey/episodes/{eid}/nudges/{nudge['id']}/seen", json={"by": "Nurse Meena", "at_ms": 3 * H})
    assert r.status_code == 200
    assert _rows(client, eid, "nudge.seen")[-1]["when"] == "Mon 2 Nov, 12:00"


def test_seen_never_before_the_nudge(tmp_path):
    client, eid = _episode_with_orders(tmp_path)
    nudge = _overdue(client, eid)
    client.post(f"/journey/episodes/{eid}/nudges/{nudge['id']}/seen", json={"by": "Nurse Meena", "at_ms": 0})
    assert _rows(client, eid, "nudge.seen")[-1]["when"].endswith(nudge["when"])  # the audit shows the full date


def _drafted(client, eid):
    base = f"/journey/episodes/{eid}"
    return client.post(f"{base}/handover", json={"from_nurse": "Nurse A", "to_nurse": "Nurse B", "at_ms": 3 * H}).json()["handover"]


def test_accept_takes_demo_time(tmp_path):
    client, eid = _episode_with_orders(tmp_path)
    drafted = _drafted(client, eid)
    r = client.post(f"/journey/episodes/{eid}/handover/{drafted['id']}/accept", json={"by": "Nurse B", "at_ms": 5 * H})
    assert r.status_code == 200
    assert _rows(client, eid, "handover.accepted")[-1]["when"] == "Mon 2 Nov, 14:00"


def test_accept_never_before_the_handover(tmp_path):
    client, eid = _episode_with_orders(tmp_path)
    drafted = _drafted(client, eid)
    client.post(f"/journey/episodes/{eid}/handover/{drafted['id']}/accept", json={"by": "Nurse B", "at_ms": 0})
    assert _rows(client, eid, "handover.accepted")[-1]["when"] == "Mon 2 Nov, 12:00"


def _count(client, eid, **body):
    return client.post(f"/journey/episodes/{eid}/count", json=body)


def _new_episode(client):
    return client.post("/morning/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]


def _short_count(client, eid):
    _count(client, eid, step="opened", quantity=20, by="Nurse Scrub", at_ms=24 * H)
    view = _count(client, eid, step="closing", returned=19, by="Nurse Scrub", at_ms=24 * H + 50 * 60_000).json()
    return view


def test_count_short_raises_nurse_nudge(tmp_path):
    client = _client(tmp_path)
    eid = _new_episode(client)
    view = _short_count(client, eid)
    assert [(n["kind"], n["to"], n["says"]) for n in view["nudges"]] == [
        ("count_open", "nurse", "Closing count: 19 of 20 back, 1 unaccounted.")
    ]


def test_count_correction_strikes_through(tmp_path):
    client = _client(tmp_path)
    eid = _new_episode(client)
    view = _short_count(client, eid)
    nudge = view["nudges"][0]
    first = _rows(client, eid, "count.closing")[0]
    r = _count(client, eid, step="closing", returned=20, detail="Swab found in the drape fold.",
               by="Nurse Scrub", at_ms=24 * H + 54 * 60_000, supersedes_id=first["id"])
    assert r.status_code == 200
    closings = _rows(client, eid, "count.closing")
    assert closings[0]["replaced_by"] == closings[1]["id"]
    assert closings[1]["replaced_by"] is None
    client.post(f"/journey/episodes/{eid}/nudges/{nudge['id']}/seen", json={"by": "Nurse Scrub", "at_ms": 24 * H + 55 * 60_000})
    assert client.get(f"/journey/episodes/{eid}").json()["nudges"] == []


def test_count_closing_needs_opened(tmp_path):
    client = _client(tmp_path)
    eid = _new_episode(client)
    r = _count(client, eid, step="closing", returned=19, by="Nurse Scrub", at_ms=24 * H)
    assert r.status_code == 409


def test_count_rejects_foreign_supersede(tmp_path):
    client = _client(tmp_path)
    eid, other = _new_episode(client), _new_episode(client)
    _short_count(client, other)
    foreign = _rows(client, other, "count.closing")[0]["id"]
    _count(client, eid, step="opened", quantity=20, by="Nurse Scrub", at_ms=24 * H)
    r = _count(client, eid, step="closing", returned=20, by="Nurse Scrub", at_ms=24 * H + 1, supersedes_id=foreign)
    assert r.status_code == 404


def _seed(client):
    return client.post("/journey/demo/seed").json()["patients"]


def test_seed_three_patients(tmp_path):
    client = _client(tmp_path)
    patients = _seed(client)
    assert [p["bed"] for p in patients] == ["4", "7", "9"]
    assert [p["name"] for p in patients] == [
        "R. Kumar, 58 M (synthetic)",
        "S. Iyer, 64 F (synthetic)",
        "A. Das, 47 M (synthetic)",
    ]
    for p in patients:
        assert client.get(f"/journey/episodes/{p['id']}").status_code == 200


def test_seed_iyer_overdue_by_rule(tmp_path):
    client = _client(tmp_path)
    iyer = _seed(client)[1]["id"]
    base = f"/journey/episodes/{iyer}"
    assert client.get(base).json()["nudges"] == []
    view = client.post(f"{base}/tick", json={"at_ms": 2 * H}).json()
    overdue = [n for n in view["nudges"] if n["kind"] == "obs_overdue"]
    assert len(overdue) == 1
    assert overdue[0]["to"] == "nurse"


def test_seed_starting_states(tmp_path):
    client = _client(tmp_path)
    views = [client.get(f"/journey/episodes/{p['id']}").json() for p in _seed(client)]
    assert [v["state"] for v in views] == ["clinic", "ward", "clinic"]


def test_seed_iyer_has_one_open_recurring_obs_task(tmp_path):
    client = _client(tmp_path)
    view = client.get(f"/journey/episodes/{_seed(client)[1]['id']}").json()
    assert [(t["kind"], t["status"], t["every_h"], t["due_ms"]) for t in view["tasks"]] == [("obs", "open", 1, H)]
    assert view["order_list"][0]["acknowledged_by"] == "Nurse Meena (synthetic)"


def test_seed_das_quiet(tmp_path):
    client = _client(tmp_path)
    view = client.get(f"/journey/episodes/{_seed(client)[2]['id']}").json()
    assert view["card"] is None
    assert view["nudges"] == []


def test_count_closing_needs_returned(tmp_path):
    client = _client(tmp_path)
    eid = _new_episode(client)
    assert _count(client, eid, step="closing", by="Nurse Scrub", at_ms=24 * H).status_code == 422


def test_count_opened_cannot_supersede(tmp_path):
    client = _client(tmp_path)
    eid = _new_episode(client)
    r = _count(client, eid, step="opened", quantity=20, by="Nurse Scrub", at_ms=24 * H, supersedes_id="x")
    assert r.status_code == 422
