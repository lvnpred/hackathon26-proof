"""Promotion of names many clinics learned (plan I1-g simple, Task 4): counts only, read-only, clinician-gated. Offline."""
import csv
import hashlib
import json
import re
import shutil
from contextlib import closing
from pathlib import Path

import pytest

from doctor_dictation import admin, clinics, promotion
from doctor_dictation import db as dbmod
from doctor_dictation.core.formulary import key
from doctor_dictation.core.lexicon import build
from doctor_dictation.db import formulary as fdb
from doctor_dictation.scope import clinic_dir

DATA = Path(__file__).parent / "data"
CONFLICT = str(DATA / "conflict_fixture.csv")
PEPPER = "test-pepper-0123456789-abcdefghijklmnop"
EMPTY = json.dumps({"entries": [], "version": "dd-promotion-v2"}, indent=2) + "\n"


@pytest.fixture()
def lexicon(tmp_path, monkeypatch):
    """build.py and the ledger work on copies: the frozen lexicon and an empty ledger."""
    shutil.copy(DATA / "lexicon_frozen.json", tmp_path / "drugs.json")
    (tmp_path / "ledger.json").write_text(EMPTY, encoding="utf-8")
    monkeypatch.setenv("PROMOTION_LEDGER_PEPPER", PEPPER)
    monkeypatch.setattr(build, "DRUGS_JSON", tmp_path / "drugs.json")
    monkeypatch.setattr(build, "IMPORTED_JSON", tmp_path / "imported.json")
    monkeypatch.setattr(promotion, "LEDGER_JSON", tmp_path / "ledger.json")
    return tmp_path


def learn(path, *names, generic="", removed=()):
    """Confirm each name on two saved prescriptions (the learning threshold), then soft-remove ``removed``."""
    with closing(dbmod.get_conn(path)) as conn:
        dbmod.migrate(conn)
        eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "40 / M", None))
        docs = [dbmod.save_document(conn, eid, f"sha{i}", {"rx": []}) for i in range(2)]
        for name in names:
            for doc in docs:
                fdb.record_confirmation(conn, key(name), name, generic if name == "Zorbexin" else "", doc, None)
        for row in fdb.list_active(conn):
            if row["name"] in removed:
                fdb.remove(conn, row["id"])


@pytest.fixture()
def three_clinics(multi, lexicon):
    common = ("Zorbexin", "Ravi Kulkarni", "Crocin", "Murexol", "Taxivane", "Glycomat")
    for slug, extra, removed in (("alpha", ("Velquara",), ()), ("beta", ("Velquara",), ()), ("gamma", (), ("Taxivane",))):
        clinics.provision_clinic(slug, slug.title() + " Clinic")
        learn(clinic_dir(slug) / "app.db", *common, *extra, generic="paracetamol", removed=removed)
    entry = {"batch": "2026-09", "date": "2026-09-30", "decision": "reject", "key": promotion.ledger_key("Murexol"),
             "outcome": "rejected", "reviewer": "Dr. K. Iyer"}
    promotion.LEDGER_JSON.write_text(json.dumps({"entries": [entry], "pepper_check": promotion.pepper_check(),
                                                 "version": "dd-promotion-v2"}) + "\n", encoding="utf-8")
    return multi


def digests(root):
    """sha256 of every clinic database (SQLite may add its usual -wal/-shm side files when it reads, as the app does)."""
    return {p.parent.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob("clinics/*/app.db"))}


def test_candidates_count_clinics_and_exclude_what_must_not_be_proposed(three_clinics, tmp_path):
    before = digests(three_clinics)
    out = tmp_path / "review" / "candidates.csv"
    assert admin.main(["promote-candidates", "--out", str(out), "--conflict-map", CONFLICT]) == 0
    text = out.read_text(encoding="utf-8")
    header, row = text.splitlines()
    assert header == "name,generic,clinics_count,first_seen,last_seen,decision,reviewer,notes"
    assert re.fullmatch(r"Zorbexin,Paracetamol,3,(\d{4}-\d\d-\d\d),\1,,,", row)            # counts only, empty review columns
    assert not any(s in text.lower() for s in ("alpha", "beta", "gamma", "ravi"))           # no clinic, no person
    _rows, why, failed = promotion.candidates(3, promotion.LEX.read_csv(CONFLICT))
    assert failed == {} and dict(why) == {"fewer-clinics": 2, "in-lexicon": 1, "person-like": 1, "reviewed": 1,
                                          "5-one-slip": 1}    # Velquara + removed Taxivane, Crocin, Ravi, Murexol, Glycomat
    assert digests(three_clinics) == before                                                 # no clinic file changed


def test_single_mode_reads_the_one_database_and_proposes_only_with_min_clinics_1(lexicon, monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "single.db"))
    learn(tmp_path / "single.db", "Zorbexin", generic="paracetamol")
    rows, why, _failed = promotion.candidates(3, [])
    assert rows == [] and dict(why) == {"fewer-clinics": 1}
    rows, _why, _failed = promotion.candidates(1, [])
    assert [(r["name"], r["generic"], r["clinics_count"]) for r in rows] == [("Zorbexin", "Paracetamol", 1)]


def test_the_review_csv_never_lands_inside_the_repository(tmp_path):
    with pytest.raises(SystemExit, match="inside the repository"):
        promotion.write_review(promotion.REPO / "docs" / "candidates.csv", [])
    promotion.write_review(tmp_path / "ok.csv", [])
    assert (tmp_path / "ok.csv").read_text(encoding="utf-8").startswith("name,generic,clinics_count")


def review(tmp_path, *rows):
    path = tmp_path / "reviewed.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(promotion.COLUMNS)
        w.writerows(rows)
    return path


ROWS = (("Zorbexin", "Paracetamol", 3, "2026-10-01", "2026-10-30", "approve", "", ""),
        ("Velquara", "Zorlexin", 3, "2026-10-01", "2026-10-30", "approve", "", "generic unknown"),
        ("Quenrix", "", 3, "2026-10-01", "2026-10-30", "approve", "", "no generic given"),
        ("Storvaz", "Atorvastatin", 3, "2026-10-01", "2026-10-30", "approve", "", ""),
        ("Murexol", "", 4, "2026-10-01", "2026-10-30", "reject", "Dr. K. Iyer", "a surname"),
        ("Taxivane", "", 3, "2026-10-01", "2026-10-30", "", "", ""))


def test_apply_refuses_without_a_reviewer_a_new_batch_or_confirm(lexicon, tmp_path):
    path, before = review(tmp_path, *ROWS), (lexicon / "drugs.json").read_bytes()
    for reviewer, batch, message in (("", "2026-11", "needs --reviewer"), ("Dr. Asha Rao", "Bad Batch", "--batch must be")):
        with pytest.raises(SystemExit, match=message) as refused:
            promotion.apply(path, batch, reviewer, [], True, "2026-11-02")
        assert refused.value.code == 2
    code, outcomes = promotion.apply(path, "2026-11", "Dr. Asha Rao", [], False, "2026-11-02")
    assert code == 2 and outcomes["added"] == 1
    assert (lexicon / "drugs.json").read_bytes() == before and (lexicon / "ledger.json").read_text() == EMPTY


def test_apply_merges_only_approved_rows_that_pass_and_ledgers_every_decision(lexicon, tmp_path):
    code, outcomes = promotion.apply(review(tmp_path, *ROWS), "2026-11", "Dr. Asha Rao", [], True, "2026-11-02")
    assert code == 0 and dict(outcomes) == {"added": 1, "clinic-only": 3, "rejected": 1, "undecided or already reviewed": 1}
    data = json.loads((lexicon / "drugs.json").read_text(encoding="utf-8"))
    para = next(e for e in data["entries"] if e["canonical"] == "Paracetamol")
    assert para["brands"][-1] == "Zorbexin" and para["lineage"] == {
        "Zorbexin": {"date": "2026-11-02", "reviewer": "Dr. Asha Rao", "src": "promoted-2026-11"}}
    assert (data["sources"][0]["id"], data["sources"][0]["reviewer"]) == ("promoted-2026-11", "Dr. Asha Rao")
    ledger_text = (lexicon / "ledger.json").read_text(encoding="utf-8")
    ledger = json.loads(ledger_text)["entries"]
    assert sorted(r["outcome"] for r in ledger) == ["added", "clinic-only: 1-generic", "clinic-only: 1-generic",
                                                        "clinic-only: 5-one-slip", "rejected"]
    assert [r["key"] for r in ledger] == sorted(r["key"] for r in ledger) and ledger_text.endswith("}\n")
    assert "Murexol" not in ledger_text and "Velquara" not in ledger_text and "Storvaz" not in ledger_text   # hashes only
    with pytest.raises(SystemExit, match="new --batch"):
        promotion.apply(review(tmp_path, *ROWS), "2026-11", "Dr. Asha Rao", [], True, "2026-11-03")
    assert (lexicon / "ledger.json").read_text(encoding="utf-8") == ledger_text


def test_candidates_open_read_only_and_touch_only_the_formulary_table(three_clinics, monkeypatch):
    uris, sql = [], []
    real = promotion.sqlite3.connect

    def spy(target, *a, **kw):
        conn = real(target, *a, **kw)
        uris.append(target)
        conn.set_trace_callback(sql.append)
        return conn

    monkeypatch.setattr(promotion.sqlite3, "connect", spy)
    promotion.candidates(3, [])
    clinic_uris = [u for u in uris if "app.db" in u]                      # the 4th connection is the clinic directory
    assert len(clinic_uris) == 3 and all(u.endswith("app.db?mode=ro") for u in clinic_uris)
    text = " ".join(sql).lower()
    assert "clinic_formulary" in text
    for forbidden in ("patients", "documents", "users", "added_by", "insert", "update", "delete"):
        assert forbidden not in text


def test_an_unreadable_clinic_is_reported_exit_1_and_the_csv_is_still_written(three_clinics, tmp_path, capsys):
    (clinic_dir("beta") / "app.db").unlink()
    out = tmp_path / "review" / "c.csv"
    assert admin.main(["promote-candidates", "--out", str(out), "--conflict-map", CONFLICT, "--min-clinics", "2"]) == 1
    assert out.exists() and not (clinic_dir("beta") / "app.db").exists()          # read-only open never creates a file
    assert "beta: FAILED" in capsys.readouterr().out


def test_min_clinics_is_honoured_and_must_be_positive(three_clinics, tmp_path):
    rows, _why, _f = promotion.candidates(4, promotion.LEX.read_csv(CONFLICT))
    assert rows == []
    with pytest.raises(SystemExit, match="--min-clinics"):
        admin.main(["promote-candidates", "--out", str(tmp_path / "x.csv"), "--conflict-map", CONFLICT, "--min-clinics", "0"])


def test_apply_cli_needs_reviewer_and_confirm_and_a_bad_source_is_a_clean_refusal(lexicon, tmp_path, capsys):
    path, before = review(tmp_path, *ROWS), (lexicon / "drugs.json").read_bytes()
    base = ["promote-apply", "--csv", str(path), "--batch", "2026-11", "--conflict-map", CONFLICT]
    with pytest.raises(SystemExit, match="--reviewer"):
        admin.main(base)
    assert admin.main(base + ["--reviewer", "Dr. Asha Rao"]) == 2
    assert "nothing written" in capsys.readouterr().out
    assert (lexicon / "drugs.json").read_bytes() == before and (lexicon / "ledger.json").read_text() == EMPTY
    assert admin.main(base + ["--reviewer", "Dr. Asha Rao", "--confirm"]) == 0
    assert (lexicon / "drugs.json").read_bytes() != before


def test_a_refused_source_gate_writes_nothing(lexicon, tmp_path, monkeypatch):
    def refuse(_source):
        raise ValueError("an import needs --source-id")
    monkeypatch.setattr(build, "check_source", refuse)
    before = (lexicon / "drugs.json").read_bytes()
    with pytest.raises(SystemExit, match="needs --source-id"):
        promotion.apply(review(tmp_path, *ROWS), "2026-11", "Dr. Asha Rao", [], True, "2026-11-02")
    assert (lexicon / "drugs.json").read_bytes() == before and (lexicon / "ledger.json").read_text() == EMPTY


def test_a_removed_row_is_never_proposed_even_if_its_count_survived(lexicon, monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "single.db"))
    learn(tmp_path / "single.db", "Zorbexin", generic="paracetamol")
    with closing(dbmod.get_conn(tmp_path / "single.db")) as conn:
        conn.execute("UPDATE clinic_formulary SET removed_at = '2026-10-01T00:00:00Z'")      # count stays 2: only removed_at differs
        conn.commit()
    rows, why, _failed = promotion.candidates(1, [])
    assert rows == [] and sum(why.values()) == 0


def test_the_ledger_records_are_key_sorted_and_carry_the_row_reviewer_over_the_batch_reviewer(lexicon, tmp_path):
    promotion.apply(review(tmp_path, *ROWS), "2026-11", "Dr. Asha Rao", [], True, "2026-11-02")
    ledger = json.loads((lexicon / "ledger.json").read_text(encoding="utf-8"))["entries"]
    assert all(list(r) == sorted(r) for r in ledger)                                      # byte-stable key order
    by_key = {r["key"]: r["reviewer"] for r in ledger}
    assert by_key[promotion.ledger_key("Murexol")] == "Dr. K. Iyer"
    assert by_key[promotion.ledger_key("Zorbexin")] == "Dr. Asha Rao"


def test_both_commands_fail_closed_without_a_pepper_before_opening_or_writing_anything(three_clinics, tmp_path, monkeypatch, capsys):
    opened = []
    monkeypatch.setattr(promotion.sqlite3, "connect", lambda *a, **k: opened.append(a))
    path, before = review(tmp_path, *ROWS), (promotion.LEDGER_JSON).read_bytes()
    for value in (None, "short-pepper"):                                           # missing, then under 32 characters
        if value is None:
            monkeypatch.delenv("PROMOTION_LEDGER_PEPPER")
        else:
            monkeypatch.setenv("PROMOTION_LEDGER_PEPPER", value)
        with pytest.raises(SystemExit) as c:
            admin.main(["promote-candidates", "--out", str(tmp_path / "o.csv"), "--conflict-map", CONFLICT])
        with pytest.raises(SystemExit) as a:
            admin.main(["promote-apply", "--csv", str(path), "--batch", "2026-11", "--reviewer", "Dr. Asha Rao",
                        "--conflict-map", CONFLICT, "--confirm"])
        assert c.value.code == a.value.code == 2
    assert "PROMOTION_LEDGER_PEPPER is required (32+ characters, keep it outside git)" in capsys.readouterr().err
    assert opened == [] and not (tmp_path / "o.csv").exists() and promotion.LEDGER_JSON.read_bytes() == before


def test_a_reused_batch_has_its_own_message_and_exit_2_and_other_refusals_exit_2(lexicon, tmp_path):
    path = review(tmp_path, *ROWS)
    promotion.apply(path, "2026-11", "Dr. Asha Rao", [], True, "2026-11-02")
    with pytest.raises(SystemExit, match="already in the ledger: pass a new --batch") as reused:
        promotion.apply(path, "2026-11", "Dr. Asha Rao", [], True, "2026-11-03")
    assert reused.value.code == 2
    with pytest.raises(SystemExit) as inside:
        promotion.write_review(promotion.REPO / "docs" / "c.csv", [])
    with pytest.raises(SystemExit) as minimum:
        admin.main(["promote-candidates", "--out", str(tmp_path / "x.csv"), "--conflict-map", CONFLICT, "--min-clinics", "0"])
    assert inside.value.code == minimum.value.code == 2


def test_hand_edited_rows_get_the_same_exclusions_as_candidates(lexicon, tmp_path):
    rows = (("Crocin", "Paracetamol", 3, "", "", "approve", "", ""),                  # already in the lexicon
            ("Ravi Kulkarni", "Paracetamol", 3, "", "", "approve", "", ""),            # person-like
            ("=HYPERLINK(1)", "Paracetamol", 3, "", "", "approve", "", ""),            # not a medicine name
            ("Zorbexin", "Paracetamol", 3, "", "", "approve", "", ""))
    before = json.loads((lexicon / "drugs.json").read_text(encoding="utf-8"))
    code, outcomes = promotion.apply(review(tmp_path, *rows), "2026-11", "Dr. Asha Rao", [], True, "2026-11-02")
    assert code == 0 and dict(outcomes) == {"rejected: in-lexicon": 1, "rejected: person-like": 1,
                                            "rejected: invalid-name": 1, "added": 1}
    after = json.loads((lexicon / "drugs.json").read_text(encoding="utf-8"))
    para = lambda d: next(e for e in d["entries"] if e["canonical"] == "Paracetamol")
    assert para(after)["brands"] == para(before)["brands"] + ["Zorbexin"]
    ledger = json.loads((lexicon / "ledger.json").read_text(encoding="utf-8"))["entries"]
    assert sorted(r["outcome"] for r in ledger) == ["added", "rejected: in-lexicon", "rejected: person-like"]


def test_the_pepper_needs_thirty_two_characters(monkeypatch):
    monkeypatch.setenv("PROMOTION_LEDGER_PEPPER", "x" * 31)
    with pytest.raises(SystemExit, match="32\\+ characters"):
        promotion.pepper()
    monkeypatch.setenv("PROMOTION_LEDGER_PEPPER", "x" * 32)
    assert promotion.pepper() == b"x" * 32


def test_a_wrong_pepper_is_refused_against_an_existing_ledger(three_clinics, tmp_path, monkeypatch):
    path, ledger_before = review(tmp_path, *ROWS), promotion.LEDGER_JSON.read_bytes()
    drugs = promotion.build.DRUGS_JSON.read_bytes()
    monkeypatch.setenv("PROMOTION_LEDGER_PEPPER", "another-pepper-9876543210-zyxwvutsrqponm")
    with pytest.raises(SystemExit, match="does not match the ledger") as c:
        admin.main(["promote-candidates", "--out", str(tmp_path / "o.csv"), "--conflict-map", CONFLICT])
    with pytest.raises(SystemExit, match="does not match the ledger") as a:
        admin.main(["promote-apply", "--csv", str(path), "--batch", "2026-11", "--reviewer", "Dr. Asha Rao",
                    "--conflict-map", CONFLICT, "--confirm"])
    assert c.value.code == a.value.code == 2 and not (tmp_path / "o.csv").exists()
    assert promotion.LEDGER_JSON.read_bytes() == ledger_before and promotion.build.DRUGS_JSON.read_bytes() == drugs


def test_the_ledger_holds_keyed_hashes_only_and_the_pepper_changes_them(lexicon, tmp_path, monkeypatch):
    promotion.apply(review(tmp_path, *ROWS), "2026-11", "Dr. Asha Rao", [], True, "2026-11-02")
    text = (lexicon / "ledger.json").read_text(encoding="utf-8")
    doc = json.loads(text)
    assert doc["version"] == "dd-promotion-v2" and re.fullmatch(r"[0-9a-f]{8}", doc["pepper_check"])
    assert PEPPER not in text and "Murexol" not in text
    unkeyed = {hashlib.sha256(("dd-promotion-v1:" + key("Murexol")).encode()).hexdigest(),
               hashlib.sha256(key("Murexol").encode()).hexdigest()}
    assert unkeyed.isdisjoint(r["key"] for r in doc["entries"])                    # guessable hashes do not match
    assert promotion.ledger_key("MUREXOL") == promotion.ledger_key(" murexol ") == promotion.ledger_key("Murexol")
    assert promotion.ledger_key("Murexol") in {r["key"] for r in doc["entries"]}
    first = promotion.ledger_key("Murexol")
    monkeypatch.setenv("PROMOTION_LEDGER_PEPPER", "another-pepper-9876543210-zyxwvutsrqponm")
    assert promotion.ledger_key("Murexol") != first


def test_a_quoted_newline_and_unicode_line_breaks_in_a_cell_stay_one_row(lexicon, tmp_path):
    rows = (("Zorbexin", "Paracetamol", 3, "2026-10-01", "2026-10-30", "approve", "", "line one\nline two\x85three\x0bfour\x0cfive"),
            ("Murexol", "", 4, "2026-10-01", "2026-10-30", "reject", "Dr. K. Iyer", "a surname"))
    code, outcomes = promotion.apply(review(tmp_path, *rows), "2026-11", "Dr. Asha Rao", [], True, "2026-11-02")
    assert code == 0 and dict(outcomes) == {"added": 1, "rejected": 1}


def test_a_tampered_name_never_reaches_the_csv_and_formula_cells_are_neutralised(lexicon, monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "single.db"))
    learn(tmp_path / "single.db", "Zorbexin", generic="paracetamol")
    with closing(dbmod.get_conn(tmp_path / "single.db")) as conn:
        conn.execute("UPDATE clinic_formulary SET name = '=HYPERLINK(\"x\")'")
        conn.commit()
    rows, why, _failed = promotion.candidates(1, [])
    assert rows == [] and dict(why) == {"invalid-name": 1}
    out = tmp_path / "f.csv"
    promotion.write_review(out, [{"name": "Zorbexin", "generic": "=1+1", "clinics_count": 3, "first_seen": "+x",
                                  "last_seen": "@y", "decision": "", "reviewer": "\tz", "notes": "-q"}])
    cells = next(csv.reader(out.read_text(encoding="utf-8").splitlines()[1:]))
    assert cells == ["Zorbexin", "'=1+1", "3", "'+x", "'@y", "", "'\tz", "'-q"]


def test_promotion_writes_are_atomic(lexicon, tmp_path, monkeypatch):
    out = tmp_path / "keep.csv"
    promotion.write_review(out, [])
    old_csv = out.read_bytes()
    monkeypatch.setattr(promotion.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        promotion.write_review(out, [{"name": "Zorbexin", "generic": "", "clinics_count": 3, "first_seen": "",
                                      "last_seen": "", "decision": "", "reviewer": "", "notes": ""}])
    with pytest.raises(OSError):
        promotion.apply(review(tmp_path, *ROWS), "2026-11", "Dr. Asha Rao", [], True, "2026-11-02")
    assert out.read_bytes() == old_csv and (lexicon / "ledger.json").read_text() == EMPTY
    assert not list(lexicon.glob("*.tmp")) and not list(tmp_path.glob("*.tmp"))


def test_an_incomplete_candidate_run_leaves_a_marker_that_blocks_apply(three_clinics, tmp_path, capsys):
    (clinic_dir("beta") / "app.db").unlink()
    out = tmp_path / "review" / "c.csv"
    assert admin.main(["promote-candidates", "--out", str(out), "--conflict-map", CONFLICT, "--min-clinics", "2"]) == 1
    assert "INCOMPLETE: do not apply (1 clinic(s) unreadable)" in capsys.readouterr().err
    marker = Path(str(out) + ".INCOMPLETE")
    assert marker.exists()
    ledger, drugs = promotion.LEDGER_JSON.read_bytes(), promotion.build.DRUGS_JSON.read_bytes()
    args = ["promote-apply", "--csv", str(out), "--batch", "2026-11", "--reviewer", "Dr. Asha Rao",
            "--conflict-map", CONFLICT, "--confirm"]
    with pytest.raises(SystemExit, match="INCOMPLETE") as e:
        admin.main(args)
    assert e.value.code == 2 and promotion.LEDGER_JSON.read_bytes() == ledger and promotion.build.DRUGS_JSON.read_bytes() == drugs
    marker.unlink()                                                                # the operator accepts it explicitly
    assert admin.main(args) == 0
