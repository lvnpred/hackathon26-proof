"""Archived with the routes they test (spec §9 "Archiving", Task 16). Not collected: pytest testpaths is backend/tests.

Original file: backend/tests/test_camera_advice.py. These ran against routes that no longer exist and are kept for reference, not run.
The care-app features they map to have the §9 row tests in the plan appendix; the discharge-tier, PDF-encoding and
nudge-wording checks are re-pinned in backend/tests/test_kept_coverage.py. Not every old edge case has a care twin.
"""

from __future__ import annotations

import dataclasses
import re

import pytest

from app.journey import camera_api, switches
from app.journey.stories import CAMERA_BY
from app.media_pipeline import SamCallFailed
from tests.test_care_demo import _client
from tests.test_count_gate_paths import NURSE, _begin_with_pack, _camera, _events, _new_patient, _post_json


def test_morning_routes_still_call_the_moved_bodies(tmp_path):
    client = _client(tmp_path)
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]
    r = client.post(f"/morning/episodes/{eid}/count/manual", json={"track_id": "swab-3"})
    assert r.status_code == 200, r.text
    assert [e["payload"] for e in _kinds(client, eid, "count.item_out")] == [
        {"track_id": "swab-3", "frame_id": None, "source": "manual"}
    ]
    for t in range(3):
        r = client.post(f"/morning/episodes/{eid}/count/frame",
                        json={"track_id": "swab-1", "zone": "bucket", "frame_id": f"f{t}", "t_ms": t * 100})
        assert r.status_code == 200, r.text
    assert r.json()["out"] == ["swab-1"] and len(r.json()["emitted"]) == 1
