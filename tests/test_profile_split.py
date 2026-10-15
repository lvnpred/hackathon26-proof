"""Profile split (M3 Task 4, spec 8.1) and the template routes' audit actor. Offline."""
from fastapi.testclient import TestClient
from starlette.requests import Request

from doctor_dictation.api import templates as templates_api
from doctor_dictation.db import details
from doctor_dictation.db import templates as tdb
from doctor_dictation.sessions import Identity
from authorship_fixtures import CLINIC, H, MEHTA, OLD, RAO, as_user, clinic_conn, team  # noqa: F401
from template_fixtures import GOOD_LAYOUT

MINE = {"doctor_name": "Dr. M. Mehta", "qualifications": "MD", "reg_no": "M-999"}
NEW_CLINIC = {"clinic_name": "Rao & Mehta Clinic", "address": "2 Main Road", "phone": "040 222"}


def test_signed_in_profile_is_my_details_plus_the_clinic_details(team):
    for uid, me in ((team.rao, RAO), (team.mehta, MEHTA)):
        r = as_user(team.client, uid).get("/api/v1/profile")
        assert r.status_code == 200 and r.json() == {**me, **CLINIC, "op_prefix": "OP"}
        assert list(r.json()) == ["doctor_name", "qualifications", "reg_no", "clinic_name", "address", "phone", "op_prefix"]


def test_put_shares_the_clinic_details_and_keeps_my_details_mine(team):
    c = as_user(team.client, team.mehta)
    r = c.put("/api/v1/profile", json={**MINE, **NEW_CLINIC}, headers=H)
    assert (r.status_code, r.json()) == (200, {**MINE, **NEW_CLINIC, "op_prefix": "OP"})
    assert as_user(c, team.rao).get("/api/v1/profile").json() == {**RAO, **NEW_CLINIC, "op_prefix": "OP"}
    with clinic_conn() as conn:
        assert details.my_details(conn, team.mehta) == MINE
        assert details.saved_doctor_details(conn) == OLD          # the shared row's doctor columns are untouched


def test_profile_fields_are_length_checked(team, tmp_path, monkeypatch):
    long = {**MINE, "address": "x" * 301}
    assert as_user(team.client, team.rao).put("/api/v1/profile", json=long, headers=H).status_code == 422
    monkeypatch.setenv("MULTI_CLINIC", "0")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "single.db"))
    from doctor_dictation.api.app import create_app
    with TestClient(create_app()) as c:
        assert c.put("/api/v1/profile", json=long).status_code == 422
        assert c.put("/api/v1/profile", json={**MINE, "address": "x" * 300}).status_code == 200


def _request(state):
    scope = {"type": "http", "method": "POST", "path": "/", "headers": []}
    if state is not None:
        scope["state"] = state
    return Request(scope)


def test_template_actor_is_the_signed_in_username_and_none_in_single_mode():
    me = Identity("rao", 7, "dr.mehta", "doctor")
    assert templates_api._actor(_request({"identity": me})) == "dr.mehta"
    assert templates_api._actor(_request({})) is None
    assert templates_api._actor(_request(None)) is None


def test_template_discard_is_audited_with_the_signed_in_username(team):
    with clinic_conn() as conn:
        tid = tdb.create_template_draft(conn, GOOD_LAYOUT)
    r = as_user(team.client, team.mehta).delete(f"/api/v1/templates/{tid}", headers=H)
    assert r.status_code == 204
    with clinic_conn() as conn:
        row = conn.execute("SELECT actor FROM audit_log WHERE action = 'template_discard'").fetchone()
    assert row["actor"] == "dr.mehta"


def test_signed_in_put_cleans_hidden_and_control_characters(team):
    c = as_user(team.client, team.mehta)
    r = c.put("/api/v1/profile", json={"doctor_name": "Dr.‮ M​\nMehta", "qualifications": " MD\x00 ", "reg_no": "M-9",
                                       "clinic_name": "Clinic One", "address": "1 Road", "phone": "1"}, headers=H)
    body = r.json()
    assert r.status_code == 200 and (body["doctor_name"], body["qualifications"], body["clinic_name"]) == (
        "Dr. M Mehta", "MD", "Clinic One")
