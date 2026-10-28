import pytest

from doctor_dictation.core.fallback import fallback_format
from doctor_dictation.core.hints import _base
from doctor_dictation.core.spoken import _STRENGTH


def rx(text):
    return {r["name"]: r for r in fallback_format(text)["rx"]}


def test_a_medicine_window_stops_at_the_next_medicine():
    r = rx("Tab Pan 40 mg once daily before food. Tab Dolo 650 mg three times a day for 3 days")
    assert (r["Pan"]["dose"], r["Pan"]["timing"], r["Pan"]["duration"]) == ("1-0-0", "Before food", "")
    assert (r["Dolo"]["dose"], r["Dolo"]["duration"]) == ("1-1-1", "3 days")


def test_one_medicine_with_a_long_gap_keeps_its_details():
    d = rx("Tab Dolo 650 mg, one tablet after food, to be taken three times a day for 3 days")["Dolo"]
    assert (d["dose"], d["timing"], d["duration"]) == ("1-1-1", "After food", "3 days")


def test_single_medicine_simple():
    d = rx("Tab Dolo 650 mg three times a day for 3 days")["Dolo"]
    assert (d["dose"], d["duration"]) == ("1-1-1", "3 days")


@pytest.mark.parametrize("s", ["0.125 mg", "60000 IU", "60000 iu", "650 mg", "12.5 mcg"])
def test_strength_accepts_real_strengths(s):
    assert _STRENGTH.fullmatch(s)


def test_strength_rejects_a_phone_number():
    assert not _STRENGTH.fullmatch("9876543210")


@pytest.mark.parametrize("s,base", [("Thyronorm 0.125 mg", "Thyronorm"), ("Uprise D3 60000 IU", "Uprise D3"),
                                    ("Dolo 650", "Dolo")])
def test_hint_trailing_strength_strips(s, base):
    assert _base(s) == base


# Unpunctuated browser STT: the next match swallows the previous medicine's instructions as its name prefix.
def test_unpunctuated_two_medicines_keep_their_own_frequency():
    r = rx("please take Dolo 650 mg twice daily and Pan 40 mg once daily")
    assert (r["Dolo"]["dose"], r["Pan"]["dose"]) == ("1-0-1", "1-0-0")


def test_unpunctuated_timing_and_duration_stay_with_their_medicine():
    r = rx("Tab Augmentin 625 mg twice daily after food Tab Pan 40 mg once daily before food for 5 days")
    assert (r["Augmentin"]["dose"], r["Augmentin"]["timing"]) == ("1-0-1", "After food")
    assert (r["Pan"]["dose"], r["Pan"]["timing"], r["Pan"]["duration"]) == ("1-0-0", "Before food", "5 days")


def test_unpunctuated_twice_then_thrice():
    r = rx("Tab Pan 40 mg twice daily tab Dolo 650 mg thrice daily for 3 days")
    assert (r["Pan"]["dose"], r["Dolo"]["dose"]) == ("1-0-1", "1-1-1")


def test_unpunctuated_bedtime_stays_with_the_first_medicine():
    assert rx("Tab Pan 40 mg at bedtime Tab Dolo 650 mg")["Pan"]["dose"] == "0-0-1"


def test_a_skipped_non_drug_match_does_not_cut_the_window():
    d = rx("Tab Dolo 650 mg twice daily with 500 ml water for 5 days")["Dolo"]
    assert (d["dose"], d["duration"]) == ("1-0-1", "5 days")


def test_instruction_before_the_only_medicine_still_counts():
    assert rx("Twice daily Tab Augmentin 625 mg for 5 days")["Augmentin"]["dose"] == "1-0-1"


def test_shared_trailing_instruction_goes_to_the_last_medicine_only():
    # Accepted trade-off (final review C1): stopping leaks across medicines means a shared
    # "both twice daily" after the last medicine is read by that medicine alone; Dolo gets the 1-0-0 default.
    r = rx("Tab Dolo 650 mg, Tab Pan 40 mg, both twice daily for 5 days")
    assert (r["Dolo"]["dose"], r["Pan"]["dose"], r["Pan"]["duration"]) == ("1-0-0", "1-0-1", "5 days")


@pytest.mark.parametrize("s", ["500081", "104523"])
def test_strength_rejects_a_bare_five_or_six_digit_number(s):
    assert not _STRENGTH.fullmatch(s)


@pytest.mark.parametrize("s,base", [("Ravi 98765 43210", "Ravi 98765 43210"), ("Uprise D3 60000 IU", "Uprise D3")])
def test_hint_base_keeps_a_bare_long_number(s, base):
    assert _base(s) == base
