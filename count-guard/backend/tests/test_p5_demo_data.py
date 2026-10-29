"""P5 demo data: the prepared transcripts agree with the care template they sit beside."""

from __future__ import annotations

import json
from pathlib import Path

from app.journey.procedures import tray_plan

PREPARED = Path(__file__).resolve().parents[1] / "app" / "journey" / "prepared"


def test_discharge_transcript_count_matches_template():
    total = tray_plan("hernia-repair")["swab_total"]
    transcript = json.loads((PREPARED / "kumar-discharge.json").read_text())["transcript"]
    assert f"{total} of {total}" in transcript
