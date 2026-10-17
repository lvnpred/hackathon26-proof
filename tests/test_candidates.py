"""ACC3: sound-alike candidates (offline; the LLM is always stubbed)."""
import re

from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.core.candidates import MIN_SCORE, phonetic_key, suggest_candidates
from doctor_dictation.core.determinism import (
    _FORMAT_CACHE,
    RX_UNKNOWN_MEDICINE,
    RX_VERIFIED,
    UNKNOWN_MEDICINE_TEXT,
    build_repair_message,
    ground_rx,
    load_lexicon,
    loop_should_continue,
)
from test_determinism import _rx, _stub_llm

TRANSCRIPT = "fever, tablet cephixime 200 mg twice daily after food"


def test_key_basic_rules():
    assert phonetic_key("Knee") == "n"            # leading kn drops the k
    assert phonetic_key("pneumonia") == "nmn"      # leading pn drops the p
    assert phonetic_key("wrist") == "rst"          # leading wr drops the w
    assert phonetic_key("phenytoin") == phonetic_key("fenytoin") == "fntn"  # ph = f
    assert phonetic_key("xanax") == "snks"         # leading x = s, inner x = ks
    assert phonetic_key("chlor") == phonetic_key("clor") == "klr"  # ch = k, hard c = k
    assert phonetic_key("cefixime") == phonetic_key("sefixime") == "sfksm"  # soft c = s
    assert phonetic_key("cough") == "k"            # gh is silent


def test_key_classes_and_cleanup():
    assert phonetic_key("pill") == phonetic_key("bill") == "pl"      # b/p merge, ll collapses
    assert phonetic_key("dose") == phonetic_key("toes") == "ts"      # d/t merge, vowels dropped
    assert phonetic_key("Ibuprofen") == phonetic_key("aibuprofen") == "aprfn"  # first vowel = a
    assert phonetic_key("AZITHRAL") == phonetic_key("azithral")      # case ignored
    assert phonetic_key("") == "" and phonetic_key("12 -") == ""     # nothing to key


def test_key_equal_for_real_drug_mishearings():
    assert phonetic_key("Cetirizine") == phonetic_key("cetrizin") == "strsn"
    assert phonetic_key("Azithral") == phonetic_key("azithro all") == "astrl"
    assert phonetic_key("Metformin") == phonetic_key("metforman") == "mtfrmn"


def test_suggest_real_entries_top1():
    # Expected canonicals were read from the lexicon; none is spelled as listed.
    cases = {
        "azithro all": "Azithromycin", "pantaprazole": "Pantoprazole",
        "amoxycilin": "Amoxicillin", "glimiperide": "Glimepiride",
        "cephixime": "Cefixime", "siprofloxacin": "Ciprofloxacin",
        "montelucast": "Montelukast", "phentanyl": "Fentanyl",
    }
    for heard, canon in cases.items():
        got = suggest_candidates(heard)
        assert got and got[0] == canon, (heard, got)


def test_suggest_matches_brand_spelling_to_generic():
    # Azithral and Zithromax are brands of Azithromycin: the candidate is the generic.
    assert suggest_candidates("azithral")[0] == suggest_candidates("Zithromax")[0] == "Azithromycin"


def test_suggest_k_and_dedupe():
    three = suggest_candidates("tel misartan", k=3)
    assert three[0] == "Telmisartan" and len(three) == len(set(three)) <= 3
    assert suggest_candidates("tel misartan", k=1) == ["Telmisartan"]
    assert suggest_candidates("tel misartan", k=0) == []
    assert len(suggest_candidates("doxicyclin", k=10)) <= 10
    assert suggest_candidates("metformin")[0] == "Metformin"  # exact name ranks first


JUNK = ["", "ab", "12345", "xyzzy", "qqqq", "asdfgh", "kkkkk", "wxyz",
        "fever", "hello", "medalpha", "medbeta", "the doctor"]


def test_suggest_garbage_returns_empty(frozen_lexicon):
    assert 0.5 < MIN_SCORE < 1.0
    for junk in JUNK:
        assert suggest_candidates(junk) == [], junk


def test_suggest_garbage_returns_empty_on_the_live_lexicon():
    """Import gate (plan I1-g simple, Task 5): the SAME junk list on the LIVE drugs.json, no frozen copy.
    Run after a real import; refuse to commit the import if it fails."""
    for junk in JUNK:
        assert suggest_candidates(junk) == [], junk


def test_suggest_deterministic_5x():
    for heard in ["azithro all", "doxicyclin", "lazartan", "medalpha"]:
        runs = [suggest_candidates(heard) for _ in range(5)]
        assert all(r == runs[0] for r in runs), heard


def test_suggest_only_returns_lexicon_canonicals():
    canon = {e["canonical"] for e in load_lexicon()}
    for heard in ["azeethromycin", "lazartan", "cetrizine", "doxicyclin", "ramipral"]:
        assert set(suggest_candidates(heard)) <= canon


def _issues(*names):
    return ground_rx([{"name": n, "strength": ""} for n in names], TRANSCRIPT)[1]


def test_repair_message_candidates_only_for_unknown_rows():
    # Cephixime is unknown; Paracetamol is a real medicine absent from the
    # transcript (unverified-name), so it must get no candidate line.
    issues = _issues("Cephixime", "Paracetamol")
    msg = build_repair_message(issues, TRANSCRIPT)
    lines = msg.splitlines()
    i = next(n for n, ln in enumerate(lines) if "'Cephixime'" in ln)
    assert lines[i + 1].strip() == "Sound-alike names in the medicine list: Cefixime"
    j = next(n for n, ln in enumerate(lines) if "'Paracetamol'" in ln)
    assert not lines[j + 1].lstrip().startswith("Sound-alike")
    assert msg.count("Sound-alike names") == 1
    assert "pick EXACTLY ONE" in msg and "keep your spelling" in msg


def test_repair_message_has_no_candidate_text_without_candidates():
    for names in (["Medalpha"], ["Paracetamol"]):   # garbage name; non-unknown row
        msg = build_repair_message(_issues(*names), TRANSCRIPT)
        assert "Sound-alike" not in msg and "pick EXACTLY ONE" not in msg
        assert "FULL corrected JSON" in msg


def test_unknown_issue_text_is_shared_constant():
    issue = _issues("Cephixime")[0]
    assert re.match(r"^rx\[0\] 'Cephixime': " + re.escape(UNKNOWN_MEDICINE_TEXT), issue)


def test_loop_counting_unaffected_by_candidates():
    issues = _issues("Cephixime", "Medalpha", "Paracetamol")
    before = list(issues)
    build_repair_message(issues, TRANSCRIPT)
    assert issues == before and len(issues) == 3   # n_open = len(issues) is untouched
    assert loop_should_continue(3, 2, 1) is True   # guard unchanged
    assert loop_should_continue(1, 1, 2) is False


def _format(monkeypatch, drafts):
    _FORMAT_CACHE.clear()   # all three e2e tests share one transcript
    calls = _stub_llm(monkeypatch, drafts)
    r = TestClient(M.app).post("/api/format", json={"transcript": TRANSCRIPT})
    assert r.status_code == 200, r.text
    return calls, r.json()


def test_e2e_llm_picks_candidate_and_row_verifies(monkeypatch):
    bad = {"rx": [_rx("Cephixime", strength="200 mg")]}
    fixed = {"rx": [_rx("Cefixime", strength="200 mg")]}
    calls, j = _format(monkeypatch, [bad, fixed])
    assert calls["n"] == 2
    repair = calls["messages"][1][-1]["content"]
    assert "Sound-alike names in the medicine list: Cefixime" in repair
    row = j["structured"]["rx"][0]
    # "cephixime" was auto-corrected to Cefixime, which has look-alikes: one tap, not a silent tick
    assert (row["name"], row["status"]) == ("Cefixime", "lookalike-check")
    assert (row["heard"], row["lookalike"]) == ("cephixime", "Cefotaxime")
    assert j["grounding"]["open_issues"] == ["rx[0] 'Cefixime': lookalike-check"]
    assert j["grounding"]["rounds"] == 1


def test_e2e_ignored_candidate_leaves_row_flagged(monkeypatch):
    same = {"rx": [_rx("Cephixime", strength="200 mg")]}
    calls, j = _format(monkeypatch, [same, same])
    assert calls["n"] == 2          # no strict progress -> loop stops after one repair
    row = j["structured"]["rx"][0]
    assert row["name"] == "Cephixime"          # the system never renames it
    assert row["status"] == RX_UNKNOWN_MEDICINE and row["lexicon_match"] == ""
    assert "[unverified" in row["instructions"]
    assert len(j["grounding"]["open_issues"]) == 1


def test_e2e_garbage_name_gets_plain_repair_message(monkeypatch):
    bad = {"rx": [_rx("Medalpha")]}
    calls, j = _format(monkeypatch, [bad, bad])
    assert "Sound-alike" not in calls["messages"][1][-1]["content"]
    assert j["structured"]["rx"][0]["status"] == RX_UNKNOWN_MEDICINE


def test_very_long_names_get_no_candidates_and_cost_nothing():
    # Review #3: an LLM glitch must not turn into seconds of difflib work.
    import time
    t0 = time.monotonic()
    assert suggest_candidates("x" * 5000) == [] and suggest_candidates("azithro" * 50) == []
    assert time.monotonic() - t0 < 0.5


def test_repair_message_looks_up_candidates_for_at_most_a_few_rows(monkeypatch):
    import doctor_dictation.core.repair as D
    calls = []
    monkeypatch.setattr(D, "suggest_candidates", lambda name: calls.append(name) or [])
    issues = [f"rx[{i}] 'Medalpha{i}': {UNKNOWN_MEDICINE_TEXT} (444 entries)" for i in range(30)]
    msg = build_repair_message(issues, TRANSCRIPT)
    assert len(calls) <= 5 and msg.count("- rx[") == 30   # every row is still named
