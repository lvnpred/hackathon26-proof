"""Spec 9.4 through the real save and reprint routes: which letterhead, which doctors, whose details. Offline."""
import json

from doctor_dictation.pdf import build_sheet_html
from letterhead_fixtures import DOCTORS_LAYOUT, clinic_conn, rao, record_renders, stub_layout, upload  # noqa: F401
from template_fixtures import GOOD_LAYOUT

URL = "/api/v1/templates"
SAVE = {"structured": {"patientName": "Anita", "opNo": "", "rx": [{"name": "Tamsulosin", "status": "verified"}]},
        "confirmed_rows": []}


def _save(c):
    r = c.post("/api/v1/documents", json=SAVE)
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def _html(call):
    structured, meta, layout = call
    return build_sheet_html(structured, meta, layout)


def _accept(c, layout, monkeypatch, scope="clinic", mode=None, ids=None):
    stub_layout(monkeypatch, layout)
    tid = upload(c)
    if mode:
        assert c.put(f"{URL}/{tid}/doctors", json={"mode": mode, "ids": ids or []}).status_code == 200
    assert c.post(f"{URL}/{tid}/accept", json={"scope": scope}).status_code == 200
    return tid


def _pad(text):
    """GOOD_LAYOUT with a recognisable literal line, to tell two letterheads apart in the printed HTML."""
    lay = json.loads(json.dumps(GOOD_LAYOUT))
    lay["header"][2]["text"] = text
    return lay


def test_clinic_letterhead_prints_the_author_not_the_pad_snapshot(rao, monkeypatch):
    calls = record_renders(monkeypatch)
    _accept(rao.rao, GOOD_LAYOUT, monkeypatch)
    _save(rao.mehta)
    _structured, meta, layout = calls[-1]
    assert layout is not None and meta["doctors"] is None            # author mode: the sheet prints the author
    html = _html(calls[-1])
    assert "Dr. S. Mehta" in html and "Dr A. Rao" not in html         # the live author beats the stored "Dr A. Rao"


def test_my_own_letterhead_prints_only_on_my_prescriptions_until_i_switch_back(rao, monkeypatch):
    calls = record_renders(monkeypatch)
    _accept(rao.rao, _pad("Clinic pad"), monkeypatch)
    _accept(rao.mehta, _pad("Mehta pad"), monkeypatch, scope="mine")
    _save(rao.mehta)
    assert "Mehta pad" in _html(calls[-1])
    _save(rao.rao)
    assert "Clinic pad" in _html(calls[-1]) and "Mehta pad" not in _html(calls[-1])
    assert rao.mehta.post(URL + "/deactivate", json={"scope": "mine"}).json() == {"deactivated": True}
    _save(rao.mehta)
    assert "Clinic pad" in _html(calls[-1])


def test_a_colleagues_reprint_uses_the_authors_letterhead_and_details(rao, monkeypatch):
    calls = record_renders(monkeypatch)
    _accept(rao.rao, _pad("Clinic pad"), monkeypatch)
    _accept(rao.rao, _pad("Rao pad"), monkeypatch, scope="mine")
    doc = _save(rao.rao)
    with clinic_conn() as conn:                    # force the on-demand render instead of serving the stored file
        conn.execute("UPDATE documents SET pdf_path = NULL WHERE id = ?", (doc,))
        conn.commit()
    assert rao.mehta.get(f"/api/v1/documents/{doc}/pdf").status_code == 200
    html = _html(calls[-1])
    assert "Rao pad" in html and "Dr. A. Rao" in html and "Dr. S. Mehta" not in html


def test_doctors_block_all_lists_the_active_doctors_and_skips_the_disabled(rao, monkeypatch):
    calls = record_renders(monkeypatch)
    _accept(rao.rao, DOCTORS_LAYOUT, monkeypatch, mode="all")
    _save(rao.mehta)
    assert [d["name"] for d in calls[-1][1]["doctors"]] == ["Dr. A. Rao", "Dr. S. Mehta"]
    html = _html(calls[-1])
    assert "Dr. A. Rao" in html and "Reg. No: TS-2" in html and "Dr. Old" not in html


def test_doctors_block_selected_skips_a_doctor_disabled_later(rao, monkeypatch):
    calls = record_renders(monkeypatch)
    _accept(rao.rao, DOCTORS_LAYOUT, monkeypatch, mode="selected", ids=[rao.ids["mehta"], rao.ids["rao"]])
    with clinic_conn() as conn:
        conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (rao.ids["mehta"],))
        conn.commit()
    _save(rao.rao)
    assert [d["name"] for d in calls[-1][1]["doctors"]] == ["Dr. A. Rao"]


def test_doctors_block_in_author_mode_prints_only_the_author(rao, monkeypatch):
    calls = record_renders(monkeypatch)
    _accept(rao.rao, DOCTORS_LAYOUT, monkeypatch)
    _save(rao.mehta)
    html = _html(calls[-1])
    assert "Dr. S. Mehta" in html and "Dr. A. Rao" not in html and "Dr Pad Name" not in html


def test_preview_lists_the_chosen_doctors(rao, monkeypatch):
    calls = record_renders(monkeypatch, "templates")
    stub_layout(monkeypatch, DOCTORS_LAYOUT)
    tid = upload(rao.rao)
    assert rao.rao.put(f"{URL}/{tid}/doctors", json={"mode": "all"}).status_code == 200
    assert rao.rao.get(f"{URL}/{tid}/preview.pdf").status_code == 200
    assert [d["name"] for d in calls[-1][1]["doctors"]] == ["Dr. A. Rao", "Dr. S. Mehta"]


def test_layout_and_doctors_of_one_print_come_from_one_letterhead_lookup(rao, monkeypatch):
    from doctor_dictation.templates import service
    calls = record_renders(monkeypatch)
    _accept(rao.rao, DOCTORS_LAYOUT, monkeypatch, mode="all")
    looked_up = []
    real = service.active_row_for
    monkeypatch.setattr(service, "active_row_for", lambda *a, **k: looked_up.append(a) or real(*a, **k))
    _save(rao.mehta)
    assert len(looked_up) == 1                                       # a concurrent accept cannot pair layout A with doctors B
    assert [d["name"] for d in calls[-1][1]["doctors"]] == ["Dr. A. Rao", "Dr. S. Mehta"]


def test_a_doctor_with_no_reg_no_never_prints_the_pads_registration_number(rao, monkeypatch):
    calls = record_renders(monkeypatch)
    pad = json.loads(json.dumps(DOCTORS_LAYOUT))
    pad["profile"].update(doctor_name="Dr. A. Rao", qualifications="MBBS, MD", reg_no="TS-1 (Rao)")
    pad["header"].insert(0, {"type": "text", "field": "reg_no"})
    _accept(rao.rao, pad, monkeypatch)
    with clinic_conn() as conn:
        conn.execute("UPDATE users SET reg_no = '' WHERE id = ?", (rao.ids["mehta"],))
        conn.commit()
    doc = _save(rao.mehta)
    assert "TS-1 (Rao)" not in str(calls[-1][1]) and "TS-1 (Rao)" not in _html(calls[-1])
    assert "Dr. S. Mehta" in _html(calls[-1])
