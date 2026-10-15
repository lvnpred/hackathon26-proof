"""Directory database: clinics, username index, throttling table. Offline."""
import sqlite3
from contextlib import closing

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation import directory as D


def test_open_directory_creates_the_tables_and_is_idempotent(multi):
    with closing(D.open_directory()) as conn:
        names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert dbmod.migrate(conn, D.DIR_MIGRATIONS) == []   # already applied
    assert {"clinics", "login_index", "login_attempts"} <= names
    assert (multi / "directory.db").is_file()
    with closing(D.open_directory()):
        pass                                                  # reopening is fine


def test_directory_holds_no_patient_data_tables(multi):
    with closing(D.open_directory()) as conn:
        names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {n for n in names if not n.startswith("sqlite_")} == {"clinics", "login_index", "login_attempts", "revoked_sessions", "schema_migrations"}


def test_create_and_list_clinics(multi):
    with closing(D.open_directory()) as conn:
        a = D.create_clinic(conn, "rao", "  Rao Clinic ", "RAO")
        D.create_clinic(conn, "iyer", "Iyer Clinic")
        assert isinstance(a, int)
        row = D.get_clinic(conn, "rao")
        assert (row["slug"], row["name"], row["status"], row["op_prefix"]) == ("rao", "Rao Clinic", "active", "RAO")
        assert D.get_clinic(conn, "nope") is None
        assert [r["slug"] for r in D.list_clinics(conn)] == ["iyer", "rao"]
        conn.execute("UPDATE clinics SET status='disabled' WHERE slug='iyer'")
        assert [r["slug"] for r in D.list_clinics(conn, active_only=True)] == ["rao"]
        assert D.get_clinic(conn, "iyer")["op_prefix"] == "OP"


def test_create_clinic_rejects_bad_input_and_duplicates(multi):
    with closing(D.open_directory()) as conn:
        for slug, name, prefix in [("../x", "X", "OP"), ("RAO", "X", "OP"), ("rao", "   ", "OP"),
                                   ("rao", "X", "op"), ("rao", "X", "O"), ("rao", "X", "TOOLONG1")]:
            with pytest.raises(D.DirectoryError):
                D.create_clinic(conn, slug, name, prefix)
        D.create_clinic(conn, "rao", "Rao Clinic")
        with pytest.raises(D.DirectoryError, match="already exists"):
            D.create_clinic(conn, "rao", "Other")
        assert len(D.list_clinics(conn)) == 1


def test_usernames_are_unique_system_wide_ignoring_case(multi):
    with closing(D.open_directory()) as conn:
        D.create_clinic(conn, "rao", "Rao Clinic")
        conn.execute("INSERT INTO login_index(username, clinic_slug, user_id) VALUES ('Dr.Rao', 'rao', 1)")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO login_index(username, clinic_slug, user_id) VALUES ('dr.rao', 'rao', 2)")
        with pytest.raises(sqlite3.IntegrityError):   # foreign key: the clinic must exist
            conn.execute("INSERT INTO login_index(username, clinic_slug, user_id) VALUES ('x.y', 'ghost', 1)")
