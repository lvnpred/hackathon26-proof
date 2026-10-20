"""Fix round 1 of plan PQ-h Task 7: an investigation's own name rule in ``overlay.validate_data`` (medicines keep
``formulary.clean_name``), and add twins compared by the investigation list's key. Pure."""
import pytest

from doctor_dictation.core import overlay

RFT = {"canonical": "Renal Function Test", "aliases": ["rft"], "category": "Blood", "print": "RFT"}


@pytest.mark.parametrize("name", ["CA 125", "hb", "b12", "24 hr urine protein", "urine c&s", "HbA1c", "2D Echo",
                                  "CA 19-9", "USG KUB with Post Void Residue"])
def test_test_names_the_catalogue_uses_are_accepted(name):
    assert overlay.validate_data("investigation", "add", {"name": name, "aliases": [name]}) == {
        "name": name, "aliases": [name]}


def test_a_test_name_keeps_its_case_and_collapses_spaces():
    assert overlay.validate_data("investigation", "add", {"name": "  Urine   C&S "})["name"] == "Urine C&S"


@pytest.mark.parametrize("name", ["<b>", '"', ";", "=", "`", "javascript:", "12", "--", "a", "Urine C&S <b>",
                                  "x" * 61, "one two three four five six seven eight nine", "", "  ", None, 12])
def test_markup_punctuation_numbers_only_and_long_names_are_refused(name):
    with pytest.raises(ValueError, match="test name"):
        overlay.validate_data("investigation", "add", {"name": name})
    with pytest.raises(ValueError, match="test name"):
        overlay.validate_data("investigation", "edit", {"aliases": [name]})


@pytest.mark.parametrize("name", ["hb", "CA 125", "urine c&s"])
def test_medicines_keep_the_old_rule(name):
    with pytest.raises(ValueError, match="medicine or test name"):
        overlay.validate_data("medicine", "add", {"name": name, "generic": "Paracetamol"})


def test_c_and_s_spellings_are_twins():
    mine = {"entry_key": "urine c&s", "action": "add", "data": {"name": "Urine C&S", "aliases": []}}
    other = {"entry_key": "urine c and s", "action": "add", "data": {"name": "Urine C and S", "aliases": []}}
    assert overlay.conflicts("investigation", [RFT], [mine], other) == [
        "'Urine C and S' is already on your list as Urine C&S: edit it"]
    assert overlay.conflicts("investigation", [RFT], [], other) == []


USG = {"canonical": "Ultrasound Kidneys Ureters and Bladder", "aliases": ["usg kub"], "category": "Imaging", "print": "USG KUB"}


@pytest.mark.parametrize("name", ["USG. KUB", "USG/KUB", "Usg-Kub", "USGKUB", "R.F.T", "K F T", "Renal-Function Test"])
def test_an_add_spelling_any_shipped_name_is_already_on_the_list(name):
    """Final review M1: every shipped canonical, print form and alias, by investigation key and spaceless key."""
    row = {"entry_key": overlay.entry_key_of({"canonical": name}), "action": "add", "data": {"name": name, "aliases": []}}
    assert overlay.conflicts("investigation", [{**RFT, "aliases": ["rft", "kft"]}, USG], [], row) == [
        f"'{name}' is already on the list — edit it instead"]


def test_a_new_test_name_is_still_accepted():
    row = {"entry_key": "kidney panel", "action": "add", "data": {"name": "Kidney Panel", "aliases": ["kidney profile"]}}
    assert overlay.conflicts("investigation", [RFT, USG], [], row) == []


@pytest.mark.parametrize("name", ["K.F.T", "R F T", "r.f.t.", "kft"])
def test_a_spelled_hidden_test_name_is_refused(name):                                      # final review I2
    hide = {"entry_key": "renal function test", "action": "hide", "data": {}, "base_sha": ""}
    shipped = [{**RFT, "aliases": ["rft", "kft"]}, USG]
    add = {"entry_key": "kidney panel", "action": "add", "data": {"name": "Kidney Panel", "aliases": [name]}}
    assert overlay.conflicts("investigation", shipped, [hide], add) == [f"{name} is hidden on your list: Reset it first"]
    assert overlay.hidden_test_hit([name], overlay.effective_and_blocked("investigation", shipped, [hide])[2]) == name


WRAPPED = ["Repeat KFT", "Repeat R F T", "RFT test", "Rft Profile", "k.f.t. test", "Follow up RFT levels"]


@pytest.mark.parametrize("name", WRAPPED)
def test_a_hidden_test_inside_a_longer_name_is_refused(name):                             # final re-review I2
    hide = {"entry_key": "renal function test", "action": "hide", "data": {}, "base_sha": ""}
    shipped = [{**RFT, "aliases": ["rft", "kft"]}, USG]
    add = {"entry_key": "kidney panel", "action": "add", "data": {"name": "Kidney Panel", "aliases": [name]}}
    assert overlay.conflicts("investigation", shipped, [hide], add) == [f"{name} is hidden on your list: Reset it first"]
    own = {"entry_key": overlay.entry_key_of({"canonical": name}), "action": "add", "data": {"name": name, "aliases": []}}
    assert overlay.conflicts("investigation", shipped, [hide], own) == [f"{name} is hidden on your list: Reset it first"]


@pytest.mark.parametrize("name", ["Kidney Panel", "Repeat Test", "Thyroid Profile", "KFTX test"])
def test_a_wrapped_name_that_hides_nothing_is_accepted(name):
    hide = {"entry_key": "renal function test", "action": "hide", "data": {}, "base_sha": ""}
    shipped = [{**RFT, "aliases": ["rft", "kft"]}, USG]
    add = {"entry_key": overlay.entry_key_of({"canonical": name}), "action": "add", "data": {"name": name, "aliases": []}}
    assert overlay.conflicts("investigation", shipped, [hide], add) == []
