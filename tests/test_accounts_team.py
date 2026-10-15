"""Team account operations: list, disable/enable, clinic-scoped reset, safeguards. Offline."""
from contextlib import closing

import pytest

from doctor_dictation import accounts as A
from doctor_dictation import authn, clinics, policy, sessions
from doctor_dictation import db as dbmod
from doctor_dictation import passwords as P
from doctor_dictation.scope import clinic_dir
from doctor_dictation.sessions import Identity

PW = "a-long-password-1"


@pytest.fixture()
def team(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    clinics.provision_clinic("iyer", "Iyer Clinic")
    rao, _ = A.create_user("rao", "dr.rao", display_name="Dr. Rao", password=PW)
    mehta, _ = A.create_user("rao", "dr.mehta", display_name="Dr. Mehta", password=PW)
    shah, _ = A.create_user("rao", "dr.shah", password=PW)
    iyer, _ = A.create_user("iyer", "dr.iyer", display_name="Dr. Iyer", password=PW)
    return {"rao": rao, "mehta": mehta, "shah": shah, "iyer": iyer}


def _me(team, name="rao", slug="rao"):
    return Identity(slug, team[name], "dr." + name, "doctor")


def _conn(slug):
    return dbmod.get_conn(clinic_dir(slug) / "app.db")


def _row(slug, uid):
    with closing(_conn(slug)) as c:
        return c.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def _audits(slug, action):
    with closing(_conn(slug)) as c:
        return c.execute("SELECT actor, role, entity_id, detail FROM audit_log WHERE action = ? ORDER BY id",
                         (action,)).fetchall()


def test_list_users_returns_public_fields_in_id_order_for_one_clinic_only(team):
    rows = A.list_users("rao")
    assert [r["username"] for r in rows] == ["dr.rao", "dr.mehta", "dr.shah"]
    assert rows[0] == {"id": team["rao"], "username": "dr.rao", "display_name": "Dr. Rao", "role": "doctor",
                       "is_active": True, "last_login_at": None, "must_change_password": True}
    assert rows[2]["display_name"] == "dr.shah"                 # no display name given: the username
    assert [r["username"] for r in A.list_users("iyer")] == ["dr.iyer"]


def test_get_user_for_an_unknown_id_raises_no_such_user(team):
    assert A.get_user("rao", team["mehta"])["username"] == "dr.mehta"
    with pytest.raises(A.NoSuchUser):
        A.get_user("rao", 99)
    assert issubclass(A.NoSuchUser, A.AccountError)


def test_disable_bumps_the_session_version_audits_and_ends_sign_in(team):
    cookie = sessions.sign("rao", team["mehta"], 0)
    assert authn.load_identity(cookie) is not None
    user = A.set_active(_me(team), team["mehta"], False)
    row = _row("rao", team["mehta"])
    assert user["is_active"] is False and (row["is_active"], row["session_version"]) == (0, 1)
    assert authn.load_identity(cookie) is None
    assert authn.authenticate("dr.mehta", PW, "127.0.0.1") is None
    assert [tuple(a)[:3] for a in _audits("rao", "user_disable")] == [("dr.rao", "doctor", str(team["mehta"]))]


def test_enable_restores_sign_in_but_never_revives_an_old_cookie(team):
    cookie = sessions.sign("rao", team["mehta"], 0)
    A.set_active(_me(team), team["mehta"], False)
    user = A.set_active(_me(team), team["mehta"], True)
    assert user["is_active"] is True and _row("rao", team["mehta"])["session_version"] == 1
    assert authn.load_identity(cookie) is None                  # issued before the disable: stays dead
    assert authn.authenticate("dr.mehta", PW, "127.0.0.1") is not None
    assert [tuple(a)[:3] for a in _audits("rao", "user_enable")] == [("dr.rao", "doctor", str(team["mehta"]))]


def test_you_cannot_disable_yourself(team):
    with pytest.raises(A.AccountError, match="your own account"):
        A.set_active(_me(team), team["rao"], False)
    assert _row("rao", team["rao"])["is_active"] == 1 and _audits("rao", "user_disable") == []


def test_the_last_active_user_cannot_be_disabled(team):
    with closing(_conn("rao")) as c:                            # Rao was disabled by a colleague a moment ago
        c.execute("UPDATE users SET is_active = 0 WHERE id IN (?, ?)", (team["rao"], team["shah"]))
        c.commit()
    with pytest.raises(A.StaleSession):                         # the stale actor is now caught first, in the same lock
        A.set_active(_me(team), team["mehta"], False)
    assert _row("rao", team["mehta"])["is_active"] == 1 and _audits("rao", "user_disable") == []


def test_disabling_twice_changes_and_audits_once(team):
    A.set_active(_me(team), team["mehta"], False)
    A.set_active(_me(team), team["mehta"], False)
    A.set_active(_me(team), team["shah"], True)                 # already active: nothing to do
    assert _row("rao", team["mehta"])["session_version"] == 1
    assert len(_audits("rao", "user_disable")) == 1 and _audits("rao", "user_enable") == []


def test_ids_from_another_clinic_raise_no_such_user_and_change_nothing(team):
    iyer = _me(team, "iyer", "iyer")
    assert team["iyer"] == team["rao"] == 1                     # ids repeat across clinic files
    calls = (lambda: A.set_active(iyer, team["shah"], False), lambda: A.set_active(iyer, team["shah"], True),
             lambda: A.reset_user_password(iyer, team["shah"]))
    for call in calls:
        with pytest.raises(A.NoSuchUser):
            call()
    row = _row("rao", team["shah"])
    assert (row["is_active"], row["session_version"]) == (1, 0)
    assert _audits("iyer", "user_disable") == [] and _audits("iyer", "password_reset") == []


def test_reset_user_password_bumps_version_forces_a_change_and_audits_the_actor(team):
    with closing(_conn("rao")) as c:
        c.execute("UPDATE users SET must_change_password = 0 WHERE id = ?", (team["mehta"],))
        c.commit()
    temp = A.reset_user_password(_me(team), team["mehta"])
    row = _row("rao", team["mehta"])
    assert len(temp) == 16 and P.verify_password(temp, row["password_hash"])
    assert not P.verify_password(PW, row["password_hash"])
    assert (row["session_version"], row["must_change_password"]) == (1, 1)
    audit = _audits("rao", "password_reset")
    assert [tuple(a)[:3] for a in audit] == [("dr.rao", "doctor", str(team["mehta"]))]
    assert temp not in (audit[0]["detail"] or "")


def test_reset_user_password_refuses_yourself_and_unknown_ids(team):
    with pytest.raises(A.AccountError, match="your own password"):
        A.reset_user_password(_me(team), team["rao"])
    with pytest.raises(A.NoSuchUser):
        A.reset_user_password(_me(team), 99)
    assert _row("rao", team["rao"])["session_version"] == 0 and _audits("rao", "password_reset") == []


def test_the_operator_reset_by_username_still_works_and_raises_no_such_user(team):
    temp = A.reset_password("DR.MEHTA", actor="operator")
    assert P.verify_password(temp, _row("rao", team["mehta"])["password_hash"])
    assert _audits("rao", "password_reset")[0]["actor"] == "operator"
    with pytest.raises(A.NoSuchUser):
        A.reset_password("nobody")


def test_policy_knows_the_team_actions(team):
    for action in ("user.view", "user.create", "user.disable", "user.reset_password"):
        assert policy.can(_me(team), action, {"user_id": team["mehta"]}) is True, action


def test_the_same_id_in_two_clinics_is_a_different_person_and_only_the_callers_clinic_changes(team):
    assert team["rao"] == team["iyer"] == 1                     # both clinics have a user 1
    iyer_actor, _ = A.create_user("iyer", "dr.actor", password=PW)
    actor = Identity("iyer", iyer_actor, "dr.actor", "doctor")
    before_rao = tuple(_row("rao", 1))
    A.set_active(actor, 1, False)
    assert (_row("iyer", 1)["is_active"], _row("iyer", 1)["session_version"]) == (0, 1)
    assert tuple(_row("rao", 1)) == before_rao                  # Rao's user 1 is untouched, version included
    A.set_active(actor, 1, True)
    old_hash = _row("iyer", 1)["password_hash"]
    A.reset_user_password(actor, 1)
    assert _row("iyer", 1)["password_hash"] != old_hash
    assert tuple(_row("rao", 1)) == before_rao


def test_set_active_takes_the_write_lock_before_it_reads_anything(team, monkeypatch):
    seen = []
    real = A.dbmod.get_conn

    def traced(*a, **k):
        conn = real(*a, **k)
        conn.set_trace_callback(seen.append)
        return conn

    monkeypatch.setattr(A.dbmod, "get_conn", traced)
    A.set_active(_me(team), team["mehta"], False)
    flat = [s.strip().upper() for s in seen]
    begin = next(i for i, s in enumerate(flat) if s.startswith("BEGIN IMMEDIATE"))
    reads = [i for i, s in enumerate(flat) if s.startswith("SELECT") and "FROM USERS" in s]
    assert reads and all(begin < i for i in reads), flat


@pytest.mark.parametrize("how", ["disabled", "version_bumped"])
def test_a_stale_actor_changes_nothing_and_is_not_audited(team, how):
    actor = _me(team)                                           # identity loaded at version 0
    with closing(_conn("rao")) as c:
        if how == "disabled":
            c.execute("UPDATE users SET is_active = 0 WHERE id = ?", (team["rao"],))
        else:
            c.execute("UPDATE users SET session_version = 1 WHERE id = ?", (team["rao"],))
        c.commit()
    before = tuple(_row("rao", team["mehta"]))
    for call in (lambda: A.set_active(actor, team["mehta"], False), lambda: A.set_active(actor, team["mehta"], True),
                 lambda: A.reset_user_password(actor, team["mehta"])):
        with pytest.raises(A.StaleSession) as exc:
            call()
        assert not isinstance(exc.value, A.NoSuchUser)
    assert tuple(_row("rao", team["mehta"])) == before
    assert not _audits("rao", "user_disable") and not _audits("rao", "user_enable") and not _audits("rao", "password_reset")


def test_the_operator_reset_by_username_still_works(team):
    assert len(A.reset_password("dr.mehta")) == 16
    assert _row("rao", team["mehta"])["session_version"] == 1
