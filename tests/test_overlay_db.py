"""The per-clinic overlay on the shipped lists (plan PQ-f): upsert, reset, the confirmation ledger, approval. Offline."""
import sqlite3
import threading

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation.core import formulary
from doctor_dictation.db import overlay


@pytest.fixture()
def conn(tmp_path):
    c = dbmod.get_conn(tmp_path / "a.db")
    dbmod.migrate(c)
    dbmod.create_user(c, "u1", "x")
    dbmod.create_user(c, "u2", "x")
    yield c
    c.close()


def doc(conn) -> int:
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "40 / M", None))
    return dbmod.save_document(conn, eid, f"sha{conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0]}", {"rx": []})


G = {"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol"}


def confirm(conn, d, data=G):
    return overlay.record_confirmation(conn, "medicine", "zerodol-p", "add", data, "", d, 1)


def test_upsert_inserts_then_updates_one_row(conn):
    i = overlay.upsert(conn, "medicine", "zerodol-p", "add", G, "", "admin", 1)
    j = overlay.upsert(conn, "medicine", "zerodol-p", "add", {"name": "Zerodol-P", "generic": "X"}, "", "admin", 2)
    rows = overlay.list_rows(conn, "medicine")
    assert i == j and len(rows) == 1 and rows[0]["data"] == {"name": "Zerodol-P", "generic": "X"}
    assert rows[0]["created_by"] == 1


def test_reset_hides_the_row_and_upsert_revives_it(conn):
    overlay.upsert(conn, "medicine", "zerodol-p", "add", G, "", "admin", 1)
    assert overlay.reset(conn, "medicine", "zerodol-p") is True
    assert overlay.list_rows(conn, "medicine") == []
    assert overlay.reset(conn, "medicine", "zerodol-p") is False
    overlay.upsert(conn, "medicine", "zerodol-p", "add", G, "", "admin", 1)
    rows = overlay.list_rows(conn, "medicine")
    assert len(rows) == 1 and conn.execute("SELECT removed_at FROM clinic_overlay").fetchone()[0] is None


def test_kinds_are_separate(conn):
    overlay.upsert(conn, "medicine", "x", "add", G, "", "admin", 1)
    overlay.upsert(conn, "investigation", "x", "add", {"name": "X"}, "", "admin", 1)
    assert len(overlay.list_rows(conn, "medicine")) == 1 and len(overlay.list_rows(conn, "investigation")) == 1
    assert conn.execute("SELECT COUNT(*) FROM clinic_overlay").fetchone()[0] == 2


@pytest.mark.parametrize("kind,action,source", [("drug", "add", "admin"), ("medicine", "delete", "admin")])
def test_check_constraints_reject_bad_kind_action(conn, kind, action, source):
    with pytest.raises(sqlite3.IntegrityError):
        overlay.upsert(conn, kind, "k", action, {}, "", source, 1)


@pytest.mark.parametrize("source", ["doctor", "learned", "x"])
def test_upsert_is_admin_only(conn, source):
    with pytest.raises(ValueError):
        overlay.upsert(conn, "medicine", "k", "add", {}, "", source, 1)


def test_concurrent_confirmations_all_count(tmp_path):
    path = tmp_path / "t.db"
    setup = dbmod.get_conn(path)
    dbmod.migrate(setup)
    dbmod.create_user(setup, "u1", "x")
    docs = [doc(setup) for _ in range(8)]
    setup.close()
    errors = []

    def work(d):
        c = dbmod.get_conn(path)
        try:
            confirm(c, d)
        except Exception as e:  # noqa: BLE001
            errors.append(e)
        finally:
            c.close()

    threads = [threading.Thread(target=work, args=(d,)) for d in docs]
    [t.start() for t in threads]
    [t.join() for t in threads]
    c = dbmod.get_conn(path)
    try:
        ledger = c.execute("SELECT COUNT(*) FROM clinic_overlay_docs").fetchone()[0]
        count = c.execute("SELECT confirm_count FROM clinic_overlay").fetchone()[0]
        rows = c.execute("SELECT COUNT(*) FROM clinic_overlay").fetchone()[0]
    finally:
        c.close()
    assert errors == [] and rows == 1 and count == ledger == 8


def test_resave_of_the_same_document_never_counts_twice(conn):
    d = doc(conn)
    assert confirm(conn, d) == 1 and confirm(conn, d) == 1
    assert overlay.list_rows(conn, "medicine") == []
    assert overlay.list_rows(conn, "medicine", pending=True)[0]["confirm_count"] == 1


def test_different_data_restarts_at_1(conn):
    confirm(conn, doc(conn))
    assert confirm(conn, doc(conn), {"name": "Zerodol-P", "generic": "Aceclofenac"}) == 1
    assert overlay.list_rows(conn, "medicine", pending=True)[0]["data"]["generic"] == "Aceclofenac"
    assert conn.execute("SELECT COUNT(*) FROM clinic_overlay_docs").fetchone()[0] == 1


def test_reaching_threshold_activates(conn):
    confirm(conn, doc(conn))
    assert confirm(conn, doc(conn)) == formulary.THRESHOLD
    assert [r["entry_key"] for r in overlay.list_rows(conn, "medicine")] == ["zerodol-p"]
    assert overlay.list_rows(conn, "medicine", pending=True) == []


def test_admin_source_is_active_at_0(conn):
    overlay.upsert(conn, "medicine", "zerodol-p", "add", G, "", "admin", 1)
    assert overlay.list_rows(conn, "medicine")[0]["confirm_count"] == 0
    assert confirm(conn, doc(conn), {"name": "Zerodol-P", "generic": "X"}) == 0
    assert overlay.list_rows(conn, "medicine")[0]["data"] == G


def test_removed_rows_are_inactive(conn):
    confirm(conn, doc(conn))
    confirm(conn, doc(conn))
    overlay.reset(conn, "medicine", "zerodol-p")
    assert overlay.list_rows(conn, "medicine") == [] and overlay.list_rows(conn, "medicine", pending=True) == []
    assert confirm(conn, doc(conn)) == 1
    assert len(overlay.list_rows(conn, "medicine", pending=True)) == 1


def test_removed_admin_row_is_revived_as_pending_by_a_doctor(conn):
    overlay.upsert(conn, "medicine", "zerodol-p", "add", G, "", "admin", 1)
    overlay.reset(conn, "medicine", "zerodol-p")
    assert confirm(conn, doc(conn)) == 1
    row = overlay.list_rows(conn, "medicine", pending=True)[0]
    assert row["source"] == "doctor" and row["confirm_count"] == 1


def test_approve_sets_source_admin(conn):
    confirm(conn, doc(conn))
    assert overlay.approve(conn, "medicine", "zerodol-p", 2) is True
    assert overlay.list_rows(conn, "medicine")[0]["source"] == "admin"
    assert overlay.approve(conn, "medicine", "zerodol-p", 2) is False
    assert overlay.approve(conn, "medicine", "nope", 2) is False
