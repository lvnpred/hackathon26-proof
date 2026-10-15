"""Letterhead through HTTP (spec 9, 13.1): clinic default, a doctor's opt-in and switch back, the doctors block in
all three modes, a disabled doctor left off, the review warning, and no effect across clinics. Offline."""
import json
from html.parser import HTMLParser

from doctor_dictation import accounts, admin_demo
from isolation_fixtures import (A, A_MARKERS, B, H, UPLOAD_PAD, UPLOAD_PAD_LINE, accept, disable_user, enable_user,
                                doctor_warning, leaks, reprint, set_doctors, sql, upload, use_clinic_letterhead,
                                user_id, world)  # noqa: F401

RAO, MEHTA = admin_demo.doctor("dr.rao")["doctor_name"], admin_demo.doctor("dr.mehta")["doctor_name"]
SUSPICIOUS = "Dr. K. Iyer, MBBS, MS (ENT)"
NURSE = "Nurse Pooja Assistant"


class _Doctors(HTMLParser):
    """Collects the markup inside the printed ``lh-doctors`` div (nesting-aware)."""
    def __init__(self):
        super().__init__()
        self.depth, self.text, self.found = 0, [], False

    def handle_starttag(self, tag, attrs):
        if tag == "div" and (self.depth or ("class", "lh-doctors") in attrs):
            self.depth += 1
            self.found = True

    def handle_endtag(self, tag):
        if tag == "div" and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if self.depth:
            self.text.append(data)


def _parse(html):
    p = _Doctors()
    p.feed(html.split("\n", 1)[1] if html.startswith("%PDF") else html)
    return p


def has_doctors_block(html) -> bool:
    return _parse(html).found


def doctors_block(html):
    """The printed doctors text. A missing block is a failure, never an empty string a ``not in`` would let pass."""
    p = _parse(html)
    assert p.found, "the printed sheet has no lh-doctors block"
    return " | ".join(p.text)


def test_each_clinic_prints_on_its_own_clinic_letterhead(world):
    a, b = reprint(world.mehta, A, 2), reprint(world.iyer, B, 1)
    assert admin_demo.RAO_PAD_LINE in a and admin_demo.IYER_PAD_LINE not in a
    assert RAO in a and MEHTA in a                                   # the shared pad lists every doctor ("all")
    assert admin_demo.IYER_PAD_LINE in b and not leaks(b, A_MARKERS)


def test_a_doctor_can_opt_in_to_their_own_letterhead_and_switch_back(world):
    r = upload(world.mehta)                                          # the stub reads UPLOAD_PAD
    assert r.status_code == 201, r.text
    assert accept(world.mehta, r.json()["id"], scope="mine").status_code == 200
    assert UPLOAD_PAD_LINE in reprint(world.mehta, A, 2)             # Mehta's own prescription: Mehta's pad
    assert UPLOAD_PAD_LINE in reprint(world.rao, A, 2)               # the AUTHOR's choice, whoever reprints
    rao_own = reprint(world.rao, A, 1)
    assert admin_demo.RAO_PAD_LINE in rao_own and UPLOAD_PAD_LINE not in rao_own
    assert admin_demo.IYER_PAD_LINE in reprint(world.iyer, B, 1)
    rao_by_mehta = reprint(world.mehta, A, 1)                        # the author's pad, never the viewer's
    assert admin_demo.RAO_PAD_LINE in rao_by_mehta and UPLOAD_PAD_LINE not in rao_by_mehta
    assert use_clinic_letterhead(world.mehta).status_code == 200
    back = reprint(world.mehta, A, 2)
    assert admin_demo.RAO_PAD_LINE in back and UPLOAD_PAD_LINE not in back


def test_the_doctors_block_follows_author_all_and_selected(world):
    tid, mehta = world.seeded[A]["template_id"], user_id(world, "dr.mehta")
    assert set_doctors(world.rao, tid, "author").status_code == 200
    block = doctors_block(reprint(world.rao, A, 3))                  # document 3 is Rao's
    assert RAO in block and MEHTA not in block
    assert set_doctors(world.rao, tid, "all").status_code == 200
    by_rao, by_mehta = doctors_block(reprint(world.rao, A, 3)), doctors_block(reprint(world.mehta, A, 3))
    assert RAO in by_rao and MEHTA in by_rao
    assert by_rao.index(RAO) < by_rao.index(MEHTA)                   # oldest account first (Rao before Mehta)
    assert by_mehta.index(RAO) < by_mehta.index(MEHTA)               # and the same for either viewer
    assert set_doctors(world.rao, tid, "selected", [mehta]).status_code == 200
    sql(A, "UPDATE templates SET doctors_ids = ? WHERE id = ?", json.dumps([mehta, 99]), tid)        # A8: unknown id
    block = doctors_block(reprint(world.rao, A, 3))
    assert MEHTA in block and RAO not in block


def test_only_active_doctors_are_listed_never_an_assistant(world):
    accounts.create_user(A, "pooja", display_name=NURSE, doctor_name=NURSE, role="assistant", password="Pooja-pass-12345")
    assert set_doctors(world.rao, world.seeded[A]["template_id"], "all").status_code == 200
    block = doctors_block(reprint(world.rao, A, 3))
    assert RAO in block and MEHTA in block and NURSE not in block


def test_a_disabled_doctor_is_left_off_the_letterhead(world):
    tid, mehta = world.seeded[A]["template_id"], user_id(world, "dr.mehta")
    assert set_doctors(world.rao, tid, "all").status_code == 200
    assert disable_user(world.rao, mehta).status_code == 200
    block = doctors_block(reprint(world.rao, A, 3))
    assert RAO in block and MEHTA not in block
    assert enable_user(world.rao, mehta).status_code == 200
    assert set_doctors(world.rao, tid, "selected", [mehta]).status_code == 200
    assert disable_user(world.rao, mehta).status_code == 200         # selected first: the route refuses a disabled id
    assert MEHTA not in doctors_block(reprint(world.rao, A, 3))


def test_the_review_warns_about_a_literal_line_that_looks_like_a_doctor(world, monkeypatch):
    pad = json.loads(json.dumps(UPLOAD_PAD))
    pad["header"].append({"type": "text", "text": SUSPICIOUS, "role": "small", "align": "center"})
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(pad))
    r = upload(world.iyer)
    assert r.status_code == 201, r.text
    assert doctor_warning(r.json(), SUSPICIOUS)
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(UPLOAD_PAD))
    clean = upload(world.iyer)
    assert clean.status_code == 201 and not doctor_warning(clean.json(), UPLOAD_PAD_LINE)


def test_letterhead_changes_in_one_clinic_never_reach_the_other(world):
    before = [tuple(r) for r in sql(B, "SELECT * FROM templates ORDER BY id")]
    tid = world.seeded[A]["template_id"]
    assert set_doctors(world.rao, tid, "author").status_code == 200
    assert world.rao.post("/api/v1/templates/deactivate", headers=H).status_code == 200
    assert [tuple(r) for r in sql(B, "SELECT * FROM templates ORDER BY id")] == before
    assert admin_demo.IYER_PAD_LINE in reprint(world.iyer, B, 1)
    assert admin_demo.RAO_PAD_LINE not in reprint(world.rao, A, 1)   # A is on the built-in layout now


def test_a_letterhead_without_a_doctors_block_prints_none(world):
    assert not has_doctors_block(reprint(world.iyer, B, 1))          # Iyer's pad has no doctors block
    assert has_doctors_block(reprint(world.rao, A, 3))               # Rao's shared pad does
    try:
        doctors_block(reprint(world.iyer, B, 1))
    except AssertionError as exc:
        assert "no lh-doctors block" in str(exc)
    else:
        raise AssertionError("doctors_block accepted a sheet with no block")
