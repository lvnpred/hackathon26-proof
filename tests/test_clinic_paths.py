"""Per-clinic paths, fail-closed connections, and thread behaviour. Offline."""
import threading

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation import scope as S
from doctor_dictation.pdf import renderer as R
from doctor_dictation.templates import service


def test_single_mode_paths_are_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("MULTI_CLINIC", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "x" / "app.db"))
    assert dbmod.db_path() == tmp_path / "x" / "app.db"
    assert dbmod.pdf_dir() == tmp_path / "x" / "pdfs"
    assert service.templates_dir() == tmp_path / "x" / "templates"
    monkeypatch.delenv("DB_PATH")
    assert dbmod.db_path() == dbmod.DEFAULT_DB_PATH


def test_multi_mode_paths_follow_the_scope(multi):
    for slug in ("rao", "iyer"):
        with S.use_scope(S.Scope(slug)):
            root = multi / "clinics" / slug
            assert dbmod.db_path() == root / "app.db"
            assert dbmod.pdf_dir() == root / "pdfs"
            assert service.templates_dir() == root / "templates"


def test_multi_mode_fails_closed_without_scope(multi, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(multi / "stray.db"))      # must never be used as a fallback
    for call in (dbmod.db_path, dbmod.pdf_dir, service.templates_dir, dbmod.get_conn):
        with pytest.raises(S.NoScope):
            call()
    assert not (multi / "stray.db").exists()
    assert not (multi / "clinics").exists()
    with dbmod.get_conn(multi / "explicit.db") as conn:        # an explicit path is still allowed (tests, tools)
        conn.execute("SELECT 1")


def test_get_conn_in_a_bare_thread_fails_closed(multi):
    seen = []

    def work():
        try:
            dbmod.get_conn()
        except Exception as exc:  # noqa: BLE001 - recording the type is the point
            seen.append(type(exc))

    with S.use_scope(S.Scope("rao")):
        t = threading.Thread(target=work)
        t.start()
        t.join()
    assert seen == [S.NoScope]
    assert not (multi / "clinics").exists()


def test_pdf_worker_thread_has_no_scope(multi):
    seen = []

    def launcher():                       # runs on the pdf-worker thread
        seen.append(S.current_scope())
        raise RuntimeError("stop here")

    renderer = R.ChromiumPoolRenderer(launcher)
    try:
        with S.use_scope(S.Scope("rao")):
            with pytest.raises(RuntimeError):
                renderer.render("<p>x</p>", multi / "x.pdf")
    finally:
        renderer.close()
    assert seen == [None]                 # the worker renders HTML and must never open a database


def test_two_clinics_never_see_each_other(multi):
    for slug, patient in (("rao", "Asha"), ("iyer", "Bharat")):
        with S.use_scope(S.Scope(slug)):
            dbmod.init_db()
            conn = dbmod.get_conn()
            dbmod.create_patient(conn, patient, "30 / F")
            conn.close()
            dbmod.pdf_dir().mkdir(parents=True, exist_ok=True)
            (dbmod.pdf_dir() / "p.pdf").write_bytes(slug.encode())
    for slug, mine, theirs in (("rao", "Asha", "Bharat"), ("iyer", "Bharat", "Asha")):
        with S.use_scope(S.Scope(slug)):
            conn = dbmod.get_conn()
            names = [r["name"] for r in conn.execute("SELECT name FROM patients")]
            conn.close()
            assert names == [mine] and theirs not in names
            assert (dbmod.pdf_dir() / "p.pdf").read_bytes() == slug.encode()
