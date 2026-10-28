"""seed-demo: guards, the two clinics, three doctors, a document 1 in each, letterheads, OP prefixes. Offline."""
import json
import re
from contextlib import closing
from pathlib import Path

import pytest

from doctor_dictation import admin, admin_demo, authn, clinics, scope
from doctor_dictation import db as dbmod
from doctor_dictation.directory import list_clinics, open_directory
from doctor_dictation.pdf import validate_layout
from doctor_dictation.scope import clinic_dir


@pytest.fixture()
def demo(multi, monkeypatch):
    monkeypatch.setenv(admin_demo.DEMO_ENV, "1")
    return multi


def _rows(slug, query, *args):
    with closing(dbmod.get_conn(clinic_dir(slug) / "app.db")) as c:
        return c.execute(query, args).fetchall()


def test_seed_demo_refuses_unless_demo_mode_is_exactly_1(multi, monkeypatch):
    for value in (None, "", "0", "true", "yes", " 1", "1 ", "TRUE"):
        if value is None:
            monkeypatch.delenv(admin_demo.DEMO_ENV, raising=False)
        else:
            monkeypatch.setenv(admin_demo.DEMO_ENV, value)
        with pytest.raises(admin_demo.DemoError, match="DEMO_MODE=1"):
            admin_demo.seed_demo()
    assert not (multi / "clinics").exists() and not (multi / "directory.db").exists()


def test_the_cli_refuses_without_demo_mode_and_exits_1(multi, monkeypatch, capsys):
    monkeypatch.setattr(admin, "load_dotenv", lambda *a, **k: False)     # a developer's .env must not switch it on
    monkeypatch.delenv(admin_demo.DEMO_ENV, raising=False)
    assert admin.main(["seed-demo"]) == 1
    assert "DEMO_MODE=1" in capsys.readouterr().err
    assert not (multi / "clinics").exists()


def test_seed_demo_refuses_a_data_folder_that_already_has_a_clinic(demo):
    clinics.provision_clinic("real", "A Real Clinic")
    with pytest.raises(admin_demo.DemoError, match="NEW empty folder"):
        admin_demo.seed_demo()
    with closing(open_directory()) as d:
        assert [r["slug"] for r in list_clinics(d)] == ["real"]
    assert not clinic_dir("rao").exists() and not clinic_dir("iyer").exists()


def test_three_demo_doctors_sign_in_with_their_published_passwords(demo):
    seeded = admin_demo.seed_demo()
    assert seeded["rao"]["users"] == {"dr.rao": 1, "dr.mehta": 2} and seeded["iyer"]["users"] == {"dr.iyer": 1}
    for d in admin_demo.DOCTORS:
        ident = authn.authenticate(d["username"], d["password"], "10.0.0.9")
        assert ident is not None and ident.clinic_slug == d["clinic"], d["username"]
        assert (ident.display_name, ident.must_change_password) == (d["display_name"], False)
    mehta = admin_demo.doctor("dr.mehta")
    row = _rows("rao", "SELECT doctor_name, qualifications, reg_no FROM users WHERE username = 'dr.mehta'")[0]
    assert tuple(row) == (mehta["doctor_name"], mehta["qualifications"], mehta["reg_no"])


def test_each_clinic_gets_fake_patients_and_its_own_document_1(demo):
    seeded = admin_demo.seed_demo()
    assert seeded["rao"]["documents"] == [1, 2, 3] and seeded["iyer"]["documents"] == [1, 2]

    def first_patient(slug):
        return json.loads(_rows(slug, "SELECT structured_json FROM documents WHERE id = 1")[0][0])["patientName"]

    assert (first_patient("rao"), first_patient("iyer")) == ("Asha Verma", "Bharat Menon")
    authorship = ("SELECT d.id, e.doctor_id, d.finalized_by FROM documents d"
                  " JOIN encounters e ON e.id = d.encounter_id ORDER BY d.id")
    assert [tuple(r) for r in _rows("rao", authorship)] == [(1, 1, 1), (2, 2, 2), (3, 1, 1)]
    assert [tuple(r) for r in _rows("iyer", authorship)] == [(1, 1, 1), (2, 1, 1)]
    start, end = dbmod.local_day_bounds_utc()
    for slug in ("rao", "iyer"):
        assert all(start <= r["created_at"] < end for r in _rows(slug, "SELECT created_at FROM documents"))


def test_seeded_op_numbers_carry_each_clinics_prefix_and_start_at_001(demo):
    admin_demo.seed_demo()
    for slug, prefix, count in (("rao", "RAO", 3), ("iyer", "IYER", 2)):
        ops = [r["op_no"] for r in _rows(slug, "SELECT op_no FROM patients ORDER BY id")]
        assert [o[-3:] for o in ops] == [f"{i:03d}" for i in range(1, count + 1)], ops
        assert all(re.fullmatch(rf"{prefix}-\d{{8}}-\d{{3}}", o) for o in ops), ops
        assert [r["op_no"] for r in _rows(slug, "SELECT op_no FROM encounters ORDER BY id")] == ops


def test_each_clinic_gets_its_own_active_letterhead_and_logo(demo):
    admin_demo.seed_demo()
    logos = {}
    for slug, mode, line in (("rao", "all", admin_demo.RAO_PAD_LINE), ("iyer", "author", admin_demo.IYER_PAD_LINE)):
        rows = _rows(slug, "SELECT * FROM templates WHERE status = 'active'")
        assert len(rows) == 1, slug
        layout = json.loads(rows[0]["layout_json"])
        validate_layout(layout)
        assert rows[0]["owner_user_id"] is None and rows[0]["doctors_mode"] == mode
        assert line in [b.get("text") for b in layout["header"]]
        logo = Path(rows[0]["logo_path"])
        assert logo.is_file() and logo.resolve().is_relative_to((clinic_dir(slug) / "templates").resolve())
        logos[slug] = logo.read_bytes()
    assert logos["rao"] != logos["iyer"]
    rao_layout = json.loads(_rows("rao", "SELECT layout_json FROM templates WHERE id = 1")[0][0])
    assert any(b["type"] == "doctors" for b in rao_layout["header"])


def test_the_cli_prints_the_demo_logins_once_with_a_demo_only_warning(demo, monkeypatch, capsys):
    monkeypatch.setattr(admin, "load_dotenv", lambda *a, **k: False)
    assert admin.main(["seed-demo"]) == 0
    out = capsys.readouterr().out
    assert "DEMO ONLY" in out
    for d in admin_demo.DOCTORS:
        assert d["username"] in out and out.count(d["password"]) == 1


def test_seeded_audit_rows_name_each_prescriptions_author_and_never_a_password(demo):
    admin_demo.seed_demo()
    a = {(r["actor"], r["action"]) for r in _rows("rao", "SELECT actor, action FROM audit_log")}
    b = {(r["actor"], r["action"]) for r in _rows("iyer", "SELECT actor, action FROM audit_log")}
    assert {("dr.rao", "finalize"), ("dr.mehta", "finalize"), ("seed-demo", "user_create")} <= a
    assert ("dr.iyer", "finalize") in b and not {actor for actor, _ in b} & {"dr.rao", "dr.mehta"}
    every = " ".join(str(tuple(r)) for slug in ("rao", "iyer") for r in _rows(slug, "SELECT * FROM audit_log"))
    assert not [d["password"] for d in admin_demo.DOCTORS if d["password"] in every]


def test_seed_demo_refuses_when_data_dir_is_unset_and_creates_nothing(demo, monkeypatch, tmp_path):
    default = tmp_path / "default-data"
    monkeypatch.setattr(scope, "DEFAULT_DATA_DIR", default)
    monkeypatch.delenv("DATA_DIR", raising=False)
    with pytest.raises(admin_demo.DemoError, match="NEW empty folder"):
        admin_demo.seed_demo()
    assert not default.exists()


def test_seed_demo_refuses_the_default_data_folder_even_when_named_explicitly(demo, monkeypatch, tmp_path):
    default = tmp_path / "default-data"
    default.mkdir()
    monkeypatch.setattr(scope, "DEFAULT_DATA_DIR", default.resolve())
    monkeypatch.setenv("DATA_DIR", str(default))
    with pytest.raises(admin_demo.DemoError, match="NEW empty folder"):
        admin_demo.seed_demo()
    assert list(default.iterdir()) == []


@pytest.mark.parametrize("name", ["app.db", "pdfs", "templates"])
def test_seed_demo_refuses_a_folder_holding_single_clinic_data(demo, name):
    target = demo / name
    target.mkdir() if name != "app.db" else target.write_bytes(b"")
    before = sorted(p.name for p in demo.iterdir())
    with pytest.raises(admin_demo.DemoError, match="NEW empty folder"):
        admin_demo.seed_demo()
    assert sorted(p.name for p in demo.iterdir()) == before


def test_seed_demo_refuses_a_stray_directory_file_before_looking_at_usernames(demo):
    with closing(open_directory()) as d:      # a directory.db with a stray login row: refused as non-empty
        d.execute("PRAGMA foreign_keys = OFF")
        d.execute("INSERT INTO login_index(username, clinic_slug, user_id) VALUES ('dr.rao', 'elsewhere', 1)")
        d.commit()
    with pytest.raises(admin_demo.DemoError, match="NEW empty folder"):
        admin_demo.seed_demo()
    assert not clinic_dir("rao").exists()


def test_seed_demo_refuses_a_case_variant_spelling_of_the_default_folder(demo, monkeypatch, tmp_path):
    default = tmp_path / "Default-Data"
    default.mkdir()
    monkeypatch.setattr(scope, "DEFAULT_DATA_DIR", default.resolve())
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "default-data"))
    if not (tmp_path / "default-data").exists():
        pytest.skip("case-sensitive filesystem: no case-variant spelling to test")
    with pytest.raises(admin_demo.DemoError, match="NEW empty folder"):
        admin_demo.seed_demo()
    assert list(default.iterdir()) == []


def test_seed_demo_refuses_a_folder_that_contains_the_default_folder(demo, monkeypatch, tmp_path):
    default = tmp_path / "repo" / "data"
    default.mkdir(parents=True)
    monkeypatch.setattr(scope, "DEFAULT_DATA_DIR", default.resolve())
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "repo"))
    with pytest.raises(admin_demo.DemoError, match="contains the default data folder"):
        admin_demo.seed_demo()
    assert sorted(p.name for p in (tmp_path / "repo").iterdir()) == ["data"]


@pytest.mark.parametrize("name", ["clinics", "directory.db"])
def test_seed_demo_refuses_a_folder_that_already_has_clinics_or_a_directory(demo, name):
    target = demo / name
    target.mkdir() if name == "clinics" else target.write_bytes(b"")
    with pytest.raises(admin_demo.DemoError, match="NEW empty folder"):
        admin_demo.seed_demo()
    assert sorted(p.name for p in demo.iterdir()) == [name]


def test_seed_demo_refuses_a_folder_holding_any_file_such_as_a_custom_named_database(demo):
    (demo / "my.db").write_bytes(b"")
    with pytest.raises(admin_demo.DemoError, match="NEW empty folder"):
        admin_demo.seed_demo()
    assert [p.name for p in demo.iterdir()] == ["my.db"]


def test_seed_demo_accepts_an_empty_existing_folder_and_a_missing_one(demo, monkeypatch, tmp_path):
    assert list(demo.iterdir()) == []
    assert admin_demo.seed_demo()["rao"]["documents"]                    # the empty tmp folder from the fixture
    fresh = tmp_path / "does-not-exist-yet"
    monkeypatch.setenv("DATA_DIR", str(fresh))
    assert not fresh.exists()
    assert admin_demo.seed_demo()["iyer"]["documents"] and fresh.is_dir()
