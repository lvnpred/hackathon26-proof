"""Startup: secret check, failed clinics recorded and never recreated, dev-flag warning. Offline."""
import shutil

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import clinics
from doctor_dictation.api.app import create_app
from doctor_dictation.scope import clinic_dir
from doctor_dictation.sessions import SecretError


def test_multi_mode_refuses_to_start_without_a_real_secret(multi, monkeypatch):
    monkeypatch.delenv("SESSION_SECRET")
    with pytest.raises(SecretError):
        with TestClient(create_app()):
            pass


def test_single_mode_does_not_need_a_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("MULTI_CLINIC", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with TestClient(create_app()) as c:
        assert c.get("/api/health").status_code == 200


def test_dev_flag_warns_and_starts(multi, monkeypatch, capsys):
    monkeypatch.delenv("SESSION_SECRET")
    monkeypatch.setenv("DEV_INSECURE_SESSION_SECRET", "1")
    with TestClient(create_app()):
        pass
    assert "DEV_INSECURE_SESSION_SECRET" in capsys.readouterr().err


def test_failed_clinic_is_recorded_and_other_clinics_still_serve(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    clinics.provision_clinic("iyer", "Iyer Clinic")
    shutil.rmtree(clinic_dir("rao"))
    app = create_app()
    with TestClient(app) as c:
        assert app.state.failed_clinics == frozenset({"rao"})
        assert c.get("/api/health").status_code == 200


def test_failed_clinic_is_not_recreated_by_the_startup_purge(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    shutil.rmtree(clinic_dir("rao"))
    with TestClient(create_app()):
        pass
    assert not (clinic_dir("rao") / "app.db").exists()


def test_transcribe_without_a_scope_is_401_not_an_unpersonalised_success(multi, monkeypatch):
    from doctor_dictation.api import stt
    from doctor_dictation.scope import NoScope
    with pytest.raises(NoScope):
        stt._doctor_top(10)


def test_multi_mode_refuses_an_old_sqlite(multi, monkeypatch):
    import sqlite3
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 34, 1))
    with pytest.raises(RuntimeError, match=r"3\.34\.1.*RETURNING|RETURNING.*3\.34\.1"):
        with TestClient(create_app()):
            pass


def test_single_mode_still_boots_on_an_old_sqlite(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 34, 1))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    with TestClient(create_app()) as c:
        assert c.get("/api/health").status_code == 200


def test_a_route_reaching_get_conn_with_no_scope_is_401_through_the_app(multi, monkeypatch):
    from doctor_dictation import db as dbmod
    from doctor_dictation.api import session as session_mod
    monkeypatch.setattr(session_mod, "PUBLIC_PATHS", session_mod.PUBLIC_PATHS | {"/api/v1/_noscope_probe"})
    app = create_app()

    @app.get("/api/v1/_noscope_probe")
    def probe():
        dbmod.get_conn()
        return {"ok": True}

    app.router.routes.insert(0, app.router.routes.pop())      # ahead of the "/" static mount
    with TestClient(app) as c:
        r = c.get("/api/v1/_noscope_probe")
    assert (r.status_code, r.json()) == (401, {"error": "sign in required"})
