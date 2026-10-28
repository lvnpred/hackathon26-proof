"""Plan PQ-h Task 7: "Remember for this clinic" records a confirmation on the clinic's overlay (never ``upsert``); a test
joins the clinic's list only after ``formulary.THRESHOLD`` saved prescriptions confirm the same data. Every case is proven
LIVE through the real read path (``use_investigations`` + POST /api/v1/investigations/lookup). Offline."""
import json
import logging
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api.app import create_app
from doctor_dictation.core import determinism as D
from doctor_dictation.core import overlay
from doctor_dictation.core.investigations import remember_row
from doctor_dictation.db import overlay as odb
from test_investigations_api import CAT, activate_catalogue

UROFLOW = {"canonical": "Uroflowmetry", "aliases": ["uroflow study"], "category": "Urology", "print": ""}
HB = {"canonical": "Haemoglobin", "aliases": ["hb", "hemoglobin"], "category": "Blood", "print": "Hb"}
POTASSIUM = {"canonical": "Serum Potassium", "aliases": ["potassium level"], "category": "Blood", "print": "",
             "safety": True}
CAT2 = CAT + [UROFLOW, HB, POTASSIUM]
RFT_E = CAT[0]
UF = {"text": "Uroflow at home", "canonical": "", "status": "new", "source": "dictated"}


def doc(text, canonical="", status="verified"):
    return {"text": text, "canonical": canonical, "status": status, "source": "doctor"}


# ---- remember_row: one test per table row (pure) ---------------------------------------------------------------------

def test_unknown_text_without_a_canonical_is_an_add_of_the_text():
    want = {"action": "add", "entry_key": "uroflow at home", "base_entry": None,
            "data": {"name": "Uroflow at home", "aliases": [], "category": "", "print": ""}}
    assert remember_row(UF, CAT2, CAT2) == want
    assert remember_row(doc("Uroflow at home", "uroflow  AT home"), CAT2, CAT2) == want     # C is T by name


def test_unknown_text_with_a_listed_canonical_edits_that_entry_with_the_text_as_an_alias():
    assert remember_row(doc("Kidney check", "Renal Function Test"), CAT2, CAT2) == {
        "action": "edit", "entry_key": "renal function test", "base_entry": RFT_E,
        "data": {"aliases": ["rft", "kft", "Kidney check"]}}


def test_an_edit_of_a_clinic_add_is_that_add_under_its_own_key():
    mine = {"canonical": "Home Uroflowmetry", "aliases": ["flow at home"], "category": "Urology", "print": "", "clinic": True}
    assert remember_row(doc("Home flow", "Home Uroflowmetry"), CAT2 + [mine], CAT2) == {
        "action": "add", "entry_key": "home uroflowmetry", "base_entry": None,
        "data": {"name": "Home Uroflowmetry", "aliases": ["flow at home", "Home flow"], "category": "Urology", "print": ""}}


def test_unknown_text_and_unknown_canonical_add_the_canonical_with_the_text_as_alias():
    assert remember_row(doc("Flow study at home", "Home Uroflowmetry"), CAT2, CAT2) == {
        "action": "add", "entry_key": "home uroflowmetry", "base_entry": None,
        "data": {"name": "Home Uroflowmetry", "aliases": ["Flow study at home"], "category": "", "print": ""}}


@pytest.mark.parametrize("item", [{"text": "RFT", "canonical": "", "status": "verified", "source": "dictated"},
                                  doc("RFT", "Renal Function Test"), doc("KFT", "rft"), doc("RFT", "RFT")])
def test_a_listed_text_with_no_new_canonical_has_nothing_to_learn(item):
    assert remember_row(item, CAT2, CAT2) is None


def test_a_listed_text_with_a_new_canonical_adds_the_canonical_taking_the_text():
    # An investigation edit cannot change a canonical (plan f: an edit takes aliases, category, print only), so the
    # brief's "edit E_T: canonical = C" is an add of C with the alias T; the read path takes T off E_T.
    assert remember_row(doc("KFT", "Kidney Profile"), CAT2, CAT2) == {
        "action": "add", "entry_key": "kidney profile", "base_entry": None,
        "data": {"name": "Kidney Profile", "aliases": ["KFT"], "category": "", "print": ""}}


def test_two_different_listed_tests_are_a_conflict_with_nothing_to_learn():
    assert remember_row(doc("KFT", "Uroflowmetry"), CAT2, CAT2) is None


def test_a_hidden_test_or_a_hidden_canonical_is_never_learned():
    hide = {"kind": "investigation", "entry_key": "haemoglobin", "action": "hide", "data": {}, "base_sha": ""}
    entries, _flags, blocked = overlay.effective_and_blocked("investigation", CAT2, [hide])
    view = overlay.View(entries)
    view.blocked = blocked
    assert remember_row(doc("Hb", "", "new"), view, CAT2) is None                       # T hidden
    assert remember_row(doc("Low Hb check", "Haemoglobin", "new"), view, CAT2) is None  # C hidden
    assert remember_row(doc("Low Hb check", "", "new"), view, CAT2) is not None         # a new name is still learned


def test_bad_items_have_nothing_to_learn():
    assert remember_row("RFT", CAT2, CAT2) is None
    assert remember_row({"text": "  ", "canonical": "X"}, CAT2, CAT2) is None


# ---- through Save and the read path ----------------------------------------------------------------------------------

def _fake_pdf(monkeypatch):
    def fake(structured, meta, out_path, layout=None):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)


@pytest.fixture()
def tclient(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ixr.db"))
    _fake_pdf(monkeypatch)
    activate_catalogue(monkeypatch, CAT2, tmp_path)
    D._FORMAT_CACHE.clear()
    with TestClient(create_app()) as c:
        yield c


def _save(c, item, doc_id=None, remember=(0,)):
    r = c.post("/api/v1/documents", json={"structured": {"patientName": "A", "investigations": [item], "rx": []},
                                          "remember_investigations": list(remember), "document_id": doc_id})
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def _lookup(c, text):
    """The real read path: the route's ``use_investigations`` builds this clinic's list from its ACTIVE overlay rows."""
    return c.post("/api/v1/investigations/lookup", json={"text": text}).json()


def _status(c, text):
    return _lookup(c, text)["status"]


def _rows():
    with closing(dbmod.get_conn()) as conn:
        rows = odb.list_rows(conn, "investigation") + odb.list_rows(conn, "investigation", pending=True)
    return {r["entry_key"]: r for r in rows}


def _count(k):
    row = _rows().get(k)
    return row["confirm_count"] if row else 0


def _audits():
    with closing(dbmod.get_conn()) as conn:
        return [json.loads(r["detail"]) for r in conn.execute(
            "SELECT detail FROM audit_log WHERE action = 'investigation.remember' ORDER BY id").fetchall()]


def _twice(c, item):
    _save(c, item)
    _save(c, item)


def test_first_save_is_pending_and_a_second_document_makes_it_live(tclient):
    _save(tclient, UF)
    assert _status(tclient, "Uroflow at home") == "new"                                  # pending, 1 of 2
    assert _rows()["uroflow at home"]["source"] == "doctor"
    _save(tclient, UF)
    assert _lookup(tclient, "Uroflow at home") == {"canonical": "Uroflow at home", "status": "verified"}
    assert _audits() == [{"entry_key": "uroflow at home", "action": "add", "count": 1},
                         {"entry_key": "uroflow at home", "action": "add", "count": 2}]


def test_case_alias_to_a_shipped_test_goes_live_and_keeps_its_aliases(tclient):
    _save(tclient, doc("Kidney check", "Renal Function Test", "new"))
    assert _status(tclient, "Kidney check") == "new"
    _save(tclient, doc("Kidney check", "Renal Function Test", "new"))
    assert _rows()["renal function test"]["action"] == "edit"
    assert _rows()["renal function test"]["base_sha"] == overlay.entry_sha(RFT_E)
    for text in ("Kidney check", "KFT", "RFT", "Renal Function Test"):
        assert _lookup(tclient, text) == {"canonical": "Renal Function Test", "status": "verified"}, text


def test_case_alias_to_a_clinic_add_goes_live(tclient):
    # 2b through Save: the clinic add is still PENDING (count 1), so the new data restarts it (plan f/g rule) and two
    # documents with the alias make the add live with both names.
    _save(tclient, doc("Home Uroflowmetry", "", "new"))
    _twice(tclient, doc("Home flow", "Home Uroflowmetry", "new"))
    for text in ("Home flow", "Home Uroflowmetry"):
        assert _lookup(tclient, text) == {"canonical": "Home Uroflowmetry", "status": "verified"}, text


def test_new_data_never_takes_a_live_learned_row_off_the_list(tclient, caplog):
    # Ruling (fix round 1): an ACTIVE doctor-learned row with other data is skipped and logged, not restarted; further
    # aliases go through the clinic list screen.
    _twice(tclient, doc("Home Uroflowmetry", "", "new"))
    with caplog.at_level(logging.INFO, logger="doctor_dictation.api.investigations"):
        _twice(tclient, doc("Home flow", "Home Uroflowmetry", "new"))
    assert "take the clinic's learned entry off the list" in caplog.text
    assert _count("home uroflowmetry") == 2 and _rows()["home uroflowmetry"]["data"]["aliases"] == []
    assert _status(tclient, "Home Uroflowmetry") == "verified" and _status(tclient, "Home flow") == "new"
    assert [a["count"] for a in _audits()] == [1, 2]


def test_case_new_canonical_with_the_text_as_alias_goes_live(tclient):
    _save(tclient, doc("Flow study at home", "Home Uroflowmetry", "new"))
    assert _status(tclient, "Flow study at home") == "new"
    _save(tclient, doc("Flow study at home", "Home Uroflowmetry", "new"))
    for text in ("Flow study at home", "Home Uroflowmetry"):
        assert _lookup(tclient, text) == {"canonical": "Home Uroflowmetry", "status": "verified"}, text


def test_case_listed_test_with_nothing_new_writes_nothing(tclient):
    _twice(tclient, {"text": "RFT", "canonical": "", "status": "verified", "source": "dictated"})
    _twice(tclient, doc("KFT", "Uroflowmetry"))                                         # two listed tests: a conflict
    assert _rows() == {} and _audits() == []


def test_case_listed_alias_renamed_goes_live_and_leaves_the_shipped_test(tclient):
    _save(tclient, doc("KFT", "Kidney Profile"))
    assert _lookup(tclient, "KFT")["canonical"] == "Renal Function Test"                # pending: unchanged
    _save(tclient, doc("KFT", "Kidney Profile"))
    assert _rows()["kidney profile"]["action"] == "add" and _rows()["kidney profile"]["base_sha"] == ""
    assert _lookup(tclient, "KFT") == {"canonical": "Kidney Profile", "status": "verified"}
    assert _lookup(tclient, "Kidney Profile") == {"canonical": "Kidney Profile", "status": "verified"}
    assert _lookup(tclient, "RFT") == {"canonical": "Renal Function Test", "status": "verified"}
    with closing(dbmod.get_conn()) as conn:
        assert overlay.refused_rows("investigation", CAT2, odb.list_rows(conn, "investigation")) == {}


@pytest.mark.parametrize("text", ["RFT", "Renal Function Test"])
def test_a_rename_the_read_path_would_leave_inert_is_skipped(tclient, text):
    # "RFT" stays on Renal Function Test as its print form (an add takes aliases, not print); "Renal Function Test" is
    # a shipped canonical, which overlay.conflicts refuses as another test's alias. Neither is stored or counted.
    _twice(tclient, doc(text, "Kidney Profile"))
    assert _rows() == {} and _audits() == []
    assert _lookup(tclient, text)["canonical"] == "Renal Function Test"


def test_an_alias_on_a_test_with_short_aliases_goes_live(tclient):
    # Fix round 1: the investigation name rule takes Haemoglobin's 2-letter alias "hb", so the edit carrying it is valid.
    _twice(tclient, doc("Low Hb check", "Haemoglobin", "new"))
    for text in ("Low Hb check", "Hb", "hemoglobin"):
        assert _lookup(tclient, text) == {"canonical": "Haemoglobin", "status": "verified"}, text


def test_a_name_overlay_validation_refuses_is_skipped(tclient, caplog):
    with caplog.at_level(logging.INFO, logger="doctor_dictation.api.investigations"):
        _twice(tclient, doc("Uroflow; at home", "", "new"))
    assert _rows() == {} and "is not a test name we can store" in caplog.text


def test_an_alias_on_a_safety_entry_is_skipped(tclient):
    _twice(tclient, doc("K level", "Serum Potassium", "new"))                           # the safety entry would win
    assert _rows() == {} and _status(tclient, "K level") == "new"


def test_a_hidden_test_is_never_learned(tclient):
    with closing(dbmod.get_conn()) as conn:
        odb.upsert(conn, "investigation", "haemoglobin", "hide", {}, overlay.entry_sha(HB), "admin", None)
    _twice(tclient, doc("Hb", "", "new"))
    _twice(tclient, doc("Low Hb check", "Haemoglobin", "new"))
    assert set(_rows()) == {"haemoglobin"} and _audits() == []
    assert _status(tclient, "Hb") == "new"


def test_an_admin_row_owning_the_key_counts_nothing_and_writes_no_audit(tclient):
    with closing(dbmod.get_conn()) as conn:
        odb.upsert(conn, "investigation", "renal function test", "edit", {"aliases": ["rft", "kft", "renal panel"]},
                   overlay.entry_sha(RFT_E), "admin", None)
    _twice(tclient, doc("Kidney check", "Renal Function Test", "new"))
    row = _rows()["renal function test"]
    assert row["source"] == "admin" and row["confirm_count"] == 0 and _audits() == []
    assert _status(tclient, "Kidney check") == "new"


def test_resaving_the_same_document_does_not_count_twice(tclient):
    d = _save(tclient, UF)
    _save(tclient, UF, doc_id=d)
    assert _count("uroflow at home") == 1 and _status(tclient, "Uroflow at home") == "new"


def test_different_data_restarts_the_count(tclient):
    _save(tclient, doc("Flow study at home", "Home Uroflowmetry", "new"))
    _save(tclient, doc("Uroflow at home", "Home Uroflowmetry", "new"))                 # same key, other alias
    assert _count("home uroflowmetry") == 1 and _status(tclient, "Home Uroflowmetry") == "new"
    d = _save(tclient, doc("KFT", "Kidney Profile"))
    _save(tclient, doc("KFT", "Kidney Panel"))                                          # two different full names
    assert _count("kidney profile") == 1 and _count("kidney panel") == 1
    assert _lookup(tclient, "KFT")["canonical"] == "Renal Function Test"                # neither is live
    stored = tclient.get(f"/api/v1/documents/{d}").json()["structured"]["investigations"]
    assert stored[0]["canonical"] == "Kidney Profile"                                   # the prescription keeps its own


def test_only_a_ticked_test_counts(tclient):
    _save(tclient, UF, remember=())
    _save(tclient, UF, remember=())
    _save(tclient, doc("Kidney check", "Renal Function Test", "new"), remember=())
    assert _rows() == {}


def test_indexes_point_into_the_saved_list(tclient):
    items = ["  ", "RFT", "Uroflow at home"]                         # the blank is dropped: index 1 is the saved UF
    for _ in range(2):
        r = tclient.post("/api/v1/documents", json={"structured": {"patientName": "A", "investigations": items},
                                                    "remember_investigations": [1]})
        assert r.status_code == 200, r.text
    assert set(_rows()) == {"uroflow at home"} and _status(tclient, "Uroflow at home") == "verified"


def test_bad_indexes_and_a_failing_write_never_block(tclient, monkeypatch, caplog):
    r = tclient.post("/api/v1/documents", json={"structured": {"patientName": "A", "investigations": [UF]},
                                                "remember_investigations": [5, -1, "x", True, 0.0, None]})
    assert r.status_code == 200, r.text
    assert _rows() == {}

    def boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(odb, "record_confirmation", boom)
    with caplog.at_level(logging.WARNING, logger="doctor_dictation.api.investigations"):
        d = _save(tclient, UF)
    assert d and _rows() == {} and "could not remember test 0" in caplog.text
    assert tclient.get(f"/api/v1/documents/{d}").status_code == 200                    # the prescription is saved


# ---- fix round 1: hidden spellings, twins ----------------------------------------------------------------------------

VD = {"canonical": "Vit D Level", "aliases": ["vitamin d", "usg-vd"], "category": "Blood", "print": ""}


@pytest.mark.parametrize("text,canonical", [("Vit. D Level", ""), ("vit-d level", ""), ("Vitamin-D", ""),
                                            ("Vit D test", "Vit. D Level"), ("usg vd", ""), ("Vit D test", "")])
def test_a_hidden_test_never_comes_back_under_another_spelling(text, canonical):
    """The reviewer's probe: hiding "Vit D Level" hides "Vit. D Level", "vit-d level", "Vitamin-D", "usg vd" too."""
    hide = {"entry_key": "vit d level", "action": "hide", "data": {}, "base_sha": ""}
    entries, _flags, blocked = overlay.effective_and_blocked("investigation", [VD], [hide])
    view = overlay.View(entries)
    view.blocked = blocked
    row = remember_row(doc(text, canonical, "new"), view, [VD])
    assert (row is None) == ((text, canonical) != ("Vit D test", ""))            # a new name is still learned


def test_a_row_naming_a_hidden_spelling_in_its_aliases_is_never_learned():
    hide = {"entry_key": "vit d level", "action": "hide", "data": {}, "base_sha": ""}
    mine = {"canonical": "Bone Profile", "aliases": [], "category": "", "print": "", "clinic": True}
    entries, _flags, blocked = overlay.effective_and_blocked("investigation", [VD], [hide])
    view = overlay.View([*entries, mine])
    view.blocked = blocked
    assert remember_row(doc("Vit. D. Level", "Bone Profile", "new"), view, [VD]) is None


SPELLED = [("K.F.T", ""), ("R F T", ""), ("r.f.t.", ""), ("R F T", "Kidney Panel"), ("Kidney check", "K.F.T"),
           ("Repeat KFT", ""), ("Repeat R F T", ""), ("RFT test", ""), ("Rft Profile", ""), ("k.f.t. test", "Kidney Panel")]


@pytest.mark.parametrize("text,canonical", SPELLED)
def test_a_hidden_test_never_comes_back_spelled_letter_by_letter(text, canonical):
    """Final review I2: ``lookup`` matches "k f t" to "kft", so the hide check compares spaceless forms too."""
    hide = {"entry_key": "renal function test", "action": "hide", "data": {}, "base_sha": ""}
    entries, _flags, blocked = overlay.effective_and_blocked("investigation", CAT2, [hide])
    view = overlay.View(entries)
    view.blocked = blocked
    assert remember_row(doc(text, canonical, "new"), view, CAT2) is None
    assert remember_row(doc("Kidney check", "Kidney Panel", "new"), view, CAT2) is not None   # a new name is learned


def test_a_hidden_test_spelled_by_letters_is_never_learned_through_save(tclient):
    with closing(dbmod.get_conn()) as conn:
        odb.upsert(conn, "investigation", "renal function test", "hide", {}, overlay.entry_sha(RFT_E), "admin", None)
    for text, canonical in SPELLED:
        _twice(tclient, doc(text, canonical, "new"))
    assert set(_rows()) == {"renal function test"} and _audits() == []
    assert [_status(tclient, t) for t in ("K.F.T", "k f t", "R F T", "r.f.t.", "Kidney Panel", "Repeat KFT", "RFT test",
                                          "Rft Profile", "k.f.t. test")] == ["new"] * 9


def test_a_twin_spelling_of_another_clinic_row_is_not_counted(tclient):
    _save(tclient, doc("Vit D Level", "", "new"))                                      # pending, 1 of 2
    _twice(tclient, doc("Vit. D Level", "", "new"))                                    # one lookup name: refused
    assert set(_rows()) == {"vit d level"} and _count("vit d level") == 1
    _save(tclient, doc("Vit D Level", "", "new"))
    assert _lookup(tclient, "Vit. D Level") == {"canonical": "Vit D Level", "status": "verified"}


def test_goes_live_needs_the_exact_canonical():
    from doctor_dictation.api.investigations import _goes_live
    live = {"entry_key": "vit d level", "action": "add", "base_sha": "",
            "data": {"name": "Vit D Level", "aliases": [], "category": "", "print": ""}}
    twin = {"entry_key": "vit. d level", "action": "add", "base_sha": "", "base_entry": None,
            "data": {"name": "Vit. D Level", "aliases": [], "category": "", "print": ""}}
    assert not _goes_live(CAT2, [live], twin, "Vit. D Level")                          # the older twin shadows it
    assert _goes_live(CAT2, [], twin, "Vit. D Level")
