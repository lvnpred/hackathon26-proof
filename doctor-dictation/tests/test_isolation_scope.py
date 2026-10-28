"""Fail-closed scope (spec 5.3, 13.1): with no scope every clinic path helper raises NoScope, in a bare thread and
in a fresh pool thread; a signed-in request only ever opens its own clinic's file; the PDF worker thread never
opens a database. Offline. "No scope inside a request answers 401" is pinned by tests/test_startup.py:77."""
import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation import scope as S
from doctor_dictation.directory import directory_path
from doctor_dictation.templates import service
from isolation_fixtures import A, B, hint_lookup, opened_files, save, world  # noqa: F401

HELPERS = {
    "db_path": dbmod.db_path,
    "pdf_dir": dbmod.pdf_dir,
    "templates_dir": service.templates_dir,
    "original_path": lambda: service.original_path(1),
    "get_conn": lambda: dbmod.get_conn(),
    "doctor_hints": hint_lookup,
}


def _error_type(fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - the type is the point
        return type(exc)
    return None


@pytest.mark.parametrize("name", sorted(HELPERS))
def test_every_clinic_path_helper_fails_closed_in_a_bare_thread(multi, name):
    seen = []
    with S.use_scope(S.Scope("rao")):
        t = threading.Thread(target=lambda: seen.append(_error_type(HELPERS[name])))
        t.start()
        t.join()
    assert seen == [S.NoScope]
    assert not (multi / "clinics").exists()


def test_a_thread_pool_started_inside_a_scope_starts_empty_but_to_thread_keeps_it(multi):
    with S.use_scope(S.Scope("rao")):
        with ThreadPoolExecutor(2) as pool:
            errors = {name: pool.submit(_error_type, fn).result() for name, fn in HELPERS.items()}
        kept = asyncio.run(asyncio.to_thread(dbmod.db_path))
    assert errors == dict.fromkeys(HELPERS, S.NoScope)
    assert kept == S.clinic_dir("rao") / "app.db"
    assert not (multi / "clinics").exists()


def test_to_thread_keeps_the_scope_for_every_clinic_path_helper(world):
    """The other half of the pool test: a request hands work to ``asyncio.to_thread``; every helper still resolves
    the caller's clinic there (it may do its work, it must not raise NoScope)."""
    async def run_all():
        return {name: await asyncio.to_thread(_error_type, fn) for name, fn in HELPERS.items()}

    with S.use_scope(S.Scope("rao", world.seeded["rao"]["users"]["dr.rao"], "dr.rao", "doctor")):
        errors = asyncio.run(run_all())
    assert S.NoScope not in errors.values(), errors


def test_the_pdf_worker_thread_never_opens_a_database(world, monkeypatch):
    renders_before = len(world.renders)
    with opened_files(monkeypatch) as seen:
        save(world.rao, "Worker Probe")
        assert world.iyer.get("/api/v1/documents/2/pdf").status_code == 200
        assert world.iyer.get("/api/v1/templates/1/preview.pdf").status_code == 200
    assert len(world.renders) > renders_before         # the window really printed: an empty spy proves nothing
    threads = {r["thread"] for r in world.renders[renders_before:]}
    assert threads and all(t.startswith("pdf-worker") for t in threads)
    assert [s for s in seen if s[0].startswith("pdf-worker")] == []


def test_every_database_a_request_opens_belongs_to_the_signed_in_clinic(world, monkeypatch):
    shared = str(directory_path())
    for who, mine in (("rao", A), ("iyer", B)):
        client = getattr(world, who)
        with opened_files(monkeypatch) as seen:
            save(client, "Scope Probe")
            for url in ("/api/v1/encounters/today", "/api/v1/profile", "/api/v1/patients",
                        "/api/v1/documents/1/pdf", "/api/v1/templates/active"):
                assert client.get(url).status_code == 200, url
        own = str(S.clinic_dir(mine)) + os.sep
        stray = [p for _thread, p in seen if p != shared and not p.startswith(own)]
        assert seen and stray == [], (who, stray)
