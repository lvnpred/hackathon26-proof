"""A doctor's corrected mishearings stay in that clinic and with that doctor (plan SH-H2). Offline; the two-clinic world."""
from isolation_fixtures import A, B, H, fingerprint, save_body, sql, user_id, world  # noqa: F401

LIST = "/api/v1/spoken/mishearings"


def misheard(client, patient):
    body = save_body(patient, medicine="Dolo")
    body["structured"]["rx"][0]["heard"] = "dollo"
    r = client.post("/api/v1/documents", json=body, headers=H)
    assert r.status_code == 200, r.text


def test_pairs_belong_to_the_doctor_and_the_clinic_that_saved_them(world):
    misheard(world.rao, "Asha Verma")
    misheard(world.rao, "Lakshmi Narayan")
    misheard(world.mehta, "Ravi Kulkarni")                                  # a colleague: one document only
    rows = sql(A, "SELECT t.doctor_id, m.heard, m.confirm_count FROM spoken_mishearings m"
                  " JOIN spoken_terms t ON t.id = m.term_id ORDER BY m.confirm_count DESC")
    assert [tuple(r) for r in rows] == [(user_id(world, "dr.rao"), "dollo", 2), (user_id(world, "dr.mehta"), "dollo", 1)]
    assert sql(B, "SELECT (SELECT COUNT(*) FROM spoken_mishearings) + (SELECT COUNT(*) FROM spoken_mishearing_docs)")[0][0] == 0
    (item,) = world.rao_admin.get(LIST, headers=H).json()["items"]                  # only the active pair
    assert item["doctor_id"] == user_id(world, "dr.rao") and (item["spoken"], item["heard"]) == ("Dolo", "dollo")
    assert world.iyer_admin.get(LIST, headers=H).json() == {"items": []}


def test_only_the_clinics_own_admin_removes_a_pair(world):
    misheard(world.rao, "Asha Verma")
    misheard(world.rao, "Lakshmi Narayan")
    (item,) = world.rao_admin.get(LIST, headers=H).json()["items"]
    url, before = f"{LIST}/{item['id']}", fingerprint(A)
    assert world.rao.delete(url, headers=H).status_code == 403                     # a doctor, not an admin
    assert world.iyer_admin.delete(url, headers=H).status_code == 404              # the other clinic's admin
    assert fingerprint(A) == before
    assert world.rao_admin.delete(url, headers=H).status_code == 200
    assert [tuple(r) for r in sql(A, "SELECT confirm_count, removed_at IS NOT NULL FROM spoken_mishearings")] == [(0, 1)]
