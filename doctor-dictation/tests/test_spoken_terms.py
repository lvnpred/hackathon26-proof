"""The doctor's spoken terms become the speech hints (plan SH-H1): said = shown = printed = hinted. Offline."""
import json
from contextlib import closing
from datetime import date
from pathlib import Path

import pytest

from doctor_dictation import admin
from doctor_dictation import db as dbmod
from doctor_dictation.core import formulary as F
from doctor_dictation.core import investigations as I
from doctor_dictation.core import spoken as S
from doctor_dictation.core.determinism import load_lexicon

HT = S.HintTerm
DOLO = {"form": "Tab.", "name": "Dolo", "strength": "650 mg", "dose": "1-0-1", "status": "verified"}

@pytest.fixture(autouse=True)
def _no_layer_leaks():
    F.activate(F.ClinicLayer())
    yield
    F.activate(F.ClinicLayer())

def test_key_phrase_and_rank():
    assert S.key(" Dolo-650 & Co_ ") == "dolo 650 and co" and S.key("Vit. D3") == "vit d3" and S.key(None) == ""
    assert [S.phrase("Dolo", "650 mg"), S.phrase("Urimax", "0.4 mg"), S.phrase("Dolo", "650MG")] == ["Dolo 650", "Urimax 0.4", "Dolo 650"]
    assert S.phrase("Calpol", "120 mg/5ml") == "Calpol 120 mg/5ml" and S.phrase("Pan 40", "40 mg") == "Pan 40"
    assert S.phrase("Dolo", "") == "Dolo" and S.phrase("Dolo", "as told by Ramesh") == "Dolo"   # free text never sent
    assert [t.phrase for t in S.rank([HT("b", 1.0), HT("A", 1.0), HT("c", 2.0), HT("z", 0.1, tier=1)])] == ["z", "c", "A", "b"]

def test_usual_strength_needs_sixty_percent_and_two_uses():
    assert S.usual_strength({"650 mg": 3, "500 mg": 2}) == "650 mg"            # exactly 60%
    assert S.usual_strength({"650 mg": 59, "": 41}) == ""                       # 59%: no strength said counts as a use
    assert S.usual_strength({"650 mg": 60, "": 40}) == "650 mg"
    assert S.usual_strength({"650 mg": 1}) == ""                                # 100%, but one use
    assert S.usual_strength({"650 mg": 2, "500 mg": 2}) == "" and S.usual_strength({"": 5}) == S.usual_strength({}) == ""

def test_terms_keep_the_said_name_and_never_a_patient_word():
    form = {"patientName": "Chandrika Devi", "rx": [
        {"name": "Chandrika", "strength": "5 mg"},                                # this patient's own name
        {"name": "Ramu Syrup"},                                                   # another patient's name word
        {"name": "Ramesh Kumar"},                                                 # reads as a person, no list knows it
        {"name": "Augmentin Duo", "lexicon_match": "Amoxicillin + Clavulanic Acid"},   # person-like, but grounded
        {"name": "Dolo", "form": "Tab.", "strength": "650 mg", "lexicon_match": "Paracetamol", "generic": "Paracetamol"},
        {"name": "dolo", "strength": "500 mg"}, "junk", {"name": "x" * 61}],
        "investigations": [{"text": "Liver Function Test", "canonical": "Liver Function Test"},
                           {"text": "Blood Sugar", "canonical": ""}, "CBC"]}
    got = S.terms_from_save(form, frozenset({"ramu"}))
    assert [(t.kind, t.key, t.spoken) for t in got] == [
        ("medicine", "augmentin duo", "Augmentin Duo"), ("medicine", "dolo", "Dolo"),
        ("investigation", "liver function test", "Liver Function Test"), ("investigation", "cbc", "CBC")]
    assert got[1] == S.Term("medicine", "dolo", "Dolo", "Tab", "650 mg", "Paracetamol")   # the first row wins
    assert S.terms_from_save(None, ()) == [] and S.terms_from_save({"rx": "x"}, ()) == []

def test_patient_words_with_apostrophe_or_hyphen_still_match():
    form = {"rx": [{"name": "O'Brien Syrup"}, {"name": "Mary-Ann tab"}, {"name": "Dolo"}]}
    got = S.terms_from_save(form, frozenset({"o'brien", "mary-ann"}))
    assert [t.key for t in got] == ["dolo"]

def _doc(conn, at, rx):
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "", None))
    return dbmod.save_document(conn, eid, at, {"rx": rx}, finalized_at=at)

def _fresh(tmp_path):
    conn = dbmod.get_conn(tmp_path / "s.db")
    dbmod.migrate(conn)
    return conn

def test_a_document_counts_once_and_the_use_is_dated_by_the_document(tmp_path):
    from doctor_dictation.db import spoken as sdb
    conn = _fresh(tmp_path)
    one, two = _doc(conn, "2026-10-01T09:00:00Z", [DOLO]), _doc(conn, "2026-10-11T09:00:00Z", [DOLO])
    terms = S.terms_from_save({"rx": [DOLO]}, ())
    assert [sdb.record_terms(conn, 0, terms, d) for d in (two, one, one)] == [1, 1, 0]   # out of order, then a re-save
    row = conn.execute("SELECT uses, first_used_at, last_used_at FROM spoken_terms").fetchone()
    assert tuple(row) == (2, "2026-10-01T09:00:00Z", "2026-10-11T09:00:00Z")
    assert [tuple(r) for r in conn.execute("SELECT strength, uses FROM spoken_term_strengths")] == [("650 mg", 2)]
    today = date(2026, 10, 11)
    assert sdb.doctor_hint_terms(conn, 0, today) == [HT("Dolo 650", F.usage_score(2, row[2], today), term_id=1, key="dolo")]
    assert sdb.doctor_hint_terms(conn, 7, today) == []                        # another doctor's terms are not mine
    conn.close()

def test_every_live_term_comes_back_uncapped_with_its_id_and_key(tmp_path):
    from doctor_dictation.db import spoken as sdb
    conn = _fresh(tmp_path)
    names = [e["canonical"] for e in load_lexicon()[:80]]
    rows = [{"name": n, "lexicon_match": n} for n in names]
    sdb.record_terms(conn, 3, S.terms_from_save({"rx": rows}, ()), _doc(conn, "2026-10-11T09:00:00Z", []))
    conn.execute("UPDATE spoken_terms SET removed_at = 'x' WHERE term_key = ?", (S.key(names[0]),))   # as H2 removes
    got = sdb.doctor_hint_terms(conn, 3, date(2026, 10, 11))
    assert len(got) == 79 and all(t.term_id > 0 and t.key == S.key(t.phrase) for t in got)   # far over 500 chars
    assert names[0] not in [t.phrase for t in got]
    conn.close()

def test_a_failed_record_leaves_no_half_written_term(tmp_path):
    from doctor_dictation.db import spoken as sdb
    conn = _fresh(tmp_path)
    terms = S.terms_from_save({"rx": [DOLO]}, ())
    with pytest.raises(Exception):
        sdb.record_terms(conn, 0, terms, 999)                                   # no such document: the ledger insert fails
    bad = terms + [S.Term("nonsense", "x", "X", "", "", "")]
    with pytest.raises(Exception):
        sdb.record_terms(conn, 0, bad, _doc(conn, "2026-10-11T09:00:00Z", []))   # a valid first term, then a CHECK failure
    for table in ("spoken_terms", "spoken_term_docs", "spoken_term_strengths"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    doc = _doc(conn, "2026-10-12T09:00:00Z", [])
    sdb.record_terms(conn, 0, terms, doc)
    with pytest.raises(Exception):
        sdb.record_terms(conn, 0, bad, doc, previous=terms)                     # a failed re-save keeps the earlier use too
    assert conn.execute("SELECT uses FROM spoken_terms").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM spoken_term_docs").fetchone()[0] == 1
    conn.close()


@pytest.fixture()
def app(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from doctor_dictation.api import stt as stt_mod
    from doctor_dictation.api.app import create_app
    from doctor_dictation.config import override_settings
    from doctor_dictation.providers.stt.base import Transcript
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))                  # never the real dev database
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", lambda *a, **k: 1 / 0)   # fail-soft PDF
    sent = []

    class Recorder:
        name, available = "recorder", staticmethod(lambda: True)

        async def transcribe(self, audio, filename, hints=()):
            sent.append(list(hints))
            return Transcript(text="hello", engine="recorder")
    monkeypatch.setattr(stt_mod, "make_stt", lambda settings: Recorder())
    override_settings(monkeypatch, stt_use_hints=True, stt_trim_silence=False, stt_hint_limit=12)
    with TestClient(create_app()) as client:
        def save(rows, patient="Anita Rao", confirmed=(), document_id=None):
            body = {"structured": {"patientName": patient, "ageSex": "40 / F", "opNo": "", "rx": [dict(r) for r in rows]},
                    "confirmed_rows": list(confirmed), "document_id": document_id}
            r = client.post("/api/v1/documents", json=body)
            assert r.status_code == 200, r.text
            return r.json()["document_id"]

        def hints():
            assert client.post("/api/transcribe", files={"audio": ("n.webm", b"RAW", "audio/webm")}).status_code == 200
            return sent[-1]
        yield save, hints

def _terms():
    with closing(dbmod.get_conn()) as conn:
        return [tuple(r) for r in conn.execute("SELECT doctor_id, kind, term_key, spoken, uses FROM spoken_terms ORDER BY id")]

def test_an_unknown_name_is_stored_not_sent_a_patient_word_is_never_stored_and_a_resave_counts_once(app):
    save, hints = app
    rows = [{"form": "Cap.", "name": "Urimax", "strength": "0.4 mg", "status": "unknown-medicine"},
            {"form": "Tab.", "name": "Chandrika", "status": "unknown-medicine"}]
    doc = save(rows, patient="Chandrika Devi", confirmed=(0, 1))
    save(rows, patient="Chandrika Devi", confirmed=(0, 1), document_id=doc)   # a re-save of the same document
    assert _terms() == [(0, "medicine", "urimax", "Urimax", 1)]
    assert not [h for h in hints() if "urimax" in h.casefold() or "chandrika" in h.casefold()]

def test_a_failing_hook_never_blocks_the_save(app, monkeypatch):
    from doctor_dictation.db import spoken as sdb
    save, _ = app
    monkeypatch.setattr(sdb, "record_terms", lambda *a: 1 / 0)
    assert save([DOLO]) and _terms() == []

def test_hints_are_the_doctors_phrases_and_only_eligible_ones(tmp_path, monkeypatch):
    from doctor_dictation.core.hints import build_hints, prompt_text
    assert prompt_text([]) == "" and prompt_text(["Dolo 650"]) == "Dolo 650."
    assert prompt_text(["Dolo 650", "Pan 40", "CBC"]) == "Dolo 650. Pan 40. CBC."
    out = build_hints([HT("Dolo 650", 1.6)], limit=70)
    assert out[0] == "Dolo 650" and "Dolo" not in out                           # never "Paracetamol" in its place
    many = build_hints([HT(e["canonical"], 1.0) for e in load_lexicon()[:80]], limit=200)
    assert 20 <= len(many) < 80 and len(prompt_text(many)) <= 500 >= len(prompt_text(out))   # the budget is here
    assert "Urimax 0.4" not in build_hints([HT("Urimax 0.4", 9.0)], limit=70)  # no list knows it: stored, never sent
    assert build_hints([HT("Pan D", 1.0), HT("Pan 40", 0.5)], limit=2) == ["Pan D", "Pan 40"]   # combo, base name
    F.activate(F.ClinicLayer((("Urimax", ""),)))
    assert build_hints([HT("Urimax 0.4", 9.0)], limit=3)[:2] == ["Urimax 0.4", "Diclofenac"]   # the phrase claims "Urimax"
    assert "CBC" not in build_hints([HT("CBC", 9.0)], limit=70)
    cat = tmp_path / "investigations.json"                                    # not built yet on main: serve one
    cat.write_text(json.dumps({"version": "t", "entries": [{"canonical": "Complete Blood Count", "aliases": ["cbc"]}]}))
    monkeypatch.setattr(I, "CATALOGUE_PATH", cat)
    monkeypatch.setattr(I, "_shipped_cache", None)
    assert build_hints([HT("CBC", 9.0)], limit=1) == ["CBC"]                  # a test the catalogue knows, as said

def test_dolo_650_saved_twice_is_hinted_as_said(app):
    save, hints = app
    save([DOLO])
    save([DOLO], patient="Bala Iyer")
    assert _terms() == [(0, "medicine", "dolo", "Dolo", 2)]
    got = hints()
    assert got[0] == "Dolo 650" and "Paracetamol" not in got[:1]             # before H1 the first hint was "Paracetamol"

def test_a_long_run_of_digits_after_a_brand_is_never_sent():
    from doctor_dictation.core.hints import _base, build_hints, eligible
    for typed in ("Dolo 9876543210", "Dolo 98765 43210", "Dolo 650 98765",       # phone number, UHID, age typed after a brand
                  "Dolo 98.76543210", "Dolo 9876.543210", "Dolo 2345 6789"):     # a dot or a space inside a phone number
        assert not eligible(typed) and typed not in build_hints([HT(typed, 9.0)], limit=5)
    assert eligible("Dolo 650") and eligible("Urimax 0.4") is False and "Dolo 650" in build_hints([HT("Dolo 650", 9.0)], limit=5)
    assert eligible("Telma 40 12.5") and _base("Telma 40 12.5") == "Telma" and _base("Glycomet GP 0.5") == "Glycomet GP"
    assert S.phrase("Dolo", "98.76543210") == "Dolo" and S.phrase("Dolo", "9876543210") == "Dolo"   # never joined as a strength

def test_the_backfill_replays_saved_documents_once(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "old.db"))
    with closing(dbmod.get_conn()) as conn:
        dbmod.migrate(conn)
        _doc(conn, "2026-10-01T09:00:00Z", [DOLO])
        _doc(conn, "2026-10-02T09:00:00Z", [DOLO, {"name": "Pan", "strength": "40 mg"}])
    assert admin.main(["backfill-spoken-terms"]) == 0
    assert admin.main(["backfill-spoken-terms"]) == 0                        # the ledger: nothing counted twice
    out = capsys.readouterr().out.splitlines()
    assert out == ["single: 2 documents read, 3 new term uses", "single: 2 documents read, 0 new term uses"]
    assert [t[2:] for t in _terms()] == [("dolo", "Dolo", 2), ("pan", "Pan", 1)]
    monkeypatch.setenv("DB_PATH", str(tmp_path / "missing.db"))
    assert admin.main(["backfill-spoken-terms"]) == 1 and not (tmp_path / "missing.db").exists()


def test_a_strength_or_a_name_that_is_not_one_is_never_stored():
    form = {"rx": [{"name": "Dolo", "strength": "9876543210"}, {"name": "Pan", "strength": "as told by Ramesh"},
                   {"name": "Telma", "strength": "40 mg"}, {"name": "9876543210"}, {"name": "B2", "strength": "5 mg"}],
            "investigations": ["98765 43210"]}
    assert [(t.key, t.strength) for t in S.terms_from_save(form, ())] == [("dolo", ""), ("pan", ""), ("telma", "40 mg")]

def _strengths(name):
    with closing(dbmod.get_conn()) as conn:
        return {r[0]: r[1] for r in conn.execute("SELECT s.strength, s.uses FROM spoken_term_strengths s"
                                                 " JOIN spoken_terms t ON t.id = s.term_id WHERE t.term_key = ?", (name,))}

def test_a_resave_replaces_what_the_document_taught(app):
    save, hints = app
    pan = {"form": "Tab.", "name": "Pan", "strength": "40 mg", "status": "verified"}
    doc = save([DOLO])
    save([DOLO], document_id=doc)                                             # unchanged: still counted once
    assert _terms() == [(0, "medicine", "dolo", "Dolo", 1)] and _strengths("dolo") == {"650 mg": 1}
    save([dict(DOLO, strength="500 mg")], document_id=doc)                    # the strength moves
    assert _terms() == [(0, "medicine", "dolo", "Dolo", 1)] and _strengths("dolo") == {"650 mg": 0, "500 mg": 1}
    save([pan], document_id=doc)                                              # the name was corrected: Dolo loses its use
    assert _terms() == [(0, "medicine", "dolo", "Dolo", 0), (0, "medicine", "pan", "Pan", 1)]
    from doctor_dictation.db import spoken as sdb
    with closing(dbmod.get_conn()) as conn:
        assert [t.key for t in sdb.doctor_hint_terms(conn, 0, date(2026, 10, 23))] == ["pan"]
    assert not [h for h in hints() if h.casefold().startswith("dolo")]

def test_the_backfill_and_the_save_hook_share_one_core(tmp_path, monkeypatch):
    from doctor_dictation.api import spoken as A
    from doctor_dictation.db import formulary as fdb
    conn = _fresh(tmp_path)
    doc = _doc(conn, "2026-10-01T09:00:00Z", [DOLO])
    calls = []
    monkeypatch.setattr(A, "record_from_save", lambda c, structured, d, doctor, **kw: calls.append((d, doctor)) or 1 / 0)
    with pytest.raises(ZeroDivisionError):
        A.replay_saved(conn, by_doctor=False)                                 # the backfill surfaces the error
    A.learn_spoken_terms(conn, {"rx": [DOLO]}, doc, None)                     # the save hook never raises
    assert calls == [(doc, 0), (doc, 0)]
    monkeypatch.undo()
    monkeypatch.setattr(fdb, "patient_words", lambda c: 1 / 0)
    assert A.record_from_save(conn, {"rx": [], "investigations": []}, doc, 0) == 0   # nothing to learn: patients not read
    conn.close()

def test_one_failing_database_never_stops_the_backfill(tmp_path, monkeypatch, capsys):
    paths = []
    for name in ("a", "b"):
        with closing(dbmod.get_conn(tmp_path / f"{name}.db")) as conn:
            dbmod.migrate(conn)
        paths.append((name, tmp_path / f"{name}.db"))
    monkeypatch.setattr(admin.promotion, "clinic_dbs", lambda: paths)
    real, seen = admin.replay_saved, iter(["a", "b"])

    def replay(conn, by_doctor):
        if next(seen) == "a":
            raise ValueError("bad")                                           # not an OSError or a sqlite3.Error
        return real(conn, by_doctor)
    monkeypatch.setattr(admin, "replay_saved", replay)
    assert admin.main(["backfill-spoken-terms"]) == 1
    out, err = capsys.readouterr()
    assert out.splitlines() == ["b: 0 documents read, 0 new term uses"] and err.splitlines() == ["a: FAILED bad"]
