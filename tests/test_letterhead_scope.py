"""Spec 9.1/9.2: scope at Accept, switching back, the doctors choice, a colleague's own letterhead. Offline."""
import json

from doctor_dictation import policy
from doctor_dictation.sessions import Identity
from letterhead_fixtures import clinic_conn, rao, record_renders, upload  # noqa: F401
from template_fixtures import make_jpeg, tclient  # noqa: F401

URL = "/api/v1/templates"


def _current(c):
    r = c.get(URL + "/current")
    assert r.status_code == 200, r.text
    return r.json()


def _scope_changes(conn):
    return [(r["actor"], json.loads(r["detail"])) for r in conn.execute(
        "SELECT actor, detail FROM audit_log WHERE action = 'letterhead_scope_change' ORDER BY id")]


def test_accept_defaults_to_the_whole_clinic(rao):
    tid = upload(rao.rao)
    out = rao.rao.post(f"{URL}/{tid}/accept")
    assert out.status_code == 200 and out.json()["scope"] == "clinic"
    for c in (rao.rao, rao.mehta):
        cur = _current(c)
        assert cur["clinic"]["id"] == tid and cur["mine"] is None and cur["personal"] is True


def test_my_own_letterhead_is_mine_only_and_audited(rao):
    clinic = upload(rao.rao)
    rao.rao.post(f"{URL}/{clinic}/accept")
    mine = upload(rao.mehta)
    r = rao.mehta.post(f"{URL}/{mine}/accept", json={"scope": "mine"})
    assert r.status_code == 200 and r.json()["scope"] == "mine"
    cur = _current(rao.mehta)
    assert cur["mine"]["id"] == mine and cur["clinic"]["id"] == clinic
    assert _current(rao.rao)["mine"] is None
    with clinic_conn() as conn:
        assert _scope_changes(conn) == [("dr.mehta", {"scope": "mine"})]


def test_use_the_clinic_letterhead_switches_back(rao):
    clinic = upload(rao.rao)
    rao.rao.post(f"{URL}/{clinic}/accept")
    mine = upload(rao.mehta)
    rao.mehta.post(f"{URL}/{mine}/accept", json={"scope": "mine"})
    assert rao.mehta.post(URL + "/deactivate", json={"scope": "mine"}).json() == {"deactivated": True}
    cur = _current(rao.mehta)
    assert cur["mine"] is None and cur["clinic"]["id"] == clinic
    assert rao.mehta.post(URL + "/deactivate", json={"scope": "mine"}).json() == {"deactivated": False}
    with clinic_conn() as conn:
        assert [d for _a, d in _scope_changes(conn)] == [{"scope": "mine"}, {"scope": "clinic"}]


def test_only_a_clinic_accept_changes_the_shared_clinic_details_and_only_the_accepters_doctor_fields(rao):
    with clinic_conn() as conn:
        conn.execute("INSERT INTO clinic_profile(id, clinic_name, updated_at) VALUES (1, 'Rao Clinic', 'x')"
                     " ON CONFLICT(id) DO UPDATE SET clinic_name = 'Rao Clinic'")
        conn.commit()
    mine = upload(rao.mehta)
    rao.mehta.post(f"{URL}/{mine}/accept", json={"scope": "mine"})
    with clinic_conn() as conn:
        assert conn.execute("SELECT clinic_name FROM clinic_profile").fetchone()[0] == "Rao Clinic"
    clinic = upload(rao.mehta)                      # the pad names "Dr A. Rao"; Mehta accepts it for the clinic
    rao.mehta.post(f"{URL}/{clinic}/accept")
    with clinic_conn() as conn:
        shared = conn.execute("SELECT clinic_name, doctor_name FROM clinic_profile").fetchone()
        assert (shared[0], shared[1]) == ("Meridian Clinic", "")      # clinic fields merged, doctor column untouched
        names = dict(conn.execute("SELECT username, doctor_name FROM users").fetchall())
    assert names["dr.mehta"] == "Dr A. Rao" and names["dr.rao"] == "Dr. A. Rao"   # only the accepter takes the pad's name


def test_doctors_choice_on_a_draft_and_on_an_active_letterhead(rao):
    tid = upload(rao.rao)
    r = rao.rao.put(f"{URL}/{tid}/doctors", json={"mode": "all"})
    assert r.status_code == 200 and r.json()["doctors"] == {"mode": "all", "ids": []}
    rao.rao.post(f"{URL}/{tid}/accept")
    pick = [rao.ids["mehta"], rao.ids["rao"], rao.ids["mehta"]]
    r = rao.mehta.put(f"{URL}/{tid}/doctors", json={"mode": "selected", "ids": pick})
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert _current(rao.rao)["clinic"]["doctors"] == {"mode": "selected", "ids": [rao.ids["mehta"], rao.ids["rao"]]}


def test_bad_doctors_choices_are_refused_and_change_nothing(rao):
    tid = upload(rao.rao)
    for body in ({"mode": "everyone"}, {"mode": "selected", "ids": []}, {"mode": "selected", "ids": [rao.ids["old"]]},
                 {"mode": "selected", "ids": [999]}, {"mode": "selected", "ids": ["1"]},
                 {"mode": "selected", "ids": [True]}, {"mode": "all", "ids": "1"},
                 {"mode": "selected", "ids": list(range(1, 52))}):
        r = rao.rao.put(f"{URL}/{tid}/doctors", json=body)
        assert r.status_code == 400 and "error" in r.json(), body
    with clinic_conn() as conn:
        assert conn.execute("SELECT doctors_mode FROM templates WHERE id = ?", (tid,)).fetchone()[0] == "author"
    assert rao.rao.put(f"{URL}/999/doctors", json={"mode": "all"}).status_code == 404
    rao.rao.post(f"{URL}/{tid}/accept")
    newer = upload(rao.rao)
    rao.rao.post(f"{URL}/{newer}/accept")                        # archives tid
    assert rao.rao.put(f"{URL}/{tid}/doctors", json={"mode": "all"}).status_code == 409


def test_a_colleagues_own_letterhead_is_invisible_to_me(rao, monkeypatch):
    record_renders(monkeypatch, "templates")
    mine = upload(rao.mehta)
    rao.mehta.post(f"{URL}/{mine}/accept", json={"scope": "mine"})
    assert rao.rao.put(f"{URL}/{mine}/doctors", json={"mode": "all"}).status_code == 404
    assert rao.rao.get(f"{URL}/{mine}/preview.pdf").status_code == 404
    assert rao.mehta.put(f"{URL}/{mine}/doctors", json={"mode": "all"}).status_code == 200
    body = {"lines": [{"section": "header", "index": 2, "remove": True}], "keep": []}
    assert rao.rao.put(f"{URL}/{mine}/lines", json=body).status_code == 404
    assert rao.mehta.put(f"{URL}/{mine}/lines", json=body).status_code == 200
    assert rao.mehta.get(f"{URL}/{mine}/preview.pdf").status_code == 200


def test_doctor_choices_list_the_active_doctors_in_clinic_order(rao):
    got = rao.mehta.get(URL + "/doctors").json()["doctors"]
    assert [(d["id"], d["name"], d["qualifications"], d["reg_no"]) for d in got] == [
        (rao.ids["rao"], "Dr. A. Rao", "MBBS, MD", "TS-1"), (rao.ids["mehta"], "Dr. S. Mehta", "MBBS, DNB", "TS-2")]


def test_single_mode_has_only_the_clinic_scope(tclient):
    tid = tclient.post(URL, files={"image": ("p.jpg", make_jpeg(), "image/jpeg")}).json()["id"]
    assert tclient.post(f"{URL}/{tid}/accept", json={"scope": "mine"}).status_code == 400
    assert tclient.post(f"{URL}/{tid}/accept", json={"scope": "both"}).status_code == 400
    assert tclient.post(URL + "/deactivate", json={"scope": "mine"}).status_code == 400
    assert tclient.get(URL + "/current").json() == {"clinic": None, "mine": None, "personal": False}
    assert tclient.post(f"{URL}/{tid}/accept").status_code == 200        # the refusals left it a draft
    assert tclient.get(URL + "/current").json()["clinic"]["id"] == tid
    assert tclient.get(URL + "/doctors").json() == {"doctors": []}


def test_policy_lets_only_the_owner_manage_a_personal_letterhead():
    me = Identity("rao", 1, "dr.rao", "doctor")
    assert policy.can(me, "letterhead.manage", {"owner_user_id": None}) is True
    assert policy.can(me, "letterhead.manage", {"owner_user_id": 1}) is True
    assert policy.can(me, "letterhead.manage", {"owner_user_id": 2}) is False
    assert policy.can(me, "letterhead.manage") is True


def _status(conn, tid):
    return conn.execute("SELECT status FROM templates WHERE id = ?", (tid,)).fetchone()[0]


def test_a_clinic_accept_leaves_an_active_personal_letterhead_active(rao):
    mine = upload(rao.mehta)
    rao.mehta.post(f"{URL}/{mine}/accept", json={"scope": "mine"})
    clinic = upload(rao.rao)
    assert rao.rao.post(f"{URL}/{clinic}/accept").status_code == 200
    with clinic_conn() as conn:
        assert (_status(conn, mine), _status(conn, clinic)) == ("active", "active")
    assert _current(rao.mehta)["mine"]["id"] == mine


def test_accept_after_a_mine_deactivate_works(rao):
    first = upload(rao.mehta)
    rao.mehta.post(f"{URL}/{first}/accept", json={"scope": "mine"})
    assert rao.mehta.post(URL + "/deactivate", json={"scope": "mine"}).json() == {"deactivated": True}
    second = upload(rao.mehta)
    assert rao.mehta.post(f"{URL}/{second}/accept", json={"scope": "mine"}).status_code == 200
    with clinic_conn() as conn:
        assert (_status(conn, first), _status(conn, second)) == ("archived", "active")


def test_the_doctors_choice_audit_row_carries_only_the_mode_and_ids(rao):
    tid = upload(rao.rao)
    rao.rao.put(f"{URL}/{tid}/doctors", json={"mode": "selected", "ids": [rao.ids["mehta"]]})
    with clinic_conn() as conn:
        rows = conn.execute("SELECT actor, entity_id, detail FROM audit_log WHERE action = 'template_doctors'").fetchall()
    assert [(r["actor"], r["entity_id"], json.loads(r["detail"])) for r in rows] == [
        ("dr.rao", str(tid), {"mode": "selected", "ids": [rao.ids["mehta"]]})]


def test_a_colleagues_personal_letterhead_answers_404_not_409_on_every_draft_action(rao):
    mine = upload(rao.mehta)
    rao.mehta.post(f"{URL}/{mine}/accept", json={"scope": "mine"})              # now active and Mehta's alone
    assert rao.rao.put(f"{URL}/{mine}", json={"profile": {}, "lines": []}).status_code == 404
    assert rao.rao.post(f"{URL}/{mine}/accept").status_code == 404
    assert rao.rao.post(f"{URL}/{mine}/use-details").status_code == 404
    assert rao.rao.delete(f"{URL}/{mine}").status_code == 404
    assert rao.mehta.put(f"{URL}/{mine}", json={"profile": {}, "lines": []}).status_code == 409   # the owner still gets the real reason
