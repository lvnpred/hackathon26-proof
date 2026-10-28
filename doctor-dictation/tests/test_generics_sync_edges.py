"""Plan I2-d Tasks 1-3, hardening: CSV edge cases, gate classes, sync safety, reader isolation. Offline; synthetic data."""
import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

from doctor_dictation.core import generics
from doctor_dictation.core.determinism import correct_drugs, validate_structured
from test_generics_sync import NLEM, SRC, gs, sync          # noqa: F401  (gs: generics_sync on a tmp copy of the frozen lexicon)
from test_lexicon_import import build                        # noqa: F401

LIVE = Path(__file__).resolve().parents[1] / "doctor_dictation" / "core" / "lexicon"
GOOD = ("--source-id", "edge-1", *SRC)


def write(tmp_path, text, name="e.csv", raw=None):
    p = tmp_path / name
    p.write_bytes(raw if raw is not None else text.encode("utf-8"))
    return p


def plan(gs, rows, current=None, rules=None, apply_removals=False, src="edge-1"):
    return gs.plan_sync(rows, current, gs.build.load_drugs()["entries"], rules or gs.load_rules(), src, apply_removals)


def row(generic, schedule="", line=2, src_line=""):
    return {"line": line, "generic": generic, "list": "NLEM", "schedule": schedule, "source_line": src_line}


def test_csv_crlf_extra_columns_schedule_spellings_and_long_source_line(gs, tmp_path):
    p = write(tmp_path, "", raw=("generic,list,extra,schedule,source_line\r\nOndansetron,NLEM,zz,h1,1\r\n"
                                 "Cetirizine,NLEM,zz,Schedule X ,%s\r\nParacetamol,NLEM,zz, ,\r\n" % ("9" * 30)).encode())
    rows = gs.read_csv(p, {})
    assert [(r["generic"], r["schedule"]) for r in rows] == [("Ondansetron", "H1"), ("Cetirizine", "X"), ("Paracetamol", "")]
    assert rows[1]["source_line"] == "9" * 20 and "extra" not in rows[0]


def test_csv_caps_row_count_field_size_empty_file_and_blank_or_odd_list_names(gs, tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "MAX_ROWS", 2)
    with pytest.raises(SystemExit, match="more than 2 rows"):
        gs.read_csv(write(tmp_path, "generic,list\nA,N\nB,N\nC,N\n"), {})
    assert len(gs.read_csv(write(tmp_path, "generic,list\nA,N\nB,N\n"), {})) == 2          # exactly at the cap is fine
    with pytest.raises(SystemExit, match="cannot be read"):
        gs.read_csv(write(tmp_path, "generic,list\n%s,NLEM\n" % ("A" * (csv.field_size_limit() + 5))), {})
    for text, why in [("generic,list\n", "no rows"), ("generic,list\nA,\n", "list name"), ("generic,list\nA,2025\n", "list name"),
                      ("generic,list\nA,%s\n" % ("N" * 41), "list name")]:
        with pytest.raises(SystemExit, match=why):
            gs.read_csv(write(tmp_path, text), {})


def test_gates_title_case_combinations_notes_shape_and_never_fuzzy(gs, tmp_path):
    p = write(tmp_path, "generic,list\nONDANSETRON,NLEM\nParacetamol / Cetirizine (oral),NLEM\n")
    assert [r["generic"] for r in gs.read_csv(p, {})] == ["Ondansetron", "Paracetamol + Cetirizine"]
    rows = [row("Paracetamoll", line=2), row("A" * 81, line=3), row("1Tab", line=4), row("", line=5), row("Dose, 5mg", line=6),
            row("Zinc+", line=7)]
    data, rep = plan(gs, rows)
    assert [(e["generic"], e["lexicon"]) for e in data["entries"]] == [("Paracetamoll", "")]       # one slip is NEVER linked
    assert rep["new_generics"] == [{"generic": "Paracetamoll", "near": ["Paracetamol"], "twins": ["Paracetamol"]}]
    assert [(s["line"], s["checks"]) for s in rep["skipped"]] == [(n, ["shape"]) for n in (3, 4, 5, 6, 7)]


def test_curated_skip_is_a_class_dict_and_skipped_rows_never_enter(gs):
    rules = {**gs.load_rules(), "skip_generics": {"zorbexamide"}}
    data, rep = plan(gs, [row("Zorbexamide", line=2), row("Cetirizine", line=3)], rules=rules)
    assert [e["generic"] for e in data["entries"]] == ["Cetirizine"] and rep["skipped"] == [
        {"line": 2, "generic": "Zorbexamide", "checks": ["curated-skip"]}]
    rules_json = json.loads((LIVE / "import_rules.json").read_text(encoding="utf-8"))
    assert rules_json["skip_generics"] == {} and gs.load_rules()["skip_generics"] == set()


def test_skip_generics_accepts_a_class_dict_in_the_rules_file(gs, tmp_path):
    p = tmp_path / "rules.json"
    raw = json.loads((LIVE / "import_rules.json").read_text(encoding="utf-8"))
    p.write_text(json.dumps({**raw, "skip_generics": {"hospital-only": ["Zorbexamide", "Zorbex2"]}}), encoding="utf-8")
    assert gs.load_rules(p)["skip_generics"] == {"zorbexamide", "zorbex2"}


def test_a_generic_present_with_a_bad_schedule_is_not_a_removal(gs):
    cur, _ = plan(gs, [row("Cetirizine", "H", 2), row("Ondansetron", "", 3)])
    data, rep = plan(gs, [row("Cetirizine", "Q", 2)], current=cur, apply_removals=True, src="edge-2")      # typo'd schedule
    assert rep["removed"] == ["Ondansetron"] and rep["dropped"] == ["Ondansetron"]
    by = {e["generic"]: e for e in data["entries"]}
    assert by["Cetirizine"]["lists"]["NLEM"]["schedule"] == "H"                    # kept, not dropped, not changed
    assert [s["checks"] for s in rep["skipped"]] == [["bad-schedule"]]


def test_removal_keeps_other_lists_and_drops_only_the_empty_entry(gs):
    cur = {"entries": [{"generic": "Cetirizine", "lexicon": "Cetirizine", "lists": {
        "NLEM": {"src": "a"}, "Schedules": {"src": "b", "schedule": "H"}}},
        {"generic": "Zorbexamide", "lexicon": "", "lists": {"NLEM": {"src": "a"}}}], "sources": [], "version": "0.3.0"}
    data, rep = plan(gs, [row("Ondansetron", "", 2)], current=cur, apply_removals=True)
    by = {e["generic"]: e for e in data["entries"]}
    assert list(by["Cetirizine"]["lists"]) == ["Schedules"] and rep["dropped"] == ["Zorbexamide"]
    assert rep["removed"] == ["Cetirizine", "Zorbexamide"] and "Zorbexamide" not in by      # an entry left with no list is dropped
    assert data["version"] == "0.3.0"                                                # plan_sync never bumps; do_sync does


def test_three_way_conflict_and_a_repeated_schedule_after_a_conflict(gs):
    data, rep = plan(gs, [row("Cetirizine", "H", 2), row("Cetirizine", "X", 3), row("Cetirizine", "H", 4), row("Cetirizine", "H1", 5)])
    assert rep["conflicts"] == [{"generic": "Cetirizine", "lines": [2, 3, 5], "schedules": ["H", "X", "H1"]}]
    assert [(s["line"], s["checks"], s["first_line"]) for s in rep["skipped"]] == [(4, ["duplicate"], 2)]
    assert "schedule" not in data["entries"][0]["lists"]["NLEM"]


def test_the_lexicon_link_is_recomputed_for_kept_generics_but_the_lists_are_untouched(gs):
    cur = {"entries": [{"generic": "Cetirizine", "lexicon": "", "lists": {"Other": {"src": "o", "schedule": "X"}}}],
           "sources": [], "version": "0.1.0"}
    data, _ = plan(gs, [row("Ondansetron", "", 2)], current=cur)
    (cet,) = [e for e in data["entries"] if e["generic"] == "Cetirizine"]
    assert cet["lexicon"] == "Cetirizine" and cet["lists"] == {"Other": {"src": "o", "schedule": "X"}}


def test_a_reused_source_id_with_another_file_is_refused_and_nothing_changes(gs, monkeypatch, tmp_path):
    sync(gs, monkeypatch, "--csv", str(NLEM), *GOOD, "--report", str(tmp_path / "a.json"))
    before = gs.GENERICS_JSON.read_bytes()
    other = write(tmp_path, "generic,list\nCetirizine,NLEM\n", "o.csv")
    with pytest.raises(SystemExit, match="already used for another file"):
        sync(gs, monkeypatch, "--csv", str(other), *GOOD, "--report", str(tmp_path / "b.json"))
    assert gs.GENERICS_JSON.read_bytes() == before and not (tmp_path / "b.json").exists()


def test_a_no_change_run_keeps_the_version_the_report_and_the_live_lexicon_files(gs, monkeypatch, tmp_path):
    live = {n: (LIVE / n).read_bytes() for n in ("drugs.json", "imported.json", "seed_extra.json", "import_rules.json")}
    sync(gs, monkeypatch, "--csv", str(NLEM), *GOOD, "--source-url", "https://example.invalid/x", "--report", str(tmp_path / "a.json"))
    report = (tmp_path / "a.json").read_bytes()
    (tmp_path / "a.json").write_bytes(b"{}")                                       # a second run must not rewrite it
    sync(gs, monkeypatch, "--csv", str(NLEM), *GOOD, "--source-url", "https://example.invalid/x", "--report", str(tmp_path / "a.json"))
    data = json.loads(gs.GENERICS_JSON.read_text(encoding="utf-8"))
    assert (tmp_path / "a.json").read_bytes() == b"{}" and report != b"{}" and data["version"] == "0.1.0"
    (src,) = data["sources"]
    assert src["url"] == "https://example.invalid/x" and src["licence"].startswith("Synthetic") and src["published"] == "2022-09-13"
    assert {n: (LIVE / n).read_bytes() for n in live} == live          # the live lexicon files are never touched by a test sync
    for e in data["entries"]:
        assert all(m["src"] == "edge-1" for m in e["lists"].values())              # lineage on every membership


def test_licence_and_published_have_no_default_and_a_bad_date_is_refused(gs, monkeypatch, tmp_path):
    for published in ("2022-13-45", "20220913", "2022-9-13", ""):
        with pytest.raises(SystemExit) as exc:
            sync(gs, monkeypatch, "--csv", str(NLEM), "--source-id", "edge-1", "--source-name", "X fixture", "--licence",
                 "Synthetic test data, public domain (test only)", "--published", published, "--report", str(tmp_path / "r.json"))
        assert exc.value.code == 2
    assert not gs.GENERICS_JSON.exists()
    src = Path(gs.__file__).read_text(encoding="utf-8")
    assert "default=" not in src                                                   # no argparse default for any source flag


def test_a_corrupt_current_generics_file_stops_the_sync_cleanly(gs, monkeypatch, tmp_path):
    gs.GENERICS_JSON.write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit, match="not valid JSON"):
        sync(gs, monkeypatch, "--csv", str(NLEM), *GOOD, "--report", str(tmp_path / "a.json"))
    assert gs.GENERICS_JSON.read_text() == "{not json" and not (tmp_path / "a.json").exists()


def test_check_with_a_new_id_but_identical_entries_is_drift_because_the_source_is_unrecorded(gs, monkeypatch, tmp_path, capsys):
    sync(gs, monkeypatch, "--csv", str(NLEM), *GOOD, "--report", str(tmp_path / "a.json"))
    monkeypatch.setattr(sys, "argv", ["generics_sync.py", "sync", "--check", "--csv", str(NLEM), "--source-id", "edge-9", *SRC])
    assert gs.main() == 1
    out = capsys.readouterr().out
    assert "source edge-9 is not recorded in generics.json (run the sync to record it)" in out and "added=0" not in out


# ---- reader: isolation and information only ---------------------------------------------------------------------

FIX = Path(__file__).parent / "data" / "generics_fixture.json"
T = "tab crocin 500 mg sos, tab paracetamol 500 mg, tab prednisolone 5 mg, tab zorbexamide 5 mg"


def rows_for(names):
    s, _ = validate_structured({"rx": [{"form": "Tab.", "name": n} for n in names]}, T, T)
    return s["rx"]


def test_grounding_is_identical_with_and_without_a_generics_file_except_schedule(monkeypatch):
    names = ["Crocin", "Paracetamol", "Prednisolone", "Zorbexamide", "Zzqxwv"]
    monkeypatch.setattr(generics, "GENERICS_PATH", FIX)
    generics.reset()
    with_file = rows_for(names)
    monkeypatch.setattr(generics, "GENERICS_PATH", FIX.with_name("absent.json"))
    generics.reset()
    without = rows_for(names)
    generics.reset()
    strip = lambda rs: [{k: v for k, v in r.items() if k != "schedule"} for r in rs]          # noqa: E731
    assert strip(with_file) == strip(without) and [r["schedule"] for r in without] == [""] * 5
    assert [r["schedule"] for r in with_file] == ["H", "H", "X", "", ""]
    assert all(set(r) - set(w) <= {"schedule"} for r, w in zip(with_file, without))


def test_a_government_only_generic_never_rewrites_a_transcript_or_becomes_a_known_name(monkeypatch):
    text = "tab zorbexamida 5 mg and tab zorbexamid 5 mg"
    before = correct_drugs(text)
    monkeypatch.setattr(generics, "GENERICS_PATH", FIX)
    generics.reset()
    assert correct_drugs(text) == before == text
    assert rows_for(["Zorbexamide"])[0]["status"] == "unknown-medicine" and rows_for(["Zorbexamide"])[0]["lexicon_match"] == ""
    generics.reset()


def test_reader_ignores_entries_without_a_lexicon_link_junk_marks_and_is_case_insensitive(monkeypatch, tmp_path):
    p = tmp_path / "g.json"
    p.write_text(json.dumps({"entries": [
        {"generic": "Zorbexamide", "lexicon": "", "lists": {"L": {"schedule": "X"}}},
        {"generic": "Cetirizine", "lexicon": "Cetirizine", "lists": {"A": {"schedule": "h"}, "B": {"schedule": "H1"}, "C": 5, "D": {"schedule": "X "}}},
        "junk", {"lexicon": "Ondansetron", "lists": "nope"}, {"lexicon": "Paracetamol", "lists": {"L": {"schedule": "H"}}, "extra": [1]}],
        "version": 3}), encoding="utf-8")
    monkeypatch.setattr(generics, "GENERICS_PATH", p)
    generics.reset()
    assert [generics.schedule_of(n) for n in ("Zorbexamide", "cetirizine", "CETIRIZINE", "Ondansetron", "paracetamol", None, 7)] == \
        ["", "H1", "H1", "", "H", "", ""] and generics.generics_version() == "3"
    generics.reset()


def test_the_shipped_path_is_beside_the_lexicon_and_a_missing_file_is_an_empty_list(monkeypatch, tmp_path):
    assert generics.GENERICS_PATH == LIVE / "generics.json"
    monkeypatch.setattr(generics, "GENERICS_PATH", tmp_path / "never-written.json")
    generics.reset()
    assert [r["schedule"] for r in rows_for(["Crocin", "Paracetamol"])] == ["", ""] and generics.generics_version() == ""
    generics.reset()
