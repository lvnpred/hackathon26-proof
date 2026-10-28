"""Plan SH-B2: a doctor never gets another doctor's or clinic's patient group in Spell it. Offline; the two-clinic world."""
from isolation_fixtures import H, save_body, world  # noqa: F401

URL = "/api/v1/rx/check-row"


def save(client, patient, *medicines):
    ids = []
    for m in medicines:
        r = client.post("/api/v1/documents", json=save_body(patient, medicine=m, document_id=None),
                        headers=H)
        assert r.status_code == 200, r.text
        ids.append(r.json()["document_id"])
    return ids


def groups(client, document_id, name="Suresh Babu"):
    ctx = {"diagnosis": [], "patient": {"name": name, "age_sex": "40 / M", "op_no": ""}}
    r = client.post(URL, json={"row": {"name": "Montelukat"}, "transcript": "tab montelukat", "context": ctx,
                               "document_id": document_id}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["context"], r.text


def test_another_doctors_or_clinics_saved_sheet_gives_no_patient_group(world):
    for who in ("rao", "mehta", "iyer"):                                  # every doctor has both medicines in use
        save(getattr(world, who), "Gopal Das", "Montelukast", "Azithromycin")
    first, last = save(world.mehta, "Suresh Babu", "Montelukast", "Azithromycin")
    got, _ = groups(world.mehta, last)
    assert [g["kind"] for g in got] == ["patient"] and [i["name"] for i in got[0]["items"]] == ["Montelukast"]
    for other in (world.rao, world.iyer):                                 # same clinic, other doctor; other clinic
        for name in ("Suresh Babu", "Gopal Das"):
            got, text = groups(other, last, name)
            assert got == [] and "Suresh" not in text and "Mehta" not in text
