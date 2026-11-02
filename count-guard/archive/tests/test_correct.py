"""Archived with the routes they test (spec §9 "Archiving", Task 16). Not collected: pytest testpaths is backend/tests.

Original file: backend/tests/test_correct.py. These ran against routes that no longer exist and are kept for reference, not run.
The care-app features they map to have the §9 row tests in the plan appendix; the discharge-tier, PDF-encoding and
nudge-wording checks are re-pinned in backend/tests/test_kept_coverage.py. Not every old edge case has a care twin.
"""

from __future__ import annotations

import pytest

from test_care_demo import _client
from test_stream import _patient


def test_morning_route_keeps_its_three_refusals(tmp_path):
    """Until Task 16 archives it, the morning route asks the same shared helper."""
    client = _client(tmp_path)
    eid = client.post("/morning/episodes", json={}).json()["id"]
    for kind in ("count.closing", "surgery.began", "patient.state"):
        old = _store(client).append(eid, kind, {"by": NURSE}, ts_ms=1)
        r = client.post(f"/morning/episodes/{eid}/events/{old['id']}/correct", json={"payload": {}})
        assert r.status_code == 409
    fine = _store(client).append(eid, "druglog.parsed", {"text": "x"}, ts_ms=1)
    assert client.post(f"/morning/episodes/{eid}/events/{fine['id']}/correct", json={"payload": {"text": "y"}}).status_code == 200
