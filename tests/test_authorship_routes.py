"""Authorship through the real app (M3 Task 2, spec 7.1): who is recorded, who may edit, what prints. Offline."""
from fastapi import Request

from doctor_dictation import db as dbmod
from doctor_dictation import policy
from authorship_fixtures import CLINIC, H, MEHTA, OLD, RAO, SAVE, as_user, clinic_conn, legacy_document, save, team  # noqa: F401

DENIED = {"error": "This prescription belongs to Dr. Rao. You can view and reprint it."}


def _rows(doc):
    with clinic_conn() as conn:
        d = dict(dbmod.get_document(conn, doc))
        e = dict(dbmod.get_encounter(conn, d["encounter_id"]))
        actions = [r["action"] for r in conn.execute("SELECT action FROM audit_log WHERE action IN ('finalize', 'resave')")]
    return d, e, actions


def _resave(c, doc, name="Anita"):
    body = {**SAVE, "structured": {**SAVE["structured"], "patientName": name}, "document_id": doc}
    return c.post("/api/v1/documents", json=body, headers=H)


def test_first_save_records_the_signed_in_doctor_as_author_and_saver(team):
    doc = save(as_user(team.client, team.mehta))
    d, e, _ = _rows(doc)
    assert (e["doctor_id"], d["finalized_by"]) == (team.mehta, team.mehta)


def test_author_resave_keeps_the_author_and_a_legacy_resave_records_the_saver(team):
    c = as_user(team.client, team.rao)
    doc = save(c)
    assert _resave(c, doc, "Anita R").status_code == 200
    d, e, _ = _rows(doc)
    assert (e["doctor_id"], d["finalized_by"]) == (team.rao, team.rao)
    old = legacy_document()
    assert _resave(as_user(c, team.mehta), old, "Old Patient").status_code == 200
    d, e, _ = _rows(old)
    assert (e["doctor_id"], d["finalized_by"]) == (None, team.mehta)     # still no author: stays editable by anyone


def test_colleague_resave_is_403_with_the_exact_message_and_changes_nothing(team):
    c = as_user(team.client, team.rao)
    doc = save(c)
    before, _, _ = _rows(doc)
    n = len(team.rendered)
    r = _resave(as_user(c, team.mehta), doc, "Hijacked")
    assert (r.status_code, r.json()) == (403, DENIED)
    after, _, actions = _rows(doc)
    assert after == before and len(team.rendered) == n and actions == ["finalize"]


def test_colleague_correct_is_403_but_the_author_and_an_unsaved_draft_may_correct(team):
    c = as_user(team.client, team.rao)
    doc = save(c)
    body = {"transcript": "", "current_form": SAVE["structured"]}
    assert c.post("/api/v1/correct", json={**body, "document_id": doc}, headers=H).status_code == 200
    as_user(c, team.mehta)
    r = c.post("/api/v1/correct", json={**body, "document_id": doc}, headers=H)
    assert (r.status_code, r.json()) == (403, DENIED)
    assert c.post("/api/v1/correct", json=body, headers=H).status_code == 200            # a fresh draft of his own


def test_any_doctor_may_view_and_the_answer_says_who_wrote_it(team):
    c = as_user(team.client, team.rao)
    doc = save(c)
    mine = c.get(f"/api/v1/documents/{doc}").json()
    assert mine["can_edit"] is True and mine["author"] == {"user_id": team.rao, "name": "Dr. Rao", **RAO}
    theirs = as_user(c, team.mehta).get(f"/api/v1/documents/{doc}")
    assert theirs.status_code == 200
    assert theirs.json()["can_edit"] is False and theirs.json()["author"]["name"] == "Dr. Rao"
    assert theirs.json()["structured"]["patientName"] == "Anita"


def test_colleague_reprint_prints_the_authors_details_not_the_viewers(team):
    c = as_user(team.client, team.rao)
    doc = save(c)
    with clinic_conn() as conn:
        conn.execute("UPDATE documents SET pdf_path = NULL WHERE id = ?", (doc,))   # force an on-demand render
        conn.commit()
    r = as_user(c, team.mehta).get(f"/api/v1/documents/{doc}/pdf")
    assert r.status_code == 200 and r.content == b"%PDF-fake"
    assert team.rendered[-1]["profile"] == {**RAO, **CLINIC}


def test_save_prints_the_savers_own_details_with_the_clinic_details(team):
    save(as_user(team.client, team.mehta))
    assert team.rendered[-1]["profile"] == {**MEHTA, **CLINIC}


def test_legacy_document_prints_the_saved_profile_and_anyone_may_open_it_for_editing(team):
    old = legacy_document()
    j = as_user(team.client, team.mehta).get(f"/api/v1/documents/{old}").json()
    assert j["can_edit"] is True and j["author"] == {"user_id": None, "name": "", **OLD}
    assert team.client.get(f"/api/v1/documents/{old}/pdf").status_code == 200
    assert team.rendered[-1]["profile"] == {**OLD, **CLINIC}


def test_every_document_route_asks_policy_can(team, monkeypatch):
    """Each route asks its own action, recorded as (route path, action): removing any one check fails this."""
    import sys
    from doctor_dictation.api import authorship
    c = as_user(team.client, team.rao)
    doc = save(c)
    asked = []
    real_check, real_can = authorship.check, policy.can

    def check(conn, request, action, document_id):      # check_document delegates here too
        asked.append((request.url.path, action))
        return real_check(conn, request, action, document_id)

    def can(user, action, resource=None):
        if sys._getframe(1).f_code.co_name == "author_view":       # can_edit; check()'s own call is already recorded
            asked.append(("author_view", action))
        return real_can(user, action, resource)
    monkeypatch.setattr(authorship, "check", check)
    monkeypatch.setattr(policy, "can", can)

    def asks(send):
        asked.clear()
        send()
        return list(asked)
    assert asks(lambda: c.get(f"/api/v1/documents/{doc}")) == [(f"/api/v1/documents/{doc}", "document.view"),
                                                               ("author_view", "document.edit")]
    assert asks(lambda: c.get(f"/api/v1/documents/{doc}/pdf")) == [(f"/api/v1/documents/{doc}/pdf", "document.reprint")]
    assert asks(lambda: _resave(c, doc)) == [("/api/v1/documents", "document.edit")]
    assert asks(lambda: c.post("/api/v1/correct", json={"transcript": "", "current_form": {}, "document_id": doc},
                               headers=H)) == [("/api/v1/correct", "document.edit")]


def test_colleague_resave_is_403_before_the_verify_gate(team):
    c = as_user(team.client, team.rao)
    doc = save(c)
    unverified = {"structured": {**SAVE["structured"], "rx": [{"name": "Tamsulosin", "status": "unverified-name"}]},
                  "confirmed_rows": [], "document_id": doc}
    assert as_user(c, team.rao).post("/api/v1/documents", json=unverified, headers=H).status_code == 409   # the body does trip the gate
    r = as_user(c, team.mehta).post("/api/v1/documents", json=unverified, headers=H)
    assert (r.status_code, r.json()) == (403, DENIED)


def test_a_signed_out_request_in_multi_clinic_mode_fails_closed(multi, monkeypatch):
    from fastapi.testclient import TestClient
    from doctor_dictation.api import authorship, session as session_mod
    from doctor_dictation.api.app import create_app
    monkeypatch.setattr(session_mod, "PUBLIC_PATHS", session_mod.PUBLIC_PATHS | {"/api/v1/_authz_probe"})
    app = create_app()

    @app.get("/api/v1/_authz_probe")
    def probe(request: Request):
        return authorship.check_document(request, "document.edit", 1) or {"ok": True}

    app.router.routes.insert(0, app.router.routes.pop())      # ahead of the "/" static mount
    with TestClient(app) as c:
        r = c.get("/api/v1/_authz_probe")
    assert (r.status_code, r.json()) == (401, {"error": "sign in required"})


def test_signed_in_post_encounter_is_the_signed_in_doctors_whatever_the_body_says(team):
    c = as_user(team.client, team.mehta)
    pid = c.post("/api/v1/patients", json={"name": "Asha"}, headers=H).json()["id"]
    r = c.post("/api/v1/encounters", json={"patient_id": pid, "doctor_id": team.rao}, headers=H)
    assert r.status_code == 201
    with clinic_conn() as conn:
        assert dbmod.get_encounter(conn, r.json()["id"])["doctor_id"] == team.mehta


def test_an_unknown_document_is_still_404_when_signed_in(team):
    c = as_user(team.client, team.mehta)
    assert c.get("/api/v1/documents/999").status_code == 404
    assert c.get("/api/v1/documents/999/pdf").status_code == 404
    assert _resave(c, 999).status_code == 404
