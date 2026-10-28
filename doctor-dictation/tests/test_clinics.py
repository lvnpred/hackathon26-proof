"""Clinic lifecycle, startup in multi-clinic mode and the no-scope answer. Offline."""
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import clinics
from doctor_dictation import db as dbmod
from doctor_dictation import directory as D
from doctor_dictation import scope as S


def _versions(path):
    with closing(dbmod.get_conn(path)) as conn:
        return [r["version"] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]


def test_provision_clinic_creates_folder_database_and_directory_row(multi):
    clinics.provision_clinic("rao", "Rao Clinic", "RAO")
    assert (multi / "clinics" / "rao" / "app.db").is_file()
    assert _versions(multi / "clinics" / "rao" / "app.db")[0] == "001_init.sql"
    with closing(D.open_directory()) as d:
        row = D.get_clinic(d, "rao")
    assert (row["name"], row["op_prefix"], row["status"]) == ("Rao Clinic", "RAO", "active")


def test_provision_rejects_bad_input_and_duplicates_without_touching_disk(multi):
    for slug, name, prefix in [("../x", "X", "OP"), ("RAO", "X", "OP"), ("rao\n", "X", "OP"), ("rao", "", "OP"), ("rao", "X", "op")]:
        with pytest.raises(D.DirectoryError):
            clinics.provision_clinic(slug, name, prefix)
    assert not (multi / "clinics").exists()
    clinics.provision_clinic("rao", "Rao Clinic")
    marker = multi / "clinics" / "rao" / "marker.txt"
    marker.write_text("keep")
    with pytest.raises(D.DirectoryError, match="already exists"):
        clinics.provision_clinic("rao", "Again")
    assert marker.read_text() == "keep"


def test_for_each_clinic_sets_the_scope_and_skips_disabled_clinics(multi):
    for slug in ("rao", "iyer", "nair"):
        clinics.provision_clinic(slug, slug.title())
    with closing(D.open_directory()) as d:
        d.execute("UPDATE clinics SET status='disabled' WHERE slug='nair'")
        d.commit()
    seen = []
    for slug in clinics.for_each_clinic():
        seen.append((slug, S.require_scope().clinic_slug, dbmod.db_path().parent.name))
    assert seen == [("iyer", "iyer", "iyer"), ("rao", "rao", "rao")]
    assert S.current_scope() is None


def test_migrate_all_continues_after_a_failing_clinic(multi):
    for slug in ("rao", "iyer"):
        clinics.provision_clinic(slug, slug.title())
    (multi / "clinics" / "iyer" / "app.db").write_bytes(b"this is not a database" * 50)
    done, failed = clinics.migrate_all()
    assert done == {"rao": []}                       # already migrated, nothing new to apply
    assert list(failed) == ["iyer"] and failed["iyer"]


def test_app_starts_in_multi_mode_migrates_each_clinic_and_serves_health(multi, monkeypatch):
    from doctor_dictation.api.app import create_app

    default_db = multi / "dflt" / "app.db"
    monkeypatch.setattr(dbmod, "DEFAULT_DB_PATH", default_db)

    clinics.provision_clinic("rao", "Rao Clinic")
    with TestClient(create_app()) as client:
        assert client.get("/api/health").status_code == 200
    assert (multi / "directory.db").is_file()
    assert _versions(multi / "clinics" / "rao" / "app.db")
    assert not default_db.exists()                   # the single-database fallback was not used


def test_route_without_scope_answers_401_and_creates_nothing(multi):
    from doctor_dictation.api.app import create_app

    with TestClient(create_app()) as client:
        res = client.get("/api/v1/profile")
    assert res.status_code == 401
    assert res.json() == {"error": "sign in required"}
    assert list(multi.rglob("app.db")) == []


def test_migrate_all_reports_a_lost_clinic_instead_of_recreating_it(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    clinics.provision_clinic("iyer", "Iyer Clinic")
    (multi / "clinics" / "rao" / "app.db").unlink()
    done, failed = clinics.migrate_all()
    assert "iyer" in done and list(failed) == ["rao"] and "folder missing" in failed["rao"]
    assert not (multi / "clinics" / "rao" / "app.db").exists()
    import shutil
    shutil.rmtree(multi / "clinics" / "iyer")
    _, failed = clinics.migrate_all()
    assert set(failed) == {"rao", "iyer"} and not (multi / "clinics" / "iyer").exists()


def test_migrate_all_puts_a_mirror_failure_only_in_failed(multi, monkeypatch):
    clinics.provision_clinic("rao", "Rao Clinic")

    def boom(slug, prefix):
        raise RuntimeError("mirror broke")
    monkeypatch.setattr(clinics, "_mirror_prefix", boom)
    done, failed = clinics.migrate_all()
    assert "rao" not in done and "mirror broke" in failed["rao"]


def test_migrate_all_does_not_let_the_mirror_create_a_missing_clinic(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    import shutil
    shutil.rmtree(multi / "clinics" / "rao")
    done, failed = clinics.migrate_all()
    assert done == {} and list(failed) == ["rao"]
    assert not (multi / "clinics" / "rao").exists()
