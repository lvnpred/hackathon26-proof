"""Plan I2-d: the generics list importer and sync. Offline; synthetic fixtures; writes only under tmp_path."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

from test_lexicon_import import FROZEN, build, load      # noqa: F401  (build: a tmp copy of the frozen lexicon)

DATA = Path(__file__).parent / "data"
NLEM, NEWER = DATA / "generics_nlem_fixture.csv", DATA / "generics_nlem_newer_fixture.csv"
SRC = ("--source-name", "NLEM fixture", "--licence", "Synthetic test data, public domain (test only)", "--published", "2022-09-13")

@pytest.fixture()
def gs(build, tmp_path, monkeypatch):
    mod = load("generics_sync")
    monkeypatch.setattr(mod, "build", build)
    monkeypatch.setattr(mod, "GENERICS_JSON", tmp_path / "generics.json")
    monkeypatch.setattr(mod, "PAIRS_JSON", tmp_path / "lasa_pairs.json")
    (tmp_path / "lasa_pairs.json").write_text(json.dumps({"note": "test", "pairs": []}), encoding="utf-8")
    return mod

def sync(gs, monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["generics_sync.py", "sync", *argv])
    return gs.main()

def test_the_csv_contract_reads_cleans_and_refuses_bad_files(gs, tmp_path):
    rows = gs.read_csv(NLEM, {})
    assert (len(rows), rows[1], rows[9]["generic"]) == (11, {"line": 3, "generic": "Paracetamol", "list": "NLEM", "schedule": "", "source_line": "1.3"},
                                                      "Amoxicillin + Clavulanic acid")
    assert rows[9]["schedule"] == "H" and rows[10]["schedule"] == "Q"           # checked later, by the gates
    p = tmp_path / "c.csv"
    for text, why in [("generic,schedule\nX,\n", "needs the columns"), ("generic,list\nA,NLEM\nB,NLEM 2025\n", "one list per file")]:
        p.write_text(text, encoding="utf-8")
        with pytest.raises(SystemExit, match=why):
            gs.read_csv(p, {})
    p.write_bytes("﻿GENERIC,List\nCetirizine,NLEM\n".encode("utf-8"))           # a BOM and upper-case column names
    assert gs.read_csv(p, {}) == [{"line": 2, "generic": "Cetirizine", "list": "NLEM", "schedule": "", "source_line": ""}]
    (tmp_path / "bad.csv").write_bytes(b"generic,list\n\xff,NLEM\n")
    with pytest.raises(SystemExit, match="not UTF-8"):
        gs.read_csv(tmp_path / "bad.csv", {})

def test_the_gates_link_exact_and_synonym_and_report_new_duplicate_conflict_shape_and_schedule(gs):
    data, rep = gs.plan_sync(gs.read_csv(NLEM, {}), {}, gs.build.load_drugs()["entries"], gs.load_rules(), "nlem-2022")
    by = {e["generic"]: e for e in data["entries"]}
    assert {g: e["lexicon"] for g, e in by.items()} == {"Amoxicillin + Clavulanic acid": "Co-Amoxiclav", "Cetirizine": "Cetirizine",
        "Levothyroxine": "Thyroxine", "Ondansetron": "Ondansetron", "Paracetamol": "Paracetamol", "Zorbexamide": "", "Zorbexonide": ""}
    assert by["Amoxicillin + Clavulanic acid"]["lists"]["NLEM"] == {"line": "6.2", "schedule": "H", "src": "nlem-2022"}
    assert "schedule" not in by["Ondansetron"]["lists"]["NLEM"]                                # a conflict is never guessed
    assert rep["linked"] == {"exact": 3, "synonym": 2} and rep["new"] == 2 and rep["rows_read"] == 11
    assert [(s["line"], s["checks"]) for s in rep["skipped"]] == [(7, ["duplicate"]), (10, ["shape"]), (12, ["bad-schedule"])]
    assert rep["conflicts"] == [{"generic": "Ondansetron", "lines": [8, 9], "schedules": ["H", "H1"]}]
    assert rep["new_generics"] == [{"generic": "Zorbexamide", "near": [], "twins": ["Zorbexonide"]},
                                   {"generic": "Zorbexonide", "near": [], "twins": ["Zorbexamide"]}]

def test_the_sync_writes_lineage_and_a_second_run_is_byte_identical(gs, monkeypatch, tmp_path, capsys):
    argv = ("--csv", str(NLEM), "--source-id", "nlem-2022", *SRC, "--report", str(tmp_path / "r.json"))
    sync(gs, monkeypatch, *argv)
    first = gs.GENERICS_JSON.read_bytes()
    data = json.loads(first)
    assert data["version"] == "0.1.0" and len(data["entries"]) == 7 and first.endswith(b"}\n") and b"\r\n" not in first
    (src,) = data["sources"]
    assert {k: src[k] for k in ("id", "list", "published", "rows_read")} == {"id": "nlem-2022", "list": "NLEM", "published": "2022-09-13", "rows_read": 11}
    assert src["input_sha256"] == hashlib.sha256(NLEM.read_bytes()).hexdigest() and "notes" not in first.decode()
    sync(gs, monkeypatch, *argv)
    assert gs.GENERICS_JSON.read_bytes() == first and "no change" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["generics_sync.py", "sync", "--check", "--csv", str(NLEM), "--source-id", "nlem-2022", *SRC])
    assert gs.main() == 0

def test_the_licence_gate_refuses_before_reading_anything(gs, monkeypatch, tmp_path):
    monkeypatch.setattr(gs, "read_csv", lambda *a: pytest.fail("read before the gate"))
    good = {"--source-id": "nlem-2022", "--source-name": "NLEM fixture", "--licence": "Synthetic test data, public domain (test only)",
            "--published": "2022-09-13", "--report": str(tmp_path / "r.json")}
    cases = [{k: v for k, v in good.items() if k != drop} for drop in good] + [
        {**good, "--published": "13-09-2022"}, {**good, "--source-id": "promoted-x"}, {**good, "--licence": "short"},
        {**good, "--report": str(Path(gs.HERE) / "r.json")}]                         # a report inside the repository
    for argv in cases:
        with pytest.raises(SystemExit) as exc:
            sync(gs, monkeypatch, "--csv", str(NLEM), *[x for kv in argv.items() for x in kv])
        assert exc.value.code == 2, argv
    assert not gs.GENERICS_JSON.exists()

def test_a_newer_list_reports_added_changed_removed_and_renames_and_keeps_what_was_removed(gs, monkeypatch, tmp_path):
    sync(gs, monkeypatch, "--csv", str(NLEM), "--source-id", "nlem-2022", *SRC, "--report", str(tmp_path / "a.json"))
    newer = ("--csv", str(NEWER), "--source-id", "nlem-2025", "--source-name", "NLEM newer fixture", "--licence",
             "Synthetic test data, public domain (test only)", "--published", "2025-01-01")
    sync(gs, monkeypatch, *newer, "--report", str(tmp_path / "b.json"))
    rep, data = json.loads((tmp_path / "b.json").read_text()), json.loads(gs.GENERICS_JSON.read_text())
    assert rep["added"] == ["Zorbexamida"] and rep["removed"] == ["Zorbexamide", "Zorbexonide"] and rep["removals_applied"] is False
    assert rep["changed"] == [{"generic": "Amoxicillin + Clavulanic acid", "list": "NLEM", "new": "H1", "old": "H"},
                              {"generic": "Ondansetron", "list": "NLEM", "new": "H", "old": ""}]
    assert rep["possible_renames"] == [{"added": "Zorbexamida", "removed": "Zorbexamide"}]
    by = {e["generic"]: e for e in data["entries"]}
    assert by["Zorbexamide"]["lists"]["NLEM"]["src"] == "nlem-2022" and data["version"] == "0.2.0"     # kept, old lineage
    sync(gs, monkeypatch, *newer[:3], "nlem-2025b", *newer[4:], "--apply-removals", "--report", str(tmp_path / "c.json"))
    rep = json.loads((tmp_path / "c.json").read_text())
    assert rep["dropped"] == ["Zorbexamide", "Zorbexonide"] and rep["removals_applied"] is True
    assert {e["generic"] for e in json.loads(gs.GENERICS_JSON.read_text())["entries"]} >= {"Zorbexamida"}

def test_check_mode_reports_drift_and_writes_nothing(gs, monkeypatch, tmp_path, capsys):
    sync(gs, monkeypatch, "--csv", str(NLEM), "--source-id", "nlem-2022", *SRC, "--report", str(tmp_path / "a.json"))
    before = gs.GENERICS_JSON.read_bytes()
    monkeypatch.setattr(sys, "argv", ["generics_sync.py", "sync", "--check", "--csv", str(NEWER), "--source-id", "nlem-2025", *SRC])
    assert gs.main() == 1 and gs.GENERICS_JSON.read_bytes() == before
    out = capsys.readouterr().out
    assert "check FAILED" in out and "added=1 changed=2 removed=2 (kept)" in out
