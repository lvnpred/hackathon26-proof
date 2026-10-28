"""The per-clinic learned drug list in SQLite (plan I1-h): the ledger, the threshold and soft removal. Offline."""
import pytest

from doctor_dictation import db as dbmod
from doctor_dictation.core.formulary import key
from doctor_dictation.db import formulary as fdb


@pytest.fixture()
def conn(tmp_path):
    c = dbmod.get_conn(tmp_path / "f.db")
    dbmod.migrate(c)
    yield c
    c.close()


@pytest.fixture()
def docs(conn):
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "40 / M", None))
    return [dbmod.save_document(conn, eid, f"sha{i}", {"rx": []}) for i in range(4)]


def count(conn, doc, name="Zorbexin", user=None):
    return fdb.record_confirmation(conn, key(name), name, "", doc, user)


def added_by(conn):
    return conn.execute("SELECT added_by FROM clinic_formulary").fetchone()[0]


def test_a_name_needs_two_different_documents_and_a_resave_never_double_counts(conn, docs):
    d1, d2, d3, _ = docs
    assert (count(conn, d1), count(conn, d1), count(conn, d1)) == (1, 1, 1)             # the same document again
    assert fdb.list_active(conn) == []
    assert count(conn, d2) == 2
    (row,) = fdb.list_active(conn)
    assert (row["name"], row["confirm_count"], row["generic"]) == ("Zorbexin", 2, None)
    assert count(conn, d3) == 3 and len(fdb.list_active(conn)) == 1


def test_a_removed_name_needs_two_fresh_documents_and_old_ones_do_not_count(conn, docs):
    d1, d2, d3, d4 = docs
    count(conn, d1), count(conn, d2)
    (row,) = fdb.list_active(conn)
    assert fdb.remove(conn, row["id"]) == "Zorbexin" and fdb.remove(conn, row["id"]) is None   # second removal: not active
    assert fdb.list_active(conn) == []
    assert count(conn, d1) == 0 and count(conn, d2) == 0 and fdb.list_active(conn) == []       # re-saving old documents
    assert count(conn, d3) == 1 and fdb.list_active(conn) == []                                # one new one is not enough
    assert count(conn, d4) == 2 and [r["name"] for r in fdb.list_active(conn)] == ["Zorbexin"]
    assert conn.execute("SELECT removed_at FROM clinic_formulary").fetchone()[0] is None


def test_the_name_key_is_unique(conn, docs):
    count(conn, docs[0])
    with pytest.raises(Exception):
        conn.execute("INSERT INTO clinic_formulary(name_key, name, first_seen_at, last_seen_at) VALUES ('zorbexin','Z','x','x')")


def test_added_by_is_the_user_whose_confirmation_activated_the_name(conn, docs):
    d1, d2, d3, d4 = docs
    a, b, c = (dbmod.create_user(conn, u, "x") for u in ("a", "b", "c"))
    count(conn, d1, user=a)
    assert added_by(conn) is None                      # not active yet
    count(conn, d2, user=b)
    assert added_by(conn) == b
    count(conn, d3, user=c)
    assert added_by(conn) == b                         # a later confirmation does not take over
    (row,) = fdb.list_active(conn)
    fdb.remove(conn, row["id"])
    count(conn, d3, user=c), count(conn, d4, user=a)   # d3 is already in the ledger: only d4 is new
    assert fdb.list_active(conn) == []
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "Q", "30 / F", None))
    d5 = dbmod.save_document(conn, eid, "sha5", {"rx": []})
    count(conn, d5, user=c)
    assert added_by(conn) == c and len(fdb.list_active(conn)) == 1


def test_a_combination_or_misspelt_name_goes_live_only_after_the_threshold(conn, docs):
    from doctor_dictation.core.formulary import THRESHOLD
    for name in ("Zerodol-P", "Crocinn"):
        assert count(conn, docs[0], name) == 1 and name not in [r["name"] for r in fdb.list_active(conn)]
        assert count(conn, docs[1], name) == THRESHOLD and name in [r["name"] for r in fdb.list_active(conn)]
