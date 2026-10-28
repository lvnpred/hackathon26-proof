"""Findings section (owner, 2026-10-20): examination and report findings in one list, after Investigations on the screen and the
printout. Offline."""
from pathlib import Path

from doctor_dictation.api.format import SYSTEM_PROMPT
from doctor_dictation.core.correction import merge_form
from doctor_dictation.core.determinism import validate_structured
from doctor_dictation.core.fallback import fallback_format
from doctor_dictation.core.prose import unheard
from doctor_dictation.pdf import build_sheet_html

FRONT = Path(__file__).resolve().parents[1] / "frontend"
FX = ["Pedal oedema present.", "S. creatinine 2.1 mg/dL."]


def test_validation_keeps_the_findings_list():
    out, _ = validate_structured({"findings": FX + ["  "]}, "", vitals_typed=True)
    assert out["findings"] == FX


def test_findings_print_after_investigations_and_before_rx():
    html = build_sheet_html({"investigations": ["RFT"], "findings": FX, "rx": [{"name": "Crocin"}]}, {"date": "2026-10-20"})
    assert html.index("Investigations Advised") < html.index(">Findings<") < html.index("Rx (MEDICATIONS)")
    assert "S. creatinine 2.1 mg/dL." in html


def test_no_findings_prints_no_heading():
    assert ">Findings<" not in build_sheet_html({"findings": []}, {"date": "2026-10-20"})


def test_the_prompt_asks_for_findings_apart_from_tests_advised():
    assert '"findings": [' in SYSTEM_PROMPT and "never in findings" in SYSTEM_PROMPT


def test_a_correction_adds_to_the_findings_list():
    assert merge_form({"findings": ["Chest clear."]}, {"findings": FX})["findings"] == ["Chest clear."] + FX
    assert merge_form({"findings": ["Chest clear."]}, {})["findings"] == ["Chest clear."]


def test_an_unheard_finding_is_flagged():
    assert unheard({"findings": ["Creatinine 3.4"]}, "creatinine two point one") == [{"field": "findings", "index": 0, "words": ["3.4"]}]


def test_the_rules_only_fallback_has_an_empty_findings_list():
    assert fallback_format("tab crocin 500 mg sos")["findings"] == []


def test_the_screen_has_the_section_after_investigations():
    html, app = (FRONT / "index.html").read_text(encoding="utf-8"), (FRONT / "app.js").read_text(encoding="utf-8")
    assert html.index('id="pIx"') < html.index(">FINDINGS<") < html.index('id="pFx"') < html.index('id="pRx"')
    assert 'base.findings = readList("pFx");' in app and 'renderList($("pFx"), s.findings);' in app
