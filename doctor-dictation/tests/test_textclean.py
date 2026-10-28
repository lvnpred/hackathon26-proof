"""clean_text: the one place typed free text is made safe to store and print. Offline."""
import pytest

from doctor_dictation.textclean import clean_text


@pytest.mark.parametrize("raw, want", [
    ("Dr.‮Rao", "Dr.Rao"),                 # bidi override deleted
    ("Dr. Rao", "Dr. Rao"),                # line separator becomes a space
    ("Dr. Rao", "Dr. Rao"),
    ("Dr.​Rao", "Dr.Rao"),                 # zero-width space deleted
    ("﻿Dr", "Dr"),
    ("a⁦b⁩c", "abc"),
    ("ಕ‍‌d", "ಕ‍‌d"),        # ZWJ and ZWNJ kept: Indic scripts need them
    ("Dr.\nRao\x00 \t One", "Dr. Rao One"),
    ("  padded  ", "padded"),
    (None, ""),
    (12, ""),
])
def test_clean_text(raw, want):
    assert clean_text(raw) == want
