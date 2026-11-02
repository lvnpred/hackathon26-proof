"""Archived with the routes they test (spec §9 "Archiving", Task 16). Not collected: pytest testpaths is backend/tests.

Original file: backend/tests/test_count_gate.py. These ran against routes that no longer exist and are kept for reference, not run.
The care-app features they map to have the §9 row tests in the plan appendix; the discharge-tier, PDF-encoding and
nudge-wording checks are re-pinned in backend/tests/test_kept_coverage.py. Not every old edge case has a care twin.
"""

from __future__ import annotations

from tests.test_capture import _closing, _counted
from tests.test_flow_states import _count, _move, _new, _surgery, _to_theatre
from tests.test_p3_tray import fake_frames, no_network  # noqa: F401  (fixtures)


def test_replay_route_closing_without_a_person_does_not_end_surgery(tmp_path):
    client, eid = _begun(tmp_path)
    client.post(f"/morning/episodes/{eid}/count/replay")
    r = _surgery(client, eid, "ended")
    assert r.status_code == 409 and r.json()["detail"] in (SAVE_FIRST, NOT_ADDING_UP)
