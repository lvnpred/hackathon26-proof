"""Files (spec 13.1): Clinic A's PDFs, logos and uploads are unreadable through Clinic B, including stored paths
that point into A by absolute path, ".." traversal or a symlink (the cross-clinic form of
tests/test_document_pdf.py:67-86). Offline."""
import base64
import os
from contextlib import closing
from pathlib import Path

import pytest

from doctor_dictation.directory import directory_path, open_directory
from doctor_dictation.scope import clinic_dir
from isolation_fixtures import A, A_MARKERS, B, leaks, pdf_text, reprint, sql, upload, world  # noqa: F401


def _a_pdf(world):
    """Render and store Clinic A's document 3 (only A has it); return the stored file."""
    assert world.rao.get("/api/v1/documents/3/pdf").status_code == 200
    path = Path(sql(A, "SELECT pdf_path FROM documents WHERE id = 3")[0]["pdf_path"])
    assert path.is_file() and b"Lakshmi Narayan" in path.read_bytes()
    return path


def test_clinic_a_pdf_is_404_through_clinic_b(world):
    _a_pdf(world)
    r = world.iyer.get("/api/v1/documents/3/pdf")
    assert r.status_code == 404 and b"Lakshmi" not in r.content


@pytest.mark.parametrize("shape", ["absolute", "dotdot", "symlink"])
def test_a_stored_path_into_clinic_a_is_never_served_to_clinic_b(world, shape):
    target = _a_pdf(world)
    secret = target.read_bytes()
    b_pdfs = clinic_dir(B) / "pdfs"
    b_pdfs.mkdir(parents=True, exist_ok=True)
    if shape == "absolute":
        raw = str(target)
    elif shape == "dotdot":
        raw = str(b_pdfs / ".." / ".." / A / "pdfs" / target.name)
    else:
        link = b_pdfs / "looks_local.pdf"
        link.symlink_to(target)
        raw = str(link)
    sql(B, "UPDATE documents SET pdf_path = ? WHERE id = 1", raw)
    r = world.iyer.get("/api/v1/documents/1/pdf")
    assert r.status_code == 200
    body = pdf_text(r)
    assert "Bharat Menon" in body and not leaks(body, A_MARKERS)       # B's own document 1, rendered afresh
    assert target.read_bytes() == secret                               # A's file untouched


def test_a_logo_stored_in_clinic_a_is_never_embedded_for_clinic_b(world):      # finding F1 if it fails
    a_logo = Path(sql(A, "SELECT logo_path FROM templates WHERE id = 1")[0]["logo_path"])
    b_logo = Path(sql(B, "SELECT logo_path FROM templates WHERE id = 1")[0]["logo_path"])
    secret = base64.b64encode(a_logo.read_bytes()).decode("ascii")
    own = base64.b64encode(b_logo.read_bytes()).decode("ascii")
    assert secret != own and own in reprint(world.iyer, B, 1)            # positive control: B's own logo prints
    link = b_logo.parent / "looks_local_logo.jpg"
    link.symlink_to(a_logo)
    for raw in (str(a_logo), str(b_logo.parent / ".." / ".." / A / "templates" / a_logo.name), str(link)):
        sql(B, "UPDATE templates SET logo_path = ? WHERE id = 1", raw)
        assert secret not in reprint(world.iyer, B, 1), raw
        preview = world.iyer.get("/api/v1/templates/1/preview.pdf")
        assert preview.status_code == 200 and secret.encode() not in preview.content, raw
    assert a_logo.is_file()


def test_an_upload_lands_in_the_uploading_clinics_folder_only(world):
    a_dir, b_dir = clinic_dir(A) / "templates", clinic_dir(B) / "templates"
    before = sorted(p.name for p in a_dir.iterdir())
    r = upload(world.iyer)
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    assert (b_dir / f"{tid}_original.jpg").is_file() and (b_dir / f"{tid}_logo.jpg").is_file()
    assert sorted(p.name for p in a_dir.iterdir()) == before
    stored = sql(B, "SELECT logo_path FROM templates WHERE id = ?", tid)[0]["logo_path"]
    assert Path(stored).resolve().is_relative_to(b_dir.resolve())


def test_the_directory_holds_no_patient_data_and_each_clinic_has_its_own_file(world):
    a_db, b_db = clinic_dir(A) / "app.db", clinic_dir(B) / "app.db"
    assert a_db.is_file() and b_db.is_file() and not os.path.samefile(a_db, b_db)
    with closing(open_directory()) as d:
        tables = {r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert not tables & {"patients", "encounters", "documents", "users", "audit_log", "templates", "clinic_profile"}
    raw = b"".join(p.read_bytes() for p in directory_path().parent.glob("directory.db*"))
    for value in ("Asha Verma", "Bharat Menon", "Paracetamol", "12 MG Road", "demo-rao-pass-1"):
        assert value.encode() not in raw, value
