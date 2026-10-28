"""The usual rows stay with the doctor who saved them and the clinic they are in (plan SH-B6). Offline; the seeded two-clinic world."""
from fastapi.testclient import TestClient

from isolation_fixtures import B, H, fingerprint, save_body, world  # noqa: F401


def save(client, patient):
    body = save_body(patient, medicine="Dolo")
    body["structured"]["rx"][0].update({"strength": "650 mg", "dose": "1-0-1", "timing": "After food", "duration": "5 days"})
    body["structured"]["diagnosis"] = ["Acute pharyngitis"]
    body["confirmed_rows"] = [0]
    r = client.post("/api/v1/documents", json=body, headers=H)
    assert r.status_code == 200, r.text


def ask(client):
    return client.post("/api/v1/spoken/usual", json={"diagnosis": ["Acute pharyngitis"]}, headers=H)


def test_the_usual_rows_are_the_saving_doctors_own_in_their_own_clinic(world):
    before_b = fingerprint(B)
    for patient in ("Asha Verma", "Lakshmi Narayan"):
        save(world.rao, patient)
    assert fingerprint(B) == before_b
    mine = ask(world.rao)
    assert mine.status_code == 200
    items = [i for g in mine.json()["groups"] for i in g["items"]]
    assert [(i["name"], i["strength"], i["dose"], i["count"]) for i in items] == [("Dolo", "650 mg", "1-0-1", 2)]
    for other in (world.mehta, world.iyer):                       # same clinic other doctor; the other clinic
        r = ask(other)
        assert r.status_code == 200 and r.json() == {"groups": []}
    assert fingerprint(B) == before_b                              # a read changes nothing


def test_a_signed_out_client_gets_401_in_multi_clinic_mode(world):
    with TestClient(world.app) as anon:
        assert anon.post("/api/v1/spoken/usual", json={"diagnosis": ["Fever"]}, headers=H).status_code == 401
