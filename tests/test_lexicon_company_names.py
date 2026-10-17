"""Plan I2-a fix round: the LIVE lexicon (no frozen fixture) holds no company name and no wrong single-generic link."""
import pytest

from doctor_dictation.core import determinism as D
from doctor_dictation.core.rowcheck import did_you_mean, ground_with_notes

COMPANIES = ["Cipla", "Sun", "Mankind", "Lupin", "Zydus", "Alkem", "Torrent", "Glenmark", "Cadila", "Abbott", "Pfizer",
             "Ipca", "Intas", "Macleods", "Micro Labs", "Biocon", "Dr Reddy", "Dr Reddys", "Dr. Reddy's"]


def _names():
    out = set()
    for e in D.load_lexicon():
        out.update(str(x).strip().lower() for x in [e["canonical"], *e.get("aliases", []), *e.get("brands", [])])
    return out


@pytest.mark.parametrize("name", ["Combiflam", "Cipla"])
def test_the_two_wrong_live_entries_are_not_recognised(name):
    status, match, _issue = D._ground_row(name, "", name.lower())
    assert (status, match) == ("unknown-medicine", "")
    row, _notes = ground_with_notes({"name": name}, name.lower(), name.lower())
    assert (row["status"], row["lexicon_match"], row["generic"]) == ("unknown-medicine", "", "")


def test_no_company_name_is_a_lexicon_name_alias_or_brand():
    names = _names()
    assert [c for c in COMPANIES if c.lower() in names] == []


def test_a_real_brand_beside_the_removed_ones_still_verifies():
    for name, generic in (("Brufen", "Ibuprofen"), ("Inderal", "Propranolol"), ("Crocin", "Paracetamol")):
        assert D._ground_row(name, "", name.lower())[:2] == ("verified", generic)


def test_the_live_lexicon_suggests_the_obvious_names_inline():
    assert did_you_mean("citrizene", "unknown-medicine") == {"did_you_mean": "Cetirizine", "did_you_mean_generic": "Cetirizine"}
    assert did_you_mean("croissin", "unknown-medicine") == {"did_you_mean": "Crocin", "did_you_mean_generic": "Paracetamol"}
