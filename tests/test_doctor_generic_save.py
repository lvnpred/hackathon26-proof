"""Save gate, settle, and the clinic list count for a doctor generic (plan PQ-g, Task 5). Offline.

Stub LLM, fake PDF renderer, DB_PATH in a temp folder; the hide tests run in the two-clinic world of test_users_routes.
"""
import contextvars
import json
from contextlib import closing
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api.app import create_app
from doctor_dictation.config import override_settings
from doctor_dictation.core import determinism as D
from doctor_dictation.core import formulary, overlay
from doctor_dictation.core.safety import screen_unverified
from doctor_dictation.db import formulary as fdb
from doctor_dictation.db import overlay as odb
from test_users_routes import H, _conn, _signed_in, world  # noqa: F401

COMBO = "Aceclofenac + Paracetamol"
DOC = {"name": "Zerodol-P", "generic": COMBO, "generic_source": "doctor", "generic_pending": True,
       "status": "unknown-medicine", "lexicon_match": "", "generic_suggestion": COMBO}
CROCIN = {**DOC, "name": "Crocin", "generic": "Paracetamol + Caffeine", "status": "verified",
          "lexicon_match": "Paracetamol", "generic_suggestion": ""}


def _fake_pdf(monkeypatch):
    def fake(structured, meta, out_path, layout=None):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "g.db"))
    _fake_pdf(monkeypatch)
    D._FORMAT_CACHE.clear()
    with TestClient(create_app()) as c:
        yield c


def save(c, row=DOC, patient="Anita Rao", confirmed=(0,), remember=(), document_id=None, headers=None, structured=None):
    body = {"structured": structured or {"patientName": patient, "ageSex": "40 / F", "opNo": "", "rx": [dict(row)]},
            "confirmed_rows": list(confirmed), "remember_generics": list(remember), "document_id": document_id}
    r = c.post("/api/v1/documents", json=body, headers=headers or {})
    assert r.status_code == 200, r.text
    return r.json()


def stored_rx(conn, document_id):
    return json.loads(dbmod.get_document(conn, document_id)["structured_json"])["rx"]


def under_clinic(conn, fn):
    """``fn()`` with this database's clinic layer and overlay active (a fresh context, nothing leaks into other tests)."""
    def run():
        formulary.activate(formulary.ranked_layer(fdb.list_active(conn), date.today()))
        overlay.activate(overlay.state_from_rows([r for k in overlay.KINDS for r in odb.list_rows(conn, k)]))
        return fn()
    return contextvars.Context().run(run)


def all_rows(conn):
    """Every overlay row of the medicine list, active and pending, as (entry_key, action, source, count, data)."""
    rows = odb.list_rows(conn, "medicine") + odb.list_rows(conn, "medicine", pending=True)
    return sorted((r["entry_key"], r["action"], r["source"], r["confirm_count"], r["data"]) for r in rows)


def doctor_audits(conn):
    return [json.loads(r["detail"]) for r in
            conn.execute("SELECT detail FROM audit_log WHERE action = 'generic.doctor' ORDER BY id").fetchall()]


# ---- the gate ---------------------------------------------------------------------------------------------------------

def test_gate_blocks_an_unconfirmed_doctor_generic_even_on_a_verified_row():
    row = {**DOC, "name": "Crocin", "status": "verified", "lexicon_match": "Paracetamol"}
    assert screen_unverified({"rx": [row]}, []) == [{"index": 0, "name": "Crocin", "status": "verified", "generic": "pending"}]
    assert screen_unverified({"rx": [row]}, [0]) == []
    assert screen_unverified({"rx": [{**row, "generic": "<x>"}]}, [0])[0]["generic"] == "invalid"     # Review Focus 5


def test_gate_puts_the_generic_on_the_rows_own_status_entry_and_ignores_other_rows():
    assert screen_unverified({"rx": [DOC]}, []) == [
        {"index": 0, "name": "Zerodol-P", "status": "unknown-medicine", "generic": "pending"}]
    not_pending = {**DOC, "status": "verified", "generic_pending": False}
    lexicon = {**DOC, "status": "verified", "generic_source": "lexicon", "generic": "<x>"}
    assert screen_unverified({"rx": [not_pending, lexicon]}, []) == []


def test_the_save_route_answers_409_with_the_generic_block(client):
    r = client.post("/api/v1/documents", json={"structured": {"rx": [CROCIN]}, "confirmed_rows": []})
    assert r.status_code == 409 and r.json()["block"] == [
        {"index": 0, "name": "Crocin", "status": "verified", "generic": "pending"}]


# ---- settle and the count ---------------------------------------------------------------------------------------------

def test_first_save_is_pending_not_in_the_clinic_list(client):
    res = save(client)
    with closing(dbmod.get_conn()) as conn:
        rx = stored_rx(conn, res["document_id"])
        assert "generic_pending" not in rx[0] and rx[0]["generic"] == COMBO and rx[0]["generic_source"] == "doctor"
        assert odb.list_rows(conn, "medicine") == []                                  # nothing active
        assert all_rows(conn) == [("zerodol-p", "add", "doctor", 1, {"name": "Zerodol-P", "generic": COMBO})]
        assert under_clinic(conn, lambda: D._exact_lookup("Zerodol-P")) == ""         # not in the effective list
        audit = doctor_audits(conn)
        assert len(audit) == 1 and audit[0]["from_suggestion"] is True
        assert {k: audit[0][k] for k in ("name", "generic", "action", "document_id", "count")} == \
            {"name": "Zerodol-P", "generic": COMBO, "action": "add", "document_id": res["document_id"], "count": 1}


def test_second_save_in_another_document_goes_live(client, monkeypatch):
    save(client)
    save(client, patient="Ravi Kulkarni")
    with closing(dbmod.get_conn()) as conn:
        assert [(r["entry_key"], r["confirm_count"]) for r in odb.list_rows(conn, "medicine")] == [("zerodol-p", 2)]
        assert under_clinic(conn, lambda: D._exact_lookup("Zerodol-P")) == COMBO
        assert [a["count"] for a in doctor_audits(conn)] == [1, 2]
    stub = {"form": "Tab.", "name": "Zerodol-P", "strength": "", "dose": "1-0-1", "timing": "", "duration": "",
            "instructions": ""}
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps({"rx": [stub]}))
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True)
    D._FORMAT_CACHE.clear()
    row = client.post("/api/format", json={"transcript": "tab zerodol-p 1-0-1"}).json()["structured"]["rx"][0]
    assert (row["generic"], row["generic_source"]) == (COMBO, "lexicon")


def test_resave_of_the_same_document_stays_pending(client):          # Review Focus 4
    first = save(client)
    with closing(dbmod.get_conn()) as conn:
        stored = json.loads(dbmod.get_document(conn, first["document_id"])["structured_json"])
    again = save(client, structured=stored, confirmed=(0,), document_id=first["document_id"])   # (a) stored row: not pending
    assert again["document_id"] == first["document_id"]
    with closing(dbmod.get_conn()) as conn:
        assert all_rows(conn)[0][3] == 1 and len(doctor_audits(conn)) == 1             # no new confirmation
    save(client, document_id=first["document_id"])                                   # (b) DOC re-confirmed
    with closing(dbmod.get_conn()) as conn:
        assert all_rows(conn)[0][3] == 1
        assert under_clinic(conn, lambda: D._exact_lookup("Zerodol-P")) == ""


def test_a_stored_non_pending_doctor_generic_resaves_unconfirmed_when_its_status_is_verified(client):
    first = save(client, row=CROCIN, remember=(0,))
    with closing(dbmod.get_conn()) as conn:
        stored = json.loads(dbmod.get_document(conn, first["document_id"])["structured_json"])
    assert stored["rx"][0]["status"] == "verified" and "generic_pending" not in stored["rx"][0]
    save(client, structured=stored, confirmed=(), document_id=first["document_id"])   # the gate lets it through
    with closing(dbmod.get_conn()) as conn:
        assert [r[3] for r in all_rows(conn)] == [1]


def test_a_different_generic_restarts_the_count(client):
    save(client)
    other = "Aceclofenac + Serratiopeptidase"
    save(client, row={**DOC, "generic": other}, patient="Ravi Kulkarni")
    with closing(dbmod.get_conn()) as conn:
        assert all_rows(conn) == [("zerodol-p", "add", "doctor", 1, {"name": "Zerodol-P", "generic": other})]
        assert under_clinic(conn, lambda: D._exact_lookup("Zerodol-P")) == ""
        assert doctor_audits(conn)[1]["from_suggestion"] is False


def test_a_listed_brand_counts_only_with_remember(client):            # Q20
    first = save(client, row=CROCIN)
    with closing(dbmod.get_conn()) as conn:
        assert all_rows(conn) == [] and doctor_audits(conn) == []
        assert stored_rx(conn, first["document_id"])[0]["generic"] == "Paracetamol + Caffeine"
    save(client, row=CROCIN, patient="Ravi Kulkarni", remember=(0,))
    save(client, row=CROCIN, patient="Meena Iyer", remember=(0,))
    with closing(dbmod.get_conn()) as conn:
        rows = odb.list_rows(conn, "medicine")
        shipped = next(e for e in D.shipped_lexicon() if e["canonical"] == "Paracetamol")
        assert [(r["entry_key"], r["action"], r["confirm_count"]) for r in rows] == [("crocin", "add", 2)]
        assert rows[0]["base_sha"] == overlay.entry_sha(shipped) != ""               # the shipped entry it overrides
        assert under_clinic(conn, lambda: D._exact_lookup("Crocin")) == "Paracetamol + Caffeine"
        assert under_clinic(conn, lambda: D._exact_lookup("Dolo")) == "Paracetamol"    # other brands keep the generic


def test_learning_never_blocks_the_save(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("overlay down")
    monkeypatch.setattr(odb, "record_confirmation", boom)
    res = save(client)
    with closing(dbmod.get_conn()) as conn:
        assert stored_rx(conn, res["document_id"])[0]["generic"] == COMBO and doctor_audits(conn) == []


# ---- a name the clinic hid is printed but never learned (multi-clinic world) -------------------------------------------

HIDES = {"brand dropped": ("edit", "paracetamol", {"brands": ["Dolo", "Calpol", "Fepanil"]}),
         "entry hidden": ("hide", "paracetamol", None)}


@pytest.mark.parametrize("how", sorted(HIDES))
def test_a_hidden_name_prints_the_doctors_generic_but_is_never_learned(world, monkeypatch, how):
    _fake_pdf(monkeypatch)
    op, key, data = HIDES[how]
    with _signed_in("dr.rao") as (rao,):
        body = {"op": op, "entry_key": key, **({"data": data} if data is not None else {})}
        assert rao.post("/api/v1/lists/medicine/changes", json=body, headers=H).status_code == 200
        with closing(_conn("rao")) as conn:
            assert under_clinic(conn, lambda: D._exact_lookup("Crocin")) == ""
        docs = [save(rao, row=CROCIN, patient=p, remember=(0,), headers=H) for p in ("Asha Verma", "Ravi Kulkarni")]
    with closing(_conn("rao")) as conn:
        assert [r["entry_key"] for r in odb.list_rows(conn, "medicine") + odb.list_rows(conn, "medicine", pending=True)] \
            == ["paracetamol"]                                                         # only the admin's row
        assert doctor_audits(conn) == []
        assert under_clinic(conn, lambda: D._exact_lookup("Crocin")) == ""
        for d in docs:
            assert stored_rx(conn, d["document_id"])[0]["generic"] == "Paracetamol + Caffeine"


# ---- fix round 1: a brand override is flagged when the shipped entry behind it changes --------------------------------

def _ship(monkeypatch, change):
    """Replace the shipped list with a copy whose Paracetamol entry ``change`` edits (the next request sees it)."""
    import copy
    lex = copy.deepcopy(D.shipped_lexicon())
    change(next(e for e in lex if e["canonical"] == "Paracetamol"))
    monkeypatch.setattr(D, "_lexicon_cache", lex)


def _items(c):
    return {i["entry_key"]: i for i in c.get("/api/v1/lists/medicine").json()["items"]}


SHIPPED_CHANGES = {"entry changed": lambda e: e["strengths"].append("650 mg"),
                   "brand dropped": lambda e: e["brands"].remove("Crocin")}


@pytest.mark.parametrize("how", sorted(SHIPPED_CHANGES))
def test_a_brand_override_is_flagged_when_the_shipped_entry_changes_and_the_clinic_still_wins(client, monkeypatch, how):
    save(client)
    save(client, patient="Ravi Kulkarni")                                            # Zerodol-P: an add with no base_sha
    for p in ("Asha Verma", "Meena Iyer"):
        save(client, row=CROCIN, patient=p, remember=(0,))
    assert _items(client)["crocin"]["flag"] == "" and _items(client)["zerodol-p"]["flag"] == ""
    _ship(monkeypatch, SHIPPED_CHANGES[how])
    got = _items(client)
    assert (got["crocin"]["flag"], got["crocin"]["badge"]) == ("shipped-changed", "clinic-added")
    assert got["zerodol-p"]["flag"] == ""                                              # base_sha "": never flagged
    with closing(dbmod.get_conn()) as conn:
        assert under_clinic(conn, lambda: D._exact_lookup("Crocin")) == "Paracetamol + Caffeine"   # the clinic wins
    r = client.post("/api/v1/lists/medicine/changes", json={"op": "keep-mine", "entry_key": "crocin"})
    assert r.status_code == 200, r.text
    assert r.json()["item"]["flag"] == "" and _items(client)["crocin"]["flag"] == ""
    with closing(dbmod.get_conn()) as conn:
        assert under_clinic(conn, lambda: D._exact_lookup("Crocin")) == "Paracetamol + Caffeine"


def test_a_name_an_admin_row_owns_is_not_audited(client):
    assert client.post("/api/v1/lists/medicine/changes", json={"op": "add", "entry_key": "zerodol-p", "data": {
        "name": "Zerodol-P", "generic": COMBO}}).status_code == 200
    save(client, row={**DOC, "generic": "Aceclofenac + Serratiopeptidase"}, remember=(0,))   # listed now: remembered
    with closing(dbmod.get_conn()) as conn:
        assert doctor_audits(conn) == []
        assert [(r["source"], r["data"]["generic"]) for r in odb.list_rows(conn, "medicine")] == [("admin", COMBO)]


# ---- final review I2: a generic naming a medicine the clinic hid is never learned back ---------------------------------

def test_a_doctor_generic_naming_a_hidden_canonical_never_undoes_the_hide(world, monkeypatch):
    _fake_pdf(monkeypatch)
    row = {**DOC, "name": "Fooprol", "generic": "Paracetamol", "generic_suggestion": ""}
    with _signed_in("dr.rao") as (rao,):
        body = {"op": "hide", "entry_key": "paracetamol"}
        assert rao.post("/api/v1/lists/medicine/changes", json=body, headers=H).status_code == 200
        docs = [save(rao, row=row, patient=p, headers=H) for p in ("Asha Verma", "Ravi Kulkarni")]
    with closing(_conn("rao")) as conn:
        assert all_rows(conn) == [("paracetamol", "hide", "admin", 0, {})] and doctor_audits(conn) == []
        assert under_clinic(conn, lambda: (D._exact_lookup("Paracetamol"), D.is_blocked("Paracetamol"))) == ("", True)
        assert under_clinic(conn, lambda: D._exact_lookup("Fooprol")) == ""
        for d in docs:                                                                  # the doctor's text still prints
            assert stored_rx(conn, d["document_id"])[0]["generic"] == "Paracetamol"
