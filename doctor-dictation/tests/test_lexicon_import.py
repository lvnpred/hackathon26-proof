"""CSV brand import (plan I1-g simple, Task 2): licence gate, the five checks, lineage. Offline, synthetic fixtures only;
build.py works on a COPY of the frozen lexicon in tmp_path, never the real file."""
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

LEX = Path(__file__).resolve().parents[1] / "doctor_dictation" / "core" / "lexicon"
DATA = Path(__file__).parent / "data"
FIXTURE, CONFLICT, FROZEN = DATA / "brands_fixture.csv", DATA / "conflict_fixture.csv", DATA / "lexicon_frozen.json"
SOURCE = ("--source-id", "fixture-2026", "--source-name", "Fixture Brands 2026",
          "--licence", "Synthetic test data, public domain (test only)", "--conflict-map", str(CONFLICT))


def load(name):
    spec = importlib.util.spec_from_file_location(name, LEX / f"{name.split('_under')[0]}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def build(tmp_path, monkeypatch):
    mod = load("build_under_test")
    (tmp_path / "drugs.json").write_bytes(FROZEN.read_bytes())
    monkeypatch.setattr(mod, "DRUGS_JSON", tmp_path / "drugs.json")
    monkeypatch.setattr(mod, "IMPORTED_JSON", tmp_path / "imported.json", raising=False)
    seed = tmp_path / "seed_frozen.json"          # the default seed, frozen: editing seed_extra.json never breaks these tests
    seed.write_text(json.dumps(json.loads(FROZEN.read_text(encoding="utf-8"))["entries"]), encoding="utf-8")
    monkeypatch.setattr(mod, "DEFAULT_SEED", seed)
    return mod


def run(build, monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["build.py", *argv])
    build.main()


def exit_code(build, monkeypatch, *argv):
    with pytest.raises(SystemExit) as exc:
        run(build, monkeypatch, *argv)
    return exc.value.code


def read(build):
    return json.loads(build.DRUGS_JSON.read_text(encoding="utf-8"))


def merge(tmp_path):
    return ("--merge", str(FIXTURE), *SOURCE, "--report", str(tmp_path / "report.json"))


def test_merge_of_a_csv_refuses_without_its_source_licence_map_and_report(build, monkeypatch, capsys, tmp_path):
    before, rep = build.DRUGS_JSON.read_bytes(), ("--report", str(tmp_path / "r.json"))
    full = dict(zip(SOURCE[::2], SOURCE[1::2]))
    for drop in ("--source-id", "--source-name", "--licence", "--conflict-map"):
        argv = [x for k, v in full.items() if k != drop for x in (k, v)]
        assert exit_code(build, monkeypatch, "--merge", str(FIXTURE), *argv, *rep) == 2, drop
        assert exit_code(build, monkeypatch, "--check", "--merge", str(FIXTURE), *argv, *rep) == 2, drop
    assert exit_code(build, monkeypatch, "--merge", str(FIXTURE), *SOURCE) == 2                       # no --report
    for bad_id in ("seed", "clinic", "promoted-2026-11", "X"):
        argv = [x for k, v in {**full, "--source-id": bad_id}.items() for x in (k, v)]
        assert exit_code(build, monkeypatch, "--merge", str(FIXTURE), *argv, *rep) == 2, bad_id
    assert "Nothing was read or written" in capsys.readouterr().err
    assert build.DRUGS_JSON.read_bytes() == before and not (tmp_path / "r.json").exists()
    run(build, monkeypatch, "--merge")                       # the repo's own seed needs no source and changes nothing
    assert build.DRUGS_JSON.read_bytes() == before and exit_code(build, monkeypatch, "--check") == 0


def test_the_gate_refuses_before_any_file_is_read_or_written(build, monkeypatch, capsys, tmp_path):
    csv_path, conflict, report = tmp_path / "missing.csv", tmp_path / "conflict.csv", tmp_path / "r.json"
    conflict.write_text("brand,generic\n", encoding="utf-8")
    real = {n: getattr(Path, n) for n in ("read_bytes", "read_text", "open", "is_file", "exists")}
    touched = []

    def guard(name):
        def wrapper(self, *a, **k):
            if self in (csv_path, conflict) or self.resolve() in (csv_path.resolve(), conflict.resolve()):
                touched.append(name)
                raise AssertionError(f"{name} on {self} before the gate")
            return real[name](self, *a, **k)
        return wrapper
    for n in real:
        monkeypatch.setattr(Path, n, guard(n))
    base = ["--source-id", "fixture-2026", "--source-name", "Fixture Brands 2026", "--conflict-map", str(conflict),
            "--report", str(report)]
    for licence in ([], ["--licence", "short"]):                       # missing, then under 10 characters
        assert exit_code(build, monkeypatch, "--merge", str(csv_path), *base, *licence) == 2
        assert exit_code(build, monkeypatch, "--check", "--merge", str(csv_path), *base, *licence) == 2
    assert "Nothing was read or written" in capsys.readouterr().err
    assert touched == [] and not report.exists() and not (tmp_path / "imported.json").exists()


def test_the_report_path_must_be_outside_the_repository_and_the_source_check_raises_value_error(build, monkeypatch, capsys, tmp_path):
    before = build.DRUGS_JSON.read_bytes()
    inside = Path(build.__file__).resolve().parents[3] / "docs" / "g2-report-must-not-exist.json"
    argv = [x for x in merge(tmp_path) if x != str(tmp_path / "report.json")]
    assert exit_code(build, monkeypatch, *argv, str(inside)) == 2
    assert "outside the repository" in capsys.readouterr().err and not inside.exists()
    assert build.DRUGS_JSON.read_bytes() == before
    assert exit_code(build, monkeypatch, "--check", *argv, str(inside)) == 2
    for bad in ({"id": "fx-1", "name": "ab", "licence": "x" * 10}, {"id": "fx-1", "name": "abc", "licence": "short"},
                {"id": "X", "name": "abc", "licence": "x" * 10}, {}):
        with pytest.raises(ValueError, match="Nothing was read or written"):
            build.check_source(bad)
    good = {"id": "fx-1", "name": "abc", "licence": "x" * 10}
    assert build.check_source(good) is good


def plan(rows_path=FIXTURE):
    lex = load("lexicon_import")
    entries = json.loads(FROZEN.read_text(encoding="utf-8"))["entries"]
    changed, report = lex.plan_import(lex.read_csv(rows_path), entries, lex.read_csv(CONFLICT), lex.load_rules(), "fx-1")
    return {e["canonical"]: e for e in changed}, report


def test_the_five_checks_on_the_fixture():
    changed, rep = plan()
    assert set(changed) == {"Amoxicillin", "Atorvastatin", "Levodopa + Carbidopa", "Paracetamol", "Thyroxine"}
    assert changed["Paracetamol"]["brands"] == ["Crocin", "Dolo", "Calpol", "Zentramol"]    # order kept; "TAB." dropped, "CAPS" normalised (never rejected)
    assert changed["Paracetamol"]["lineage"] == {"Zentramol": {"src": "fx-1"}}
    assert changed["Paracetamol"]["strengths"] == ["500 mg", "650 mg", "120 mg/5ml"]       # brands only: strengths untouched
    assert changed["Thyroxine"]["brands"][-1] == "Thyrobex"                                 # Levothyroxine via the synonym table
    assert changed["Atorvastatin"]["brands"][-1] == "Mirtavel"                              # "Rx" prefix gone
    assert (rep["brands_added"], rep["already_present"]) == (5, 1)                          # Crocin was already there
    assert rep["generics"] == {"exact": 8, "synonym": 1, "not_in_lexicon": 3}
    assert {s["brand"]: s["checks"] for s in rep["skipped"]} == {
        "Pantocid": ["2-one-generic"], "Quorabex": ["2-one-generic"],                       # the lexicon / the CDCI map
        "Novakind": ["1-generic"], "Plantiva": ["1-generic"], "Lunexa": ["1-generic"],      # fuzzy, unknown, blank generic
        "Glycomat": ["5-one-slip"], "Rubexil": ["5-one-slip"], "Rubexal": ["5-one-slip"], "Kelvorin": ["5-one-slip"],
        "Zix": ["3-five-letters"], "Clear": ["4-ordinary-word"], "Zorbin Day": ["4-ordinary-word"], "Decvar.": ["shape"],
        "Zentramol": ["duplicate"]}                                                         # line 3 repeats line 2: not a check
    assert rep["brands_added"] + rep["already_present"] + len(rep["skipped"]) == rep["rows_read"] == 20   # every row accounted
    dup = next(s for s in rep["skipped"] if s["checks"] == ["duplicate"])
    assert (dup["line"], dup["first_line"]) == (3, 2) and changed["Paracetamol"]["brands"][-1] == "Zentramol"
    by = {s["brand"]: s for s in rep["skipped"]}
    assert by["Novakind"]["looks_like"] == "Amoxicillin" and "looks_like" not in by["Plantiva"]   # reported, never merged
    assert (by["Glycomat"]["near"], by["Glycomat"]["rewrites_to"]) == (["glycomet"], "Metformin")
    assert by["Kelvorin"]["near"] == ["kelvorine"] and by["Pantocid"]["line"] == 5


def test_adapter_lookups_follow_the_runtime_rules():
    from doctor_dictation.core import determinism as D
    lex, entries = load("lexicon_import"), D.load_lexicon()
    assert lex.alias_map(entries) == D._alias_map()
    check = lex.Checker(entries, [], [], lex.load_rules())
    assert [check.resolve(n)[:2] for n in ("amoxycillin", "Levothyroxine", "Crocin", "Amoxicilin")] == [
        ("Amoxicillin", "exact"), ("Thyroxine", "synonym"), ("", ""), ("", "")]                # a brand never names a generic


def test_a_csv_without_the_required_columns_is_refused(tmp_path):
    (tmp_path / "bad.csv").write_text("brand,strength\nCrocin,500 mg\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="needs the columns"):
        load("lexicon_import").read_csv(tmp_path / "bad.csv")


def test_checker_pools_and_row_order_on_small_synthetic_inputs():
    lex = load("lexicon_import")
    entries = [{"canonical": "Alphadrug", "aliases": [], "brands": ["Zentrabex"], "strengths": [], "forms": []},
               {"canonical": "Betadrug", "aliases": [], "brands": [], "strengths": [], "forms": []}]
    row = lambda line, brand, generic: {"line": line, "brand": brand, "generic": generic}      # noqa: E731
    changed, rep = lex.plan_import([row(2, "Zentrabez", "Betadrug"), row(3, "Moravil", "Betadrug"),
                                    row(4, "Moravil", "Alphadrug"), row(5, "Quillor", "Betadrug"), row(9, "Quillor", "Betadrug")],
                                   entries, [], {"version": "t", "short_ok": set(), "synonyms": {}}, "t-1")
    skipped = {s["brand"]: s for s in rep["skipped"] if s["checks"] != ["duplicate"]}
    assert skipped["Zentrabez"]["checks"] == ["5-one-slip"] and skipped["Zentrabez"]["near"] == ["zentrabex"]   # an EXISTING brand
    assert skipped["Zentrabez"]["rewrites_to"] == "Alphadrug"
    assert skipped["Moravil"]["checks"] == ["2-one-generic"]                      # listed under two generics in the same file
    assert [e["canonical"] for e in changed] == ["Betadrug"] and changed[0]["brands"] == ["Quillor"]
    assert changed[0]["lineage"] == {"Quillor": {"src": "t-1"}} and (rep["brands_added"], rep["already_present"]) == (1, 0)
    assert [s["line"] for s in rep["skipped"]] == [2, 3, 4, 9]                  # sorted by line; the Quillor repeat is last
    assert rep["brands_added"] + rep["already_present"] + len(rep["skipped"]) == rep["rows_read"] == 5
    dup = lex.plan_import([row(2, "Zix", "Betadrug"), row(9, "Zix", "Betadrug")], entries, [],
                          {"version": "t", "short_ok": set(), "synonyms": {}}, "t-1")[1]
    assert [(s["line"], s["checks"]) for s in dup["skipped"]] == [(2, ["3-five-letters"]), (9, ["duplicate"])]   # FIRST row decides
    assert dup["skipped"][1]["first_line"] == 2 and dup["rows_read"] == 2
    check = lex.Checker(entries, [], [], {"version": "t", "short_ok": set(), "synonyms": {}})
    assert check.resolve("Zentrabex")[0] == ""                                     # a brand key never names a generic


def test_merge_brands_never_loses_an_existing_entrys_aliases_or_brands():
    lex = load("lexicon_import")
    entries = json.loads(FROZEN.read_text(encoding="utf-8"))["entries"]
    old = next(e for e in entries if e["canonical"] == "Paracetamol")
    (new,) = lex.merge_brands(entries, {"Paracetamol": [("Zentramol", {"src": "x-1"}), ("crocin", {"src": "x-1"})]})
    assert new["brands"] == [*old["brands"], "Zentramol"]               # existing first, a casefold duplicate is ignored
    assert {k: v for k, v in new.items() if k not in ("brands", "lineage")} == {k: v for k, v in old.items() if k != "brands"}
    assert new["lineage"] == {"Zentramol": {"src": "x-1"}} and list(new) == sorted(new)
    assert lex.merge_brands(entries, {"Paracetamol": [("Crocin", None)]}) == []


def test_the_frozen_lexicon_is_drugs_json_v1_1_0_before_any_import():
    data = json.loads(FROZEN.read_text(encoding="utf-8"))
    assert (data["version"], len(data["entries"]), sum(len(e["brands"]) for e in data["entries"])) == ("1.1.0", 444, 508)
    assert list(data) == ["entries", "version"] and not any("lineage" in e for e in data["entries"])


def test_merge_records_lineage_and_one_source_and_is_byte_identical_on_a_second_run(build, monkeypatch, tmp_path):
    run(build, monkeypatch, *merge(tmp_path))
    first = build.DRUGS_JSON.read_bytes()
    data = json.loads(first)
    (src,) = data["sources"]
    assert data["version"] == "1.2.0" and list(data) == ["entries", "version", "sources"]    # the addition goes last
    assert (src["id"], src["name"], src["brands_added"], src["rules"]) == ("fixture-2026", "Fixture Brands 2026", 5, "g-1")
    assert len(src["input_sha256"]) == len(src["conflict_map_sha256"]) == 64 and list(src) == sorted(src)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", src["merged_at"])
    para = next(e for e in data["entries"] if e["canonical"] == "Paracetamol")
    assert para["lineage"] == {"Zentramol": {"src": "fixture-2026"}} and list(para) == sorted(para)
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    # 14, not the plan's 13: the repeated Zentramol row is reported as skipped with the id "duplicate" (Task 2 fix round)
    assert report["brands_added"] == 5 and len(report["skipped"]) == 14 and report["already_present"] == 1
    assert report["brands_added"] + report["already_present"] + len(report["skipped"]) == report["rows_read"] == 20
    run(build, monkeypatch, *merge(tmp_path))
    assert build.DRUGS_JSON.read_bytes() == first and first.endswith(b"}\n") and b"\r\n" not in first


def test_existing_entries_and_names_are_never_changed_or_stolen(build, monkeypatch, tmp_path):
    lex, old = load("lexicon_import"), read(build)["entries"]
    run(build, monkeypatch, *merge(tmp_path))
    new = read(build)["entries"]
    assert [e["canonical"] for e in new] == [e["canonical"] for e in old]                    # no canonical added or moved
    by_new = {e["canonical"]: e for e in new}
    for e in old:
        assert by_new[e["canonical"]]["brands"][:len(e["brands"])] == e["brands"], e["canonical"]   # additions go last
        assert {k: v for k, v in by_new[e["canonical"]].items() if k not in ("brands", "lineage")} == \
            {k: v for k, v in e.items() if k != "brands"}
    old_map, new_map = lex.alias_map(old), lex.alias_map(new)
    assert all(new_map[key] == canonical for key, canonical in old_map.items())    # no existing name changed hands
    assert new_map["pantocid"] == "Pantoprazole" and not {"glycomat", "quorabex", "clear", "zix"} & set(new_map)
    from doctor_dictation.core import determinism as D                             # the new keys break no reader
    monkeypatch.setattr(D, "LEXICON_PATH", build.DRUGS_JSON)
    monkeypatch.setattr(D, "LEXICON_VERSION", D.lexicon_version())
    monkeypatch.setattr(D, "_lexicon_cache", None)
    assert D._canonical_lookup("Thyrobex") == "Thyroxine" and D.lexicon_version() == "1.2.0"
    assert D.correct_drugs("tab zentramol 650") == "tab Zentramol 650"            # brand as dictated


def test_check_fails_before_and_passes_after_and_the_default_seed_never_undoes_an_import(build, monkeypatch, tmp_path):
    assert exit_code(build, monkeypatch, "--check", *merge(tmp_path)) == 1
    run(build, monkeypatch, *merge(tmp_path))
    merged = build.DRUGS_JSON.read_bytes()
    assert exit_code(build, monkeypatch, "--check", *merge(tmp_path)) == 0
    assert exit_code(build, monkeypatch, "--check") == 0          # the CI gate: seed_extra.json plus imported.json == drugs.json
    run(build, monkeypatch, "--merge")                            # re-merging the authored seed keeps the imported brands
    assert build.DRUGS_JSON.read_bytes() == merged
    imported = json.loads(build.IMPORTED_JSON.read_text(encoding="utf-8"))
    assert [e["canonical"] for e in imported] == ["Amoxicillin", "Atorvastatin", "Levodopa + Carbidopa", "Paracetamol", "Thyroxine"]


def second_csv(tmp_path, brand, source_id):
    path = tmp_path / f"{brand}.csv"
    path.write_text(f"brand,generic,strength,form\n{brand},Paracetamol,500 mg,Oral tablet\n", encoding="utf-8")
    source = ["--source-id", source_id, *SOURCE[2:]]
    return ("--merge", str(path), *source, "--report", str(tmp_path / "report2.json"))


def test_a_second_source_appends_to_sources_and_imported_json_and_a_reused_id_is_refused(build, monkeypatch, tmp_path):
    run(build, monkeypatch, *merge(tmp_path))
    run(build, monkeypatch, *second_csv(tmp_path, "Brolvani", "fixture-2027"))
    data = read(build)
    assert [s["id"] for s in data["sources"]] == ["fixture-2026", "fixture-2027"] and data["version"] == "1.3.0"   # one minor per import
    para = next(e for e in data["entries"] if e["canonical"] == "Paracetamol")
    assert para["brands"][-2:] == ["Zentramol", "Brolvani"] and para["lineage"] == \
        {"Brolvani": {"src": "fixture-2027"}, "Zentramol": {"src": "fixture-2026"}}
    recorded = {e["canonical"]: e for e in json.loads(build.IMPORTED_JSON.read_text(encoding="utf-8"))}
    assert set(recorded) == {"Amoxicillin", "Atorvastatin", "Levodopa + Carbidopa", "Paracetamol", "Thyroxine"}   # first import kept
    assert recorded["Paracetamol"]["lineage"] == para["lineage"] and exit_code(build, monkeypatch, "--check") == 0
    before, imported = build.DRUGS_JSON.read_bytes(), build.IMPORTED_JSON.read_bytes()
    with pytest.raises(SystemExit) as exc:                                    # a new brand under an id already used
        run(build, monkeypatch, *second_csv(tmp_path, "Trelmavo", "fixture-2026"))
    assert "already used" in str(exc.value)
    assert build.DRUGS_JSON.read_bytes() == before and build.IMPORTED_JSON.read_bytes() == imported


def test_the_report_is_sorted_json_and_overlay_keeps_brands_the_seed_gained_since(build, monkeypatch, tmp_path):
    run(build, monkeypatch, *merge(tmp_path))
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert list(report) == sorted(report) and all(list(s) == sorted(s) for s in report["skipped"])
    seed = [{"canonical": "Paracetamol", "brands": ["Dolo", "Later"], "aliases": []}]
    imported = [{"canonical": "Paracetamol", "brands": ["Dolo", "Newer"], "aliases": [], "lineage": {"Newer": {"src": "x"}}}]
    (entry,) = load("lexicon_import").overlay(seed, imported)
    assert entry["brands"] == ["Dolo", "Later", "Newer"] and entry["lineage"] == {"Newer": {"src": "x"}}


def test_curated_skip_brands_are_never_imported_and_say_so_in_the_report(tmp_path):
    lex = load("lexicon_import")
    entries = json.loads(FROZEN.read_text(encoding="utf-8"))["entries"]
    csv_path = tmp_path / "one.csv"
    csv_path.write_text("brand,generic\nBrolvani,Paracetamol\n", encoding="utf-8")
    rows, rules = lex.read_csv(csv_path), lex.load_rules()
    changed, report = lex.plan_import(rows, entries, [], rules, "fx-1")
    assert report["brands_added"] == 1 and report["skipped"] == [] and changed[0]["brands"][-1] == "Brolvani"   # passes all five checks
    changed, report = lex.plan_import(rows, entries, [], {**rules, "skip": {"brolvani"}}, "fx-1")
    assert changed == [] and report["brands_added"] == 0
    assert report["skipped"] == [{"brand": "Brolvani", "checks": ["curated-skip"], "generic": "Paracetamol", "line": 2}]
    custom = tmp_path / "rules.json"
    custom.write_text(json.dumps({"version": "t", "short_brands_allowed": [], "synonyms": {}, "skip_brands": ["Tg-Tor", "BROLVANI"]}),
                      encoding="utf-8")
    assert lex.load_rules(custom)["skip"] == {"tg-tor", "brolvani"}                          # casefolded
    assert "tg-tor" in rules["skip"]                                                          # the shipped list: junk-suggestion fix


def test_a_json_seed_other_than_the_default_needs_no_source_flags_and_check_needs_no_report(build, monkeypatch, tmp_path):
    seed = tmp_path / "other_seed.json"
    seed.write_text(json.dumps([{"aliases": [], "brands": ["Qwerzol"], "canonical": "Qwerzolamide", "forms": [], "strengths": []}]),
                    encoding="utf-8")
    run(build, monkeypatch, "--merge", str(seed))                                  # no --source-id, --licence, --report
    assert "Qwerzolamide" in {e["canonical"] for e in read(build)["entries"]} and "sources" not in read(build)
    assert exit_code(build, monkeypatch, "--check", "--merge", str(seed)) == 0
    run(build, monkeypatch, *merge(tmp_path))
    no_report = [x for x in merge(tmp_path)[:-2]]
    assert exit_code(build, monkeypatch, "--check", *no_report) == 0                # --check --merge CSV: no --report demanded
    assert exit_code(build, monkeypatch, *no_report) == 2                           # a merge still needs it


def test_a_no_change_rerun_keeps_the_first_runs_report(build, monkeypatch, tmp_path):
    run(build, monkeypatch, *merge(tmp_path))
    first = (tmp_path / "report.json").read_bytes()
    assert json.loads(first)["brands_added"] == 5
    run(build, monkeypatch, *merge(tmp_path))                                        # nothing changes: the report is not rewritten
    assert (tmp_path / "report.json").read_bytes() == first


def test_do_merge_from_python_without_a_source_raises_value_error_and_reads_nothing(build, tmp_path):
    before = build.DRUGS_JSON.read_bytes()
    for source in (None, {}):
        with pytest.raises(ValueError, match="Nothing was read or written"):
            build.do_merge(FIXTURE, source, str(CONFLICT), str(tmp_path / "r.json"))
        with pytest.raises(ValueError, match="Nothing was read or written"):
            build.do_check(FIXTURE, source, str(CONFLICT))
    assert build.DRUGS_JSON.read_bytes() == before and not (tmp_path / "r.json").exists() and not build.IMPORTED_JSON.exists()


def test_skip_brands_may_be_a_dict_of_classes_and_the_shipped_list_names_its_classes():
    lex = load("lexicon_import")
    raw = json.loads((LEX / "import_rules.json").read_text(encoding="utf-8"))
    assert isinstance(raw["skip_brands"], dict) and "_comment" in raw and all(raw["skip_brands"].values())
    skip = lex.load_rules()["skip"]
    assert skip == {b.casefold() for v in raw["skip_brands"].values() for b in v} and len(skip) == 49
    assert {"arden", "gastrium", "ventryl", "limitex", "blisfer", "graftin", "propal", "rumorf", "diamet", "singulair",
            "salazar", "iwata", "suboxone", "duodopa", "gris odt", "advent", "pyridoxine hcl", "magnesium sulphate",
            "tg-tor"} <= skip


def test_read_csv_gives_clean_errors_and_keeps_quoted_newlines_and_unicode_separators_inside_a_cell(tmp_path):
    lex = load("lexicon_import")
    bad = tmp_path / "latin1.csv"
    bad.write_bytes(b"brand,generic\nCaf\xe9x,Paracetamol\n")
    with pytest.raises(SystemExit, match="UTF-8"):
        lex.read_csv(bad)
    big = tmp_path / "big.csv"
    big.write_text("brand,generic\n" + "A" * 140_000 + ",Paracetamol\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="field"):
        lex.read_csv(big)
    odd = tmp_path / "odd.csv"
    odd.write_bytes('brand,generic\n"Foo\nBar",Paracetamol\nBaz\x85Qux,Paracetamol\nAbc Def,Paracetamol\nLast,Paracetamol\n'
                    .encode("utf-8"))
    rows = lex.read_csv(odd)
    assert [r["generic"] for r in rows] == ["Paracetamol"] * 4 and [r["line"] for r in rows] == [2, 3, 4, 5]
    assert rows[3]["brand"] == "Last"


def test_a_csv_merge_that_changes_nothing_says_so_and_does_not_claim_to_write(build, monkeypatch, capsys, tmp_path):
    run(build, monkeypatch, *merge(tmp_path))
    assert "wrote" in capsys.readouterr().out
    run(build, monkeypatch, *merge(tmp_path))
    out = capsys.readouterr().out
    assert "no change" in out and "wrote" not in out


def test_plan_merge_checks_the_source_before_it_reads_the_csv_or_the_conflict_map(build, tmp_path):
    csv_path, conflict = tmp_path / "x.csv", tmp_path / "c.csv"
    csv_path.write_text("brand,generic\nBrolvani,Paracetamol\n", encoding="utf-8")
    conflict.write_text("brand,generic\n", encoding="utf-8")
    real = {n: getattr(Path, n) for n in ("read_bytes", "read_text", "open", "is_file", "exists")}
    touched = []

    def guard(name):
        def wrapper(self, *a, **k):
            if self.resolve() in (csv_path.resolve(), conflict.resolve()):
                touched.append(name)
            return real[name](self, *a, **k)
        return wrapper

    with pytest.MonkeyPatch.context() as mp:
        for name in real:
            mp.setattr(Path, name, guard(name))
        for source in (None, {}, {"id": "fx-1", "name": "ab", "licence": "x" * 10}):
            with pytest.raises(ValueError, match="Nothing was read or written"):
                build.plan_merge(csv_path, source, str(conflict))
    assert touched == []


def test_a_brand_one_slip_from_a_word_of_another_drugs_hyphenated_or_spaced_brand_is_skipped_for_that_alone():
    """Runtime tokens are single words, so 'Amozid-CV' is heard as 'Amozid': check 5 compares every word (5+ letters) of a
    multi-word name in the lexicon or the CDCI map, not only the whole name (review finding: Amozid-CV -> Amzid-CV)."""
    lex = load("lexicon_import")
    entries = [{"canonical": "Alphadrug", "aliases": [], "brands": ["Qelmovex Plus", "Tavrel-XR"], "strengths": [], "forms": []},
               {"canonical": "Betadrug", "aliases": [], "brands": [], "strengths": [], "forms": []}]
    conflict = [{"line": 2, "brand": "Zorvabex-CV", "generic": "Alphadrug"}]
    rules = {"version": "t", "short_ok": set(), "synonyms": {}}
    row = lambda brand, generic: [{"line": 2, "brand": brand, "generic": generic}]             # noqa: E731
    plan = lambda brand, generic="Betadrug": lex.plan_import(row(brand, generic), entries, conflict, rules, "t-1")  # noqa: E731
    for brand, word in (("Qelmovx", "qelmovex"), ("Zorvabx", "zorvabex")):                    # lexicon word; CDCI-map word
        changed, rep = plan(brand)
        (skipped,) = rep["skipped"]
        assert changed == [] and skipped["checks"] == ["5-one-slip"] and skipped["near"] == [word]      # nothing else fails
        assert skipped["rewrites_to"].casefold() == "alphadrug"
    changed, rep = plan("Qelmovx", "Alphadrug")                       # a word of its OWN drug's brand rewrites to the same drug
    assert rep["skipped"] == [] and changed[0]["brands"][-1] == "Qelmovx"
    changed, rep = plan("Tavr")                                       # words under 5 letters are not runtime keys
    assert [s["checks"] for s in rep["skipped"]] == [["3-five-letters"]]
    assert plan("Plusx")[1]["skipped"] == []                          # "Plus" has 4 letters: not a runtime key, so not a pool word
    check = lex.Checker(entries, conflict, [], rules)
    assert check.failures("Qelmovx", "Betadrug")[0] == ["5-one-slip"] and check.failures("Quillor", "Betadrug")[0] == []
