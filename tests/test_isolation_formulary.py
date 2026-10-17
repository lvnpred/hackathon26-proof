"""Clinic A learns a drug; Clinic B never sees it (plan I1-h4). Offline; the seeded two-clinic world."""
import json

from doctor_dictation.api import stt as api_stt
from doctor_dictation.config import override_settings
from doctor_dictation.core import determinism as D
from isolation_fixtures import A, A_MARKERS, B, H, a_only_id, fingerprint, leaks, save_body, sql, user_id, world  # noqa: F401
from test_isolation_routes import ADMIN_ONLY      # the admin sweep reuses the doctor sweep's own skip list

ROW = {"form": "Tab.", "name": "Zorbexin", "strength": "10 mg", "dose": "1-0-0", "timing": "", "duration": "5 days",
       "instructions": "", "status": "unknown-medicine"}
ASK = {"transcript": "tablet Zorbexin 10 mg once daily for 5 days"}


def learn(client, patient):
    body = save_body(patient, medicine="Zorbexin")
    body["structured"]["rx"][0]["status"] = "unknown-medicine"
    body["confirmed_rows"] = [0]
    r = client.post("/api/v1/documents", json=body, headers=H)
    assert r.status_code == 200, r.text


def test_clinic_a_learns_a_drug_and_clinic_b_still_sees_it_as_unknown(world, monkeypatch):
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps({"rx": [ROW]}))
    D._FORMAT_CACHE.clear()
    ask = lambda client: client.post("/api/format", json=ASK, headers=H).json()["structured"]["rx"][0]   # noqa: E731
    assert ask(world.rao)["status"] == ask(world.iyer)["status"] == "unknown-medicine"
    learn(world.rao, "Asha Verma")
    learn(world.mehta, "Ravi Kulkarni")                                  # a second doctor of the same clinic counts too
    assert (ask(world.rao)["status"], ask(world.rao)["source"]) == ("verified", "clinic")
    assert (ask(world.mehta)["status"], ask(world.iyer)["status"]) == ("verified", "unknown-medicine")
    assert [i["name"] for i in world.mehta.get("/api/v1/formulary").json()["items"]] == ["Zorbexin"]
    assert world.iyer.get("/api/v1/formulary").json() == {"items": []}
    assert sql(B, "SELECT COUNT(*) FROM clinic_formulary")[0][0] == 0 and sql(A, "SELECT COUNT(*) FROM clinic_formulary")[0][0] == 1


def test_the_speech_hints_carry_only_the_callers_own_clinic_names(world, monkeypatch):
    learn(world.rao, "Asha Verma")
    learn(world.rao, "Lakshmi Narayan")
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, stt_chain=("stub",),
                      stt_use_hints=True, stt_trim_silence=False)
    real, seen = api_stt.build_hints, {}
    for who in ("rao", "iyer"):
        monkeypatch.setattr(api_stt, "build_hints", lambda top, limit, who=who: seen.setdefault(who, real(top, limit)))
        r = getattr(world, who).post("/api/transcribe", files={"audio": ("a.webm", b"x" * 64, "audio/webm")}, headers=H)
        assert r.status_code == 200, r.text
    assert "Zorbexin" in seen["rao"] and "Zorbexin" not in seen["iyer"]


def test_only_a_clinic_admin_removes_and_only_in_their_own_clinic(world):
    learn(world.rao, "Asha Verma")
    learn(world.rao, "Lakshmi Narayan")
    adm_a, adm_b = world.rao_admin, world.iyer_admin
    (item,) = world.rao.get("/api/v1/formulary").json()["items"]
    before_a = fingerprint(A)
    assert world.rao.delete(f"/api/v1/formulary/{item['id']}", headers=H).status_code == 403    # a doctor, not an admin
    assert adm_b.delete(f"/api/v1/formulary/{item['id']}", headers=H).status_code == 404        # the other clinic's admin
    assert fingerprint(A) == before_a
    assert adm_a.delete(f"/api/v1/formulary/{item['id']}", headers=H).status_code == 200
    assert world.rao.get("/api/v1/formulary").json() == {"items": []}


def test_the_admin_sweep_covers_every_admin_only_route_across_clinics(world):
    """ADMIN_ONLY routes are skipped by the doctor sweep (a doctor gets 403 first); sweep them here. A new admin-only route
    changes the list and must be reviewed. As a doctor: 403 on each and nothing changes. As Clinic B's admin: 404 for an id
    only A has, nothing of A changes or leaks. As A's own admin: the same requests are not refused."""
    ops = sorted((m.upper(), p) for p, o in world.app.openapi()["paths"].items() if p.startswith(ADMIN_ONLY)
                 for m in o if m.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"})
    assert ops == [("DELETE", "/api/v1/formulary/{entry_id}"), ("POST", "/api/v1/users/{user_id}/disable"),
                   ("POST", "/api/v1/users/{user_id}/enable"), ("POST", "/api/v1/users/{user_id}/reset-password")], ops
    learn(world.rao, "Asha Verma")
    learn(world.rao, "Lakshmi Narayan")
    (item,) = world.rao.get("/api/v1/formulary").json()["items"]
    colleague, a_only_user = user_id(world, "dr.mehta"), a_only_id("users")      # the admin's own id exists only in A
    before_a = fingerprint(A)

    def url(path, user):
        return path.replace("{entry_id}", str(item["id"])).replace("{user_id}", str(user))

    for method, path in ops:
        r = world.rao.request(method, url(path, colleague), headers=H)                      # a doctor of A
        assert r.status_code == 403 and r.json() == {"error": "You are not allowed to do that"}, (method, path, r.text)
        assert "temporary_password" not in r.text
        r = world.iyer_admin.request(method, url(path, a_only_user), headers=H)             # another clinic's admin
        assert r.status_code == 404 and not leaks(r.text, ("Zorbexin", *A_MARKERS)), (method, path, r.text)
        r = world.iyer.request(method, url(path, a_only_user), headers=H)                   # another clinic's doctor
        assert r.status_code == 403, (method, path, r.status_code)
    assert world.iyer_admin.get("/api/v1/formulary").json() == {"items": []}
    assert fingerprint(A) == before_a
    assert world.rao_admin.get("/api/v1/formulary").json()["items"][0]["name"] == "Zorbexin"
    for method, path in ops:                                                                # A's own admin: allowed
        assert world.rao_admin.request(method, url(path, colleague), headers=H).status_code == 200, (method, path)
