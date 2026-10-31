"""Task 2 (design): the pill names the clinical finding (spec 5.2). One test per row of the table."""

from __future__ import annotations

from app.journey.ai_moments import moments
from tests.test_ai_moments import ASHA, DOSE, OBS, RAO, SAM, VOICE, _closing, _ev, _swab_flag
from tests.test_ai_moments import no_network  # noqa: F401  (fixture)

HOUR = 3_600_000
MIN = 60_000


def _pill(rows, capability, index=0):
    m = [r for r in rows if r["capability"] == capability][index]
    return m["finding_role"], m["finding_text"]


def _count_nudge(fact_id="c1", ts=3):
    return _ev("n1", "nudge.raised", ts, key="k", kind="count_open", to="nurse", says="x", says_staff="x",
               intent_id=None, fact_id=fact_id, at_ms=ts)


def _orders(**extra):
    return _ev("o1", "ward.orders_set", 1, by=RAO, doses=[{"key": "paracetamol", "name": "Paracetamol", "every_h": 6}],
               obs_every_h=4, limits={"sbp_min": 90, **extra})


def test_unaccounted_count_is_danger_until_corrected():
    short = _closing("c1", 2, 14)
    assert _pill(moments([_swab_flag(), short, _count_nudge()]), "nudge") == ("danger", "1 swab unaccounted")
    assert _pill(moments([_swab_flag(), _closing("c1", 2, 13), _count_nudge()]), "nudge") == ("danger", "2 swabs unaccounted")
    fixed = {**_closing("c2", 12, 15), "supersedes_id": "c1"}
    rows = moments([_swab_flag(), short, fixed, _count_nudge()])
    assert _pill(rows, "swabs") == ("done", "Replaced by count")
    assert _pill(rows, "nudge") == ("fine", "Count complete")


def test_camera_count_waits_on_a_person_until_counted():
    assert _pill(moments([_swab_flag()]), "swabs") == ("check", "Check this")


def test_tray_flag_goes_to_the_surgeon():
    tray = _ev("t1", "tray.checked", 10, rows=[{"concept": "needle holder", "planned": 3, "seen": 2}], match="mismatch",
               why="w", media="video", source="prepared", calls=[SAM], by=ASHA, evidence_id="e" * 32, frame_ids=[])
    assert _pill(moments([tray]), "tray") == ("check", "Surgeon to decide")


def test_resolved_flag_names_person():
    tray = _ev("t1", "tray.checked", 10, rows=[{"concept": "needle holder", "planned": 3, "seen": 2}], match="mismatch",
               why="w", media="video", source="prepared", calls=[SAM], by=ASHA, evidence_id="e" * 32, frame_ids=[])
    again = _ev("t2", "tray.checked", 20, rows=[{"concept": "needle holder", "planned": 3, "seen": 3}], match="ok",
                why="", media="video", source="prepared", calls=[SAM], by=ASHA, evidence_id="f" * 32, frame_ids=[])
    rows = moments([tray, again])
    first = [m for m in rows if m["id"] == "t1"][0]
    assert (first["finding_role"], first["finding_text"]) == ("fine", f"Checked by {ASHA}")
    assert [m for m in rows if m["id"] == "t2"][0]["finding_text"] == "Matches"


def test_limit_nudge_is_danger_while_open():
    obs = _ev("b1", "obs.recorded", 2, by=ASHA, sbp=82, dbp=54, hr=90)
    nudge = _ev("n1", "nudge.raised", 3, key="obs:b1:sbp_min", kind="obs_past_limit", to="nurse",
                says="Systolic BP 82 is below the limit of 90 set by x.", says_staff="s", intent_id="o1", fact_id="b1", at_ms=3)
    assert _pill(moments([_orders(), obs, nudge]), "nudge") == ("danger", "Below limit")
    up = {**nudge, "payload": {**nudge["payload"], "key": "obs:b1:hr_max"}}
    assert _pill(moments([_orders(), obs, up]), "nudge") == ("danger", "Above limit")


def test_overdue_nudge_says_how_late():
    obs = _ev("b1", "obs.recorded", 0, by=ASHA, sbp=110, dbp=70, hr=80)

    def late(minutes):
        at = 4 * HOUR + minutes * MIN
        return _ev("n1", "nudge.raised", at, key="obs-due:b1", kind="obs_overdue", to="nurse", says="x", says_staff="x",
                   intent_id="o1", fact_id="b1", at_ms=at)

    assert _pill(moments([_orders(), obs, late(75)]), "nudge") == ("check", "Late 1 h 15 min")
    assert _pill(moments([_orders(), obs, late(40)]), "nudge") == ("check", "Late 40 min")
    dose = _ev("n2", "nudge.raised", 7 * HOUR, key="dose-due:paracetamol:o1", kind="dose_overdue", to="nurse", says="x",
               says_staff="x", intent_id="o1", fact_id=None, at_ms=7 * HOUR)
    assert _pill(moments([_orders(), dose]), "nudge")[1] == "Late 59 min"  # order at 1 ms, due every 6 h, 7 h on


def test_open_moment_with_another_owner_waits():
    drafted = _ev("d1", "order.drafted", 10, items=[DOSE, OBS], transcript="a b", heard_by="prepared", source="rules",
                  calls=[VOICE], by=RAO)
    assert _pill(moments([drafted]), "orders") == ("wait", "Waiting for the doctor")


def test_matches_reads_matches():
    strip = _ev("p1", "proof.checked", 10, values_read={"sbp": 120, "dbp": 80, "hr": 70}, match="ok", source="prepared",
                photo_id="ph", regions=[], calls=[SAM], by=ASHA)
    assert _pill(moments([strip]), "monitor") == ("fine", "Matches")


def test_signed_draft_is_done_with_the_signing_time():
    drafted = _ev("d1", "order.drafted", 10, items=[DOSE, OBS], transcript="a b", heard_by="prepared", source="rules",
                  calls=[VOICE], by=RAO)
    signed = _ev("s1", "order.signed", 20 * MIN, items=[DOSE, OBS], draft_id="d1", by=RAO)
    assert _pill(moments([drafted, signed]), "orders") == ("done", "Signed 09:20")


def test_other_recorded_is_saved_with_a_time():
    card = _ev("k1", "discharge.card", 5 * MIN, warning_signs=["x"], schedule=[], by=RAO)
    role, text = _pill(moments([card]), "discharge_card")
    assert (role, text) == ("done", "Saved 09:05")


def test_nothing_is_ever_called_recorded():
    rows = moments([_swab_flag(), _closing("c1", 11, 14), _closing("c2", 12, 15)])
    assert rows and all("Recorded" not in m["finding_text"] for m in rows)


def _tray_flag():
    return _ev("t1", "tray.checked", 10, rows=[{"concept": "needle holder", "planned": 3, "seen": 2}], match="mismatch",
               why="w", media="video", source="prepared", calls=[SAM], by=ASHA, evidence_id="e" * 32, frame_ids=[])


def test_leaving_theatre_does_not_make_a_flag_green():
    state = lambda eid, ts, to: _ev(eid, "patient.state", ts, to=to)  # noqa: E731
    rows = moments([state("s1", 1, "theatre"), _tray_flag(), state("s2", 20, "ward")])
    role, text = _pill(rows, "tray")
    assert (role, text) == ("check", "Not checked: left theatre")


def test_limit_direction_comes_from_the_key():
    obs = _ev("b1", "obs.recorded", 2, by=ASHA, sbp=82, dbp=54, hr=140)

    def nudge(name):
        return _ev("n1", "nudge.raised", 3, key=f"obs:b1:{name}", kind="obs_past_limit", to="nurse", says="s",
                   says_staff="s", intent_id="o1", fact_id="b1", at_ms=3)

    assert _pill(moments([_orders(), obs, nudge("sbp_min")]), "nudge") == ("danger", "Below limit")
    assert _pill(moments([_orders(), obs, nudge("hr_max")]), "nudge") == ("danger", "Above limit")


def test_answered_count_nudge_is_not_count_complete_while_swabs_are_missing():
    seen = _ev("n2", "nudge.seen", 4, nudge_id="n1", by=ASHA, note="found later")
    rows = moments([_swab_flag(), _closing("c1", 2, 14), _count_nudge(), seen])
    assert _pill(rows, "nudge") == ("danger", "1 swab unaccounted")
