"""Task 8: the patient checks a medicine in every state, home included. Typed and photo paths write
`brownbag.med_found` with `by: patient`, and the view matches each row to the latest prescription."""

from __future__ import annotations

from pathlib import Path

from tests.test_care_demo import _client, _seed
from tests.test_flow_states import _move, _new, _to_ward, DISCHARGE_CHECKS

DEMO = Path(__file__).resolve().parents[2] / "eval/media/home-medicines/strips-metoprolol-amlodipine-synthetic.png"


def _url(eid, tail):
    return f"/journey/episodes/{eid}/{tail}"


def _found(client, eid):
    return [e for e in client.app.state.morning.events(eid) if e["event_type"] == "brownbag.med_found"]


def _to_home(client, eid):
    _to_ward(client, eid)
    store = client.app.state.morning
    store.append(eid, "discharge.signed", {"by": "Dr. A. Rao (synthetic)"}, ts_ms=1000)
    assert _move(client, eid, "discharging").json()["state"] == "discharging"
    assert _move(client, eid, "home", checklist=DISCHARGE_CHECKS).json()["state"] == "home"


def test_typed_check_at_home_is_kept_as_the_patient(tmp_path):
    client, eid = _new(tmp_path)
    assert client.post(_url(eid, "rx/demo"), json={"at_ms": 0}).status_code == 200
    _to_home(client, eid)
    r = client.post(_url(eid, "strips"), json={"strips": [{"name": "Metoprolol", "strength": "25 mg"}]})
    assert r.status_code == 200, r.text
    [row] = _found(client, eid)
    assert row["payload"]["by"] == "patient" and row["payload"]["source"] == "typed"
    [listed] = r.json()["strips"]
    assert listed["generic"] == "metoprolol" and listed["match"]["kind"] == "on_prescription"


def test_photo_check_at_home_is_kept_as_the_patient(tmp_path):
    client = _client(tmp_path)
    eid = _seed(client)[2]["id"]
    assert client.post(_url(eid, "rx/demo"), json={"at_ms": 0}).status_code == 200
    _to_home(client, eid)
    r = client.post(_url(eid, "strips/photo"), files={"file": ("strip.png", DEMO.read_bytes(), "image/png")})
    assert r.status_code == 200, r.text
    rows = _found(client, eid)
    assert [p["payload"]["generic"] for p in rows] == ["metoprolol", "amlodipine"]
    assert all(p["payload"]["by"] == "patient" for p in rows)
    assert [s["generic"] for s in r.json()["strips"]] == ["metoprolol", "amlodipine"]


def _rx(rows, ts_ms):
    full = [{"form": "", "name": n, "strength": s, "dose": "1-0-1", "timing": "", "duration": "", "instructions": "",
             "key": n.lower()} for n, s in rows]
    return {"by": "Dr", "rows": full}, ts_ms


def test_rows_follow_the_latest_prescription(tmp_path):
    client, eid = _new(tmp_path)
    store = client.app.state.morning
    payload, ts = _rx([("Metoprolol", "25 mg")], 1)
    store.append(eid, "rx.ordered", payload, ts_ms=ts)
    r = client.post(_url(eid, "strips"), json={"by": "patient", "strips": [{"name": "Metoprolol", "strength": "25 mg"}]})
    assert r.json()["strips"][0]["match"]["kind"] == "on_prescription"
    payload, ts = _rx([("Metoprolol", "50 mg")], 2)
    store.append(eid, "rx.ordered", payload, ts_ms=ts)
    view = client.get(_url(eid, "")[:-1]).json()
    assert view["strips"][0]["match"]["kind"] == "strength_differs"
    assert view["strips"][0]["match"]["text"] == "Prescription says 50 mg."
    payload, ts = _rx([("Amlodipine", "5 mg")], 3)
    store.append(eid, "rx.ordered", payload, ts_ms=ts)
    view = client.get(_url(eid, "")[:-1]).json()
    assert view["strips"][0]["match"]["kind"] == "not_on_prescription"


def test_check_before_any_prescription_says_so(tmp_path):
    client, eid = _new(tmp_path)
    r = client.post(_url(eid, "strips"), json={"by": "patient", "strips": [{"name": "Metoprolol", "strength": "25 mg"}]})
    assert r.status_code == 200, r.text
    assert r.json()["strips"][0]["match"]["kind"] == "no_prescription"
