"""Surgery cannot end on an unsaved or unexplained swab count; a closing that does not match needs a reason (spec 5.3)."""

from __future__ import annotations

from tests.test_capture import _closing, _counted
from tests.test_flow_states import _count, _new, _surgery, _to_theatre
from tests.test_p3_tray import fake_frames, no_network  # noqa: F401  (fixtures)

SAVE_FIRST = "Save the swab count first."
NOT_ADDING_UP = "The swab count does not add up. Record what the team did first."
SAY_WHAT = "Say what the team did: the count does not match."


def _begun(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    assert _surgery(client, eid, "began").status_code == 200
    return client, eid


def test_end_refused_without_count(tmp_path):
    client, eid = _begun(tmp_path)
    r = _surgery(client, eid, "ended")
    assert r.status_code == 409 and r.json()["detail"] == SAVE_FIRST
    _count(client, eid, "opened", quantity=20)  # a pack opened is not a count saved
    assert _surgery(client, eid, "ended").json()["detail"] == SAVE_FIRST


def test_end_refused_when_unaccounted_without_reason(tmp_path):
    client, eid = _begun(tmp_path)
    _count(client, eid, "opened", quantity=20)
    assert _count(client, eid, "closing", returned=19).status_code == 422
    # A closing with a reason stands; blank out the reason by writing the event as the old client did.
    from app.journey import states
    events = client.app.state.morning.events(eid)
    assert not states.count_reconciled(events)
    r = _surgery(client, eid, "ended")
    assert r.status_code == 409 and r.json()["detail"] == SAVE_FIRST


def test_unreconciled_closing_on_record_refuses_end(tmp_path):
    client, eid = _begun(tmp_path)
    client.app.state.morning.append(eid, "count.pack_opened", {"quantity": 20, "by": "N"}, ts_ms=1)
    client.app.state.morning.append(eid, "count.closing", {"opened": 20, "returned": 19, "unaccounted": 1, "detail": " ", "by": "N"}, ts_ms=2)
    r = _surgery(client, eid, "ended")
    assert r.status_code == 409 and r.json()["detail"] == NOT_ADDING_UP


def test_end_allowed_after_reconciled_count(tmp_path):
    client, eid = _begun(tmp_path)
    _count(client, eid, "opened", quantity=20)
    assert _count(client, eid, "closing", returned=20).status_code == 200
    assert _surgery(client, eid, "ended").status_code == 200


def test_end_allowed_with_reason_and_unaccounted(tmp_path):
    client, eid = _begun(tmp_path)
    _count(client, eid, "opened", quantity=20)
    assert _count(client, eid, "closing", returned=19, detail="X-ray taken, nothing seen.").status_code == 200
    assert _surgery(client, eid, "ended").status_code == 200


def test_closing_needs_reason_when_camera_differs(tmp_path):
    client, eid = _new(tmp_path)
    ev = _counted(client, eid)["evidence_id"]  # camera reads 14, pack opened 15
    r = _closing(client, eid, returned=15, evidence_id=ev)
    assert r.status_code == 422 and r.json()["detail"] == SAY_WHAT
    assert _closing(client, eid, returned=15, evidence_id=ev, detail="Found under the drape").status_code == 200


def test_closing_needs_reason_when_short_without_camera(tmp_path):
    client, eid = _begun(tmp_path)
    _count(client, eid, "opened", quantity=20)
    assert _count(client, eid, "closing", returned=19, detail="  ").json()["detail"] == SAY_WHAT


def test_superseded_count_does_not_count(tmp_path):
    client, eid = _begun(tmp_path)
    _count(client, eid, "opened", quantity=20)
    first = _count(client, eid, "closing", returned=20).json()
    first_id = [t for t in first["timeline"] if t["type"] == "count.closing"][-1]["id"]
    # The saved count is replaced by a short one that has a reason: still reconciled by the reason.
    _count(client, eid, "closing", returned=19, detail="Searching.", supersedes_id=first_id)
    assert _surgery(client, eid, "ended").status_code == 200


def test_superseded_reconciled_count_is_not_the_standing_one(tmp_path):
    from app.journey import states
    client, eid = _begun(tmp_path)
    store = client.app.state.morning
    store.append(eid, "count.pack_opened", {"quantity": 20, "by": "N"}, ts_ms=1)
    good = store.append(eid, "count.closing", {"opened": 20, "returned": 20, "unaccounted": 0, "detail": "", "by": "N"}, ts_ms=2)
    store.append(eid, "count.closing", {"opened": 20, "returned": 19, "unaccounted": 1, "detail": "", "by": "N"},
                 ts_ms=3, supersedes_id=good["id"])
    assert not states.count_reconciled(store.events(eid))
