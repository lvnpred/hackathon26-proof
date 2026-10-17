"""Plan I2-b fix round: the rules-only path (no LLM) restates only what was dictated. Table of review probes."""
import json
import re
from pathlib import Path

import pytest

from doctor_dictation.core.determinism import normalize_transcript
from doctor_dictation.core.fallback import fallback_format

DEMO = next(c["transcript"] for c in json.loads((Path(__file__).parent / "golden.json").read_text()) if c["id"] == "ureteric-seeded")

# (id, dictation, history, diagnosis, advice, investigations, review)
PROBES = [
    ("owner example", "Patient Ravi Kumar 34 year old male. c/o fever with chills for three days, associated body aches, no vomiting. No h/o similar episodes. "
     "Diagnosis viral fever. Tab Crocin 650 mg thrice daily after food for 3 days. Advice drink plenty of water. Review after 1 week.",
     ["C/o fever with chills for 3 days, associated body aches, no vomiting", "No h/o similar episodes"], ["Viral fever"], ["Drink plenty of water"], [], "Review after 1 week"),
    ("short form pt", "pt has fever since 3d, have paracetamol", ["Pt has fever since 3d"], [], [], [], ""),
    ("gastritis no dx", "gastritis with vomiting tablet panto 40 mg once daily before food", ["Gastritis with vomiting"], [], [], [], ""),
    ("drug list only", "tablet Paracetamol 650 mg twice daily after food for 3 days, tablet Pantoprazole 40 mg once daily before food", [], [], [], [], ""),
    ("allergies then c/o", "no known allergies. c/o headache since two days", ["No known allergies", "C/o headache since 2 days"], [], [], [], ""),
    ("diabetes years", "h/o diabetes 5 yrs c/o polyuria Dx T2DM", ["H/o diabetes 5 yrs c/o polyuria"], ["T2DM"], [], [], ""),
    ("name age sex first", "Mrs Sunita 45 yrs F knee pain 2 mo Dx OA", ["Knee pain 2 mo"], ["OA"], [], [], ""),
    ("hinglish", "bukhar hai three days se. Dx viral fever", ["Bukhar hai 3 days se"], ["Viral fever"], [], [], ""),
    ("dx before complaints", "Diagnosis acute gastritis. c/o epigastric pain since 2 days", ["C/o epigastric pain since 2 days"], ["Acute gastritis"], [], [], ""),
    ("symptoms only", "fever cough cold no breathlessness", ["Fever cough cold no breathlessness"], [], [], [], ""),
    ("empty", "", [], [], [], [], ""),
    ("name age sex known case", "patient name Anil age 60 male HTN known case", ["HTN known case"], [], [], [], ""),
    ("chest pain dx", "chest pain Dx ACS", ["Chest pain"], ["ACS"], [], [], ""),
    ("45M impression", "Rahul 45M cough 1 week impression URTI", ["Cough 1 week"], ["URTI"], [], [], ""),
    ("negations are not diagnoses", "no vomiting no fever. c/o abdominal pain", ["No vomiting no fever", "C/o abdominal pain"], [], [], [], ""),
    ("dengue plan", "provisional Dx dengue, c/o high grade fever 4 days, body aches. advise CBC and NS1 antigen",
     ["C/o high grade fever 4 days, body aches"], ["Dengue"], [], ["CBC", "NS1 antigen"], ""),
    ("uti", "28 year old woman burning micturition since two days. Diagnosis UTI.", ["Burning micturition since 2 days"], ["UTI"], [], [], ""),
    ("two diagnosis sentences", "c/o fever. Diagnosis viral fever. Diagnosis dengue suspected", ["C/o fever"], ["Viral fever", "Dengue suspected"], [], [], ""),
    ("old case asthma", "old case of asthma, c/o wheeze since 2 days. diagnosis acute exacerbation of asthma",
     ["Old case of asthma, c/o wheeze since 2 days"], ["Acute exacerbation of asthma"], [], [], ""),
    ("two drugs only", "tab Pan 40 mg once daily, tab Dolo 650 mg SOS", [], [], [], [], ""),
    ("sore throat gargle", "sore throat since 3 days. Diagnosis pharyngitis. Gargle with warm salt water", ["Sore throat since 3 days"], ["Pharyngitis"],
     ["Gargle with warm salt water"], [], ""),
    ("boy", "7 yr boy fever no cough", ["Fever no cough"], [], [], [], ""),
    ("dx and review", "Diagnosis hypertension. Review after 1 month", [], ["Hypertension"], [], [], "Review after 1 month"),
    ("admit and surgery", "pain abdomen K/c/o DM 10 yrs Dx appendicitis. Admit and surgery", ["Pain abdomen K/c/o DM 10 yrs"], ["Appendicitis"], ["Admit and surgery"], [], ""),
    ("malaria suspected", "fever chills vomiting Dx malaria suspected", ["Fever chills vomiting"], ["Malaria suspected"], [], [], ""),
    # years inside the history are never identity (I1)
    ("back pain 3 years", "c/o back pain since 3 years", ["C/o back pain since 3 years"], [], [], [], ""),
    ("hypertension 5 years", "known case of hypertension for 5 years", ["Known case of hypertension for 5 years"], [], [], [], ""),
    ("kco dm", "K/c/o DM since 10 years", ["K/c/o DM since 10 years"], [], [], [], ""),
    # clause classes: dose lines, instruction fragments, inheritance after a marker
    ("clinical words before an age phrase", "knee pain 45 year old male", ["Knee pain"], [], [], [], ""),
    ("tablet without strength", "fever 2 days. tablet Pantoprazole once daily", ["Fever 2 days"], [], [], [], ""),
    ("dose line of an unknown medicine", "c/o cough, Zyxomab 5 mg nightly", ["C/o cough"], [], [], [], ""),
    ("history after a diagnosis", "Dx viral fever, fever since 3 days", ["Fever since 3 days"], ["Viral fever"], [], [], ""),
    ("diagnosis list", "Dx T2DM, hypertension", [], ["T2DM, hypertension"], [], [], ""),
    ("advice list", "advise rest, fluids", [], [], ["Rest, fluids"], [], ""),
    # identity clauses leave, the clinical remainder stays (I2)
    ("aged male comma", "Patient aged 45, male, c/o cough", ["C/o cough"], [], [], [], ""),
    ("name only clause", "name Anil. c/o fever since 2 days", ["C/o fever since 2 days"], [], [], [], ""),
]
IDS = [p[0] for p in PROBES]


def _run(text):
    return fallback_format(normalize_transcript(text))


@pytest.mark.parametrize("pid,text,hist,dx,adv,ix,rev", PROBES, ids=IDS)
def test_the_rules_path_sections_each_probe_from_what_was_dictated(pid, text, hist, dx, adv, ix, rev):
    out = _run(text)
    assert (out["complaints"], out["diagnosis"], out["advice"], out["investigations"], out["review"]) == (hist, dx, adv, ix, rev), pid


TOKEN = re.compile(r"[a-z0-9]+")


@pytest.mark.parametrize("pid,text,hist,dx,adv,ix,rev", PROBES, ids=IDS)
def test_every_word_of_history_diagnosis_advice_and_tests_was_dictated(pid, text, hist, dx, adv, ix, rev):
    """Nothing is invented. 'Dictated' means raw wording or the deterministic normalisation the code applies first
    (number words to digits such as three -> 3, lexicon spellings)."""
    out = _run(text)
    said = set(TOKEN.findall(text.lower())) | set(TOKEN.findall(normalize_transcript(text).lower()))
    for field in ("complaints", "diagnosis", "advice", "investigations"):
        for item in out[field]:
            assert set(TOKEN.findall(item.lower())) <= said, (pid, field, item)


def test_the_seeded_demo_note_applies_only_to_the_whole_demo_dictation():
    out = _run(DEMO)
    assert any("ureteric" in d.lower() for d in out["diagnosis"]) and out["review"].startswith("In 2 weeks")
    assert {r["name"] for r in out["rx"]} >= {"Tamsulosin", "Deflazacort"}
    for part in ["right flank pain and burning micturition since two days", "burning micturition since 2 days", "ureteric calculus 5 mm",
                 "flank pain since 3 days. Diagnosis renal colic", "right flank pain, 5 mm lower ureteric calculus, tablet Tamsulosin 0.4 mg once daily",
                 "ureteric calculus 5 mm. tablet Tamsulosin 0.4 mg once daily, tablet Deflazacort 6 mg twice daily"]:   # four of the five phrases
        o = _run(part)
        assert (o["review"], o["investigations"], o["advice"]) == ("", [], []), part
        assert not any(r["name"] in ("Deflazacort", "Potassium Magnesium Citrate") and r["name"].lower() not in part.lower() for r in o["rx"]), part
        assert not any("5 mm" in d for d in o["diagnosis"]) or "5 mm" in part, part


def test_no_keyword_ever_becomes_a_diagnosis():
    for text in ["fever cough cold", "pt has fever since 3d", "no vomiting no fever. c/o abdominal pain", "headache and migraine, hypertension, diabetes"]:
        assert _run(text)["diagnosis"] == [], text
    assert _run("old case of asthma. diagnosis acute exacerbation of asthma")["complaints"] == ["Old case of asthma"]


# ---- fix batch 2: a negated review line keeps its negation (I3) ----
NEG_REVIEW = [
    ("no follow up needed", "No follow up needed"), ("no review needed", "No review needed"), ("follow up not needed", "Follow up not needed"),
    ("review not required", "Review not required"), ("no need to review", "No need to review"), ("without follow up", "Without follow up"),
    ("Diagnosis viral fever. Review after one week.", "Review after 1 week"),
    ("c/o fever since 2 days, no follow up needed", "No follow up needed"),
]


@pytest.mark.parametrize("text,review", NEG_REVIEW)
def test_a_negated_review_line_keeps_the_doctors_negation_and_leaves_no_stray_word(text, review):
    out = _run(text)
    assert out["review"] == review, text
    assert not any(c.strip(" ,.").lower() in ("no", "not", "nil", "without", "no need to") for c in out["complaints"]), out["complaints"]


def test_a_negated_review_line_gets_no_date():
    from datetime import date
    from doctor_dictation.core import followup
    for text in ("no follow up needed", "no review needed", "no need to review", "review not required"):
        assert followup.review_date(_run(text)["review"], date(2026, 10, 17)) == "", text


def test_the_named_patient_leaves_the_history_and_the_name_stops_at_the_complaint():
    out = _run("named Suresh Rao complaining of chest pain")
    assert out["patientName"] == "Suresh Rao" and out["complaints"] == ["Complaining of chest pain"]
    out = _run("patient named Anil Kumar suffering from cough since 2 days")
    assert out["patientName"] == "Anil Kumar" and out["complaints"] == ["Suffering from cough since 2 days"]
    assert _run("name is Mina having fever 3 days")["patientName"] == "Mina"
