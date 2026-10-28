"""can() and the audit actor taken from the request scope. Offline."""
from contextlib import closing
from types import SimpleNamespace as NS

from doctor_dictation import clinics
from doctor_dictation import db as dbmod
from doctor_dictation import policy
from doctor_dictation.scope import Scope, use_scope
from doctor_dictation.sessions import Identity


def _me(uid=1):
    return Identity("rao", uid, "dr.rao", "doctor")


def test_unknown_actions_are_denied():
    assert policy.can(_me(), "document.delete") is False
    assert policy.can(_me(), "") is False


def test_ordinary_actions_are_allowed_for_any_signed_in_user():
    for action in ("document.view", "document.reprint", "user.view", "letterhead.manage"):
        assert policy.can(_me(), action, NS(author_id=2)) is True, action


def test_only_the_author_may_edit_a_document():
    assert policy.can(_me(1), "document.edit", NS(author_id=1)) is True
    assert policy.can(_me(1), "document.edit", NS(author_id=2)) is False
    assert policy.can(_me(1), "document.edit", {"author_id": 2}) is False
    assert policy.can(_me(1), "document.edit", None) is False


def test_a_document_with_no_recorded_author_can_be_edited_by_anyone_in_the_clinic():
    assert policy.can(_me(5), "document.edit", NS(author_id=None)) is True


def test_log_audit_fills_actor_and_role_from_the_scope(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    with use_scope(Scope("rao", 5, "dr.rao", "doctor")):
        with closing(dbmod.get_conn()) as conn:
            dbmod.log_audit(conn, action="probe")
            row = conn.execute("SELECT actor, role FROM audit_log WHERE action = 'probe'").fetchone()
    assert (row["actor"], row["role"]) == ("dr.rao", "doctor")


def test_an_explicit_actor_wins_over_the_scope(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    with use_scope(Scope("rao", 5, "dr.rao", "doctor")):
        with closing(dbmod.get_conn()) as conn:
            dbmod.log_audit(conn, actor="admin-cli", role="system", action="probe")
            row = conn.execute("SELECT actor, role FROM audit_log WHERE action = 'probe'").fetchone()
    assert (row["actor"], row["role"]) == ("admin-cli", "system")


def test_no_scope_leaves_the_actor_empty_as_before(tmp_path):
    with closing(dbmod.get_conn(tmp_path / "a.db")) as conn:
        dbmod.migrate(conn)
        dbmod.log_audit(conn, action="probe")
        row = conn.execute("SELECT actor, role FROM audit_log WHERE action = 'probe'").fetchone()
    assert (row["actor"], row["role"]) == (None, None)
