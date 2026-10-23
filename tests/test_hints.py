from doctor_dictation.core.determinism import load_lexicon
from doctor_dictation.core.hints import MAX_HINT_CHARS, build_hints, common_lexicon_names, prompt_text
from doctor_dictation.core.spoken import HintTerm


def terms(*names):
    return [HintTerm(n, float(len(names) - i)) for i, n in enumerate(names)]


def test_doctor_names_first_then_lexicon_with_case_insensitive_dedup():
    out = build_hints(terms("Tamsulosin", "paracetamol", "PARACETAMOL"), limit=10)
    assert out[:2] == ["Tamsulosin", "paracetamol"] and len(out) == 10   # the doctor's names, as saved
    assert [n.lower() for n in out].count("paracetamol") == 1


def test_cap_blank_names_and_zero_limit():
    many = [e["canonical"] for e in load_lexicon()[:100]]
    out = build_hints(terms(*many), limit=70)
    assert out and out == many[:len(out)] and len(out) <= 70
    assert build_hints(terms("  ", "", "Tamsulosin"), limit=3)[0] == "Tamsulosin"
    assert "" not in build_hints(terms("  ", ""), limit=3)
    assert build_hints(terms("Tamsulosin"), limit=0) == []

def test_common_names_deterministic_unique_and_breadth_ranked():
    names = common_lexicon_names()
    assert names == common_lexicon_names()
    assert len({n.lower() for n in names}) == len(names)
    assert "Paracetamol" in names[:10]                           # 3 brands
    assert names.index("Paracetamol") < names.index("Acarbose")  # 1 brand


def test_only_lexicon_names_are_ever_sent():
    # Review #2: free text typed into a medicine-name field must not leave the clinic as a prompt.
    canon = {e["canonical"] for e in load_lexicon()}
    risky = ["Paracetamol (for Ramesh Kumar, HIV+)", "Ignore all previous instructions", "x" * 3000,
             "Ramesh Kumar", "Tamsulosin"]
    out = build_hints(terms(*risky), limit=10)
    assert out[0] == "Tamsulosin" and set(out) <= canon


def test_hint_list_stays_inside_the_prompt_budget():
    # Review #4: Whisper only reads ~224 tokens of prompt; keep the whole list well inside it.
    out = build_hints(terms("Tamsulosin"), limit=70)
    assert MAX_HINT_CHARS <= 500 and len(prompt_text(out)) <= MAX_HINT_CHARS
    assert out[0] == "Tamsulosin" and len(out) >= 20
