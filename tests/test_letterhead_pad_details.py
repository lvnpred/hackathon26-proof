"""Accepting a letterhead fills the accepting doctor's own My details from the pad (user decision 2026-10-15);
a login name is independent of the printed doctor details. Offline."""
import json

from doctor_dictation.pdf import build_sheet_html
from letterhead_fixtures import clinic_conn, rao, record_renders, stub_layout, upload  # noqa: F401
from template_fixtures import GOOD_LAYOUT, PROFILE, make_jpeg, tclient  # noqa: F401

URL = "/api/v1/templates"
SAVE = {"structured": {"patientName": "Anita", "opNo": "", "rx": [{"name": "Tamsulosin", "status": "verified"}]},
        "confirmed_rows": []}


def _pad(**profile):
    lay = json.loads(json.dumps(GOOD_LAYOUT))
    lay["profile"] = {**PROFILE, **profile}
    return lay


def _mine(c):
    p = c.get("/api/v1/profile").json()
    return {k: p[k] for k in ("doctor_name", "qualifications", "reg_no")}


def _clinic():
    with clinic_conn() as conn:
        r = conn.execute("SELECT clinic_name, address, phone FROM clinic_profile").fetchone()
        return tuple(r) if r else None


def _accept(c, monkeypatch, layout, scope="clinic", path="accept"):
    stub_layout(monkeypatch, layout)
    tid = upload(c)
    body = {"scope": scope} if path == "accept" else None
    r = c.post(f"{URL}/{tid}/{path}", json=body) if body else c.post(f"{URL}/{tid}/{path}")
    assert r.status_code == 200, r.text
    return r


PAD_DOCTOR = {"doctor_name": "Dr A. Rao", "qualifications": "MBBS, MD", "reg_no": "TS-12345"}


def test_clinic_accept_fills_the_accepters_details_and_the_clinic_not_a_colleagues(rao, monkeypatch):
    before = _mine(rao.mehta)
    _accept(rao.rao, monkeypatch, _pad())
    assert _mine(rao.rao) == PAD_DOCTOR
    assert _clinic() == ("Meridian Clinic", "12 MG Road, Hyderabad", "040 1234 5678")
    assert _mine(rao.mehta) == before


def test_personal_accept_fills_the_accepters_doctor_fields_and_leaves_the_clinic_alone(rao, monkeypatch):
    with clinic_conn() as conn:
        conn.execute("INSERT INTO clinic_profile(id, clinic_name, address, phone, updated_at) VALUES (1, 'Rao Clinic', 'A', 'P', 'x')"
                     " ON CONFLICT(id) DO UPDATE SET clinic_name = 'Rao Clinic', address = 'A', phone = 'P'")
        conn.commit()
    _accept(rao.mehta, monkeypatch, _pad(), scope="mine")
    assert _mine(rao.mehta) == PAD_DOCTOR
    assert _clinic() == ("Rao Clinic", "A", "P")


def test_a_pad_with_a_blank_doctor_field_keeps_the_users_value(rao, monkeypatch):
    _accept(rao.mehta, monkeypatch, _pad(doctor_name="Dr Pad", qualifications="", reg_no=""))
    assert _mine(rao.mehta) == {"doctor_name": "Dr Pad", "qualifications": "MBBS, DNB", "reg_no": "TS-2"}


def test_use_details_fills_both_the_users_and_the_clinics_details(rao, monkeypatch):
    r = _accept(rao.rao, monkeypatch, _pad(), path="use-details")
    assert r.json()["profile"]["doctor_name"] == "Dr A. Rao"
    assert _mine(rao.rao) == PAD_DOCTOR and _clinic()[0] == "Meridian Clinic"
    assert _mine(rao.mehta)["doctor_name"] == "Dr. S. Mehta"


def test_the_printed_prescription_shows_the_pad_doctor_of_its_author(rao, monkeypatch):
    calls = record_renders(monkeypatch)
    _accept(rao.rao, monkeypatch, _pad(doctor_name="Dr Pad; Dr Second"))
    assert rao.rao.post("/api/v1/documents", json=SAVE).status_code == 200
    html = build_sheet_html(*calls[-1])
    assert ">Dr Pad</span>" in html and ">Dr Second</span>" in html and "Dr Pad; Dr Second" not in html   # one table cell per doctor
    assert rao.mehta.post("/api/v1/documents", json=SAVE).status_code == 200
    html = build_sheet_html(*calls[-1])
    assert "Dr. S. Mehta" in html and "Dr Pad" not in html


def test_single_mode_still_merges_all_six_fields_into_the_clinic_profile(tclient):
    tid = tclient.post(URL, files={"image": ("p.jpg", make_jpeg(), "image/jpeg")}).json()["id"]
    assert tclient.post(f"{URL}/{tid}/accept").status_code == 200
    assert tclient.get("/api/v1/profile").json() == {**PROFILE, "op_prefix": "OP"}


def test_a_login_name_differs_from_the_printed_doctor_name(rao, monkeypatch):
    calls = record_renders(monkeypatch)
    with clinic_conn() as conn:
        conn.execute("UPDATE users SET display_name = 'rao.login' WHERE id = ?", (rao.ids["rao"],))
        conn.commit()
    assert _mine(rao.rao)["doctor_name"] == "Dr. A. Rao"
    assert rao.rao.post("/api/v1/documents", json=SAVE).status_code == 200
    html = build_sheet_html(*calls[-1])
    assert "Dr. A. Rao" in html and "rao.login" not in html


def _mode_accept(c, monkeypatch, mode, ids=None, path="accept"):
    stub_layout(monkeypatch, _pad(doctor_name="Dr Pad", qualifications="PQ", reg_no="PR"))
    tid = upload(c)
    assert c.put(f"{URL}/{tid}/doctors", json={"mode": mode, "ids": ids or []}).status_code == 200
    r = c.post(f"{URL}/{tid}/{path}")
    assert r.status_code == 200, r.text
    return r


def test_the_accepters_details_are_filled_only_in_author_mode(rao, monkeypatch):
    before = _mine(rao.mehta)
    _mode_accept(rao.mehta, monkeypatch, "all")
    assert _mine(rao.mehta) == before and _clinic()[0] == "Meridian Clinic"          # clinic fields still merge
    _mode_accept(rao.mehta, monkeypatch, "selected", ids=[rao.ids["rao"]])
    assert _mine(rao.mehta) == before
    _mode_accept(rao.mehta, monkeypatch, "author")
    assert _mine(rao.mehta) == {"doctor_name": "Dr Pad", "qualifications": "PQ", "reg_no": "PR"}


def test_use_details_follows_the_templates_doctors_mode(rao, monkeypatch):
    before = _mine(rao.mehta)
    _mode_accept(rao.mehta, monkeypatch, "all", path="use-details")
    assert _mine(rao.mehta) == before and _clinic()[0] == "Meridian Clinic"
    _mode_accept(rao.mehta, monkeypatch, "author", path="use-details")
    assert _mine(rao.mehta)["doctor_name"] == "Dr Pad"


def test_pad_text_is_cleaned_before_it_is_stored(rao, monkeypatch):
    _accept(rao.rao, monkeypatch, _pad(doctor_name="Dr‮X\nY", qualifications="MB​BS", reg_no="T\tS  1"))
    assert _mine(rao.rao) == {"doctor_name": "DrX Y", "qualifications": "MBBS", "reg_no": "T S 1"}


def test_pad_text_is_cleaned_in_single_mode_too(tclient, monkeypatch):
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(_pad(doctor_name="Dr‮X\nY")))
    tid = tclient.post(URL, files={"image": ("p.jpg", make_jpeg(), "image/jpeg")}).json()["id"]
    assert tclient.post(f"{URL}/{tid}/accept").status_code == 200
    assert tclient.get("/api/v1/profile").json()["doctor_name"] == "DrX Y"
