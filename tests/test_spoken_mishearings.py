"""Corrected mishearings (plan SH-H2): the pair rule, the ledger, tier 1 in the hints, the admin routes. Offline."""
import sqlite3

from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api import stt as api_stt
from doctor_dictation.api.app import create_app
from doctor_dictation.api.spoken import learn_spoken_terms
from doctor_dictation.core import spoken
from doctor_dictation.core.hints import build_hints
from doctor_dictation.db import spoken as sdb

DOLO = {"name": "Dolo", "heard": "dollo"}
H = {"X-DD-Client": "1"}


def test_pairs_come_only_from_rows_whose_heard_is_another_word():
    s = {"patientName": "Ravi Kumar", "rx": [
        {"name": "Dolo", "heard": "dollo"}, {"name": "Dolo", "heard": " DOLLO "},   # a pair; once per document
        {"name": "Crocin", "heard": ""},                     # said as written
        {"name": "Paracetamol", "heard": "crocin"},          # another name of the same medicine
        {"name": "Montair-LC", "heard": "montair lc"},       # the same words by key
        {"name": "Zorbexin", "heard": "Asha"}, {"name": "Zorbexin", "heard": "Ravi Kumar"},   # S3: patient word, person-like
        {"name": "Zorbexin", "heard": "z" * 61}, {"name": "Zorbexin", "heard": "a b c d e f g h i j"},   # too long
        {"name": "Zorbexin", "heard": 42}, "not a row",      # junk from the page
        {"name": "Zorbexin", "heard": "zorbexen"},           # an unknown name misheard: a pair (stored, never hinted)
        {"name": "Dolo 650", "heard": "dolo"}, {"name": "Dolo 650", "heard": "Dolo 650"},   # the name without its strength
    ]}
    term = lambda name: spoken.terms_from_save({"rx": [{"name": name}]}, frozenset())[0].key   # noqa: E731 - H1's key
    assert spoken.mishearings_from_save(s, frozenset({"asha"})) == [(term("Dolo"), "dollo"), (term("Zorbexin"), "zorbexen")]
    assert spoken.mishearings_from_save({"rx": "x"}, frozenset()) == spoken.mishearings_from_save(None, frozenset()) == []
    assert (spoken.MAX_HEARD_CHARS, spoken.MAX_HEARD_WORDS) == (60, 9)


def test_a_spelled_name_pairs_the_words_it_replaced():
    term = lambda name: spoken.terms_from_save({"rx": [{"name": name}]}, frozenset())[0].key   # noqa: E731
    only_spelled = {"rx": [{"name": "Zorbexin", "heard": "", "spelled_heard": "zorbexen"}]}
    assert spoken.mishearings_from_save(only_spelled, frozenset()) == [(term("Zorbexin"), "zorbexen")]
    both = {"rx": [{"name": "Silodal", "heard": "silodel", "spelled_heard": "Cello  dial"}]}
    assert spoken.mishearings_from_save(both, frozenset()) == [(term("Silodal"), "Cello dial")]
    blank = {"rx": [{"name": "Silodal", "heard": "silodel", "spelled_heard": "  "}]}
    assert spoken.mishearings_from_save(blank, frozenset()) == [(term("Silodal"), "silodel")]


def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "s.db"))                # never the real dev database
    conn = dbmod.get_conn()
    dbmod.migrate(conn)
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "40 / M", None))
    return conn, (dbmod.save_document(conn, eid, f"sha{i}", {"rx": []}) for i in range(20))


def rx(*rows):
    return {"patientName": "Ravi Kumar", "rx": [{"form": "Tab.", "strength": "", "status": "verified", **r} for r in rows]}


def test_a_pair_counts_once_per_document_and_is_active_from_the_second(tmp_path, monkeypatch):
    conn, docs = _db(tmp_path, monkeypatch)
    first = next(docs)
    learn_spoken_terms(conn, rx(DOLO), first, None)
    learn_spoken_terms(conn, rx(DOLO), first, None)                                   # a re-save of the same document
    assert [tuple(r) for r in conn.execute("SELECT confirm_count, removed_at FROM spoken_mishearings")] == [(1, None)]
    assert sdb.active_mishearing_term_ids(conn, 0) == set()
    learn_spoken_terms(conn, rx(DOLO), next(docs), None)
    (tid,) = sdb.active_mishearing_term_ids(conn, 0)
    assert conn.execute("SELECT spoken FROM spoken_terms WHERE id = ?", (tid,)).fetchone()[0] == "Dolo"
    assert sdb.active_mishearing_term_ids(conn, 7) == set()                         # another doctor: untouched
    assert sdb.record_mishearings(conn, 0, [("nosuchterm", "nosuchtern")], next(docs)) == 0   # no term: nothing stored
    assert conn.execute("SELECT COUNT(*) FROM spoken_mishearings").fetchone()[0] == 1
    conn.close()


def test_a_failing_pair_step_never_blocks_the_save_or_the_terms(tmp_path, monkeypatch, caplog):
    conn, docs = _db(tmp_path, monkeypatch)
    monkeypatch.setattr(sdb, "record_mishearings", lambda *_a: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
    learn_spoken_terms(conn, rx(DOLO), next(docs), None)                            # no exception (S4)
    assert [r[0] for r in conn.execute("SELECT spoken FROM spoken_terms")] == ["Dolo"]   # H1's part still ran
    assert "spoken mishearings" in caplog.text
    conn.close()


def test_an_active_pair_puts_its_term_first_and_the_heard_word_never_leaves(tmp_path, monkeypatch):
    conn, docs = _db(tmp_path, monkeypatch)
    for _ in range(3):
        learn_spoken_terms(conn, rx({"name": "Pan", "heard": ""}), next(docs), None)
    learn_spoken_terms(conn, rx(DOLO), next(docs), None)
    assert [(h.phrase, h.tier) for h in spoken.rank(api_stt._doctor_terms(None))][:2] == [("Pan", 0), ("Dolo", 0)]
    learn_spoken_terms(conn, rx(DOLO), next(docs), None)                            # the second document: active
    terms = api_stt._doctor_terms(None)
    assert [(h.phrase, h.tier) for h in spoken.rank(terms)][:2] == [("Dolo", 1), ("Pan", 0)]   # 2 uses beat 3 by tier
    hints = build_hints(terms, 70)
    assert hints[:2] == ["Dolo", "Pan"] and not [h for h in hints if "dollo" in h.casefold()]   # S2
    conn.close()


def test_removal_is_soft_and_only_new_documents_bring_a_pair_back(tmp_path, monkeypatch):
    conn, docs = _db(tmp_path, monkeypatch)
    first = [next(docs), next(docs)]
    for d in first:
        learn_spoken_terms(conn, rx(DOLO), d, None)
    (item,) = sdb.list_active_mishearings(conn)
    assert (item["spoken"], item["heard"], item["confirm_count"], item["doctor_id"], item["doctor"]) == ("Dolo", "dollo", 2, 0, "")
    assert sdb.remove_mishearing(conn, item["id"]) == {"spoken": "Dolo", "heard": "dollo"}
    assert sdb.remove_mishearing(conn, item["id"]) is None and sdb.list_active_mishearings(conn) == []
    for d in first:
        learn_spoken_terms(conn, rx(DOLO), d, None)                                 # old documents re-saved: no count
    learn_spoken_terms(conn, rx(DOLO), next(docs), None)
    assert sdb.active_mishearing_term_ids(conn, 0) == set()                         # 1 new document of 2
    learn_spoken_terms(conn, rx(DOLO), next(docs), None)
    assert len(sdb.active_mishearing_term_ids(conn, 0)) == 1
    assert conn.execute("SELECT COUNT(*) FROM spoken_mishearings").fetchone()[0] == 1   # the same row came back
    conn.close()


def test_the_routes_list_and_remove_like_the_formulary_routes_and_spell_it_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "r.db"))
    row = {"form": "Tab.", "name": "Dolo", "status": "verified", "heard": "dollo"}
    ask, url = {"row": {"name": "dollo"}, "transcript": "tab dollo 650 twice daily"}, "/api/v1/spoken/mishearings"
    with TestClient(create_app()) as c:
        before = c.post("/api/v1/rx/check-row", json=ask, headers=H).json()
        for patient in ("Sita Devi", "Mohan Lal"):
            body = {"structured": {"patientName": patient, "ageSex": "40 / M", "opNo": "", "rx": [row]}, "confirmed_rows": []}
            assert c.post("/api/v1/documents", json=body, headers=H).status_code == 200
        (item,) = c.get(url, headers=H).json()["items"]
        assert set(item) == {"id", "spoken", "heard", "confirm_count", "first_seen_at", "last_seen_at", "doctor_id", "doctor"}
        assert (item["spoken"], item["heard"], item["confirm_count"]) == ("Dolo", "dollo", 2)
        assert c.post("/api/v1/rx/check-row", json=ask, headers=H).json() == before        # S1
        assert c.delete(f"{url}/0", headers=H).status_code == 422
        gone = c.delete(f"{url}/{item['id'] + 1}", headers=H)
        assert (gone.status_code, gone.json()) == (404, {"error": "no such mishearing"})
        r = c.delete(f"{url}/{item['id']}", headers=H)
        assert (r.status_code, r.json()) == (200, {"removed": item["id"], "spoken": "Dolo", "heard": "dollo"})
        assert c.get(url, headers=H).json() == {"items": []}

        monkeypatch.setattr(sdb, "list_active_mishearings", lambda _c: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
        assert (c.get(url, headers=H).status_code, c.get(url, headers=H).json()) == (503, {"error": "try again"})
    conn = dbmod.get_conn()
    (detail,) = [r[0] for r in conn.execute("SELECT detail FROM audit_log WHERE action = 'spoken.mishearing.remove'")]
    assert "dollo" in detail and "Dolo" in detail
    conn.close()


def test_a_pair_whose_term_has_no_uses_left_is_not_active(tmp_path, monkeypatch):
    conn, docs = _db(tmp_path, monkeypatch)
    first = [next(docs), next(docs)]
    for d in first:
        learn_spoken_terms(conn, rx(DOLO), d, None)
    assert len(sdb.list_active_mishearings(conn)) == 1 and len(sdb.active_mishearing_term_ids(conn, 0)) == 1
    for d in first:                                                                  # both documents re-saved without Dolo
        learn_spoken_terms(conn, rx({"name": "Pan", "heard": ""}), d, None, previous=rx(DOLO))
    assert conn.execute("SELECT uses FROM spoken_terms WHERE spoken = 'Dolo'").fetchone()[0] == 0
    assert sdb.list_active_mishearings(conn) == [] and sdb.active_mishearing_term_ids(conn, 0) == set()
    conn.close()


def test_a_failing_tier_lift_keeps_the_doctors_terms(tmp_path, monkeypatch, capsys):
    conn, docs = _db(tmp_path, monkeypatch)
    learn_spoken_terms(conn, rx({"name": "Pan", "heard": ""}), next(docs), None)
    monkeypatch.setattr(sdb, "active_mishearing_term_ids", lambda *_a: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
    assert [(h.phrase, h.tier) for h in api_stt._doctor_terms(None)] == [("Pan", 0)]
    assert "hints: mishearing lift unavailable" in capsys.readouterr().out
    conn.close()
