"""Plan C1 Task 4: the PDF lays sections out from the list; the default list prints byte-identical to before."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from doctor_dictation.api.app import create_app
from doctor_dictation.core import determinism as D
from doctor_dictation.core.sections import BUILT_INS, coerce_extra, load_file, parse
from doctor_dictation.pdf import build_sheet_html

FULL = {"patientName": "Anita Rao", "ageSex": "34 F", "complaints": ["Fever for two days", "Body ache"],
        "diagnosis": ["Viral fever"], "investigations": [{"text": "CBC"}, {"text": "CRP"}], "findings": ["Throat congested"],
        "rx": [{"name": "Paracetamol", "form": "Tab", "strength": "500 mg", "dose": "1-0-1", "timing": "after food",
                "duration": "3 days", "instructions": "With water"},
               {"name": "Cetirizine", "form": "Tab", "strength": "10 mg", "dose": "0-0-1", "duration": "5 days"}],
        "advice": ["Rest"], "review": "After 1 week", "review_date": "2026-11-02", "vitals": {"bp": "120/80"}}
META = {"date": "26 Oct 2026", "opNo": "OP 9"}
GOLDEN = (Path(__file__).parent / "data" / "sheet_seven_sections.html")


def _list(on_advice=True, extra=(), heads=None):
    heads = heads or {}
    rows = [{"key": b.key, "heading": heads.get(b.key, b.heading), "cue": "", "kind": b.kind, "order": b.order,
             "on": on_advice or b.key != "advice"} for b in BUILT_INS]
    rows += [{"key": k, "heading": h, "cue": "", "kind": "text", "order": o, "on": True} for k, h, o in extra]
    return parse({"version": 1, "sections": rows})


FH = _list(False, [("family_history", "Family History", 25), ("notes", "Notes <b> & Co", 95)])


def test_the_default_list_prints_byte_identical_to_before():
    golden = GOLDEN.read_text(encoding="utf-8")
    assert build_sheet_html(FULL, META) == golden == build_sheet_html(FULL, {**META, "sections": BUILT_INS})
    assert build_sheet_html(FULL, {**META, "sections": load_file()}) == golden


def test_added_off_and_deleted_sections_print_by_the_list():
    form = {**FULL, "advice": [], "extra": {"family_history": {"heading": "Family History", "lines": ["Father diabetic"]},
                                           "notes": {"heading": "Notes <b> & Co", "lines": ["x"]},
                                           "old_sec": {"heading": "Old Sec", "lines": ["kept"]}}}
    html = build_sheet_html(form, {**META, "sections": FH})
    fh = '<div class="sec-title">Family History</div><div class="prose"><p>Father diabetic</p></div>'
    assert fh in html and html.index("Diagnosis / Clinical") < html.index(fh) < html.index("Investigations Advised")
    assert "Notes &lt;b&gt; &amp; Co" in html and "<b>" not in html
    assert "Dietary" not in html                                    # advice is off and empty
    assert html.index("Notes &lt;b&gt;") < html.index("Old Sec") and html.index("Review / Follow-up") < html.index("Old Sec")
    held = build_sheet_html({**FULL, "advice": ["Rest"]}, {**META, "sections": FH})
    assert "Dietary &amp; General Advice" in held and "<li>Rest</li>" in held     # off, but the document holds data


def test_a_renamed_built_in_prints_its_new_heading_escaped():
    secs = _list(heads={"findings": "O/E & Findings", "rx": "Medicines <i>"})
    html = build_sheet_html(FULL, {**META, "sections": secs})
    assert '<div class="sec-title">O/E &amp; Findings</div>' in html
    assert '<div class="sec-title">Medicines &lt;i&gt;</div><table class="rx">' in html


def test_save_renders_with_the_clinics_list(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "sp.db"))
    monkeypatch.setattr("doctor_dictation.api.sections.sections_for", lambda clinic, doctor_id=None: FH)
    seen = []

    def fake(structured, meta, out_path, layout=None):
        seen.append((structured, meta))
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)
    D._FORMAT_CACHE.clear()
    extra = {"family_history": {"heading": "Family History", "lines": ["Father diabetic"]}}
    with TestClient(create_app()) as c:
        r = c.post("/api/v1/documents", json={"structured": {"patientName": "A", "extra": extra}})
        assert r.status_code == 200, r.text
        stored = c.get(f"/api/v1/documents/{r.json()['document_id']}").json()["structured"]
    assert seen[0][1]["sections"] == FH
    assert stored["extra"] == extra


def test_extra_headings_lose_newlines_and_double_quotes():
    got = coerce_extra({"abc": {"heading": 'Fam\n  "History"\r\nNotes', "lines": ["x"]}})
    assert got["abc"]["heading"] == "Fam History Notes"
