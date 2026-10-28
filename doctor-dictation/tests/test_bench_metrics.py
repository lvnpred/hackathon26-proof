import pytest

from doctor_dictation.bench.metrics import drug_recall, wer


@pytest.mark.parametrize("ref,hyp,expected", [
    ("Tab Dolo 650", "tab dolo 650", 0.0),               # identical
    ("one two three four", "one two three five", 0.25),  # substitution
    ("one two", "one two three", 0.5),                   # insertion
    ("one two three four", "one two four", 0.25),        # deletion
    ("one", "one two three", 2.0),                       # not capped
    ("", "", 0.0), ("  ...  ", "", 0.0), ("", "something", 1.0),  # empty reference
    ("five hundred mg", "500 mg", 2 / 3),                # number words kept as-is
    ("Tab. Dolo-650, Don't 1-0-1!", "tab dolo 650 dont 1 0 1", 0.0),  # punctuation, case
])
def test_wer(ref, hyp, expected):
    assert wer(ref, hyp) == pytest.approx(expected)


def test_drug_recall_multiword_needs_same_words_in_order():
    names = ["Calcium Carbonate"]
    assert drug_recall("give calcium carbonate", "give Calcium-Carbonate", names) == (1, 1)
    assert drug_recall("give calcium carbonate", "give calcium and carbonate", names) == (0, 1)
    assert drug_recall("give calcium carbonate", "give carbonate calcium", names) == (0, 1)


def test_drug_recall_whole_word_case_insensitive_and_distinct():
    assert drug_recall("Add DOLO", "add dolo", ["Dolo"]) == (1, 1)
    assert drug_recall("add dolo", "add dolor", ["Dolo"]) == (0, 1)
    assert drug_recall("add dolo", "add adolo", ["Dolo"]) == (0, 1)
    assert drug_recall("only paracetamol", "paracetamol zinc", ["Paracetamol", "paracetamol", "Zinc", " "]) == (1, 1)
