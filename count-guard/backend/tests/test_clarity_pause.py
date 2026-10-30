from tests.test_flow_states import _move, _new, _surgery, _to_ward
from tests.test_flow_tasks import DOSE, H, OBS, _ack, _done, _sign


def _kinds(view):
    return {n["kind"] for n in view["nudges"]}


def test_due_nudges_pause_in_theatre_and_resume(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    order = _sign(client, eid, [DOSE, OBS]).json()["order_list"][0]
    view = _ack(client, eid, order["id"]).json()
    obs_task = next(t for t in view["tasks"] if t["kind"] == "obs")
    assert _done(client, eid, obs_task["id"], values={"sbp": 120, "dbp": 80, "hr": 70}).status_code == 200
    assert _move(client, eid, "theatre", procedure="hernia-repair").status_code == 200
    tick = lambda at: client.post(f"/journey/episodes/{eid}/tick", json={"at_ms": at}).json()
    assert not _kinds(tick(7 * H)) & {"dose_overdue", "obs_overdue"}
    _surgery(client, eid, "began"); _surgery(client, eid, "ended")
    assert _move(client, eid, "ward", by="Nurse Asha (synthetic)", reason="", checklist={}, at_ms=7 * H + 1000).status_code == 200
    assert {"dose_overdue", "obs_overdue"} <= _kinds(tick(7 * H + 2000))
