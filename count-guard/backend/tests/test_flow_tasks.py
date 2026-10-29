"""Orders become nurse tasks: sign, acknowledge, tick or start and end, and the discharge signing."""

from __future__ import annotations

from tests.test_flow_states import _move, _new, _to_ward, _view

H = 3_600_000
DOC = "Dr. A. Rao (synthetic)"
NURSE = "Nurse Asha (synthetic)"
DOSE = {"kind": "dose", "text": "Paracetamol 1 g every 6 h", "name": "Paracetamol", "amount": "1 g", "every_h": 6}
OBS = {"kind": "obs", "text": "BP every 1 h", "every_h": 1, "limits": {"sbp_min": 90}}


def _url(eid, tail):
    return f"/journey/episodes/{eid}/{tail}"


def _sign(client, eid, items, at_ms=0):
    return client.post(_url(eid, "orders/sign"), json={"items": items, "by": DOC, "at_ms": at_ms})


def _ack(client, eid, order_id, at_ms=0):
    return client.post(_url(eid, f"orders/{order_id}/ack"), json={"by": NURSE, "at_ms": at_ms})


def _done(client, eid, task_id, at_ms=0, **extra):
    return client.post(_url(eid, f"tasks/{task_id}/done"), json={"by": NURSE, "via": "tap", "at_ms": at_ms, **extra})


def _ward_with_tasks(tmp_path, items, ack_at=0):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    order = _sign(client, eid, items).json()["order_list"][0]
    view = _ack(client, eid, order["id"], ack_at).json()
    return client, eid, order, view


def test_sign_writes_order_and_merged_ward_orders(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    view = _sign(client, eid, [DOSE, OBS]).json()
    assert view["order_list"][0]["acknowledged_by"] is None
    assert view["orders"]["obs_every_h"] == 1
    assert view["orders"]["limits"]["sbp_min"] == 90
    assert [d["name"] for d in view["orders"]["doses"]] == ["Paracetamol"]
    other = {"kind": "dose", "text": "Ondansetron 4 mg every 8 h", "name": "Ondansetron", "amount": "4 mg", "every_h": 8}
    view = _sign(client, eid, [other], at_ms=1000).json()
    assert [d["name"] for d in view["orders"]["doses"]] == ["Paracetamol", "Ondansetron"]
    assert view["orders"]["obs_every_h"] == 1


def test_sign_refused_outside_care_states(tmp_path):
    client, eid = _new(tmp_path)
    assert _move(client, eid, "clinic_done").status_code == 200
    assert _sign(client, eid, [DOSE]).status_code == 409


def test_ack_creates_one_task_per_item_once(tmp_path):
    client, eid, order, view = _ward_with_tasks(tmp_path, [DOSE, OBS], ack_at=5000)
    assert len(view["tasks"]) == 2
    assert all(t["status"] == "open" and t["due_ms"] == 5000 for t in view["tasks"])
    assert _ack(client, eid, order["id"]).status_code == 409
    assert len(_view(client, eid)["tasks"]) == 2
    assert _ack(client, eid, "nope").status_code == 404


def test_tick_dose_writes_dose_given_and_recurs(tmp_path):
    client, eid, _, view = _ward_with_tasks(tmp_path, [DOSE])
    task = view["tasks"][0]
    view = _done(client, eid, task["id"], at_ms=2 * H).json()
    assert any(e["type"] == "dose.given" for e in view["timeline"])
    assert view["tasks"][0]["status"] == "open"
    assert view["tasks"][0]["due_ms"] == 2 * H + 6 * H
    assert view["tasks"][0]["done"][0]["by"] == NURSE


def test_obs_task_needs_values_and_feeds_limit_nudge(tmp_path):
    client, eid, _, view = _ward_with_tasks(tmp_path, [OBS])
    task = view["tasks"][0]
    assert _done(client, eid, task["id"]).status_code == 422
    view = _done(client, eid, task["id"], values={"sbp": 82, "dbp": 50, "hr": 90}).json()
    assert any(e["type"] == "obs.recorded" for e in view["timeline"])
    assert any(n["kind"] == "obs_past_limit" for n in view["nudges"])


def test_start_end_task(tmp_path):
    item = {"kind": "procedure", "mode": "start_end", "text": "Saline 1 L over 2 h"}
    client, eid, _, view = _ward_with_tasks(tmp_path, [item])
    tid = view["tasks"][0]["id"]
    assert _done(client, eid, tid).status_code == 409
    begin = lambda at: client.post(_url(eid, f"tasks/{tid}/begin"), json={"by": NURSE, "at_ms": at})
    assert begin(1000).json()["tasks"][0]["status"] == "running"
    assert begin(2000).status_code == 409
    task = _done(client, eid, tid, at_ms=3000).json()["tasks"][0]
    assert task["status"] == "done" and task["began_ms"] == 1000


def test_tick_task_cannot_begin(tmp_path):
    client, eid, _, view = _ward_with_tasks(tmp_path, [DOSE])
    r = client.post(_url(eid, f"tasks/{view['tasks'][0]['id']}/begin"), json={"by": NURSE})
    assert r.status_code == 409


def test_non_recurring_done_twice_is_409(tmp_path):
    item = {"kind": "check", "text": "Check wound dressing"}
    client, eid, _, view = _ward_with_tasks(tmp_path, [item])
    tid = view["tasks"][0]["id"]
    task = _done(client, eid, tid).json()["tasks"][0]
    assert task["status"] == "done" and task["due_ms"] is None
    assert _done(client, eid, tid).status_code == 409


def test_discharge_sign_moves_to_discharging(tmp_path):
    client, eid = _new(tmp_path)
    body = {"summary": "Recovered well.", "by": DOC, "at_ms": 0}
    assert client.post(_url(eid, "discharge/sign"), json=body).status_code == 409
    _to_ward(client, eid)
    view = client.post(_url(eid, "discharge/sign"), json=body).json()
    assert view["state"] == "discharging"
    assert view["card"] is not None
    assert "discharge" in view["now_next"]["next"]
