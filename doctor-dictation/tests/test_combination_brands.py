"""Owner decision (d): 4 combination brands become combination entries, 7 stay recognised but show and print no generic and get no dose
check, and none of it adds a look-alike warning or changes a status of the old names. LIVE lexicon (no frozen fixture). Offline."""
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.core import determinism as D, dosing, lasa
from doctor_dictation.core.determinism import validate_structured
from doctor_dictation.core.rowcheck import ground_with_notes
from doctor_dictation.pdf import build_sheet_html
from dosing_fixtures import FIXTURE, _e, use_fixture

ROOT = Path(__file__).resolve().parents[1]
LEX = ROOT / "doctor_dictation" / "core" / "lexicon"
MODELLED = {"Ultracet": "Tramadol + Paracetamol", "Savlon": "Chlorhexidine + Cetrimide", "Doxinate": "Doxylamine + Pyridoxine",
            "Shelcal": "Calcium Carbonate + Cholecalciferol"}
HIDDEN = {"Neopeptine": "Simethicone", "Fefol": "Ferrous Sulfate", "Autrin": "Ferrous Fumarate", "Feronia-XT": "Ferrous Ascorbate",
          "Calcimax": "Calcium Citrate", "Nurokind": "Methylcobalamin", "Adzolex-Plus": "Lactulose"}
COMPONENTS = {"Tramadol", "Paracetamol", "Chlorhexidine", "Doxylamine", "Pyridoxine", "Calcium Carbonate", "Cholecalciferol"}


def _row(name, strength="", text=None, **kw):
    out, _w = validate_structured({"rx": [{"form": "Tab.", "name": name, "strength": strength, **kw}]}, text or f"tab {name.lower()} {strength}".strip())
    return out["rx"][0]


def _entries():
    return {e["canonical"]: e for e in D.load_lexicon()}


def test_the_four_modelled_brands_are_combination_entries_and_left_their_single_generic():
    ent = _entries()
    for brand, canon in MODELLED.items():
        assert canon in ent and brand in ent[canon]["brands"], canon
        assert ent[canon].get("strengths") == [] and ent[canon].get("forms") == []                  # no strength or form invented
        others = [c for c, e in ent.items() if c != canon and brand.lower() in [x.lower() for x in [*e["brands"], *e["aliases"]]]]
        assert others == [], (brand, others)                                                          # the brand and its alias left the single entry
        parts = {p.strip() for p in canon.split("+")}
        assert not parts & {a.strip().title() for a in ent[canon]["aliases"]}, canon
        assert all("+" in a for a in ent[canon]["aliases"]), "a doctor saying one component must still ground to that component"
        assert D._canonical_lookup(brand) == canon
    for part in COMPONENTS:
        assert D._canonical_lookup(part) == part and part in ent


def test_grounding_of_the_eleven_brands_rules_path():
    for brand, generic in MODELLED.items():
        row = _row(brand, "500 mg" if brand == "Shelcal" else "")
        assert (row["status"], row["lexicon_match"], row["generic"], row["name"]) == ("verified", generic, generic, brand), brand
    for brand, single in HIDDEN.items():
        row = _row(brand)
        assert (row["name"], row["generic"]) == (brand, "") and row["lexicon_match"] == single, brand     # recognised as today, no generic shown
        assert row["status"] in ("verified", "unverified-strength"), brand
    assert _row("Fefole")["generic"] == ""                                                               # a near spelling of a hidden brand too
    assert _row("Ferrous Sulfate")["generic"] == "Ferrous Sulfate" and _row("Methylcobalamin")["generic"] == "Methylcobalamin"
    assert _row("Duphalac")["generic"] == "Lactulose" and _row("Orofer")["generic"] == "Ferrous Ascorbate"   # the other brands of the same entries


def test_check_row_route_answers_the_same(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "c.db"))
    client = TestClient(M.app)
    for name, generic in (("Ultracet", "Tramadol + Paracetamol"), ("Fefol", "")):
        r = client.post("/api/v1/rx/check-row", json={"row": {"name": name}, "transcript": f"tab {name.lower()}", "age_sex": ""}).json()
        assert (r["row"]["generic"], r["row"]["status"]) == (generic, "verified"), name


def test_a_hidden_brand_is_in_the_pdf_without_a_generic_line_and_a_combination_prints_in_full():
    hidden, combo, plain = _row("Fefol"), _row("Ultracet"), _row("Crocin", "500 mg")
    for row, line in ((hidden, False), (combo, True), (plain, True)):
        html = build_sheet_html({"patientName": "A", "rx": [row]}, {})
        assert ("generic:" in html) is line
    assert "generic: Tramadol + Paracetamol" in build_sheet_html({"rx": [combo]}, {})


def test_every_hidden_brand_is_a_brand_of_its_own_entry():
    for e in D.load_lexicon():
        hidden = e.get("generic_hidden", [])
        assert isinstance(hidden, list) and all(isinstance(h, str) and h in e["brands"] for h in hidden), e["canonical"]
    assert {b for e in D.load_lexicon() for b in e.get("generic_hidden", [])} == set(HIDDEN)


def test_a_hidden_brand_gets_no_dose_check_but_the_generic_name_still_does(monkeypatch, tmp_path):
    ref = copy.deepcopy(FIXTURE)
    ref["entries"].append(_e("Ferrous Sulfate", ["200 mg"], ["Tab."], "200 mg", 300))                    # 200 x 3 = 600 > 300
    use_fixture(monkeypatch, tmp_path, ref)
    text = "ferrous sulfate 200 mg three times daily, fefol 200 mg three times daily"
    out, _w = validate_structured({"ageSex": "45 / M", "rx": [{"form": "Tab.", "name": "Ferrous Sulfate", "strength": "200 mg", "dose": "1-1-1"},
                                                              {"form": "Tab.", "name": "Fefol", "strength": "200 mg", "dose": "1-1-1"}]}, text)
    generic, brand = out["rx"]
    assert (generic["status"], generic["dose_note"]) == ("dose-check", "600 mg a day; usual adult maximum 300 mg")
    assert (brand["status"], brand["dose_note"], brand["strength_options"], brand["usual_strength"]) == ("verified", "", [], "")


def test_the_combination_names_add_no_lookalike_warning_and_the_old_rows_are_unchanged():
    base = {"status": "verified", "lookalike": "", "heard": "", "source": "lexicon", "dose_note": "", "instructions": ""}
    for name, strength in (("Tramadol", "50 mg"), ("Paracetamol", "500 mg"), ("Chlorhexidine", ""), ("Pyridoxine", ""), ("Calcium Carbonate", "500 mg")):
        row = _row(name, strength)
        assert {k: row[k] for k in base} == base and row["lexicon_match"] == name and row["generic"] == name, name
    assert lasa.twins("Tramadol") == [] and lasa.twins("Paracetamol") == [] and lasa.twins("Pyridoxine") == []
    assert lasa.twins("Chlorhexidine") == ["Chlorpheniramine"] and lasa.twins("Calcium Carbonate") == ["Lithium Carbonate", "Calcium Citrate"]
    assert lasa.twins("Doxylamine") == ["Doxofylline", "Doxycycline"]
    for combo in MODELLED.values():
        assert not [t for t in lasa.twins(combo) if t in COMPONENTS or t in MODELLED.values()], combo
        for part in (p.strip() for p in combo.split("+")):
            assert combo not in lasa.twins(part)
    assert [lasa.twins(a) for a in ("Prednisone", "Citalopram")] == [["Prednisolone"], ["Escitalopram"]]
    assert len(lasa.always_flag_names()) == 16                                                           # the 8 curated pairs


def test_the_frozen_fixture_did_not_change():
    assert hashlib.sha256((ROOT / "tests" / "data" / "lexicon_frozen.json").read_bytes()).hexdigest() == \
        "7a6963cdc33d24287e92654e479ce63eb030259ab4c81cfd9669602461ab8594"


def test_build_check_is_in_sync():
    r = subprocess.run([sys.executable, str(LEX / "build.py"), "--check"], capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_short_combination_and_its_own_component_are_not_lookalikes_but_other_close_names_still_are(monkeypatch):
    def entry(canon):
        return {"canonical": canon, "aliases": [canon.lower()], "brands": [], "forms": [], "strengths": []}
    lex = [entry("Zorbexin"), entry("Zorbexin + A"), entry("Zorbexen"), entry("Zorbexen + A"), entry("A + Zorbexin")]
    monkeypatch.setattr(D, "_lexicon_cache", lex)
    monkeypatch.setattr(lasa, "_slot", {})
    assert "Zorbexin + A" not in lasa.twins("Zorbexin") and "Zorbexin" not in lasa.twins("Zorbexin + A")   # 0.8 alike by spelling, same family
    assert "A + Zorbexin" not in lasa.twins("Zorbexin") and "Zorbexin" not in lasa.twins("A + Zorbexin")   # the component may be the second part
    assert "Zorbexen" in lasa.twins("Zorbexin")                                                              # a different drug that looks alike still is
    assert "Zorbexen" in lasa.twins("Zorbexin + A") or "Zorbexen + A" in lasa.twins("Zorbexin + A")


def test_a_brand_plus_suffix_prints_no_generic_line():
    html = build_sheet_html({"patientName": "A", "rx": [_row("Zerodol-P"), _row("Crocinn", text="tab crocinn")]}, {})
    assert "generic:" not in html and "ZERODOL-P" in html
