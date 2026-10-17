"""The team actions are admin only, and a new user is an admin by default until real roles exist (owner decision).
Offline. Reuses the world of test_users_routes: dr.rao and dr.iyer are admins, dr.mehta and dr.shah are doctors."""
from contextlib import closing

from fastapi.testclient import TestClient

from doctor_dictation import accounts, admin
from doctor_dictation import db as dbmod
from doctor_dictation import scope as S
from doctor_dictation.api.app import create_app
from test_users_routes import H, _conn, _login, _names, _signed_in, world  # noqa: F401


def _row(uid):
    with closing(_conn("rao")) as c:
        return tuple(c.execute("SELECT is_active, session_version, password_hash, must_change_password FROM users WHERE id = ?",
                               (uid,)).fetchone())


def test_a_doctor_gets_403_on_every_team_write_and_nothing_changes(world):
    ids = [world["rao"], world["mehta"], world["shah"]]
    before = [_row(i) for i in ids]
    with _signed_in("dr.mehta") as (mehta,):
        names_before = _names(mehta)
        answers = [mehta.post("/api/v1/users", json={"username": "dr.sneak"}, headers=H)]
        for verb in ("disable", "enable", "reset-password"):
            for target in ("rao", "shah"):                      # an admin and a colleague
                answers.append(mehta.post(f"/api/v1/users/{world[target]}/{verb}", headers=H))
        names_after = _names(mehta)                              # reading the list is still allowed
    assert all(r.status_code == 403 and r.json() == {"error": "You are not allowed to do that"} for r in answers), [r.text for r in answers]
    assert not any("temporary_password" in r.text for r in answers)
    assert [_row(i) for i in ids] == before and names_before == names_after and "dr.sneak" not in names_after


def test_the_escalation_chain_is_closed_a_doctor_cannot_reset_an_admin_and_become_them(world):
    with _signed_in("dr.mehta") as (mehta,):
        reset = mehta.post(f"/api/v1/users/{world['rao']}/reset-password", headers=H)
        disable = mehta.post(f"/api/v1/users/{world['rao']}/disable", headers=H)
    assert (reset.status_code, disable.status_code) == (403, 403) and "temporary_password" not in reset.text
    with TestClient(create_app(), follow_redirects=False) as fresh:
        assert _login(fresh, "dr.rao").status_code == 200       # the admin's password still works and they are not disabled


def test_an_admin_still_creates_disables_enables_and_resets(world):
    with _signed_in("dr.rao") as (rao,):
        made = rao.post("/api/v1/users", json={"username": "dr.ok"}, headers=H)
        off = rao.post(f"/api/v1/users/{world['shah']}/disable", headers=H)
        on = rao.post(f"/api/v1/users/{world['shah']}/enable", headers=H)
        reset = rao.post(f"/api/v1/users/{world['shah']}/reset-password", headers=H)
    assert (made.status_code, off.status_code, on.status_code, reset.status_code) == (201, 200, 200, 200)
    assert reset.json()["temporary_password"]


def test_a_user_added_through_the_team_form_is_an_admin_by_default_and_the_body_cannot_choose(world):
    with _signed_in("dr.rao") as (rao,):
        r = rao.post("/api/v1/users", json={"username": "dr.def", "role": "doctor"}, headers=H)     # an unknown field is ignored
    assert r.status_code == 201 and r.json()["user"]["role"] == accounts.DEFAULT_ROLE == "admin"


def _role(slug, username):
    with closing(dbmod.get_conn(S.clinic_dir(slug) / "app.db")) as c:
        return c.execute("SELECT role FROM users WHERE username = ?", (username,)).fetchone()["role"]


def test_the_first_user_and_create_user_default_to_admin_and_an_explicit_role_wins(multi, capsys):
    assert admin.main(["create-clinic", "--slug", "rao", "--name", "Rao", "--first-user", "dr.rao"]) == 0
    assert admin.main(["create-user", "--clinic", "rao", "--username", "dr.def"]) == 0
    assert admin.main(["create-user", "--clinic", "rao", "--username", "dr.doc", "--role", "doctor"]) == 0
    assert admin.main(["create-user", "--clinic", "rao", "--username", "dr.assist", "--role", "assistant"]) == 0
    assert [_role("rao", u) for u in ("dr.rao", "dr.def", "dr.doc", "dr.assist")] == ["admin", "admin", "doctor", "assistant"]


def test_the_demo_seed_still_creates_plain_doctors(multi, monkeypatch):
    from doctor_dictation import admin_demo
    monkeypatch.setenv(admin_demo.DEMO_ENV, "1")
    seeded = admin_demo.seed_demo()
    assert seeded and {_role(admin_demo.doctor(u)["clinic"], u) for slug in seeded.values() for u in slug["users"]} == {"doctor"}
