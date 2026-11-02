"""Archived with the routes they test (spec §9 "Archiving", Task 16). Not collected: pytest testpaths is backend/tests.

Original file: backend/tests/test_journey.py. These ran against routes that no longer exist and are kept for reference, not run.
The care-app features they map to have the §9 row tests in the plan appendix; the discharge-tier, PDF-encoding and
nudge-wording checks are re-pinned in backend/tests/test_kept_coverage.py. Not every old edge case has a care twin.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.agent.verifier import ADVICE
from app.config import Settings
from app.journey import nudges as rules
from app.journey import rx as rxmod
from app.journey.rx import DEMO_DOCUMENT, from_document
from app.journey.schedule import build, days, reminders_ics, slots
from app.main import create_app


def test_no_nudge_in_the_demo_tells_anyone_what_to_do_clinically(tmp_path):
    api = _client(tmp_path)
    eid = _episode(api)
    api.post(f"/journey/episodes/{eid}/play")
    rows = api.get(f"/journey/episodes/{eid}/audit").json()["rows"]
    raised = [row["what"] for row in rows if row["type"] == "nudge.raised"]
    assert len(raised) == 8  # strip, count, BP, early dose, overdue dose, obs round, sign, help
    for text in raised:
        assert not ADVICE.search(text), text
        assert not INSTRUCTION.search(text), text


def test_the_demo_completes_all_three_stories_with_corrections_kept(tmp_path):
    api = _client(tmp_path)
    eid = _episode(api)
    view = api.post(f"/journey/episodes/{eid}/play").json()
    assert [(s["who"], s["done"], s["total"]) for s in view["stories"]] == [
        ("Doctor", 4, 4), ("Nurse", 5, 5), ("Patient", 4, 4),
    ]
    assert sorted(_kinds(view)) == ["help_requested", "warning_sign_ticked"]
    assert view["ics_url"] == f"/journey/episodes/{eid}/reminders.ics"  # kept after a reload
    assert [s["strength"] for s in view["strips"] if s["generic"] == "amlodipine"] == ["5 mg"]
    rows = api.get(f"/journey/episodes/{eid}/audit").json()["rows"]
    replaced = [row for row in rows if row["replaced_by"]]
    assert {row["type"] for row in replaced} == {"brownbag.med_found", "count.closing"}
