from pathlib import Path

import pytest

from doctor_dictation.core.lexicon.build_investigations import build, key, rows_from_csv

DRAFT_CSV = (Path(__file__).resolve().parent.parent
             / "docs/working/2026-10-19-prescription-quality/investigations-draft.csv")


def test_a_row_becomes_an_entry_with_split_aliases():
    csv_text = "canonical,aliases,category,print\nRenal Function Test,rft;kft; kidney function test ,Blood,RFT\n"
    assert rows_from_csv(csv_text) == [{"canonical": "Renal Function Test", "aliases": ["rft", "kft", "kidney function test"],
                                        "category": "Blood", "print": "RFT"}]


def test_hash_lines_are_skipped_but_an_unreviewed_draft_is_refused():
    body = "canonical,aliases,category,print\nESR,esr,Blood,ESR\n"
    assert rows_from_csv("# reviewed 2026-10-20\n" + body)[0]["canonical"] == "ESR"
    with pytest.raises(ValueError, match="NOT REVIEWED"):
        rows_from_csv("# DRAFT - NOT REVIEWED\n" + body)
    assert rows_from_csv("# DRAFT - NOT REVIEWED\n" + body, allow_draft=True)


def test_a_name_claimed_by_two_entries_is_refused():
    clash = "canonical,aliases,category,print\nA Test,abc,Blood,A\nB Test,ABC,Blood,B\n"
    with pytest.raises(ValueError, match="abc"):
        rows_from_csv(clash)


def test_blank_canonical_or_unknown_category_is_refused():
    for bad in (",x,Blood,X", "T,x,Bloods,T"):
        with pytest.raises(ValueError):
            rows_from_csv("canonical,aliases,category,print\n" + bad + "\n")


def test_the_draft_csv_builds(tmp_path):
    doc = build(DRAFT_CSV, tmp_path / "ix.json", "1.0.0", allow_draft=True)
    assert 140 <= len(doc["entries"]) <= 200 and doc["version"] == "1.0.0"


def test_key_keeps_letters_in_any_script():
    assert key("β-hCG") == "β hcg"
    assert key("Ü_Test & Co") == "ü test and co"


def test_not_reviewed_check_ignores_case():
    with pytest.raises(ValueError, match="NOT REVIEWED"):
        rows_from_csv("# not reviewed\ncanonical,aliases,category,print\nESR,esr,Blood,ESR\n")
