"""Team routes through the real app: list, add, disable, enable, reset; clinic isolation, sessions, audit. Offline."""
import json
from contextlib import ExitStack, closing, contextmanager

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import accounts as A
from doctor_dictation import clinics
from doctor_dictation import db as dbmod
from doctor_dictation.api import users as users_api
from doctor_dictation.api.app import create_app
from doctor_dictation.directory import DirectoryError
from doctor_dictation.scope import clinic_dir

H = {"X-DD-Client": "1"}
PW = "a-long-password-1"


def _conn(slug):
    return dbmod.get_conn(clinic_dir(slug) / "app.db")


def _make(slug, username, display, role="doctor"):
    uid, _ = A.create_user(slug, username, display_name=display, password=PW, role=role)
    with closing(_conn(slug)) as c:                                 # skip the forced first-login change
        c.execute("UPDATE users SET must_change_password = 0 WHERE id = ?", (uid,))
        c.commit()
    return uid


@pytest.fixture()
def world(multi):
    """dr.rao and dr.iyer are clinic ADMINS (the team actions are admin-only); dr.mehta and dr.shah are plain doctors."""
    clinics.provision_clinic("rao", "Rao Clinic")
    clinics.provision_clinic("iyer", "Iyer Clinic")
    return {"rao": _make("rao", "dr.rao", "Dr. Rao", role="admin"), "mehta": _make("rao", "dr.mehta", "Dr. Mehta"),
            "shah": _make("rao", "dr.shah", "Dr. Shah"), "iyer": _make("iyer", "dr.iyer", "Dr. Iyer", role="admin")}


def _login(c, username, pw=PW):
    return c.post("/api/v1/auth/login", json={"username": username, "password": pw}, headers=H)


@contextmanager
def _signed_in(*usernames):
    """One TestClient per username (each its own cookie jar) on one app, each signed in."""
    app = create_app()
    with ExitStack() as stack:
        clients = []
        for name in usernames:
            c = stack.enter_context(TestClient(app, follow_redirects=False))
            r = _login(c, name)
            assert r.status_code == 200, r.text
            clients.append(c)
        yield clients


def _names(c):
    return [u["username"] for u in c.get("/api/v1/users").json()["users"]]


def test_users_routes_are_404_in_single_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "single.db"))
    c = TestClient(create_app())                                    # no `with`: no lifespan, no database touched
    assert c.get("/api/v1/users").status_code == 404
    for path in ("/api/v1/users", "/api/v1/users/1/disable", "/api/v1/users/1/enable", "/api/v1/users/1/reset-password"):
        assert c.post(path, json={"username": "dr.x"}).status_code == 404, path


def test_list_shows_only_this_clinic_with_public_fields_and_who_i_am(world):
    with _signed_in("dr.mehta", "dr.iyer") as (mehta, iyer):
        ra, rb = mehta.get("/api/v1/users"), iyer.get("/api/v1/users")
    a, b = ra.json(), rb.json()
    assert a["me"] == world["mehta"] and [u["username"] for u in a["users"]] == ["dr.rao", "dr.mehta", "dr.shah"]
    assert b["me"] == world["iyer"] and [u["username"] for u in b["users"]] == ["dr.iyer"]
    row = a["users"][1]
    assert set(row) == {"id", "username", "display_name", "role", "is_active", "last_login_at", "must_change_password"}
    assert (row["display_name"], row["is_active"], row["must_change_password"]) == ("Dr. Mehta", True, False)
    assert row["last_login_at"] is not None and a["users"][0]["last_login_at"] is None
    assert "password_hash" not in ra.text and "scrypt$" not in ra.text


def test_add_user_shows_a_temporary_password_once_and_it_signs_in_with_a_forced_change(world):
    with _signed_in("dr.rao") as (rao,):
        r = rao.post("/api/v1/users", json={"username": "dr.new", "display_name": " Dr. New ", "doctor_name": "Dr N. New",
                                            "qualifications": "MBBS", "reg_no": "TS-9"}, headers=H)
        listing = rao.get("/api/v1/users")
    assert r.status_code == 201 and r.headers["cache-control"] == "no-store"
    body = r.json()
    temp = body["temporary_password"]
    assert len(temp) == 16 and (body["user"]["username"], body["user"]["display_name"]) == ("dr.new", "Dr. New")
    assert body["user"]["must_change_password"] is True and body["user"]["is_active"] is True
    assert temp not in listing.text
    with closing(_conn("rao")) as c:
        row = c.execute("SELECT doctor_name, qualifications, reg_no, role FROM users WHERE username = 'dr.new'").fetchone()
    assert tuple(row) == ("Dr N. New", "MBBS", "TS-9", "admin")      # the Team form has no role field: DEFAULT_ROLE
    with TestClient(create_app(), follow_redirects=False) as fresh:
        r = _login(fresh, "dr.new", temp)
    assert (r.status_code, r.json()["must_change_password"]) == (200, True)


def test_add_user_rejects_bad_taken_and_oversized_usernames(world):
    with _signed_in("dr.rao") as (rao,):
        bad = rao.post("/api/v1/users", json={"username": "a b"}, headers=H)
        taken = rao.post("/api/v1/users", json={"username": "DR.IYER"}, headers=H)     # Iyer Clinic's user, other case
        huge = rao.post("/api/v1/users", json={"username": "x" * 65}, headers=H)
        names = _names(rao)
    assert bad.status_code == 400 and "3 to 40" in bad.json()["error"]
    assert taken.status_code == 400 and "taken" in taken.json()["error"]
    assert huge.status_code == 422
    assert names == ["dr.rao", "dr.mehta", "dr.shah"]


def test_add_user_leaves_no_clinic_row_when_the_directory_write_fails(world, monkeypatch):
    def boom(*_a, **_k):
        raise DirectoryError("directory is down")

    monkeypatch.setattr(A, "index_username", boom)
    with _signed_in("dr.rao") as (rao,):
        r = rao.post("/api/v1/users", json={"username": "dr.new"}, headers=H)
        names = _names(rao)
    assert r.status_code == 400 and "temporary_password" not in r.json()
    assert "dr.new" not in names


def test_disable_ends_the_session_at_once_and_enable_does_not_revive_it(world):
    with _signed_in("dr.rao", "dr.mehta") as (rao, mehta):
        assert mehta.get("/api/v1/auth/me").status_code == 200
        r = rao.post(f"/api/v1/users/{world['mehta']}/disable", headers=H)
        assert r.status_code == 200 and r.json()["user"]["is_active"] is False
        assert mehta.get("/api/v1/auth/me").status_code == 401
        assert _login(mehta, "dr.mehta").status_code == 401
        r = rao.post(f"/api/v1/users/{world['mehta']}/enable", headers=H)
        assert r.status_code == 200 and r.json()["user"]["is_active"] is True
        assert mehta.get("/api/v1/auth/me").status_code == 401          # the old cookie stays dead
        assert _login(mehta, "dr.mehta").status_code == 200
        assert mehta.get("/api/v1/auth/me").status_code == 200


def test_reset_password_ends_the_session_and_the_new_temp_password_forces_a_change(world):
    with _signed_in("dr.rao", "dr.mehta") as (rao, mehta):
        r = rao.post(f"/api/v1/users/{world['mehta']}/reset-password", headers=H)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        temp = r.json()["temporary_password"]
        assert len(temp) == 16
        assert mehta.get("/api/v1/auth/me").status_code == 401
        assert _login(mehta, "dr.mehta").status_code == 401             # the old password is gone
        r = _login(mehta, "dr.mehta", temp)
        assert (r.status_code, r.json()["must_change_password"]) == (200, True)


def test_you_cannot_disable_or_reset_yourself(world):
    with _signed_in("dr.rao") as (rao,):
        d = rao.post(f"/api/v1/users/{world['rao']}/disable", headers=H)
        p = rao.post(f"/api/v1/users/{world['rao']}/reset-password", headers=H)
        still = rao.get("/api/v1/auth/me").status_code
    assert d.status_code == 400 and "your own account" in d.json()["error"]
    assert p.status_code == 400 and "your own password" in p.json()["error"]
    assert still == 200


def test_ids_from_another_clinic_are_404_and_untouched(world):
    shah = world["shah"]                                            # id 3 exists only in Rao Clinic
    with _signed_in("dr.iyer") as (iyer,):
        answers = [iyer.post(f"/api/v1/users/{shah}/{verb}", headers=H) for verb in ("disable", "enable", "reset-password")]
        own_id = iyer.post(f"/api/v1/users/{world['rao']}/disable", headers=H)   # id 1 here is Iyer, not Rao
    assert [(r.status_code, r.json()) for r in answers] == [(404, {"error": "no such user"})] * 3
    assert world["rao"] == world["iyer"] and own_id.status_code == 400 and "your own account" in own_id.json()["error"]
    with closing(_conn("rao")) as c:
        rows = c.execute("SELECT is_active, session_version FROM users WHERE id IN (?, ?)", (shah, world["rao"])).fetchall()
        audits = c.execute("SELECT COUNT(*) FROM audit_log WHERE action IN ('user_disable', 'user_enable', 'password_reset')"
                           ).fetchone()[0]
    assert [tuple(r) for r in rows] == [(1, 0), (1, 0)] and audits == 0


def test_bad_ids_are_422(world):
    with _signed_in("dr.rao") as (rao,):
        codes = {p: rao.post(f"/api/v1/users/{p}/disable", headers=H).status_code for p in ("0", "-1", "abc", str(2**64))}
    assert set(codes.values()) == {422}, codes


def test_every_team_action_is_audited_with_the_signed_in_actor_and_no_password(world):
    with _signed_in("dr.rao") as (rao,):
        created = rao.post("/api/v1/users", json={"username": "dr.new"}, headers=H).json()
        rao.post(f"/api/v1/users/{world['mehta']}/disable", headers=H)
        rao.post(f"/api/v1/users/{world['mehta']}/enable", headers=H)
        reset = rao.post(f"/api/v1/users/{world['mehta']}/reset-password", headers=H).json()
    with closing(_conn("rao")) as c:
        rows = c.execute("SELECT actor, role, action, entity_id, detail FROM audit_log WHERE actor IS NOT NULL AND action IN"
                         " ('user_create', 'user_disable', 'user_enable', 'password_reset') ORDER BY id").fetchall()
    mehta, new = str(world["mehta"]), str(created["user"]["id"])
    assert [(r["actor"], r["role"], r["action"], r["entity_id"]) for r in rows] == [
        ("dr.rao", "admin", "user_create", new), ("dr.rao", "admin", "user_disable", mehta),
        ("dr.rao", "admin", "user_enable", mehta), ("dr.rao", "admin", "password_reset", mehta)]
    secrets = (created["temporary_password"], reset["temporary_password"])
    assert not any(s in (r["detail"] or "") for r in rows for s in secrets)
    assert json.loads(rows[0]["detail"]) == {"username": "dr.new"}


def test_every_team_route_asks_policy_can_and_a_denial_is_403(world, monkeypatch):
    asked = []
    monkeypatch.setattr(users_api.policy, "can", lambda user, action, resource=None: asked.append(action) or False)
    with _signed_in("dr.rao") as (rao,):
        answers = [rao.get("/api/v1/users"), rao.post("/api/v1/users", json={"username": "dr.new"}, headers=H),
                   rao.post(f"/api/v1/users/{world['mehta']}/disable", headers=H),
                   rao.post(f"/api/v1/users/{world['mehta']}/enable", headers=H),
                   rao.post(f"/api/v1/users/{world['mehta']}/reset-password", headers=H)]
    assert [(r.status_code, r.json()) for r in answers] == [(403, {"error": "You are not allowed to do that"})] * 5
    assert asked == ["user.view", "user.create", "user.disable", "user.disable", "user.reset_password"]
    with closing(_conn("rao")) as c:
        assert c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3
        row = c.execute("SELECT is_active, session_version, password_hash FROM users WHERE id = ?", (world["mehta"],)).fetchone()
    assert (row["is_active"], row["session_version"]) == (1, 0)


def test_add_user_strips_control_characters_from_the_free_text_fields(world):
    with _signed_in("dr.rao") as (rao,):
        r = rao.post("/api/v1/users", json={"username": "dr.ctl", "display_name": "Dr.\nCtl\x00 \tOne",
                                            "doctor_name": "\x07", "qualifications": "MBBS\r\nMD", "reg_no": "TS\x00-9"},
                     headers=H)
    assert r.status_code == 201, r.text
    assert r.json()["user"]["display_name"] == "Dr. Ctl One"
    with closing(_conn("rao")) as c:
        row = c.execute("SELECT display_name, doctor_name, qualifications, reg_no FROM users WHERE username = 'dr.ctl'").fetchone()
    assert tuple(row) == ("Dr. Ctl One", "", "MBBS MD", "TS -9")


def test_a_directory_error_is_a_400_not_a_500(world, monkeypatch):
    def boom(*_a, **_k):
        raise DirectoryError("directory is down")

    monkeypatch.setattr(users_api.accounts, "list_users", boom)
    with _signed_in("dr.rao") as (rao,):
        r = rao.get("/api/v1/users")
    assert r.status_code == 400 and r.json() == {"error": "directory is down"}


def test_the_add_user_route_documents_201():
    assert "201" in create_app().openapi()["paths"]["/api/v1/users"]["post"]["responses"]


def test_add_user_strips_bidi_and_zero_width_characters_but_keeps_zwj(world):
    with _signed_in("dr.rao") as (rao,):
        r = rao.post("/api/v1/users", json={"username": "dr.bidi", "display_name": "Dr.‮ R​ao ಕ‍"}, headers=H)
    assert r.status_code == 201 and r.json()["user"]["display_name"] == "Dr. Rao ಕ‍"


def test_a_stale_actor_is_a_401_sign_in_required(world, monkeypatch):
    def stale(*_a, **_k):
        raise A.StaleSession("sign in required")

    monkeypatch.setattr(users_api.accounts, "set_active", stale)
    monkeypatch.setattr(users_api.accounts, "reset_user_password", stale)
    with _signed_in("dr.rao") as (rao,):
        answers = [rao.post(f"/api/v1/users/{world['mehta']}/{verb}", headers=H) for verb in ("disable", "enable", "reset-password")]
    assert [(r.status_code, r.json()) for r in answers] == [(401, {"error": "sign in required"})] * 3
