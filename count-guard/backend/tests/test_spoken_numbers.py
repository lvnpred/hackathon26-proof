"""Spoken numbers become digits (clarity §4.5): "hundred", "a hundred and five", and "one twenty over eighty"."""

from __future__ import annotations

import pytest

from app.journey import dictation
from app.journey.spoken import parse_values
from app.journey.spoken_numbers import words_to_digits


@pytest.mark.parametrize("said, heard", [
    ("one hundred twenty over eighty", "120 over 80"),
    ("a hundred and five", "105"),
    ("seventy two", "72"),
    ("one twenty over eighty", "120 over 80"),
    ("one eighteen over seventy six", "118 over 76"),
    ("one twenty / eighty", "120 / 80"),
    ("one hundred", "100"),
    ("two hundred and ten", "210"),
    ("pulse one hundred and four", "pulse 104"),
    ("temp thirty seven point five", "temp 37.5"),
    ("eighty two over fifty four", "82 over 54"),
    ("one gram", "1 gram"),
    ("twenty", "20"),
    ("seventeen", "17"),
    ("120/80, pulse 72", "120/80, pulse 72"),
])
def test_words_to_digits(said, heard):
    assert words_to_digits(said) == heard


def test_one_twenty_is_120_only_before_over():
    assert words_to_digits("one twenty minutes") == "1 20 minutes"
    assert words_to_digits("one twenty over eighty") == "120 over 80"


def test_dictation_digits_uses_it():
    assert dictation.digits("BP one hundred twenty over eighty") == "BP 120 over 80"


def test_bp_and_pulse_from_words():
    assert parse_values("BP one hundred twenty over eighty, pulse seventy two") == {"sbp": 120, "dbp": 80, "hr": 72}
    assert parse_values("BP one twenty over eighty, pulse a hundred and five") == {"sbp": 120, "dbp": 80, "hr": 105}


@pytest.mark.parametrize("said, heard", [
    ("one hundred point two", "100.2"),
    ("a hundred point two", "100.2"),
    ("thirty eight point one two", "38.12"),
    ("one fifteen over eighty", "115 over 80"),
    ("one fifteen over 80", "115 over 80"),
    ("one fifteen over the limit", "1 15 over the limit"),
])
def test_fix_round_numbers(said, heard):
    assert words_to_digits(said) == heard


def test_temp_reads_three_digits_and_drops_out_of_range():
    assert parse_values("temp 100") == {}  # 100 is no Celsius reading; it was never 10
    assert parse_values("temperature thirty eight point one two") == {"temp": 38.12}
    assert parse_values("temp thirty seven point five") == {"temp": 37.5}
    assert parse_values("BP 400 over 80, pulse 72") == {"hr": 72}  # a pressure is both numbers or neither
