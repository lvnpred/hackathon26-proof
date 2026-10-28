from doctor_dictation.core import doctor_generic as G


def test_clean_generic_normalises_separators_and_keeps_the_doctors_case():
    assert G.clean_generic("Aceclofenac+Paracetamol") == "Aceclofenac + Paracetamol"
    assert G.clean_generic("  aceclofenac   plus  paracetamol ") == "aceclofenac + paracetamol"
    assert G.clean_generic("Paracetamol + paracetamol") == "Paracetamol"          # duplicate component, first spelling kept
    assert G.clean_generic("Calcium Carbonate + Vitamin D3") == "Calcium Carbonate + Vitamin D3"


def test_clean_generic_rejects_bad_text_with_a_message():
    cases = {"": G.MESSAGES["empty"], "Aceclofenac + ": G.MESSAGES["parts"], "+ +": G.MESSAGES["parts"],
             "x" * 161: G.MESSAGES["long"], "<script>": G.MESSAGES["chars"], "A1": G.MESSAGES["chars"],
             " + ".join(f"Drug{c}" for c in "abcdefg"): G.MESSAGES["many"]}
    for raw, msg in cases.items():
        assert G.generic_problem(raw) == msg and G.clean_generic(raw) == ""
    assert G.clean_generic(None) == "" and G.clean_generic(["x"]) == ""


def test_unknown_components_lists_what_no_lexicon_canonical_names(monkeypatch):
    monkeypatch.setattr("doctor_dictation.core.determinism.load_lexicon",
                        lambda: [{"canonical": "Aceclofenac"}, {"canonical": "Paracetamol"}, {"canonical": "Calcium + Vitamin D3"}])
    assert G.unknown_components("Aceclofenac + paracetamol") == []
    assert G.unknown_components("Aceclofenac + Serratiopeptidase") == ["Serratiopeptidase"]
    assert G.unknown_components("Vitamin D3") == []                                # a combination canonical is split too


def test_edge_cases_pin_current_behaviour():
    assert G.clean_generic("Plusfen") == "Plusfen"                                 # "plus" splits only as a whole word
    assert G.generic_problem("plus") == G.MESSAGES["parts"]
    assert G.clean_generic("Aceclofenac\t+\nParacetamol") == "Aceclofenac + Paracetamol"
    assert G.clean_generic("x" * 160) == "x" * 160
    assert G.generic_problem("x" * 161) == G.MESSAGES["long"]
    assert G.clean_generic("Vitamin B12") == "Vitamin B12"
    assert G.generic_problem("Café") == G.MESSAGES["chars"]                        # ASCII letters only


def test_a_component_may_start_with_a_number_and_hyphen():
    assert G.clean_generic("5-Fluorouracil") == "5-Fluorouracil"
    assert G.clean_generic("6-Mercaptopurine + Methotrexate") == "6-Mercaptopurine + Methotrexate"
    assert G.generic_problem("5-1") == G.MESSAGES["chars"]                         # still needs 3+ letters
    assert G.generic_problem("5Fluorouracil") == G.MESSAGES["chars"]
    assert G.generic_problem("\u0665-Fluorouracil") == G.MESSAGES["chars"]          # ASCII digits only (Arabic-Indic five refused)
