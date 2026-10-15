"""Stored template paths are never trusted: a logo or file outside this clinic's templates folder is never read,
embedded or deleted. Offline."""
import base64
import os
from pathlib import Path

from doctor_dictation import clinics
from doctor_dictation.config import get_settings
from doctor_dictation.db import templates as tdb
from doctor_dictation.templates import service
from letterhead_fixtures import add_doctor, clinic_conn, rao, record_renders, signed_in, upload  # noqa: F401
from template_fixtures import GOOD_LAYOUT, make_jpeg, tconn  # noqa: F401

SAVE = {"structured": {"patientName": "Anita", "opNo": "", "rx": [{"name": "Tamsulosin", "status": "verified"}]},
        "confirmed_rows": []}


def test_a_logo_outside_the_templates_folder_is_never_read(tconn, tmp_path):
    secret = tmp_path / "outside" / "secret.jpg"
    secret.parent.mkdir()
    secret.write_bytes(make_jpeg())
    service.templates_dir().mkdir(parents=True, exist_ok=True)
    inside = service.templates_dir() / "1_logo.jpg"
    inside.write_bytes(make_jpeg())
    sibling = service.templates_dir().parent / "templates-evil" / "3_logo.jpg"      # shares the folder's name as a prefix
    sibling.parent.mkdir()
    sibling.write_bytes(make_jpeg())
    link = service.templates_dir() / "2_logo.jpg"
    os.symlink(secret, link)                                     # a link inside the folder pointing out of it
    assert service.logo_data_uri(inside).startswith("data:image/jpeg;base64,")
    for bad in (secret, str(secret), sibling, link, service.templates_dir() / ".." / "outside" / "secret.jpg", None, "", 5):
        assert service.logo_data_uri(bad) is None, bad


def test_purge_and_discard_never_delete_outside_the_templates_folder(tconn, tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    fresh = tdb.create_template_draft(tconn, GOOD_LAYOUT)
    old = tdb.create_template_draft(tconn, GOOD_LAYOUT, created_at="2020-01-01T00:00:00Z")
    for tid in (fresh, old):
        tdb.set_template_logo(tconn, tid, str(victim))
    service.discard(tconn, fresh)
    assert service.purge_expired(tconn, get_settings()) == 1
    assert victim.read_text() == "keep me"
    assert tdb.get_template(tconn, fresh) is None and tdb.get_template(tconn, old) is None


def test_clinic_b_never_embeds_clinic_a_logo(rao, monkeypatch):
    saves, previews = record_renders(monkeypatch), record_renders(monkeypatch, "templates")
    a_tid = upload(rao.rao)
    assert rao.rao.post(f"/api/v1/templates/{a_tid}/accept").status_code == 200
    with clinic_conn("rao") as conn:
        a_logo = tdb.get_template(conn, a_tid)["logo_path"]
    a_b64 = base64.b64encode(Path(a_logo).read_bytes()).decode("ascii")
    clinics.provision_clinic("iyer", "Iyer Clinic", "IYR")
    add_doctor("iyer", "dr.iyer", "Dr. K. Iyer")
    with signed_in(rao.app, "dr.iyer") as iyer:
        b_tid = upload(iyer)
        assert iyer.post(f"/api/v1/templates/{b_tid}/accept").status_code == 200
        with clinic_conn("iyer") as conn:                       # clinic B's row points at clinic A's logo file
            conn.execute("UPDATE templates SET logo_path = ? WHERE id = ?", (a_logo, b_tid))
            conn.commit()
        assert iyer.post("/api/v1/documents", json=SAVE).status_code == 200
        assert iyer.get(f"/api/v1/templates/{b_tid}/preview.pdf").status_code == 200
    _structured, meta, layout = saves[-1]
    assert layout is not None and "logo" not in meta             # the letterhead still prints, without the logo
    assert previews[-1][1]["logo"] is None
    assert not any(a_b64 in str(m) for _s, m, _l in saves + previews)
    assert Path(a_logo).is_file()                                # clinic B's requests never deleted clinic A's file


def test_unlink_refuses_the_folder_itself_a_prefix_sibling_and_a_directory(tconn, tmp_path):
    folder = service.templates_dir()
    folder.mkdir(parents=True, exist_ok=True)
    sibling = folder.parent / "templates-evil"
    sibling.mkdir()
    evil = sibling / "x.jpg"
    evil.write_bytes(b"keep")
    subdir = folder / "sub"
    subdir.mkdir()
    service._unlink(folder, sibling, evil, subdir, str(evil))
    assert folder.is_dir() and sibling.is_dir() and evil.read_bytes() == b"keep" and subdir.is_dir()


def test_unlink_deletes_a_real_file_inside_the_templates_folder(tconn):
    service.templates_dir().mkdir(parents=True, exist_ok=True)
    f = service.templates_dir() / "9_logo.jpg"
    f.write_bytes(b"x")
    service._unlink(f)
    assert not f.exists()
