"""E4: patient blanks are left out at import, kept as left_out entries, and restorable. Offline."""
import copy

import pytest

from doctor_dictation.pdf import validate_layout
from doctor_dictation.pdf.sheet import build_sheet_html
from doctor_dictation.templates import TemplateError, lines
from letterhead_fixtures import clinic_conn, rao, stub_layout  # noqa: F401
from template_fixtures import GOOD_LAYOUT, PROFILE, make_jpeg

BLANK = {"type": "text", "text": "Name: M F Age: Date:"}
AFTER = {"type": "text", "text": "Visit After"}


def _layout():
    return {"header": [{"type": "logo", "crop": [0, 0, .1, .1]}, dict(BLANK), {"type": "rule"}, dict(AFTER)],
            "footer": [{"type": "text", "field": "address"}],
            "body": {"top": 0.22, "bottom": 0.92}, "profile": dict(PROFILE)}


def _dropped():
    lay = _layout()
    lay["left_out"] = lines.left_out_entries(lay)
    lines.drop_fill_in_lines(lay)
    return lay


def test_classifier_pins_the_specs_examples():
    yes = ["Name: M F Age: Date:", "Name ____ Age ___", "Name:", "Date:", "Age / Sex", "O.P. No."]
    no = ["Dr. A. Kumar, MD", "Reg. No: 82233", "Ph: 040 1234 5678", "12 MG Road, Hyderabad 500001", "Open Mon to Sat"]
    assert [t for t in yes if not lines.is_fill_in_label(t)] == []
    assert [t for t in no if lines.is_fill_in_label(t)] == []


def test_left_out_entries_keep_the_original_index_and_block():
    lay = _layout()
    entries = lines.left_out_entries(lay)
    assert entries == [{"section": "header", "index": 1, "block": BLANK},
                       {"section": "header", "index": 3, "block": AFTER}]
    assert entries[0]["block"] is not lay["header"][1]


def test_restore_puts_a_line_back_between_its_old_neighbours_and_prints():
    lay = _dropped()
    assert len(lay["header"]) == 2
    lay["skipped_labels"] = [BLANK["text"], "Sex:"]
    lines.restore_left_out(lay, [0])
    assert lay["skipped_labels"] == ["Sex:"]
    assert lay["header"][1] == BLANK and len(lay["left_out"]) == 1
    html = build_sheet_html({"patientName": "R", "rx": [], "advice": [], "review": ""}, {"date": "", "opNo": ""},
                            validate_layout(lay))
    assert "Name: M F Age: Date:" in html
    only = _dropped()
    lines.restore_left_out(only, [1])
    assert only["header"][2] == AFTER and only["left_out"][0]["block"] == BLANK
    both = _dropped()
    lines.restore_left_out(both, [0, 1])
    assert both["header"] == _layout()["header"] and "left_out" not in both


@pytest.mark.parametrize("bad", [[5], [-1], [True], [0, 0], "x", [[1]], [{}]])
def test_restore_refuses_bad_include(bad):
    lay = _dropped()
    before = copy.deepcopy(lay)
    with pytest.raises(TemplateError) as exc:
        lines.restore_left_out(lay, bad)
    assert exc.value.status == 400 and lay == before


def _upload(c):
    r = c.post("/api/v1/templates", files={"image": ("pad.jpg", make_jpeg(), "image/jpeg")})
    assert r.status_code == 201, r.text
    return r.json()


def test_tidy_route_include_restores_and_old_letterheads_still_work(rao, monkeypatch):
    c = rao.rao
    stub_layout(monkeypatch, _layout())
    made = _upload(c)
    tid = made["id"]
    assert [e["index"] for e in made["layout"]["left_out"]] == [1, 3]
    r = c.put(f"/api/v1/templates/{tid}/lines", json={"lines": [], "keep": [], "include": [0]})
    assert r.status_code == 200, r.text
    lay = r.json()["layout"]
    assert lay["header"][1]["text"] == "Name: M F Age: Date:" and len(lay["left_out"]) == 1
    stub_layout(monkeypatch, GOOD_LAYOUT)
    old = _upload(c)
    with clinic_conn() as conn:
        raw = conn.execute("SELECT layout_json FROM templates WHERE id = ?", (old["id"],)).fetchone()[0]
    r = c.put(f"/api/v1/templates/{old['id']}/lines", json={"lines": [], "keep": [], "include": []})
    assert r.status_code == 200 and r.json() == old and "left_out" not in r.json()["layout"]
    with clinic_conn() as conn:
        assert conn.execute("SELECT layout_json FROM templates WHERE id = ?", (old["id"],)).fetchone()[0] == raw


def test_bad_include_through_the_route_is_400_and_changes_nothing(rao, monkeypatch):
    c = rao.rao
    stub_layout(monkeypatch, _layout())
    tid = _upload(c)["id"]

    def stored():
        with clinic_conn() as conn:
            return conn.execute("SELECT layout_json FROM templates WHERE id = ?", (tid,)).fetchone()[0]
    before = stored()
    for bad in ([[1]], [{}], [9], [0, 0], "x"):
        r = c.put(f"/api/v1/templates/{tid}/lines", json={"lines": [], "keep": [], "include": bad})
        assert r.status_code == 400, (bad, r.text)
    assert stored() == before


def test_edit_route_include_restores_the_line(rao, monkeypatch):
    c = rao.rao
    stub_layout(monkeypatch, _layout())
    made = _upload(c)
    tid = made["id"]
    r = c.put(f"/api/v1/templates/{tid}", json={"profile": made["profile"], "lines": [], "keep": [], "include": [0]})
    assert r.status_code == 200, r.text
    lay = r.json()["layout"]
    assert lay["header"][1]["text"] == "Name: M F Age: Date:" and len(lay["left_out"]) == 1
    assert BLANK["text"] not in lay.get("skipped_labels", [])
