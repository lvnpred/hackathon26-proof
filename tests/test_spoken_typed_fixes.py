import json
from contextlib import closing

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation.core import formulary as F
from doctor_dictation.core import spoken
from doctor_dictation.core.correction import build_correction_messages
from doctor_dictation.db import spoken as sdb
from doctor_dictation.pdf import build_sheet_html

term = lambda name: spoken.terms_from_save({"rx": [{"name": name}]}, frozenset())[0].key   # noqa: E731
URIMAX = lambda n: spoken.key(n) == "urimax"                                                # the clinic list knows Urimax


def test_a_typed_fix_that_sounds_like_the_heard_words_is_a_pair():
    s = {"rx": [{"name": "Urimax", "heard": "", "typed_heard": "Urimacks"},
                {"name": "Silodal", "heard": "", "typed_heard": "Cello dial"}]}
    assert spoken.mishearings_from_save(s, frozenset(), listed=URIMAX) == [(term("Urimax"), "Urimacks"), (term("Silodal"), "Cello dial")]
    assert spoken.mishearings_from_save({"rx": [s["rx"][0]]}, frozenset()) == [(term("Urimax"), "Urimacks")]   # R2: no list needed


def test_a_typed_change_of_medicine_is_no_pair():
    s = {"rx": [{"name": "Montair", "typed_heard": "Montek"},         # alike (0.62) but heard is a known medicine (R1)
                {"name": "Crocin", "typed_heard": "Dolo"},
                {"name": "Tamsulosin", "typed_heard": "Urimacks"},    # cleared and retyped: not alike (Review Focus 2)
                {"name": "Urimax", "typed_heard": "Urimacks"}]}       # heard is on the clinic list: known
    assert spoken.mishearings_from_save(s, frozenset(), listed=lambda n: spoken.key(n) == "urimacks") == []


def test_one_pair_per_row_spelled_then_heard_then_typed():
    s = {"rx": [{"name": "Silodal", "spelled_heard": "Cello dial", "typed_heard": "Silo dal"},
                {"name": "Dolo", "heard": "dollo", "typed_heard": "Dolo"}]}
    assert spoken.mishearings_from_save(s, frozenset()) == [(term("Silodal"), "Cello dial"), (term("Dolo"), "dollo")]


def test_typed_heard_meets_the_h2_privacy_and_size_rules():
    s = {"patientName": "Ravi Kumar", "rx": [{"name": "Ravikind", "typed_heard": "Ravi kind"}, {"name": "Urimax", "typed_heard": 42},
                                             {"name": "Urimax", "typed_heard": "u" * 61}, {"name": "Urimax", "typed_heard": "Urimax"}]}
    assert spoken.mishearings_from_save(s, frozenset()) == []
    assert spoken.TYPED_SIMILAR == 0.6


# ---- through the save (SH-B5 task 2) ----
SILODAL = {"form": "Tab.", "name": "Silodal", "strength": "8 mg", "dose": "0-0-1", "status": "", "heard": "", "typed_heard": "Cello dial"}


@pytest.fixture()
def save(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from doctor_dictation.api.app import create_app
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))                  # never the real dev database
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", lambda *a, **k: 1 / 0)   # fail-soft PDF
    F.activate(F.ClinicLayer())
    with TestClient(create_app()) as client:
        def go(row, document_id=None):
            body = {"structured": {"patientName": "Anita Rao", "ageSex": "40 / F", "opNo": "", "rx": [dict(row)]},
                    "confirmed_rows": [0], "document_id": document_id}
            return client.post("/api/v1/documents", json=body)
        yield go
    F.activate(F.ClinicLayer())


def _stored(doc_id):
    with closing(dbmod.get_conn()) as conn:
        return json.loads(conn.execute("SELECT structured_json FROM documents WHERE id = ?", (doc_id,)).fetchone()[0])["rx"][0]


def _pairs(conn):
    return [tuple(r) for r in conn.execute("SELECT heard_key, confirm_count FROM spoken_mishearings")]


def test_two_saves_with_a_typed_fix_make_an_active_pair_and_print_nothing_new(save):
    doc1, doc2 = (save(SILODAL).json()["document_id"] for _ in range(2))
    assert _stored(doc1)["typed_heard"] == "Cello dial"                    # survives validate + restore
    with closing(dbmod.get_conn()) as conn:
        (tid,) = conn.execute("SELECT id FROM spoken_terms WHERE term_key = 'silodal'").fetchone()
        assert sdb.active_mishearing_term_ids(conn, 0) == {tid}            # active from the second document
    html = build_sheet_html({"patientName": "Anita Rao", "rx": [_stored(doc2)]}, {})
    assert "Cello dial" not in html and "typed_heard" not in html          # print unchanged


def test_a_resave_does_not_count_the_typed_pair_again(save):
    doc = save(SILODAL).json()["document_id"]
    assert save(SILODAL, document_id=doc).status_code == 200
    with closing(dbmod.get_conn()) as conn:
        assert _pairs(conn) == [("cello dial", 1)]                         # Review Focus 4


def test_junk_typed_heard_never_blocks_the_save(save):
    for junk, kept in ((42, ""), ("x" * 10_000, ""), (None, ""), (["Urimacks"], ""), ("Ravi Kumar", "Ravi Kumar")):
        r = save({"name": "Urimax", "status": "", "typed_heard": junk})
        assert r.status_code == 200
        assert _stored(r.json()["document_id"])["typed_heard"] == kept
    with closing(dbmod.get_conn()) as conn:
        assert _pairs(conn) == []                                          # Review Focus 3


def test_the_correction_model_never_sees_typed_heard():
    form = {"rx": [{"name": "Urimax", "typed_heard": "Urimacks"}]}
    assert "Urimacks" not in build_correction_messages("stop it", form)[1]["content"]
    assert form["rx"][0]["typed_heard"] == "Urimacks"                      # the caller's form is untouched


def test_the_backfill_honours_the_clinic_list_of_the_database_it_replays(tmp_path, monkeypatch):
    from doctor_dictation.api.spoken import replay_saved
    monkeypatch.setenv("DB_PATH", str(tmp_path / "b.db"))                    # never the real dev database
    F.activate(F.ClinicLayer())                                              # the CLI has no layer loaded, as here
    with closing(dbmod.get_conn()) as conn:
        dbmod.migrate(conn)
        eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "40 / M", None))
        for i, heard in enumerate(("Urimacks", "Cello dial")):               # a clinic-only name, then a plain mishearing
            name = "Urimax" if i == 0 else "Silodal"
            doc = dbmod.save_document(conn, eid, f"sha{i}", {"rx": [{"form": "Tab.", "name": name, "status": "verified", "typed_heard": heard}]})
            conn.execute("UPDATE documents SET finalized_at = '2026-10-28T00:00:00' WHERE id = ?", (doc,))
        conn.execute("INSERT INTO clinic_formulary(name_key, name, confirm_count, first_seen_at, last_seen_at)"
                     " VALUES ('urimacks', 'Urimacks', 2, 't', 't')")        # the clinic's own medicine, not in the lexicon
        conn.commit()
        replay_saved(conn, by_doctor=False)
        assert _pairs(conn) == [("cello dial", 1)]                           # Urimacks is a known medicine here (R1)
