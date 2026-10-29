"""P4 final fix wave: plain wording on patient screens."""

from __future__ import annotations

import re

from app.journey import video
from app.journey.doctor_status import current
from app.journey.states import MOVES
from app.journey.stories import CARE_TEMPLATES, plain

ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)


def test_plain_state_moves_have_no_raw_state_words():
    for src, targets in MOVES.items():
        for dst in targets:
            text = plain({"event_type": "patient.state", "payload": {"by": "Dr. A. Rao", "from": src, "to": dst}})
            assert "_" not in text and not ADVICE.search(text), text
    first = plain({"event_type": "patient.state", "payload": {"by": "Dr. A. Rao", "from": None, "to": "ward"}})
    assert "_" not in first and "admitted" in first


def test_plain_clinic_done_reads_as_end_of_visit():
    text = plain({"event_type": "patient.state", "payload": {"by": "X", "from": "clinic", "to": "clinic_done"}})
    assert text == "X moved the patient from the clinic to the end of the clinic visit."


def test_plain_answer_via_is_words():
    for via, word in (("voice", "(by voice)"), ("text", "(typed)")):
        text = plain({"event_type": "question.answered", "payload": {"by": "Dr", "source": "doctor", "via": via}})
        assert word in text and "(voice)" not in text and "(text)" not in text, text


def test_warning_signs_pass_advice_check():
    for sign in CARE_TEMPLATES["hernia-repair"]["warning_signs"]:
        assert not ADVICE.search(sign), sign


def test_chip_past_estimate_says_free_soon():
    H = 3_600_000
    payload = {"doctor": "Dr. A. Rao", "status": "in_theatre", "patient": "R. Kumar", "until_ms": 2 * H, "source": "auto"}
    state = {"id": "s", "event_type": "patient.state", "ts_ms": 0, "payload": {"to": "theatre"}}
    ds = {"id": "d", "event_type": "doctor.status", "ts_ms": 1, "payload": payload}
    before = current("Dr. A. Rao", [[state, ds]], [], H)
    assert before["text"].endswith("free about 11:00") or "free about" in before["text"]
    for now in (2 * H, 3 * H):
        got = current("Dr. A. Rao", [[state, ds]], [], now)
        assert got["text"] == "Dr. A. Rao: In theatre with R. Kumar, expected free soon", got["text"]


def test_no_answer_for_photos_does_not_say_video_model():
    why = video._said(video.NO_ANSWER, "photos")
    assert "video model" not in why and "the model" in why
