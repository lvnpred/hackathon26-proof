"""lexicon/build_dosing.py: validation, refusal of unknown canonicals, atomic and idempotent output. Offline."""
import importlib.util
import json
import os
from pathlib import Path

import pytest

from doctor_dictation.core.determinism import ALLOWED_FORMS

SCRIPT = Path(__file__).resolve().parents[1] / "doctor_dictation" / "core" / "lexicon" / "build_dosing.py"
HEADER = "canonical,strengths,forms,usual,freq,max_daily_mg,source,reviewed\n"
GOOD = ("Paracetamol,500 mg;650 mg;1 g,Tab.;Syr.,650 mg,three times daily,1500,SYNTHETIC TEST DATA,yes\n"
        "amlodipine,2.5 mg;5 mg,Tab.,5 mg,once daily,10,SYNTHETIC TEST DATA,no\n")
OK = "Amlodipine,5 mg,Tab.,5 mg,od,10,S,yes"

@pytest.fixture(scope="module")
def build():
    spec = importlib.util.spec_from_file_location("build_dosing", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _run(build, tmp_path, body, header=HEADER):
    (tmp_path / "in.csv").write_text(header + body, encoding="utf-8")
    out = tmp_path / "dosing.json"
    return build.main([str(tmp_path / "in.csv"), "--version", "t-1", "--built-at", "2026-01-01", "--out", str(out)]), out

def test_good_csv_is_sorted_with_lexicon_spelling_and_a_rerun_is_byte_identical(build, tmp_path):
    assert build.FORMS == ALLOWED_FORMS
    code, out = _run(build, tmp_path, GOOD)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0 and (doc["version"], doc["built_at"]) == ("t-1", "2026-01-01")
    assert [(e["canonical"], e["reviewed"]) for e in doc["entries"]] == [("Amlodipine", False), ("Paracetamol", True)]
    assert doc["entries"][1]["adult"] == {"usual": "650 mg", "freq": "three times daily", "max_daily_mg": 1500}
    first = out.read_bytes()
    assert _run(build, tmp_path, GOOD)[0] == 0 and out.read_bytes() == first
    assert not list(tmp_path.glob("*.tmp"))

@pytest.mark.parametrize("row,why", [
    ("Notadrugxyz,5 mg,Tab.,5 mg,od,10,S,yes", "is not in drugs.json"),
    ("Amlodipine,5 tabs,Tab.,5 tabs,od,10,S,yes", "strengths must be like"),
    ("Amlodipine,5 mg,Tab.,10 mg,od,10,S,yes", "usual '10 mg' is not one of the strengths"),
    ("Amlodipine,5 mg,Tab.,5 mg,od,0,S,yes", "not a positive number"),
    ("Amlodipine,5 mg,Tab.,5 mg,od,lots,S,yes", "not a positive number"),
    ("Amlodipine,5 mg,Tablet,5 mg,od,10,S,yes", "forms must be"),
    ("Amlodipine,5 mg,Tab.,5 mg,od,10,,yes", "source is blank"),
    ("Amlodipine,5 mg,Tab.,5 mg,od,10,S,maybe", "reviewed must be yes or no"),
    (OK + "\n" + OK, "duplicate canonical"),
])
def test_a_bad_row_is_refused_and_the_previous_file_is_kept(build, tmp_path, row, why, capsys):
    _, out = _run(build, tmp_path, GOOD)
    before = out.read_bytes()
    assert _run(build, tmp_path, GOOD + row + "\n")[0] == 1
    assert why in capsys.readouterr().err and out.read_bytes() == before

# ---- fix round 1: hardening ----
def test_header_only_csv_is_refused_with_trailing_newline(build, tmp_path, capsys):
    _, out = _run(build, tmp_path, GOOD)
    before = out.read_bytes()
    assert _run(build, tmp_path, "")[0] == 1
    assert "no data rows" in capsys.readouterr().err
    assert out.read_bytes() == before and not list(tmp_path.glob("*.tmp"))

def test_header_only_csv_without_trailing_newline_is_refused(build, tmp_path, capsys):
    _, out = _run(build, tmp_path, GOOD)
    before = out.read_bytes()
    assert _run(build, tmp_path, "", header=HEADER.rstrip("\n"))[0] == 1
    assert "no data rows" in capsys.readouterr().err
    assert out.read_bytes() == before and not list(tmp_path.glob("*.tmp"))

@pytest.mark.parametrize("cap", ["1_000", "١٠", "1e3", "0x10", "nan", "inf", "-5", "+5", "1e308", "100001", ".5", "5."])
def test_max_daily_mg_grammar_and_ceiling(build, tmp_path, cap, capsys):
    _, out = _run(build, tmp_path, GOOD)
    before = out.read_bytes()
    assert _run(build, tmp_path, GOOD + f"Amlodipine,5 mg,Tab.,5 mg,od,{cap},S,yes\n")[0] == 1
    assert "not a positive number" in capsys.readouterr().err and out.read_bytes() == before

def test_max_daily_mg_ceiling_is_accepted_and_named(build, tmp_path):
    assert build.MAX_DAILY_MG_CEILING == 100000
    code, out = _run(build, tmp_path, "Amlodipine,5 mg,Tab.,5 mg,od,100000,S,yes\n")
    assert code == 0 and json.loads(out.read_text("utf-8"))["entries"][0]["adult"]["max_daily_mg"] == 100000

@pytest.mark.parametrize("row,why", [
    ("Amlodipine,5 mg,Tab.,5 mg,od,10,S,yes,extra", "wrong number of columns"),
    ("Amlodipine,5 mg,Tab.,5 mg,od,10,S", "wrong number of columns"),
    ("Amlodipine,5 mg,Tab.,5 mg,od,10,S\x00x,yes", "NUL"),
    ("Amlodipine,5 mg;5 mg,Tab.,5 mg,od,10,S,yes", "duplicate strength"),
    ("Amlodipine,5 mg,Tab.;Tab.,5 mg,od,10,S,yes", "duplicate form"),
])
def test_row_shape_nul_and_duplicate_cells_are_refused(build, tmp_path, row, why, capsys):
    _, out = _run(build, tmp_path, GOOD)
    before = out.read_bytes()
    assert _run(build, tmp_path, GOOD + row + "\n")[0] == 1
    err = capsys.readouterr().err
    assert why in err and "row 4" in err and out.read_bytes() == before

@pytest.mark.parametrize("version", ["", "   "])
def test_blank_version_is_refused(build, tmp_path, version, capsys):
    (tmp_path / "in.csv").write_text(HEADER + GOOD, encoding="utf-8")
    out = tmp_path / "dosing.json"
    assert build.main([str(tmp_path / "in.csv"), "--version", version, "--out", str(out)]) == 1
    assert "version" in capsys.readouterr().err and not out.exists()

def test_wrong_header_exits_1(build, tmp_path, capsys):
    assert _run(build, tmp_path, GOOD, header="canonical,strengths\n")[0] == 1
    assert "header must be exactly" in capsys.readouterr().err

def test_missing_out_directory_and_out_that_is_a_directory_exit_1_without_tmp(build, tmp_path, capsys):
    (tmp_path / "in.csv").write_text(HEADER + GOOD, encoding="utf-8")
    for target in (tmp_path / "nodir" / "d.json", tmp_path):
        assert build.main([str(tmp_path / "in.csv"), "--version", "v", "--out", str(target)]) == 1
        assert "ERROR" in capsys.readouterr().err
    assert not list(tmp_path.rglob("*.tmp"))

@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_unwritable_directory_exits_1_without_tmp(build, tmp_path, capsys):
    ro = tmp_path / "ro"
    ro.mkdir()
    (tmp_path / "in.csv").write_text(HEADER + GOOD, encoding="utf-8")
    ro.chmod(0o500)
    try:
        code = build.main([str(tmp_path / "in.csv"), "--version", "v", "--out", str(ro / "d.json")])
    finally:
        ro.chmod(0o700)
    assert code == 1 and "ERROR" in capsys.readouterr().err and not list(tmp_path.rglob("*.tmp"))

def test_bom_and_crlf_csv_builds_identically(build, tmp_path):
    _, plain = _run(build, tmp_path, GOOD)
    want = plain.read_bytes()
    (tmp_path / "in.csv").write_bytes(("﻿" + HEADER + GOOD).replace("\n", "\r\n").encode("utf-8"))
    assert build.main([str(tmp_path / "in.csv"), "--version", "t-1", "--built-at", "2026-01-01", "--out", str(plain)]) == 0
    assert plain.read_bytes() == want

def test_built_file_round_trips_through_dosing_load(build, tmp_path, monkeypatch, caplog):
    from doctor_dictation.core import dosing
    _, out = _run(build, tmp_path, GOOD)
    monkeypatch.setattr(dosing, "DOSING_PATH", out)
    with caplog.at_level("WARNING"):
        loaded = dosing._load()
    assert sorted(loaded["entries"]) == ["amlodipine", "paracetamol"]
    assert not caplog.records

# ---- final fix round: shrink guard ----
NAMES = ["Amlodipine", "Paracetamol", "Metformin", "Digoxin", "Ceftriaxone", "Prednisolone", "Atenolol", "Warfarin"]

def _build(build, tmp_path, n, *flags):
    rows = "".join(f"{x},5 mg,Tab.,5 mg,od,10,S,yes\n" for x in NAMES[:n])
    (tmp_path / "in.csv").write_text(HEADER + rows, encoding="utf-8")
    return build.main([str(tmp_path / "in.csv"), "--version", "t-2", "--out", str(tmp_path / "dosing.json"), *flags])

def test_shrinking_a_reference_of_five_or_more_by_over_20_percent_is_refused(build, tmp_path, capsys):
    assert _build(build, tmp_path, 8) == 0
    assert "old: 0 entries, new: 8 entries" in capsys.readouterr().out
    before = (tmp_path / "dosing.json").read_bytes()
    assert _build(build, tmp_path, 3) == 1
    cap = capsys.readouterr()
    assert "old: 8 entries, new: 3 entries" in cap.out and "ERROR" in cap.err and "8" in cap.err and "3" in cap.err
    assert (tmp_path / "dosing.json").read_bytes() == before and not list(tmp_path.glob("*.tmp"))
    assert _build(build, tmp_path, 7) == 0                                   # 7 of 8 is not under 80%

def test_allow_shrink_overrides_the_guard(build, tmp_path):
    assert _build(build, tmp_path, 8) == 0
    assert _build(build, tmp_path, 3, "--allow-shrink") == 0
    assert len(json.loads((tmp_path / "dosing.json").read_text(encoding="utf-8"))["entries"]) == 3

def test_a_small_or_missing_or_unreadable_old_file_is_never_guarded(build, tmp_path, capsys):
    assert _build(build, tmp_path, 4) == 0 and _build(build, tmp_path, 1) == 0     # fewer than 5 old entries
    assert "old: 4 entries, new: 1 entries" in capsys.readouterr().out
    (tmp_path / "dosing.json").write_text("{broken", encoding="utf-8")
    assert _build(build, tmp_path, 1) == 0 and "old: 0 entries" in capsys.readouterr().out
