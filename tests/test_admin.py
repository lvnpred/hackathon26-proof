"""Operator command: create, list, migrate, adopt. Offline; calls main() directly."""
import os
import re
import shutil
from contextlib import closing
from pathlib import Path

import pytest

from doctor_dictation import accounts, admin, authn, sessions
from doctor_dictation import clinics
from doctor_dictation import db as dbmod
from doctor_dictation import directory as D
from doctor_dictation import scope as S


def test_create_and_list_clinics(multi, capsys):
    assert admin.main(["create-clinic", "--slug", "rao", "--name", "Rao Clinic", "--op-prefix", "RAO"]) == 0
    assert admin.main(["create-clinic", "--slug", "iyer", "--name", "Iyer Clinic"]) == 0
    assert (multi / "clinics" / "rao" / "app.db").is_file()
    capsys.readouterr()
    assert admin.main(["list-clinics"]) == 0
    out = capsys.readouterr().out
    assert "rao" in out and "Rao Clinic" in out and "RAO" in out and "iyer" in out and "active" in out


def test_create_clinic_reports_bad_input_and_duplicates_on_stderr(multi, capsys):
    assert admin.main(["create-clinic", "--slug", "../x", "--name", "X"]) == 1
    assert "error:" in capsys.readouterr().err
    assert admin.main(["create-clinic", "--slug", "rao", "--name", "Rao"]) == 0
    assert admin.main(["create-clinic", "--slug", "rao", "--name", "Again"]) == 1
    assert "already exists" in capsys.readouterr().err
    assert not (multi / "x").exists()                      # the "../x" slug never became a path


def test_migrate_all_exits_nonzero_when_a_clinic_fails(multi, capsys):
    clinics.provision_clinic("rao", "Rao Clinic")
    clinics.provision_clinic("iyer", "Iyer Clinic")
    assert admin.main(["migrate-all"]) == 0
    (multi / "clinics" / "iyer" / "app.db").write_bytes(b"garbage" * 100)
    capsys.readouterr()
    assert admin.main(["migrate-all"]) == 1
    out = capsys.readouterr()
    assert "rao" in out.out and "iyer" in out.err


def _old_install(tmp_path, monkeypatch):
    """A single-database install: app.db with a patient and profile, plus pdfs/ and templates/."""
    old = tmp_path / "old"
    monkeypatch.setenv("DB_PATH", str(old / "app.db"))
    dbmod.init_db()
    conn = dbmod.get_conn()
    dbmod.create_patient(conn, "Asha", "30 / F")
    dbmod.save_profile(conn, clinic_name="Rao Clinic", doctor_name="Dr A. Rao")
    (old / "pdfs").mkdir()
    (old / "pdfs" / "encounter_1.pdf").write_bytes(b"%PDF-old")
    (old / "templates").mkdir()
    (old / "templates" / "1_logo.jpg").write_bytes(b"jpg")
    eid = dbmod.create_encounter(conn, 1)
    conn.execute(
        "INSERT INTO documents(encounter_id, transcript_sha, created_at, pdf_path) VALUES (?, 'x', 't', ?)",
        (eid, str(old / "pdfs" / "encounter_1.pdf")),
    )
    conn.execute(
        "INSERT INTO templates(layout_json, logo_path, created_at) VALUES ('{}', ?, 't')",
        (str(old / "templates" / "1_logo.jpg"),),
    )
    conn.commit()
    return old, conn


def test_adopt_existing_moves_everything_even_with_the_old_db_open(tmp_path, monkeypatch):
    old, live = _old_install(tmp_path, monkeypatch)        # `live` stays open: its writes may still sit in the WAL
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    try:
        assert admin.main(["adopt-existing", "--slug", "rao"]) == 0
    finally:
        live.close()
    target = tmp_path / "data" / "clinics" / "rao"
    assert not (old / "app.db").exists() and not (old / "pdfs").exists() and not (old / "templates").exists()
    assert (target / "pdfs" / "encounter_1.pdf").read_bytes() == b"%PDF-old"
    assert (target / "templates" / "1_logo.jpg").exists()
    monkeypatch.setenv("MULTI_CLINIC", "1")
    monkeypatch.delenv("DB_PATH")
    with S.use_scope(S.Scope("rao")):
        with closing(dbmod.get_conn()) as conn:
            assert [r["name"] for r in conn.execute("SELECT name FROM patients")] == ["Asha"]
            pdf = Path(conn.execute("SELECT pdf_path FROM documents").fetchone()[0])
            logo = Path(conn.execute("SELECT logo_path FROM templates").fetchone()[0])
    assert pdf == target / "pdfs" / "encounter_1.pdf" and pdf.read_bytes() == b"%PDF-old"
    assert logo == target / "templates" / "1_logo.jpg" and logo.is_file()
    with closing(D.open_directory()) as d:
        assert D.get_clinic(d, "rao")["name"] == "Rao Clinic"      # taken from the saved profile


def test_adopt_existing_refuses_a_missing_source_a_taken_slug_and_an_existing_folder(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "none" / "app.db"))
    assert admin.main(["adopt-existing", "--slug", "rao"]) == 1
    assert "no database" in capsys.readouterr().err
    old, live = _old_install(tmp_path, monkeypatch)
    live.close()
    clinics.provision_clinic("rao", "Taken")
    assert admin.main(["adopt-existing", "--slug", "rao"]) == 1
    assert "already exists" in capsys.readouterr().err
    (tmp_path / "data" / "clinics" / "nair").mkdir(parents=True)
    assert admin.main(["adopt-existing", "--slug", "nair"]) == 1
    assert (old / "app.db").exists()                       # nothing was moved by any refusal


def test_adopt_existing_refuses_a_busy_database(tmp_path, monkeypatch, capsys):
    old, live = _old_install(tmp_path, monkeypatch)
    live.commit()
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    reader = dbmod.get_conn()
    reader.execute("BEGIN")
    reader.execute("SELECT * FROM patients").fetchall()    # an open read transaction pins the WAL
    dbmod.create_patient(live, "Late", "1 / M")
    live.commit()                                          # new frames in the WAL the reader cannot let go of
    try:
        assert admin.main(["adopt-existing", "--slug", "rao"]) == 1
    finally:
        reader.close()
        live.close()
    assert "in use" in capsys.readouterr().err
    assert (old / "app.db").exists() and (old / "pdfs").exists()
    assert not (tmp_path / "data" / "clinics" / "rao").exists()


def test_adopt_existing_whitespace_profile_name_falls_back_to_the_slug(tmp_path, monkeypatch):
    old, live = _old_install(tmp_path, monkeypatch)
    live.execute("UPDATE clinic_profile SET clinic_name = '   ' WHERE id = 1")
    live.commit()
    live.close()
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    assert admin.main(["adopt-existing", "--slug", "rao"]) == 0
    with closing(D.open_directory()) as d:
        assert D.get_clinic(d, "rao")["name"] == "rao"


def test_adopt_existing_bad_final_name_leaves_the_install_untouched(tmp_path, monkeypatch, capsys):
    old, live = _old_install(tmp_path, monkeypatch)
    live.close()
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    assert admin.main(["adopt-existing", "--slug", "rao", "--name", "   "]) == 1
    assert "error:" in capsys.readouterr().err
    assert (old / "app.db").exists() and (old / "pdfs").exists() and (old / "templates").exists()
    assert not (tmp_path / "data" / "clinics" / "rao").exists()


def test_adopt_existing_refuses_when_a_writer_leaves_wal_data_after_the_checkpoint(tmp_path, monkeypatch, capsys):
    old, live = _old_install(tmp_path, monkeypatch)
    live.close()
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))

    def late_writer(src_db):
        (old / "app.db-wal").write_bytes(b"frames")        # a writer got in after the checkpoint
        return "Rao Clinic"

    monkeypatch.setattr(admin, "_prepare_source", late_writer)
    assert admin.main(["adopt-existing", "--slug", "rao"]) == 1
    assert "in use" in capsys.readouterr().err
    assert (old / "app.db").exists() and (old / "pdfs").exists()
    assert not (tmp_path / "data" / "clinics" / "rao").exists()


def test_admin_main_reads_dotenv_for_data_dir(tmp_path, monkeypatch):
    data = tmp_path / "from_env"
    work = tmp_path / "cwd"
    work.mkdir()
    (work / ".env").write_text(f"DATA_DIR={data}\n")
    monkeypatch.chdir(work)
    monkeypatch.delenv("DATA_DIR", raising=False)
    try:
        assert admin.main(["list-clinics"]) == 0
        assert (data / "directory.db").is_file()
    finally:
        os.environ.pop("DATA_DIR", None)                   # load_dotenv set it outside monkeypatch


def test_adopt_existing_reports_recovery_when_a_later_move_fails(tmp_path, monkeypatch, capsys):
    old, live = _old_install(tmp_path, monkeypatch)
    live.close()
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    real, calls = shutil.move, []

    def flaky(src, dst):
        calls.append(src)
        if len(calls) == 2:
            raise OSError("disk full")
        return real(src, dst)

    monkeypatch.setattr(shutil, "move", flaky)
    assert admin.main(["adopt-existing", "--slug", "rao"]) == 1
    err = capsys.readouterr().err
    assert "already moved" in err and "create-clinic --slug rao" in err


def test_create_clinic_with_first_user_prints_the_password_once(multi, capsys):
    assert admin.main(["create-clinic", "--slug", "rao", "--name", "Rao Clinic", "--first-user", "dr.rao",
                       "--display-name", "Dr. Rao"]) == 0
    out = capsys.readouterr().out
    m = re.search(r"temporary password: (\S+)", out)
    assert m and len(m.group(1)) == 16
    assert out.count(m.group(1)) == 1
    assert "no users yet" not in out
    assert authn.authenticate("dr.rao", m.group(1), "1.1.1.1") is not None


def test_create_clinic_first_user_bad_username_leaves_no_clinic(multi, capsys):
    assert admin.main(["create-clinic", "--slug", "rao", "--name", "Rao", "--first-user", "x"]) == 1
    assert "username" in capsys.readouterr().err
    assert not (multi / "clinics" / "rao").exists()


def test_create_clinic_first_user_taken_username_leaves_no_clinic(multi, capsys):
    admin.main(["create-clinic", "--slug", "rao", "--name", "Rao", "--first-user", "dr.rao"])
    assert admin.main(["create-clinic", "--slug", "iyer", "--name", "Iyer", "--first-user", "DR.RAO"]) == 1
    assert not (multi / "clinics" / "iyer").exists()


def test_create_user_adds_a_second_user_and_audits(multi, capsys):
    admin.main(["create-clinic", "--slug", "rao", "--name", "Rao"])
    assert admin.main(["create-user", "--clinic", "rao", "--username", "dr.mehta", "--display-name", "Dr. Mehta"]) == 0
    assert "temporary password:" in capsys.readouterr().out
    with closing(dbmod.get_conn(S.clinic_dir("rao") / "app.db")) as c:
        assert [r["action"] for r in c.execute("SELECT action FROM audit_log")] == ["user_create"]


def test_create_user_unknown_clinic_and_bad_role_fail_cleanly(multi, capsys):
    assert admin.main(["create-user", "--clinic", "nope", "--username", "dr.x"]) == 1
    admin.main(["create-clinic", "--slug", "rao", "--name", "Rao"])
    with pytest.raises(SystemExit) as e:                       # argparse choices exits with 2; main never returns it
        admin.main(["create-user", "--clinic", "rao", "--username", "dr.x", "--role", "wizard"])
    assert e.value.code == 2


def test_reset_password_ends_the_old_session_and_prints_a_new_password(multi, capsys):
    admin.main(["create-clinic", "--slug", "rao", "--name", "Rao", "--first-user", "dr.rao"])
    pw = re.search(r"temporary password: (\S+)", capsys.readouterr().out).group(1)
    ident = authn.authenticate("dr.rao", pw, "1.1.1.1")
    token = sessions.sign(ident.clinic_slug, ident.user_id, ident.session_version)
    assert admin.main(["reset-password", "--user", "dr.rao"]) == 0
    new = re.search(r"temporary password: (\S+)", capsys.readouterr().out).group(1)
    assert new != pw and authn.load_identity(token) is None
    assert authn.authenticate("dr.rao", new, "1.1.1.1") is not None


def test_reset_password_unknown_user_is_an_error(multi, capsys):
    assert admin.main(["reset-password", "--user", "ghost"]) == 1
    assert "error:" in capsys.readouterr().err


def test_adopt_first_user_copies_the_doctor_fields_from_the_saved_profile(tmp_path, monkeypatch, capsys):
    old, live = _old_install(tmp_path, monkeypatch)
    dbmod.save_profile(live, clinic_name="Rao Clinic", doctor_name="Dr A. Rao", qualifications="MBBS, MD", reg_no="KMC 123")
    live.commit()
    live.close()
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    assert admin.main(["adopt-existing", "--slug", "rao", "--first-user", "dr.old"]) == 0
    assert re.search(r"temporary password: (\S+)", capsys.readouterr().out)
    with closing(dbmod.get_conn(S.clinic_dir("rao") / "app.db")) as c:
        u = c.execute("SELECT doctor_name, qualifications, reg_no FROM users WHERE username = 'dr.old'").fetchone()
        p = c.execute("SELECT doctor_name, qualifications, reg_no FROM clinic_profile WHERE id = 1").fetchone()
    assert tuple(u) == ("Dr A. Rao", "MBBS, MD", "KMC 123")
    assert tuple(p) == tuple(u)


def test_adopt_first_user_rejects_a_taken_username_before_moving_anything(tmp_path, monkeypatch, capsys):
    old, live = _old_install(tmp_path, monkeypatch)
    live.close()
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    clinics.provision_clinic("alpha", "Clinic A")
    accounts.create_user("alpha", "dr.old")
    assert admin.main(["adopt-existing", "--slug", "rao", "--first-user", "dr.old"]) == 1
    assert "taken" in capsys.readouterr().err
    assert (old / "app.db").exists() and (old / "pdfs").exists() and (old / "templates").exists()
    assert not (tmp_path / "data" / "clinics" / "rao").exists()


def test_admin_never_logs_the_password_to_the_audit_log(multi, capsys):
    admin.main(["create-clinic", "--slug", "rao", "--name", "Rao", "--first-user", "dr.rao"])
    pw = re.search(r"temporary password: (\S+)", capsys.readouterr().out).group(1)
    with closing(dbmod.get_conn(S.clinic_dir("rao") / "app.db")) as c:
        assert pw not in " ".join(str(tuple(r)) for r in c.execute("SELECT * FROM audit_log"))


def test_adopt_first_user_database_error_reports_recovery(tmp_path, monkeypatch, capsys):
    import sqlite3
    old, live = _old_install(tmp_path, monkeypatch)
    live.close()
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(accounts, "create_user", boom)
    assert admin.main(["adopt-existing", "--slug", "rao", "--first-user", "dr.old"]) == 1
    err = capsys.readouterr().err
    assert "the clinic was adopted but its first user was not created" in err and "create-user" in err
