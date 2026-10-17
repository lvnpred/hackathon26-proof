"""Plan I2-d Task 5: new generics reach the lexicon only after a clinician review sheet, reviewed look-alike pairs and the
gated promote (reviewer, --confirm, pepper, ledger). Offline; synthetic fixtures; every write goes to tmp_path copies."""
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

from test_generics_sync import NLEM, SRC, gs, sync          # noqa: F401
from test_lexicon_import import build, load, read           # noqa: F401

PEPPER = "test-pepper-0123456789-abcdefghijklmnop"
PROMO = ("--source-id", "generics-2026-11", "--reviewer", "Dr. Test Reviewer")
LIVE = [Path(__file__).resolve().parents[1] / "doctor_dictation" / "core" / "lexicon" / n
        for n in ("drugs.json", "imported.json", "seed_extra.json", "lasa_pairs.json", "promotion_ledger.json", "generics.json")]


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """The ledger, the pepper and the pairs are tmp copies; the live files are hashed around every test."""
    from doctor_dictation import promotion
    monkeypatch.setenv("PROMOTION_LEDGER_PEPPER", PEPPER)
    monkeypatch.setattr(promotion, "LEDGER_JSON", tmp_path / "ledger.json")
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in LIVE}
    yield promotion
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in LIVE} == before


@pytest.fixture(autouse=True)
def gp(gs):
    """generics_promote bound to the tmp-copy sync module (the CLI of generics_sync reaches it through ``PROMOTE``)."""
    mod = load("generics_promote")
    mod.GS, gs.PROMOTE = gs, mod
    return mod


def _sheet(gs, monkeypatch, tmp_path, name="sheet.csv"):
    sync(gs, monkeypatch, "--csv", str(NLEM), "--source-id", "nlem-2022", *SRC, "--report", str(tmp_path / "r.json"))
    monkeypatch.setattr(sys, "argv", ["generics_sync.py", "review-sheet", "--out", str(tmp_path / name)])
    assert gs.main() == 0
    with open(tmp_path / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _approved(rows, tmp_path, name="ok.csv", **edit):
    path = tmp_path / name
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows({**r, "clinician_ok": "y", **edit} for r in rows)
    return path


def _promote(gs, monkeypatch, review, *extra, confirm=True, report=None, tmp_path=None):
    argv = ["generics_sync.py", "promote", "--review", str(review), *(extra or PROMO),
            "--report", str(report or tmp_path / "p.json"), *(["--confirm"] if confirm else [])]
    monkeypatch.setattr(sys, "argv", argv)
    try:
        return gs.main()
    except SystemExit as exc:
        return exc.code


def _pairs(gs, *pairs, reviewed=True):
    gs.PAIRS_JSON.write_text(json.dumps({"note": "test", "pairs": [{"a": a, "b": b, "reviewed": reviewed, "source": "clinician test"}
                                                                  for a, b in pairs]}), encoding="utf-8")


def _names(build):
    return [e["canonical"] for e in read(build)["entries"]]


def test_the_review_sheet_lists_new_generics_with_their_twins_and_pair_status(gs, monkeypatch, tmp_path):
    rows = _sheet(gs, monkeypatch, tmp_path)
    assert [(r["generic"], r["twins"], r["curated_pair"], r["clinician_ok"]) for r in rows] == [
        ("Zorbexamide", "Zorbexonide", "n", ""), ("Zorbexonide", "Zorbexamide", "n", "")]
    assert list(rows[0]) == ["generic", "lists", "schedule", "near", "twins", "curated_pair", "clinician_ok", "notes"]
    assert [(r["lists"], r["schedule"], r["near"], r["notes"]) for r in rows] == [("NLEM", "", "", "")] * 2     # counts and names only


def test_the_sheet_marks_a_pair_only_when_a_clinician_reviewed_it_and_is_byte_stable(gs, build, monkeypatch, tmp_path):
    _sheet(gs, monkeypatch, tmp_path)
    first = (tmp_path / "sheet.csv").read_bytes()
    assert first.startswith(b"generic,lists,") and b"\r" not in first and not list(tmp_path.glob("sheet.csv.*"))   # LF, no temp left
    out = {}
    for label, reviewed in (("unreviewed", False), ("reviewed", True)):
        _pairs(gs, ("Zorbexonide", "Zorbexamide"), reviewed=reviewed)                     # either order of the pair counts
        monkeypatch.setattr(sys, "argv", ["generics_sync.py", "review-sheet", "--out", str(tmp_path / f"{label}.csv")])
        gs.main()
        out[label] = [r["curated_pair"] for r in csv.DictReader(open(tmp_path / f"{label}.csv", encoding="utf-8"))]
    assert out == {"unreviewed": ["n", "n"], "reviewed": ["y", "y"]}
    monkeypatch.setattr(sys, "argv", ["generics_sync.py", "review-sheet", "--out", str(tmp_path / "again.csv")])
    _pairs(gs)
    gs.main()
    assert (tmp_path / "again.csv").read_bytes() == first                                  # same input, same bytes


def test_the_sheet_is_sorted_neutralises_formulas_has_a_strictest_schedule_and_stays_out_of_the_repo(gs, build, monkeypatch, tmp_path, capsys):
    entries = [{"generic": g, "lexicon": "", "lists": ls} for g, ls in [
        ("Zeta drug", {"NLEM": {"src": "a"}, "Schedules": {"src": "b", "schedule": "H"}, "Other": {"src": "c", "schedule": "X"}}),
        ("alpha drug", {"NLEM": {"src": "a"}}), ("Valid drug", {"+Evil": {"src": "a"}}),
        ("=cmd|' /C calc'!A0", {"NLEM": {"src": "a"}}), ("@x", {"NLEM": {"src": "a"}}), ("Linked", {"NLEM": {"src": "a"}})]]
    entries[-1]["lexicon"] = "Paracetamol"                                                  # linked entries are not on the sheet
    gs.GENERICS_JSON.write_text(json.dumps({"entries": entries, "sources": [], "version": "0.1.0"}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["generics_sync.py", "review-sheet", "--out", str(tmp_path / "s.csv")])
    gs.main()
    rows = list(csv.DictReader(open(tmp_path / "s.csv", encoding="utf-8")))
    assert [r["generic"] for r in rows] == ["alpha drug", "Valid drug", "Zeta drug"]          # casefold order; formula-shaped names are skipped
    assert "skipped 2" in capsys.readouterr().out
    assert rows[1]["lists"] == "'+Evil" and rows[2]["lists"] == "NLEM; Other; Schedules" and rows[2]["schedule"] == "X"   # cell neutralised
    fake = tmp_path / "repo"
    fake.mkdir()
    (fake / "docs").mkdir()
    (fake / "doctor_dictation" / "core").mkdir(parents=True)
    (fake / "doctor_dictation" / "data").mkdir()
    monkeypatch.setattr(gs, "REPO_ROOT", fake)
    for target, ok in ((fake / "docs" / "s.csv", False), (fake / "doctor_dictation" / "core" / "s.csv", False),
                       (fake / "doctor_dictation" / "data" / "s.csv", True)):
        monkeypatch.setattr(sys, "argv", ["generics_sync.py", "review-sheet", "--out", str(target)])
        if ok:
            assert gs.main() == 0 and target.exists()
        else:
            with pytest.raises(SystemExit) as exc:
                gs.main()
            assert exc.value.code == 2 and not target.exists()


def test_promote_refuses_without_reviewer_confirm_pepper_or_a_safe_report_and_writes_nothing(gs, build, monkeypatch, tmp_path, capsys, isolated):
    rows = _sheet(gs, monkeypatch, tmp_path)
    ok = _approved(rows, tmp_path)
    _pairs(gs, ("Zorbexamide", "Zorbexonide"))
    before = build.DRUGS_JSON.read_bytes()
    base = ("--source-id", "generics-2026-11")
    cases = [(("--reviewer", "Dr"), True, "reviewer"), (base, True, "reviewer"), (("--source-id", "promoted-x", "--reviewer", "Dr. Test Reviewer"), True, "source-id"),
             (("--source-id", "x", "--reviewer", "Dr. Test Reviewer"), True, "source-id"), (PROMO, False, "--confirm")]
    for extra, confirm, why in cases:
        assert _promote(gs, monkeypatch, ok, *extra, confirm=confirm, tmp_path=tmp_path) == 2, why
    assert _promote(gs, monkeypatch, ok, *PROMO, report=Path(gs.HERE) / "r.json", tmp_path=tmp_path) == 2          # a report inside the repository
    monkeypatch.delenv("PROMOTION_LEDGER_PEPPER")
    assert _promote(gs, monkeypatch, ok, *PROMO, tmp_path=tmp_path) == 2
    monkeypatch.setenv("PROMOTION_LEDGER_PEPPER", "short")
    assert _promote(gs, monkeypatch, ok, *PROMO, tmp_path=tmp_path) == 2
    err = capsys.readouterr()
    assert "PROMOTION_LEDGER_PEPPER is required" in err.err and "add --confirm" in err.out
    assert build.DRUGS_JSON.read_bytes() == before and not (tmp_path / "p.json").exists() and not (tmp_path / "ledger.json").exists()
    assert not (Path(gs.HERE) / "r.json").exists() and not (tmp_path / "imported.json").exists()


def test_promote_refuses_a_twin_without_a_reviewed_pair_and_adds_a_brandless_canonical(gs, build, monkeypatch, tmp_path, capsys, isolated):
    rows = _sheet(gs, monkeypatch, tmp_path)
    ok = _approved(rows, tmp_path)
    before = build.DRUGS_JSON.read_bytes()
    assert _promote(gs, monkeypatch, ok, tmp_path=tmp_path) == 1                              # every row refused: exit 1, nothing written
    out = capsys.readouterr().out
    assert out.count("twin-without-reviewed-pair") == 2 and "Zorbexamide" in out
    assert build.DRUGS_JSON.read_bytes() == before and not (tmp_path / "ledger.json").exists()
    _pairs(gs, ("Zorbexamide", "Zorbexonide"), reviewed=False)                                # a pair that is not reviewed does not count
    assert _promote(gs, monkeypatch, ok, tmp_path=tmp_path) == 1 and build.DRUGS_JSON.read_bytes() == before
    _pairs(gs, ("Zorbexamide", "Zorbexonide"))
    assert _promote(gs, monkeypatch, ok, tmp_path=tmp_path) == 0
    lex = read(build)
    added = [e for e in lex["entries"] if e["canonical"] in ("Zorbexamide", "Zorbexonide")]
    assert [(e["canonical"], e["aliases"], e["brands"], e["strengths"], e["forms"], e["origin"]["reviewer"], e["origin"]["src"]) for e in added] == [
        ("Zorbexamide", ["zorbexamide"], [], [], [], "Dr. Test Reviewer", "generics-2026-11"),
        ("Zorbexonide", ["zorbexonide"], [], [], [], "Dr. Test Reviewer", "generics-2026-11")]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", added[0]["origin"]["date"])
    assert lex["version"] == "1.2.0" and lex["sources"][-1]["id"] == "generics-2026-11"
    rec = lex["sources"][-1]
    assert rec["reviewer"] == "Dr. Test Reviewer" and rec["licence"] == "Synthetic test data, public domain (test only)"    # the owner's words from the sync
    assert rec["input_sha256"] == hashlib.sha256(ok.read_bytes()).hexdigest()
    report = json.loads((tmp_path / "p.json").read_text(encoding="utf-8"))
    assert [(o["generic"], o["outcome"]) for o in report["outcomes"]] == [("Zorbexamide", "added"), ("Zorbexonide", "added")]
    monkeypatch.setattr(sys, "argv", ["build.py", "--check"])
    with pytest.raises(SystemExit) as exc:                                     # build.py exits with do_check's code
        build.main()
    assert exc.value.code == 0                                                 # drugs.json is in sync with seed + imported.json
    assert "Zorbexamide" in (tmp_path / "imported.json").read_text(encoding="utf-8")


def test_the_ledger_gets_hashes_only_and_the_same_batch_or_a_wrong_pepper_is_refused(gs, build, monkeypatch, tmp_path, isolated):
    rows = _sheet(gs, monkeypatch, tmp_path)
    ok = _approved(rows, tmp_path)
    _pairs(gs, ("Zorbexamide", "Zorbexonide"))
    assert _promote(gs, monkeypatch, ok, tmp_path=tmp_path) == 0
    text = (tmp_path / "ledger.json").read_text(encoding="utf-8")
    doc = json.loads(text)
    assert doc["version"] == "dd-promotion-v2" and re.fullmatch(r"[0-9a-f]{8}", doc["pepper_check"]) and PEPPER not in text
    assert [(e["batch"], e["decision"], e["outcome"], e["reviewer"], e["key"] == isolated.ledger_key(e["name"])) for e in doc["entries"]] == [
        ("generics-2026-11", "approve", "added", "Dr. Test Reviewer", True)] * 2
    assert re.fullmatch(r"[0-9a-f]{64}", doc["entries"][0]["key"])
    after = build.DRUGS_JSON.read_bytes()
    assert _promote(gs, monkeypatch, ok, tmp_path=tmp_path, report=tmp_path / "p2.json") == 2          # the same batch again
    monkeypatch.setenv("PROMOTION_LEDGER_PEPPER", "another-pepper-9876543210-zyxwvutsrqponm")
    assert _promote(gs, monkeypatch, ok, "--source-id", "generics-2026-12", "--reviewer", "Dr. Test Reviewer", tmp_path=tmp_path,
                    report=tmp_path / "p3.json") == 2                                                    # a wrong pepper
    assert build.DRUGS_JSON.read_bytes() == after and not (tmp_path / "p2.json").exists() and not (tmp_path / "p3.json").exists()


def test_the_sheet_is_not_trusted_beyond_generic_and_clinician_ok(gs, build, monkeypatch, tmp_path, capsys):
    rows = _sheet(gs, monkeypatch, tmp_path)
    before = build.DRUGS_JSON.read_bytes()
    forged = _approved(rows, tmp_path, "forged.csv", twins="", curated_pair="y", near="")    # a hand-edited twins or pair cell
    assert _promote(gs, monkeypatch, forged, tmp_path=tmp_path) == 1
    assert "twin-without-reviewed-pair" in capsys.readouterr().out and build.DRUGS_JSON.read_bytes() == before
    _pairs(gs, ("Zorbexamide", "Zorbexonide"))
    for label, edit in (("blank", {"clinician_ok": ""}), ("no", {"clinician_ok": "n"}), ("maybe", {"clinician_ok": "yes please"})):
        assert _promote(gs, monkeypatch, _approved(rows, tmp_path, f"{label}.csv", **edit), tmp_path=tmp_path) == 0
        assert build.DRUGS_JSON.read_bytes() == before, label                                  # only a plain y approves
        assert "no change" in capsys.readouterr().out
    odd = [{**rows[0], "generic": "Cetirizine", "clinician_ok": "y"},                            # already a lexicon name
           {**rows[0], "generic": "Not On The List", "clinician_ok": "y"},                       # not a new generic of generics.json
           {**rows[0], "generic": "Tab. Crocin 500", "clinician_ok": "y"},                       # shape
           {**rows[0], "generic": "Zorbexamide", "clinician_ok": "Y"}]
    p = tmp_path / "odd.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(odd)
    assert _promote(gs, monkeypatch, p, tmp_path=tmp_path) == 1
    out = capsys.readouterr().out
    for why in ("Cetirizine: refused: in-lexicon", "Not On The List: refused: not-a-new-generic", "Tab. Crocin 500: refused: not-a-new-generic",
                "Zorbexamide: added"):
        assert why in out, why
    assert _names(build).count("Zorbexamide") == 1 and "Zorbexonide" not in _names(build)       # the valid row applied, the rest did not


def test_a_new_generic_failing_the_importers_checks_is_refused_with_its_check(gs, gp, build, monkeypatch, tmp_path, capsys):
    data = {"entries": [{"generic": g, "lexicon": "", "lists": {"NLEM": {"src": "nlem-2022"}}} for g in
                        ("Vantrazine", "Ivz", "Cetirizinee", "Advice", "Vantrazine")],
            "sources": [{"id": "nlem-2022", "licence": "Synthetic test data, public domain (test only)"}], "version": "0.1.0"}
    gs.GENERICS_JSON.write_text(json.dumps(data), encoding="utf-8")
    rows = [{"generic": g, "clinician_ok": "y"} for g in ("Vantrazine", "Ivz", "Cetirizinee", "Advice", "Vantrazine")]
    assert dict(gp.promote_rows(rows, "generics-2026-10", "Dr. Test Reviewer", write=False))["Cetirizinee"].startswith("refused: twin-without")
    _pairs(gs, ("Cetirizinee", "Cetirizine"), ("Cetirizinee", "Levocetirizine"))                                      # a reviewed pair settles the look-alike, not the importer's checks
    summary = gp.promote_rows(rows, "generics-2026-11", "Dr. Test Reviewer")
    got = [(g, o.split(" (")[0]) for g, o in summary]
    assert got == [("Vantrazine", "added"), ("Ivz", "refused: 3-five-letters"), ("Cetirizinee", "refused: 5-one-slip"),
                   ("Advice", "refused: 4-ordinary-word"), ("Vantrazine", "refused: duplicate-row")]
    assert _names(build).count("Vantrazine") == 1


def test_a_promoted_generic_grounds_as_itself_with_no_dose_reference(gs, gp, build, monkeypatch, tmp_path):
    from doctor_dictation.core import determinism as D
    _sheet(gs, monkeypatch, tmp_path)
    _pairs(gs, ("Zorbexamide", "Zorbexonide"))
    gp.promote_rows([{"generic": "Zorbexamide", "clinician_ok": "y"}], "generics-2026-11", "Dr. Test Reviewer")
    monkeypatch.setattr(D, "LEXICON_VERSION", D.lexicon_version())             # restored, with the cache, after the test
    monkeypatch.setattr(D, "LEXICON_PATH", build.DRUGS_JSON)
    monkeypatch.setattr(D, "_lexicon_cache", None)
    s, _w = D.validate_structured({"rx": [{"form": "Tab.", "name": "Zorbexamide", "strength": "10 mg"}]}, "tab zorbexamide 10 mg")
    row = s["rx"][0]
    assert (row["status"], row["lexicon_match"], row["generic"], row["strength_options"]) == ("verified", "Zorbexamide", "Zorbexamide", [])


def _setup(gs, monkeypatch, tmp_path):
    rows = _sheet(gs, monkeypatch, tmp_path)
    _pairs(gs, ("Zorbexamide", "Zorbexonide"))
    return _approved(rows, tmp_path)


def test_a_crash_before_the_ledger_write_leaves_nothing(gs, build, monkeypatch, tmp_path, isolated):
    ok, before = _setup(gs, monkeypatch, tmp_path), build.DRUGS_JSON.read_bytes()
    monkeypatch.setattr(isolated, "save_ledger", lambda *a: (_ for _ in ()).throw(SystemExit("boom")))
    assert _promote(gs, monkeypatch, ok, tmp_path=tmp_path) == "boom"
    assert build.DRUGS_JSON.read_bytes() == before and not (tmp_path / "ledger.json").exists() and not (tmp_path / "p.json").exists()
    assert not (tmp_path / "imported.json").exists()


def test_a_crash_after_the_ledger_write_is_completed_by_a_rerun_of_the_same_sheet(gs, build, monkeypatch, tmp_path, capsys):
    ok, before = _setup(gs, monkeypatch, tmp_path), build.DRUGS_JSON.read_bytes()
    real = gs.build.apply_import
    monkeypatch.setattr(gs.build, "apply_import", lambda *a, **k: (_ for _ in ()).throw(SystemExit("boom")))
    assert _promote(gs, monkeypatch, ok, tmp_path=tmp_path) == "boom"
    ledger = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))["entries"]
    assert sorted(e["canonical"] for e in ledger) == ["Zorbexamide", "Zorbexonide"]                  # the ledger is written first
    assert build.DRUGS_JSON.read_bytes() == before and not (tmp_path / "p.json").exists()      # the lexicon and the report are not
    monkeypatch.setattr(gs.build, "apply_import", real)
    different = _approved(list(csv.DictReader(open(ok, encoding="utf-8")))[:1], tmp_path, "one.csv")
    assert _promote(gs, monkeypatch, different, tmp_path=tmp_path) == 2                         # a sheet that does not match the ledger
    assert build.DRUGS_JSON.read_bytes() == before
    assert _promote(gs, monkeypatch, ok, tmp_path=tmp_path) == 0                                # the same sheet completes the write
    assert "recovering" in capsys.readouterr().out
    lex = read(build)
    assert sorted(n for n in _names(build) if n.startswith("Zorbex")) == ["Zorbexamide", "Zorbexonide"]
    assert lex["sources"][-1]["id"] == "generics-2026-11" and (tmp_path / "p.json").exists()
    assert len(json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))["entries"]) == 2   # no duplicate entries
    assert _promote(gs, monkeypatch, ok, tmp_path=tmp_path) == 2                                # now it is simply used
    monkeypatch.setattr(sys, "argv", ["build.py", "--check"])
    with pytest.raises(SystemExit) as exc:
        build.main()
    assert exc.value.code == 0


def test_a_promoted_generic_gets_its_schedule_without_a_second_sync(gs, build, monkeypatch, tmp_path):
    from doctor_dictation.core import generics
    csv_path = tmp_path / "list.csv"
    csv_path.write_text("generic,list,schedule,source_line\nZorbexamide,Schedules,H1,5\nParacetamol,Schedules,H,6\n", encoding="utf-8")
    monkeypatch.setattr(generics, "GENERICS_PATH", gs.GENERICS_JSON)
    generics.reset()
    try:
        assert generics.schedule_of("Paracetamol") == ""                                           # loads (and caches) the empty state
        sync(gs, monkeypatch, "--csv", str(csv_path), "--source-id", "sched-2026", *SRC, "--report", str(tmp_path / "r.json"))
        assert (generics.schedule_of("Paracetamol"), generics.schedule_of("Zorbexamide")) == ("H", "")      # not a lexicon name yet
        monkeypatch.setattr(sys, "argv", ["generics_sync.py", "review-sheet", "--out", str(tmp_path / "sheet.csv")])
        gs.main()
        rows = list(csv.DictReader(open(tmp_path / "sheet.csv", encoding="utf-8")))
        assert [(r["generic"], r["twins"]) for r in rows] == [("Zorbexamide", "")]
        assert _promote(gs, monkeypatch, _approved(rows, tmp_path), tmp_path=tmp_path) == 0
        assert generics.schedule_of("Zorbexamide") == "H1"                                        # the link was refreshed and the file reloaded
        entry = [e for e in json.loads(gs.GENERICS_JSON.read_text(encoding="utf-8"))["entries"] if e["generic"] == "Zorbexamide"][0]
        assert entry["lexicon"] == "Zorbexamide"
        sync(gs, monkeypatch, "--csv", str(csv_path), "--source-id", "sched-2026", *SRC, "--report", str(tmp_path / "r2.json"))   # idempotent
        monkeypatch.setattr(sys, "argv", ["generics_sync.py", "sync", "--check", "--csv", str(csv_path), "--source-id", "sched-2026", *SRC])
        assert gs.main() == 0
    finally:
        generics.reset()


def test_a_brand_of_another_drug_is_noted_and_not_promotable_and_formula_text_is_skipped(gs, gp, build, monkeypatch, tmp_path, capsys):
    csv_path = tmp_path / "list.csv"
    csv_path.write_text("generic,list,schedule\nCrocin,Schedules,H\n+SUM(1),Schedules,H\n=cmd|x,Schedules,\n@evil,Schedules,\nVantrazine,Schedules,\n",
                        encoding="utf-8")
    sync(gs, monkeypatch, "--csv", str(csv_path), "--source-id", "sched-2026", *SRC, "--report", str(tmp_path / "r.json"))
    rep = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert [(x["line"], x["checks"]) for x in rep["skipped"]] == [(3, ["formula"]), (4, ["formula"]), (5, ["formula"])]
    assert sorted(e["generic"] for e in json.loads(gs.GENERICS_JSON.read_text(encoding="utf-8"))["entries"]) == ["Crocin", "Vantrazine"]
    monkeypatch.setattr(sys, "argv", ["generics_sync.py", "review-sheet", "--out", str(tmp_path / "sheet.csv")])
    gs.main()
    rows = list(csv.DictReader(open(tmp_path / "sheet.csv", encoding="utf-8")))
    assert [(r["generic"], r["notes"], r["clinician_ok"]) for r in rows] == [
        ("Crocin", "brand of Paracetamol: not promotable", ""), ("Vantrazine", "", "")]
    out = dict(gp.promote_rows([{"generic": "Crocin", "clinician_ok": "y"}, {"generic": "Vantrazine", "clinician_ok": "y"}],
                               "generics-2026-11", "Dr. Test Reviewer", write=False))
    assert out == {"Crocin": "refused: brand-of-Paracetamol", "Vantrazine": "added"}


def test_no_folder_is_created_for_a_report_or_a_sheet(gs, gp, build, monkeypatch, tmp_path, capsys, isolated):
    rows = _sheet(gs, monkeypatch, tmp_path)
    ok = _approved(rows, tmp_path)
    _pairs(gs, ("Zorbexamide", "Zorbexonide"))
    before = build.DRUGS_JSON.read_bytes()
    gone = tmp_path / "nope" / "deeper"
    assert _promote(gs, monkeypatch, ok, report=gone / "p.json", tmp_path=tmp_path) == 2
    monkeypatch.setattr(sys, "argv", ["generics_sync.py", "review-sheet", "--out", str(gone / "s.csv")])
    with pytest.raises(SystemExit) as exc:
        gs.main()
    assert exc.value.code == 2
    good = ("--csv", str(NLEM), "--source-id", "nlem-9", *SRC)
    with pytest.raises(SystemExit) as exc:
        sync(gs, monkeypatch, *good, "--report", str(gone / "r.json"))
    assert exc.value.code == 2
    assert "folder does not exist" in capsys.readouterr().err and not (tmp_path / "nope").exists()
    assert build.DRUGS_JSON.read_bytes() == before and not (tmp_path / "ledger.json").exists()
    with pytest.raises(SystemExit) as exc:                                                       # the backstop in the writer itself
        gs._atomic_write(gone / "x.json", "{}")
    assert exc.value.code == 2 and not (tmp_path / "nope").exists()


def test_the_ledger_wording_says_what_it_stores(gp, gs):
    text = gp.__doc__ + gp.LEDGER_NOTE
    assert "added generic names are public and recorded" in text and "hashes only for refused or rejected rows" in text
