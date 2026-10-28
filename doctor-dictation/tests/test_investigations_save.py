"""Plan PQ-h Task 6: a not-dictated investigation blocks Save until kept or removed, and the server regrades every
checked item from the clinic's catalogue (the page's canonical and status are never trusted). Offline."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from doctor_dictation.api.app import create_app
from doctor_dictation.core import determinism as D
from test_investigations_api import CAT, H, _add, _signed_in, activate_catalogue, world  # noqa: F401

RED = {"text": "Brain impulses", "canonical": "", "status": "not-dictated", "source": "dictated"}
UNVERIFIED_ROW = {"name": "Crocin", "dose": "1-0-1", "status": "unknown-medicine"}


def _fake_pdf(monkeypatch):
    def fake(structured, meta, out_path, layout=None):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)


@pytest.fixture()
def tclient(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ix.db"))
    _fake_pdf(monkeypatch)
    activate_catalogue(monkeypatch, CAT, tmp_path)
    D._FORMAT_CACHE.clear()
    with TestClient(create_app()) as c:
        yield c


def _save(c, items, rx=(), confirmed=(), headers=None):
    return c.post("/api/v1/documents", headers=headers or {}, json={
        "structured": {"patientName": "A", "investigations": items, "rx": list(rx)}, "confirmed_rows": list(confirmed)})


def _stored(c, res, headers=None):
    assert res.status_code == 200, res.text
    return c.get(f"/api/v1/documents/{res.json()['document_id']}", headers=headers or {}).json()["structured"]["investigations"]


def test_a_red_item_blocks_save_until_kept_or_removed(tclient):
    r = _save(tclient, [RED])
    assert r.status_code == 409 and r.json() == {"error": "investigations not dictated", "block": [],
                                                 "investigations_block": [{"index": 0, "text": "Brain impulses"}]}
    assert _save(tclient, [dict(RED, source="doctor")]).status_code == 200
    assert _save(tclient, []).status_code == 200                                      # removed


def test_an_amber_item_saves(tclient):
    amber = {"text": "Uroflow at home", "canonical": "", "status": "new", "source": "dictated"}
    assert _stored(tclient, _save(tclient, [amber]))[0]["status"] == "new"


def test_a_forged_canonical_is_regraded(tclient):                                      # Review Focus 5
    forged = {"text": "RFT", "canonical": "<b>x</b>", "status": "verified", "source": "dictated"}
    unknown = {"text": "Brain impulses", "canonical": "<b>x</b>", "status": "verified", "source": "dictated"}
    got = _stored(tclient, _save(tclient, [forged, unknown]))
    assert [(i["canonical"], i["status"]) for i in got] == [("Renal Function Test", "verified"), ("", "new")]


def test_a_doctor_item_keeps_its_own_canonical_and_gets_its_status_from_the_catalogue(tclient):
    mine = {"text": "Brain impulses", "canonical": "Brain Impulse Study", "status": "verified", "source": "doctor"}
    listed = {"text": "kft", "canonical": "", "status": "new", "source": "doctor"}
    got = _stored(tclient, _save(tclient, [mine, listed]))
    assert [(i["canonical"], i["status"]) for i in got] == [("Brain Impulse Study", "new"),
                                                            ("Renal Function Test", "verified")]


def test_an_old_document_with_strings_resaves_without_a_block(tclient):                # Review Focus 3
    got = _stored(tclient, _save(tclient, ["CBC"]))
    assert got == [{"text": "CBC", "canonical": "", "status": "", "source": "dictated"}]


def test_both_gates_report_together(tclient):
    r = _save(tclient, [RED], rx=[UNVERIFIED_ROW])
    j = r.json()
    assert r.status_code == 409 and j["error"] == "unverified medicines"
    assert j["block"] and j["investigations_block"] == [{"index": 0, "text": "Brain impulses"}]


def test_a_medicine_only_block_keeps_the_old_body(tclient):
    j = _save(tclient, [], rx=[UNVERIFIED_ROW]).json()
    assert set(j) == {"error", "block"} and j["error"] == "unverified medicines"


def test_a_test_the_clinic_hides_is_regraded_new_never_verified(world, tmp_path, monkeypatch):
    activate_catalogue(monkeypatch, CAT, tmp_path)
    _fake_pdf(monkeypatch)
    claimed = {"text": "RFT", "canonical": "Renal Function Test", "status": "verified", "source": "dictated"}
    with _signed_in("dr.rao", "dr.iyer") as (rao, iyer):
        _add(rao, "investigation", "hide", "renal function test")
        mine = _stored(rao, _save(rao, [claimed], headers=H), headers=H)
        theirs = _stored(iyer, _save(iyer, [claimed], headers=H), headers=H)
    assert (mine[0]["status"], mine[0]["canonical"]) == ("new", "")
    assert (theirs[0]["status"], theirs[0]["canonical"]) == ("verified", "Renal Function Test")
