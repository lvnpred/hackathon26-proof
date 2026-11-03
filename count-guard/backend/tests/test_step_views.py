"""What the care view carries so a card's model step can say how the model did (care-app clarity §4.1). Never a live call."""

from __future__ import annotations

from tests.test_capture import _counted
from tests.test_count_gate_paths import NURSE, _begin_with_pack, _camera, _new_patient, _post_json
from tests.test_flow_states import _new
from tests.test_p3_tray import _events, fake_frames, no_network  # noqa: F401  (fixtures)


def test_camera_count_carries_its_source(tmp_path):
    client, eid = _new(tmp_path)
    camera = _counted(client, eid)
    p = [e for e in _events(client, eid) if e["event_type"] == "swabs.counted"][-1]["payload"]
    assert camera["source"] == p["source"] and camera["source"]


def test_closed_camera_case_carries_its_evidence(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    _camera(client, eid, "clip2")
    closed = _post_json(client, eid, "/camera/close", {"by": NURSE}).json()["camera"]["closed"]
    assert closed["evidence"]["returned"]["mode"] in ("prepared", "failed", "none")
    assert "raw" in closed["evidence"]["returned"]
