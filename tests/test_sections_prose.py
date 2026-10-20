"""Plan I2-b: Brief history first, both sections as dictated prose; the prompt, the rules path and the unheard check."""
import re
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.core import prose
from doctor_dictation.core.determinism import _FORMAT_CACHE, normalize_transcript
from doctor_dictation.core.fallback import fallback_format
from doctor_dictation.pdf import build_sheet_html
from template_fixtures import tclient  # noqa: F401
from test_determinism import _stub_llm

FRONT = Path(__file__).resolve().parents[1] / "frontend"
META = {"date": "2026-10-17", "opNo": "OP-1", "patientName": "Ravi"}


def test_the_sheet_prints_brief_history_first_then_diagnosis_as_paragraphs_with_the_review_date():
    s = {"complaints": ["C/o fever with chills for 3 days, associated body aches, no vomiting.", "No h/o similar episodes."],
         "diagnosis": ["Viral fever"], "review": "1 week", "review_date": "2026-10-24"}
    html = build_sheet_html(s, META)
    assert html.index("Chief Complaints &amp; Brief History") < html.index("Diagnosis / Clinical Impression")
    assert "Investigations" not in html
    assert ('<div class="prose"><p>C/o fever with chills for 3 days, associated body aches, no vomiting.</p>'
            "<p>No h/o similar episodes.</p></div>") in html and '<div class="prose"><p>Viral fever</p></div>' in html
    assert '<div class="sec-title">Review / Follow-up</div><div class="prose"><p>' + '1 week <span class="rev-date">(Sat 24 Oct 2026)</span></p></div>' in html
    empty = build_sheet_html({"review_date": "2026-10-24"}, META)
    assert '<p>—</p>' not in empty and "Review" not in empty and 'class="rev-date"' not in empty   # no review, no date
    old = build_sheet_html({"complaints": ["epigastric pain"], "diagnosis": ["Gastritis"]}, META)   # a document saved before I2-b
    assert old.index("epigastric pain") < old.index("Gastritis")
    assert '<div class="sec-title">Investigations Advised</div><ul><li>CBC</li></ul>' in build_sheet_html({"investigations": ["CBC"]}, META)
    assert "<p>&lt;b&gt;x&lt;/b&gt;</p>" in build_sheet_html({"complaints": ["<b>x</b>"]}, META)


def test_the_screen_shows_brief_history_first_and_both_as_prose():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert html.index('id="pCc"') < html.index('id="pDx"') < html.index('id="pIx"')
    assert 'id="pCc" class="editable-list prose-list"' in html and 'id="pDx" class="editable-list prose-list"' in html
    assert all(f'id="{i}"' in html for i in ("pRevDate", "pCcNote", "pDxNote")) and int(re.search(r"sections\.js\?v=(\d+)", html).group(1)) >= 2
    assert "ul.editable-list.prose-list { list-style:none; padding-left:3px; }" in (FRONT / "styles.css").read_text(encoding="utf-8")
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    assert 'base.complaints = readList("pCc")' in app and 'base.diagnosis = readList("pDx")' in app    # the stored shape is unchanged


EX = ("Patient Ravi Kumar 34 year old male. c/o fever with chills for three days, associated body aches, no vomiting. No h/o similar episodes. "
      "Diagnosis viral fever. Tab Crocin 650 mg thrice daily after food for 3 days. Advice drink plenty of water. Review after 1 week.")


def test_the_prompt_asks_for_dictated_prose_and_forbids_invented_history():
    from doctor_dictation.api.format import SYSTEM_PROMPT
    assert "never add a symptom, duration, negative finding, past history or diagnosis" in SYSTEM_PROMPT
    assert "1 to 3 short sentences" in SYSTEM_PROMPT and "at most 400 characters" in SYSTEM_PROMPT
    schema = SYSTEM_PROMPT[SYSTEM_PROMPT.index("{\n"):]
    assert schema.index('"complaints"') < schema.index('"diagnosis"') < schema.index('"investigations"')
    assert "exactly as dictated, including brand names" in SYSTEM_PROMPT                     # the I1-b rule stays


def test_the_rules_path_keeps_history_and_diagnosis_apart_and_adds_no_word():
    out = fallback_format(normalize_transcript(EX))
    assert out["complaints"] == ["C/o fever with chills for 3 days, associated body aches, no vomiting", "No h/o similar episodes"]
    assert out["diagnosis"] == ["Viral fever"] and out["review"] == "Review after 1 week"
    assert fallback_format(normalize_transcript("patient has fever since three days please have paracetamol twice a day"))["complaints"] == ["Patient has fever since 3 days"]
    gastritis = fallback_format(normalize_transcript("gastritis with vomiting tablet panto 40 mg once daily before food"))
    assert gastritis["diagnosis"] == [] and gastritis["complaints"] == ["Gastritis with vomiting"]   # a diagnosis only when dictated
    assert prose.unheard(out, EX, normalize_transcript(EX)) == []


def test_unheard_words_and_numbers_are_listed_never_rewritten():
    said = "c/o fever with chills for three days, associated body aches, no vomiting. diagnosis viral fever."
    form = {"complaints": ["C/o fever with chils for 3 days, no vomiting.", "Known diabetic for 5 years."],
            "diagnosis": ["Viral fever", "Acute febrile illness, likely viral"]}
    assert prose.unheard(form, said, normalize_transcript(said)) == [{"field": "complaints", "index": 1, "words": ["diabetic", "5"]},
                                                                     {"field": "diagnosis", "index": 1, "words": ["acute", "febrile", "illness", "likely"]}]
    assert form["complaints"][1] == "Known diabetic for 5 years."                             # information only
    long = {"complaints": ["word " * 120], "diagnosis": ["Viral fever"]}
    assert prose.cap_items(long) == ["complaints[0]: shortened from 600 to 400 characters"] and len(long["complaints"][0]) == 400


def test_format_returns_the_prose_check_caps_long_items_and_never_stores_the_check(monkeypatch):
    _FORMAT_CACHE.clear()
    _stub_llm(monkeypatch, [{"complaints": ["C/o fever with chills for 3 days.", "Known diabetic for 5 years."],
                             "diagnosis": ["C/o fever " + "with chills " * 60], "rx": []}])
    j = TestClient(M.app).post("/api/format", json={"transcript": "c/o fever with chills for three days"}).json()
    assert j["prose_check"] == [{"field": "complaints", "index": 1, "words": ["diabetic", "5"]}]
    assert len(j["structured"]["diagnosis"][0]) <= prose.ITEM_CHARS and j["structured"]["diagnosis"][0].endswith("…")
    assert any(w.startswith("diagnosis[0]: shortened from") for w in j["warnings"]) and "prose_check" not in j["structured"]


def test_speech_spellings_are_not_flagged_but_an_invented_phrase_is():
    said = "c/o fever with chills and vomiting for three days"
    ok = {"complaints": ["C/o fevers with chils and vomitting for 3 days."], "diagnosis": []}
    assert prose.unheard(ok, said, normalize_transcript(said)) == []
    bad = {"complaints": ["C/o fever with chills, vomiting for 3 days. Known hypertensive, on Telmisartan."], "diagnosis": []}
    flagged = prose.unheard(bad, said, normalize_transcript(said))
    assert flagged == [{"field": "complaints", "index": 0, "words": ["hypertensive", "telmisartan"]}]
    assert prose.unheard({"complaints": "not a list", "diagnosis": None}, said) == []


def test_cap_leaves_short_items_and_non_list_values_alone():
    form = {"complaints": ["C/o fever.", 5], "diagnosis": "x"}
    assert prose.cap_items(form) == [] and form == {"complaints": ["C/o fever.", "5"], "diagnosis": "x"}


def test_an_old_saved_document_reprints_in_the_new_order_with_no_date_and_a_new_one_with_its_date(tclient, monkeypatch):
    from doctor_dictation import db as dbmod
    seen = []

    def fake(structured, meta, out_path, layout=None):
        seen.append(build_sheet_html(structured, meta))
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)
    c = tclient
    save = {"structured": {"patientName": "Anita", "complaints": ["epigastric pain"], "diagnosis": ["Gastritis"], "review": "1 week", "rx": []},
            "confirmed_rows": []}
    doc = c.post("/api/v1/documents", json=save).json()["document_id"]
    assert 'class="rev-date"' in seen[-1]                                    # a document saved now carries its date
    conn = dbmod.get_conn()                                                  # make it a pre-I2-b document: lists of strings, no review_date
    conn.execute("UPDATE documents SET structured_json = ?, pdf_path = NULL WHERE id = ?",
                 ('{"patientName": "Anita", "complaints": ["epigastric pain"], "diagnosis": ["Gastritis"], "review": "1 week", "rx": []}', doc))
    conn.commit()
    conn.close()
    assert c.get(f"/api/v1/documents/{doc}/pdf").status_code == 200
    html = seen[-1]
    assert html.index("epigastric pain") < html.index("Gastritis") and '<div class="sec-title">Review / Follow-up</div><div class="prose"><p>1 week</p></div>' in html and 'class="rev-date"' not in html


def test_correct_checks_only_the_prose_lists_the_patch_replaced(monkeypatch):
    _stub_llm(monkeypatch, [{"complaints": ["Known diabetic for 5 years."]}])
    form = {"complaints": ["C/o fever."], "diagnosis": ["Acute febrile illness"], "rx": []}
    j = TestClient(M.app).post("/api/v1/correct", json={"transcript": "also fever with sweating", "current_form": form}).json()
    assert j["structured"]["complaints"] == ["Known diabetic for 5 years."]
    assert j["prose_check"] == [{"field": "complaints", "index": 0, "words": ["diabetic", "5"]}]     # the untouched diagnosis is not checked


def test_the_rules_path_cuts_history_at_a_drug_name_and_caps_long_prose_on_every_engine_path(monkeypatch):
    assert fallback_format(normalize_transcript("fever since three days paracetamol twice a day"))["complaints"] == ["Fever since 3 days"]
    long = "c/o " + "fever with chills " * 40
    _FORMAT_CACHE.clear()
    j = TestClient(M.app).post("/api/format", json={"transcript": long}).json()                 # no key: the rules path
    assert j["engine"].startswith("fallback-rules") and all(len(c) <= prose.ITEM_CHARS for c in j["structured"]["complaints"])
    assert any(w.startswith("complaints[0]: shortened from") for w in j["warnings"])
    _FORMAT_CACHE.clear()

    class Broken:                                                                              # an LLM that always fails: fallback-after-error
        name, model = "x", "y"

        async def complete_json(self, messages):
            raise RuntimeError("down")
    monkeypatch.setattr("doctor_dictation.api.format.make_llm", lambda settings: Broken())
    j = TestClient(M.app).post("/api/format", json={"transcript": long}).json()
    assert j["engine"].startswith("fallback-after-error") and all(len(c) <= prose.ITEM_CHARS for c in j["structured"]["complaints"])
    assert any(w.startswith("complaints[0]: shortened from") for w in j["warnings"])


def test_a_negation_the_doctor_never_said_is_flagged_and_a_dictated_one_is_not():
    said = "fever with chills for three days. vomiting"
    turned = {"complaints": ["Fever with chills for 3 days, no vomiting"], "diagnosis": []}
    assert prose.unheard(turned, said, normalize_transcript(said)) == [{"field": "complaints", "index": 0, "words": ["no"]}]
    for ok_said, line in [("no vomiting", "No vomiting"), ("denies vomiting", "No vomiting"), ("fever, nil vomiting", "Fever, without vomiting"),
                          ("no fever no vomiting", "No fever, no vomiting")]:
        assert prose.unheard({"complaints": [line], "diagnosis": []}, ok_said) == [], ok_said
    two = {"complaints": ["No fever, no vomiting"], "diagnosis": []}
    assert prose.unheard(two, "no fever. vomiting") == [{"field": "complaints", "index": 0, "words": ["no"]}]
    assert prose.unheard({"complaints": ["Not smoker never"], "diagnosis": []}, "smoker") == [{"field": "complaints", "index": 0, "words": ["not", "never"]}]
