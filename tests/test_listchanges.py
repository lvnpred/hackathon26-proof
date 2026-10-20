"""apply-list-changes (plan PQ-f, Task 10): the owner's exported list changes folded into the shipped lists.

Every test works on COPIES of seed_extra.json, imported.json and drugs.json in tmp_path (build's paths monkeypatched);
the real lexicon files are never written."""
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from doctor_dictation import admin, listchanges
from doctor_dictation.core.lexicon import build

LEX = Path(build.__file__).resolve().parent
NOW = "2026-10-20T10:00:00Z"
ADD = {"action": "add", "entry_key": "zyxolin", "data": {"name": "Zyxolin", "generic": "Zyxoprazole",
                                                          "aliases": ["zyxoprazol"]}}


@pytest.fixture()
def lex(tmp_path, monkeypatch):
    for name in ("drugs.json", "seed_extra.json", "imported.json"):
        shutil.copyfile(LEX / name, tmp_path / name)
    monkeypatch.setattr(build, "DRUGS_JSON", tmp_path / "drugs.json")
    monkeypatch.setattr(build, "DEFAULT_SEED", tmp_path / "seed_extra.json")
    monkeypatch.setattr(build, "IMPORTED_JSON", tmp_path / "imported.json")
    monkeypatch.setattr(listchanges, "INVESTIGATIONS_JSON", tmp_path / "investigations.json")
    assert build.do_check(build.DEFAULT_SEED) == 0
    return tmp_path


def snapshot(lex):
    return {p.name: p.read_bytes() for p in sorted(lex.glob("*.json"))}


def export(tmp_path, changes, kind="medicine", name="changes.json"):
    path = tmp_path / "export" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"kind": kind, "changes": changes}), encoding="utf-8")
    return path


def drugs():
    return json.loads(build.DRUGS_JSON.read_text(encoding="utf-8"))


def entry(canonical):
    return next(e for e in drugs()["entries"] if e["canonical"].casefold() == canonical.casefold())


def seed_only_entry():
    """A seed entry imported.json does not touch."""
    imported = {e["canonical"].casefold() for e in json.loads(build.IMPORTED_JSON.read_text(encoding="utf-8"))}
    return next(e for e in build.load_seed(build.DEFAULT_SEED) if e["canonical"].casefold() not in imported
                and "generic_hidden" not in e)


def test_dry_run_writes_nothing(lex, tmp_path, capsys):
    before = snapshot(lex)
    assert listchanges.apply(export(tmp_path, [ADD]), confirm=False, now=NOW) == 2
    assert snapshot(lex) == before
    out = capsys.readouterr().out
    assert "add Zyxolin (generic Zyxoprazole)" in out and "dry run: nothing was written" in out


def test_confirm_adds_the_entry_bumps_the_minor_and_records_a_source(lex, tmp_path, capsys):
    before = drugs()
    path = export(tmp_path, [ADD])
    assert listchanges.apply(path, confirm=True, now=NOW) == 0
    assert capsys.readouterr().out.rstrip().endswith(listchanges.DONE)
    after = drugs()
    major, minor, _patch = before["version"].split(".")
    assert after["version"] == f"{major}.{int(minor) + 1}.0" == build.bump_minor(before["version"])
    assert entry("Zyxoprazole") == {"aliases": ["Zyxoprazol"], "brands": ["Zyxolin"], "canonical": "Zyxoprazole",
                                    "forms": [], "strengths": []}
    assert len(after["entries"]) == len(before["entries"]) + 1
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    new = [s for s in after["sources"] if s not in before["sources"]]
    assert new == [{"id": f"admin-list-{sha[:8]}", "input_sha256": sha, "licence": listchanges.SOURCE_LICENCE,
                    "merged_at": NOW, "name": listchanges.SOURCE_NAME}]
    assert any(e["canonical"] == "Zyxoprazole" for e in build.load_seed(build.DEFAULT_SEED))
    assert build.do_check(build.DEFAULT_SEED) == 0


def test_edit_sets_safety_and_check_stays_in_sync(lex, tmp_path):
    base = seed_only_entry()
    key = base["canonical"].casefold()
    change = {"action": "edit", "entry_key": key, "data": {"safety": True, "brands": [*base["brands"], "Qwertabrand"]}}
    assert listchanges.apply(export(tmp_path, [change]), confirm=True, now=NOW) == 0
    got = entry(base["canonical"])
    assert got["safety"] is True and got["brands"][-1] == "Qwertabrand"
    assert {k: v for k, v in got.items() if k not in ("safety", "brands")} == \
        {k: v for k, v in base.items() if k != "brands"}
    assert build.do_check(build.DEFAULT_SEED) == 0


def test_an_edit_of_an_entry_only_imported_json_has_is_copied_into_the_seed(lex, tmp_path):
    seed = {e["canonical"].casefold() for e in build.load_seed(build.DEFAULT_SEED)}
    only = [e for e in json.loads(build.IMPORTED_JSON.read_text(encoding="utf-8")) if e["canonical"].casefold() not in seed]
    if not only:
        pytest.skip("imported.json adds no new generic")
    target = entry(only[0]["canonical"])
    change = {"action": "edit", "entry_key": target["canonical"].casefold(), "data": {"safety": True}}
    assert listchanges.apply(export(tmp_path, [change]), confirm=True, now=NOW) == 0
    assert entry(target["canonical"]) == {**target, "safety": True}
    assert build.do_check(build.DEFAULT_SEED) == 0


def test_rerun_is_no_change(lex, tmp_path, capsys):
    path = export(tmp_path, [ADD])
    assert listchanges.apply(path, confirm=True, now=NOW) == 0
    once = snapshot(lex)
    capsys.readouterr()
    assert listchanges.apply(path, confirm=True, now="2027-01-01T00:00:00Z") == 0
    assert snapshot(lex) == once
    assert "no change" in capsys.readouterr().out


BAD = {
    "hide": [{"action": "hide", "entry_key": "zyxolin", "data": {}}],
    "unknown key": [{**ADD, "data": {**ADD["data"], "colour": "red"}}],
    "missing generic": [{**ADD, "data": {"name": "Zyxolin"}}],
    "entry_key is not the name's key": [{**ADD, "entry_key": "zyxolinn"}],
    "edit of an unknown canonical": [{"action": "edit", "entry_key": "notamedicineatall", "data": {"safety": True}}],
    "edit changes the generic": [{"action": "edit", "entry_key": "paracetamol", "data": {"generic": "Acetaminophen"}}],
    "name already a brand": [{**ADD, "data": {**ADD["data"], "name": "@BRAND"}, "entry_key": "@KEY"}],
    "second change bad": [ADD, {"action": "edit", "entry_key": "notamedicineatall", "data": {"safety": True}}],
}


@pytest.mark.parametrize("case", [*BAD, "not JSON", "extra top-level key", "investigation kind unknown"])
def test_invalid_files_write_nothing(lex, tmp_path, capsys, case):
    before = snapshot(lex)
    if case == "not JSON":
        path = tmp_path / "export" / "bad.json"; path.parent.mkdir(exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
    elif case == "extra top-level key":
        path = tmp_path / "export" / "bad.json"; path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"kind": "medicine", "changes": [ADD], "x": 1}), encoding="utf-8")
    elif case == "investigation kind unknown":
        path = export(tmp_path, [ADD], kind="medicines")
    else:
        seed = seed_only_entry()
        brand = seed["brands"][0]
        text = json.dumps(BAD[case]).replace("@BRAND", brand).replace("@KEY", brand.casefold()) \
            .replace("@GENERIC", seed["canonical"].upper())
        path = export(tmp_path, json.loads(text))
    for confirm in (False, True):
        assert listchanges.apply(path, confirm=confirm, now=NOW) == 1
        assert snapshot(lex) == before
        assert capsys.readouterr().err.startswith("error: ")


def test_the_error_names_the_bad_change_by_index(lex, tmp_path):
    with pytest.raises(ValueError, match=r"^change 2 \(zz\)"):
        listchanges.read_changes(export(tmp_path, [ADD, {"action": "hide", "entry_key": "zz", "data": {}}]))


def test_an_edit_that_imported_json_would_undo_is_refused(lex, tmp_path, capsys):
    imported = json.loads(build.IMPORTED_JSON.read_text(encoding="utf-8"))
    target = next(e for e in imported if e.get("lineage"))
    shipped = entry(target["canonical"])
    dropped = next(b for b in shipped["brands"] if b in target["lineage"])
    keep = [b for b in shipped["brands"] if b != dropped]
    change = {"action": "edit", "entry_key": shipped["canonical"].casefold(), "data": {"brands": keep}}
    before = snapshot(lex)
    assert listchanges.apply(export(tmp_path, [change]), confirm=True, now=NOW) == 1
    assert snapshot(lex) == before
    assert "imported.json re-adds brand" in capsys.readouterr().err
    with pytest.raises(ValueError, match="edit imported.json by hand"):
        listchanges.plan_medicines(listchanges.read_changes(export(tmp_path, [change]))[1],
                                   build.load_seed(build.DEFAULT_SEED), build.load_drugs())


def test_a_name_another_entry_already_has_is_refused_on_an_edit(lex, tmp_path, capsys):
    a, b = [e for e in build.load_seed(build.DEFAULT_SEED) if e["brands"]][:2]
    change = {"action": "edit", "entry_key": a["canonical"].casefold(), "data": {"aliases": [b["brands"][0]]}}
    before = snapshot(lex)
    assert listchanges.apply(export(tmp_path, [change]), confirm=True, now=NOW) == 1
    assert snapshot(lex) == before
    assert "already belongs to" in capsys.readouterr().err


def test_investigations_without_a_catalogue_is_an_error(lex, tmp_path, capsys):
    change = {"action": "add", "entry_key": "renal function test",
              "data": {"name": "Renal Function Test", "aliases": ["rft"], "category": "Blood", "print": "RFT"}}
    before = snapshot(lex)
    assert listchanges.apply(export(tmp_path, [change], kind="investigation"), confirm=True, now=NOW) == 1
    assert snapshot(lex) == before
    assert "investigations.json does not exist yet (plan h)" in capsys.readouterr().err


def test_plan_investigations_adds_sorted_and_bumps_the_minor():
    catalogue = {"version": "1.0.0", "entries": [{"canonical": "Serum Ferritin", "aliases": [], "category": "Blood",
                                                  "print": "Ferritin"}]}
    _kind, changes = "investigation", [listchanges._clean_change("investigation", {
        "action": "add", "entry_key": "esr", "data": {"name": "ESR", "category": "Blood", "print": "ESR"}}, set())]
    doc = listchanges.plan_investigations(changes, catalogue)
    assert doc["version"] == "1.1.0" and [e["canonical"] for e in doc["entries"]] == ["ESR", "Serum Ferritin"]
    assert listchanges.plan_investigations(changes, doc)["version"] == "1.1.0"      # applied again: no change
    with pytest.raises(ValueError, match="already belongs"):
        listchanges.plan_investigations([listchanges._clean_change("investigation", {
            "action": "add", "entry_key": "ferritin", "data": {"name": "Ferritin", "category": "Blood"}}, set())], catalogue)


def test_admin_help_lists_the_command(capsys):
    with pytest.raises(SystemExit):
        admin.main(["--help"])
    assert "apply-list-changes" in capsys.readouterr().out


def test_admin_runs_the_dry_run(lex, tmp_path):
    before = snapshot(lex)
    assert admin.main(["apply-list-changes", str(export(tmp_path, [ADD]))]) == 2
    assert snapshot(lex) == before


def test_an_add_of_a_listed_generic_folds_the_brand_into_that_entry(lex, tmp_path, capsys):
    base = seed_only_entry()
    before = drugs()
    change = {"action": "add", "entry_key": "qqqbrand", "data": {"name": "Qqqbrand", "generic": base["canonical"].upper()}}
    path = export(tmp_path, [change])
    assert listchanges.apply(path, confirm=False, now=NOW) == 2
    assert f"{base['canonical']}: + brand Qqqbrand" in capsys.readouterr().out
    assert listchanges.apply(path, confirm=True, now=NOW) == 0
    got = entry(base["canonical"])
    assert got == {**base, "brands": [*base["brands"], "Qqqbrand"]}
    assert len(drugs()["entries"]) == len(before["entries"])
    assert drugs()["version"] == build.bump_minor(before["version"])
    assert build.do_check(build.DEFAULT_SEED) == 0
    once = snapshot(lex)
    assert listchanges.apply(path, confirm=True, now=NOW) == 0          # applied again: no change
    assert snapshot(lex) == once


def test_an_add_whose_name_another_entry_has_is_still_refused(lex, tmp_path, capsys):
    a, b = [e for e in build.load_seed(build.DEFAULT_SEED) if e["brands"]][:2]
    change = {"action": "add", "entry_key": b["brands"][0].casefold(), "data": {"name": b["brands"][0], "generic": a["canonical"]}}
    before = snapshot(lex)
    assert listchanges.apply(export(tmp_path, [change]), confirm=True, now=NOW) == 1
    assert snapshot(lex) == before
    assert "already belongs to" in capsys.readouterr().err


def test_resending_the_stored_names_is_no_change(lex, tmp_path, capsys):
    base = next(e for e in build.load_seed(build.DEFAULT_SEED) if e["canonical"] == "Acarbose")
    assert any(a.islower() for a in base["aliases"])                   # stored lower case; validate_data re-cases them
    change = {"action": "edit", "entry_key": "acarbose", "data": {"aliases": base["aliases"], "brands": base["brands"]}}
    before = snapshot(lex)
    assert listchanges.apply(export(tmp_path, [change]), confirm=True, now=NOW) == 0
    assert snapshot(lex) == before
    assert "no change" in capsys.readouterr().out


def test_safety_false_on_an_entry_without_the_key_is_no_change(lex, tmp_path, capsys):
    base = seed_only_entry()
    assert "safety" not in base
    change = {"action": "edit", "entry_key": base["canonical"].casefold(), "data": {"safety": False}}
    before = snapshot(lex)
    assert listchanges.apply(export(tmp_path, [change]), confirm=True, now=NOW) == 0
    assert snapshot(lex) == before
    assert "no change" in capsys.readouterr().out


def test_a_failed_check_after_writing_puts_both_files_back(lex, tmp_path, monkeypatch, capsys):
    before = snapshot(lex)
    monkeypatch.setattr(build, "do_check", lambda *a, **k: 1)
    assert listchanges.apply(export(tmp_path, [ADD]), confirm=True, now=NOW) == 1
    assert snapshot(lex) == before
    assert "were put back" in capsys.readouterr().err


def test_a_write_error_says_cannot_write_and_puts_the_seed_back(lex, tmp_path, monkeypatch, capsys):
    before, real = snapshot(lex), listchanges.write_atomic

    def fail_on_drugs(path, text):
        if Path(path).name == "drugs.json":
            raise PermissionError(13, "Permission denied", str(path) + ".tmp")     # as write_atomic's temp file fails
        real(path, text)
    monkeypatch.setattr(listchanges, "write_atomic", fail_on_drugs)
    assert listchanges.apply(export(tmp_path, [ADD]), confirm=True, now=NOW) == 1
    assert snapshot(lex) == before
    err = capsys.readouterr().err
    assert "cannot write" in err and "drugs.json:" in err and ".tmp" not in err and "cannot read" not in err


def _edit_brands(base, brands, **extra):
    return {"action": "edit", "entry_key": base["canonical"].casefold(), "data": {"brands": brands, **extra}}


def _add_brand(name, generic, **extra):
    return {"action": "add", "entry_key": name.casefold(), "data": {"name": name, "generic": generic, **extra}}


@pytest.mark.parametrize("name, add_first", [("Aaaqbrand", True), ("Zzzqbrand", False)])
def test_an_add_and_an_edit_of_one_entry_keep_the_added_brand_in_either_order(lex, tmp_path, capsys, name, add_first):
    base = seed_only_entry()
    edit = _edit_brands(base, base["brands"], safety=True)
    add = _add_brand(name, base["canonical"])
    path = export(tmp_path, [add, edit] if add_first else [edit, add])
    assert listchanges.apply(path, confirm=False, now=NOW) == 2
    plan = [line for line in capsys.readouterr().out.splitlines() if line.startswith("  ")]
    assert plan == [f"  {base['canonical']}: + brand {name}; safety None -> True"]      # one line per entry
    assert listchanges.apply(path, confirm=True, now=NOW) == 0
    assert entry(base["canonical"]) == {**base, "brands": [*base["brands"], name], "safety": True}
    assert build.do_check(build.DEFAULT_SEED) == 0


def test_two_adds_to_one_new_generic_are_one_plan_line(lex, tmp_path, capsys):
    path = export(tmp_path, [_add_brand("Qqqone", "Zyxoprazole"), _add_brand("Qqqtwo", "Zyxoprazole")])
    assert listchanges.apply(path, confirm=False, now=NOW) == 2
    plan = [line for line in capsys.readouterr().out.splitlines() if line.startswith("  ")]
    assert plan == ["  add Qqqone (generic Zyxoprazole); + brand Qqqtwo"]


def test_safety_false_after_stacking_leaves_the_key_out(lex, tmp_path):
    base = seed_only_entry()
    path = export(tmp_path, [_add_brand("Qqqsafe", base["canonical"], safety=False),
                             _edit_brands(base, base["brands"], safety=False)])
    assert listchanges.apply(path, confirm=True, now=NOW) == 0
    got = entry(base["canonical"])
    assert "safety" not in got and got["brands"] == [*base["brands"], "Qqqsafe"]
