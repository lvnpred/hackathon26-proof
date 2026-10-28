"""Learning on save, the /api/format cache, the admin routes and the per-request clinic layer (plan I1-h3). Offline.

Stub LLM, fake PDF renderer, recorder STT, DB_PATH in a temp folder (the repo conftest also forces that).
"""
import contextvars
import json
import logging
import os
import re
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from authorship_fixtures import H, as_user, clinic_conn
from doctor_dictation import accounts, clinics
from doctor_dictation import db as dbmod
from doctor_dictation.api import formulary as route_mod
from doctor_dictation.api import stt as stt_mod
from doctor_dictation.api.app import create_app
from doctor_dictation.config import override_settings
from doctor_dictation.core import determinism as D
from doctor_dictation.core import formulary as F
from doctor_dictation.core.hints import build_hints
from doctor_dictation.db import formulary as fdb
from doctor_dictation.providers.stt.base import Transcript

TRANSCRIPT = "tablet Zorbexin 10 mg once daily for 5 days"
ROW = {"form": "Tab.", "name": "Zorbexin", "strength": "10 mg", "dose": "1-0-0", "timing": "", "duration": "5 days",
       "instructions": "", "status": "unknown-medicine"}
PAGE_ROW = {**ROW, "status": "verified", "lexicon_match": "", "heard": "", "lookalike": ""}   # what the page sends back
ADD = "INSERT INTO clinic_formulary(name_key, name, confirm_count, first_seen_at, last_seen_at) VALUES (?, ?, 2, ?, ?)"


def _offline(monkeypatch):
    def fake(structured, meta, out_path, layout=None):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps({"rx": [ROW]}))
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True)
    D._FORMAT_CACHE.clear()


def save(client, patient, confirmed=(0,), document_id=None, row=ROW, headers=H):
    body = {"structured": {"patientName": patient, "ageSex": "40 / M", "opNo": "", "rx": [dict(row)]},
            "confirmed_rows": list(confirmed), "document_id": document_id}
    return client.post("/api/v1/documents", json=body, headers=headers)


def seed(conn, *names):
    for n in names:
        conn.execute(ADD, (F.key(n), n, "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z"))
    conn.commit()


def entries(conn):
    return conn.execute("SELECT name, confirm_count, added_by FROM clinic_formulary ORDER BY id").fetchall()


@pytest.fixture()
def single(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "f.db"))
    _offline(monkeypatch)
    with TestClient(create_app()) as client:
        yield client


@pytest.fixture()
def fresh_context():
    """The test thread's own ContextVars leak into TestClient requests; run in an empty context instead."""
    ctx = contextvars.Context()
    yield ctx.run


def test_two_saved_prescriptions_teach_a_name_and_the_format_cache_notices(single):
    ask = lambda: single.post("/api/format", json={"transcript": TRANSCRIPT}).json()    # noqa: E731
    row = ask()["structured"]["rx"][0]
    assert (row["status"], row["source"]) == ("unknown-medicine", "lexicon") and ask()["cached"] is True
    assert save(single, "Anita", confirmed=()).status_code == 409                       # unconfirmed: blocked, nothing learned
    first = save(single, "Anita").json()
    assert save(single, "Anita", document_id=first["document_id"]).status_code == 200   # a re-save is not a second document
    assert single.get("/api/v1/formulary").json() == {"items": []}
    assert ask()["cached"] is True and ask()["structured"]["rx"][0]["status"] == "unknown-medicine"
    assert save(single, "Bala").status_code == 200
    (item,) = single.get("/api/v1/formulary").json()["items"]
    assert (item["name"], item["confirm_count"]) == ("Zorbexin", 2)
    after = ask()                                                                        # the cached sheet would still say unknown
    assert after["cached"] is False
    assert (after["structured"]["rx"][0]["status"], after["structured"]["rx"][0]["source"]) == ("verified", "clinic")
    assert ask()["cached"] is True
    assert single.delete(f"/api/v1/formulary/{item['id']}", headers=H).status_code == 200      # single mode: no roles
    assert ask()["structured"]["rx"][0]["status"] == "unknown-medicine" and ask()["cached"] is True


def test_the_cache_key_carries_the_layer_version(single):
    ask = lambda: single.post("/api/format", json={"transcript": TRANSCRIPT}).json()    # noqa: E731
    assert ask()["cached"] is False and ask()["cached"] is True
    with closing(dbmod.get_conn()) as conn:
        seed(conn, "Zorbexin")                                                           # a name appears with no save at all
    got = ask()
    assert got["cached"] is False and got["structured"]["rx"][0]["source"] == "clinic"
    keys = list(D._FORMAT_CACHE)
    assert len(keys) == 2 and len({k.split(":")[1] for k in keys}) == 2                 # clinic:VERSION:key:rawhash


def test_unconfirmed_text_is_never_learned(single):
    forged = {**ROW, "status": "verified"}                       # a client can claim any status; only confirmed_rows count
    for who in ("Anita", "Bala", "Chitra"):
        assert save(single, who, confirmed=(), row=forged).status_code == 200
        assert save(single, who, confirmed=(7,), row=forged).status_code == 200      # an index that is not the row
    with closing(dbmod.get_conn()) as conn:
        assert entries(conn) == []


def test_a_patient_name_typed_into_a_medicine_cell_is_not_learned_but_a_drug_is(single):
    """known_patient_words: Chandrika is a patient of this clinic (another document); Dhanvika is not."""
    assert save(single, "Chandrika", confirmed=(), row={**ROW, "name": "Paracetamol", "status": "verified"}).status_code == 200
    for who in ("Anita", "Bala"):
        for name in ("Chandrika", "Dhanvika"):
            assert save(single, who, row={**ROW, "name": name}).status_code == 200
    with closing(dbmod.get_conn()) as conn:
        assert [(r["name"], r["confirm_count"]) for r in entries(conn)] == [("Dhanvika", 2)]


def test_patient_words_are_read_from_the_clinics_patients_table(single):
    with closing(dbmod.get_conn()) as conn:
        dbmod.create_patient(conn, "Chandrika Devi-Rao", "30 / F", None)
        dbmod.create_patient(conn, "Al B", "30 / F", None)                       # words under 3 letters are ignored
        assert fdb.patient_words(conn) == frozenset({"chandrika", "devi-rao"})


# ---- the layer reaches every route that grounds rows or builds hints ------------------------------------------------

LAYER_ROUTES = [("POST", "/api/format"), ("POST", "/api/v1/correct"), ("POST", "/api/v1/documents"),
                ("POST", "/api/v1/rx/check-row"), ("POST", "/api/transcribe"), ("POST", "/api/v1/spoken/usual")]


def _api_routes(routes):
    """Every APIRoute, also inside included routers (FastAPI keeps those as lazy wrappers with an original_router)."""
    for r in routes:
        if hasattr(r, "original_router"):
            yield from _api_routes(r.original_router.routes)
        elif hasattr(r, "dependant"):
            yield r


def _carries(route):
    return route_mod.use_clinic_layer in [d.call for d in route.dependant.dependencies]


def test_every_route_that_grounds_rows_or_builds_hints_carries_the_layer_dependency():
    routes = {(m, r.path): r for r in _api_routes(create_app().routes) for m in r.methods}
    missing = [f"{m} {p}" for m, p in LAYER_ROUTES if (m, p) not in routes or not _carries(routes[(m, p)])]
    assert not missing, f"these routes ground rows or build hints without use_clinic_layer: {missing}"
    extra = sorted(f"{m} {p}" for (m, p), r in routes.items() if _carries(r) and (m, p) not in LAYER_ROUTES)
    assert not extra, f"classify in LAYER_ROUTES: {extra}"


def test_only_known_api_modules_call_the_grounding_functions():
    """A new route module that grounds rows must be reviewed (and added to LAYER_ROUTES) before this passes."""
    api = Path(__file__).resolve().parents[1] / "doctor_dictation" / "api"
    names = re.compile(r"\b(validate_structured|ground_rx|ground_one|build_hints|preserve_untouched_rx_status|ground_with_notes)\b")
    using = {p.name for p in api.glob("*.py") if names.search(p.read_text(encoding="utf-8"))}
    assert using == {"format.py", "persistence.py", "rx.py", "stt.py"}, using
    for name, count in {"format.py": 2, "persistence.py": 1, "rx.py": 1, "stt.py": 1}.items():
        text = (api / name).read_text(encoding="utf-8")
        assert text.count("dependencies=[Depends(use_clinic_layer)]") == count, name


@pytest.fixture()
def seeded(single, tmp_path, monkeypatch):
    with closing(dbmod.get_conn()) as conn:
        seed(conn, "Zorbexin")
    rec = []

    class Recorder:
        name = "recorder"
        available = staticmethod(lambda: True)

        async def transcribe(self, audio, filename, hints=()):
            rec.append(list(hints))
            return Transcript(text="hello", engine="recorder")
    monkeypatch.setattr(stt_mod, "make_stt", lambda settings: Recorder())
    override_settings(monkeypatch, stt_use_hints=True, stt_hint_limit=8)
    return single, rec


def test_format_grounds_a_clinic_name_with_the_clinic_layer(seeded):
    got = seeded[0].post("/api/format", json={"transcript": TRANSCRIPT}).json()["structured"]["rx"][0]
    assert (got["status"], got["source"]) == ("verified", "clinic")


def test_correct_keeps_a_clinic_row_verified_and_marks_its_source(seeded):
    body = {"transcript": "", "current_form": {"patientName": "A", "rx": [dict(PAGE_ROW)]}}
    got = seeded[0].post("/api/v1/correct", json=body).json()["structured"]["rx"][0]
    assert (got["status"], got["source"]) == ("verified", "clinic")


def test_save_recomputes_source_from_the_layer(seeded):
    client = seeded[0]
    r = save(client, "Anita", confirmed=(), row=PAGE_ROW)
    assert r.status_code == 200
    stored = client.get(f"/api/v1/documents/{r.json()['document_id']}").json()["structured"]["rx"][0]
    assert (stored["status"], stored["source"]) == ("verified", "clinic")


def test_check_row_grounds_a_clinic_name_with_the_clinic_layer(seeded):
    got = seeded[0].post("/api/v1/rx/check-row", json={"row": dict(ROW), "transcript": TRANSCRIPT}).json()["row"]
    assert (got["status"], got["source"]) == ("verified", "clinic")


def test_transcribe_offers_the_clinic_names_to_the_speech_engine(seeded):
    client, rec = seeded
    assert client.post("/api/transcribe", files={"audio": ("n.webm", b"RAW", "audio/webm")}).status_code == 200
    assert rec[0][0] == "Zorbexin"


def test_a_bare_thread_does_not_see_the_layer_so_grounding_must_stay_on_the_request_context(fresh_context):
    def body():
        F.activate(F.ClinicLayer((("Zorbexin", ""),)))
        seen = {}
        t = threading.Thread(target=lambda: seen.update(thread=F.active_layer().get("Zorbexin")))
        t.start()
        t.join()
        with ThreadPoolExecutor(1) as pool:
            seen["pool"] = pool.submit(lambda: F.active_layer().get("Zorbexin")).result()
        seen["copied"] = contextvars.copy_context().run(lambda: F.active_layer().get("Zorbexin"))   # to_thread, anyio
        seen["own"] = F.active_layer().get("Zorbexin")
        return seen
    seen = fresh_context(body)                                   # own context: the layer must not leak into later tests
    assert (seen["thread"], seen["pool"]) == (None, None)
    assert seen["copied"] is not None and seen["own"] is not None


def test_a_synchronous_handler_sees_the_layer_set_by_the_async_dependency(seeded, monkeypatch):
    """POST /documents is a plain def handler (anyio threadpool): the value must survive the hop."""
    import doctor_dictation.api.persistence as P
    seen, real = [], P.preserve_untouched_rx_status

    def spy(*a, **k):
        seen.append(F.active_layer().get("Zorbexin"))
        return real(*a, **k)
    monkeypatch.setattr(P, "preserve_untouched_rx_status", spy)
    assert save(seeded[0], "Anita", confirmed=(), row=PAGE_ROW).status_code == 200
    assert seen and seen[0] is not None


# ---- fail loud ------------------------------------------------------------------------------------------------------

def _probe_app():
    """The real app plus a route that grounds rows but forgot the dependency (the failure the warning catches)."""
    app, extra = create_app(), APIRouter()               # an included router, like every real one

    @extra.post("/api/v1/probe-unwired")
    def probe():
        return {"status": D.validate_structured({"rx": [dict(ROW)]}, TRANSCRIPT)[0]["rx"][0]["status"],
                "layer": F.active_layer().version}
    app.include_router(extra)
    app.router.routes.insert(0, app.router.routes.pop())          # before the static mount
    return app


def test_a_request_that_reads_the_default_empty_layer_warns_once_per_process(single, fresh_context, caplog, monkeypatch):
    monkeypatch.setattr(F, "_warned", False)
    with TestClient(_probe_app()) as client, caplog.at_level(logging.WARNING, logger=F.__name__):
        for _ in range(3):
            assert fresh_context(client.post, "/api/v1/probe-unwired", headers=H).json()["layer"] == "0"
    hits = [r for r in caplog.records if "use_clinic_layer" in r.getMessage()]
    assert len(hits) == 1, [r.getMessage() for r in caplog.records]


def test_wired_routes_and_non_request_callers_never_warn(single, fresh_context, caplog, monkeypatch):
    monkeypatch.setattr(F, "_warned", False)
    with caplog.at_level(logging.WARNING, logger=F.__name__):
        for path, body in (("/api/format", {"transcript": TRANSCRIPT}),
                           ("/api/v1/rx/check-row", {"row": dict(ROW), "transcript": TRANSCRIPT})):
            assert fresh_context(single.post, path, json=body).status_code == 200
        fresh_context(build_hints)                                  # a CLI or bench caller: no request, no layer, no warning
    assert not [r for r in caplog.records if "use_clinic_layer" in r.getMessage()]


def test_a_database_failure_while_loading_the_layer_still_answers_and_logs(single, monkeypatch, caplog):
    def boom(conn):
        raise sqlite3.OperationalError("disk I/O error")
    monkeypatch.setattr(fdb, "list_active", boom)
    with caplog.at_level(logging.WARNING, logger=route_mod.__name__):
        r = single.post("/api/v1/rx/check-row", json={"row": dict(ROW), "transcript": TRANSCRIPT})
    assert r.status_code == 200 and r.json()["row"]["source"] == "lexicon"
    assert any("formulary unavailable" in x.getMessage() for x in caplog.records)


def test_the_formulary_routes_answer_503_when_the_database_fails(single, monkeypatch):
    def boom(*a):
        raise sqlite3.OperationalError("database is locked")
    db_path, key = os.environ["DB_PATH"], os.environ["OPENAI_API_KEY"]
    with monkeypatch.context() as m:                 # NOT monkeypatch.undo(): that would also revert DB_PATH and the blank keys
        m.setattr(fdb, "list_active", boom)
        r = single.get("/api/v1/formulary")
        assert (r.status_code, r.json()) == (503, {"error": "try again"})
    monkeypatch.setattr(fdb, "remove", boom)
    r = single.delete("/api/v1/formulary/1", headers=H)
    assert (r.status_code, r.json()) == (503, {"error": "try again"})
    # the isolation the suite relies on is still in force: the temp database and the blank provider key
    assert os.environ["DB_PATH"] == db_path and "doctor_dictation" not in db_path and os.environ["OPENAI_API_KEY"] == key == ""


# ---- several clinics and roles ----------------------------------------------------------------------------------------

@pytest.fixture()
def team(multi, monkeypatch):
    _offline(monkeypatch)
    clinics.provision_clinic("rao", "Rao Clinic")
    clinics.provision_clinic("iyer", "Iyer Clinic")
    ids = {}
    for slug, user, role in (("rao", "adm.rao", "admin"), ("rao", "dr.rao", "doctor"), ("rao", "dr.rao2", "doctor"),
                             ("iyer", "adm.iyer", "admin")):
        ids[user], _ = accounts.create_user(slug, user, role=role, password="a-long-password-1")
        with clinic_conn(slug) as c:
            c.execute("UPDATE users SET must_change_password = 0 WHERE id = ?", (ids[user],))
            c.commit()
    with clinic_conn("rao") as c:
        seed(c, "Zorbexin")
    app = create_app()
    with TestClient(app) as anon:
        yield {"app": app, "anon": anon, "ids": ids,
               **{u: as_user(TestClient(app), ids[u], s) for u, s in (("adm.rao", "rao"), ("dr.rao", "rao"),
                                                                       ("dr.rao2", "rao"), ("adm.iyer", "iyer"))}}


def test_a_clinics_names_never_reach_another_clinics_requests(team):
    check = {"row": dict(ROW), "transcript": TRANSCRIPT}
    for _ in range(2):                                           # alternate, so a leaked ContextVar would show
        mine = team["dr.rao"].post("/api/v1/rx/check-row", json=check, headers=H).json()["row"]
        theirs = team["adm.iyer"].post("/api/v1/rx/check-row", json=check, headers=H).json()["row"]
        assert (mine["status"], mine["source"]) == ("verified", "clinic")
        assert (theirs["status"], theirs["source"]) == ("unknown-medicine", "lexicon")
    ask = lambda c: c.post("/api/format", json={"transcript": TRANSCRIPT}, headers=H).json()["structured"]["rx"][0]   # noqa: E731
    assert (ask(team["dr.rao"])["source"], ask(team["adm.iyer"])["source"]) == ("clinic", "lexicon")
    correct = {"transcript": "", "current_form": {"patientName": "A", "rx": [dict(PAGE_ROW)]}}
    assert team["adm.iyer"].post("/api/v1/correct", json=correct, headers=H).json()["structured"]["rx"][0]["status"] == "unknown-medicine"


def test_added_by_records_the_user_whose_save_confirmed_the_name(team):
    row = {**ROW, "name": "Dhanvika"}
    assert save(team["dr.rao"], "Anita", row=row).status_code == 200
    with clinic_conn("rao") as c:
        assert [(r["name"], r["confirm_count"], r["added_by"]) for r in entries(c) if r["name"] == "Dhanvika"] == [("Dhanvika", 1, None)]
    assert save(team["dr.rao2"], "Bala", row=row).status_code == 200
    with clinic_conn("rao") as c:
        assert [(r["confirm_count"], r["added_by"]) for r in entries(c) if r["name"] == "Dhanvika"] == [(2, team["ids"]["dr.rao2"])]
    with clinic_conn("iyer") as c:
        assert entries(c) == []


def test_an_admin_lists_and_removes_a_name_and_the_removal_is_audited(team):
    assert [i["name"] for i in team["adm.rao"].get("/api/v1/formulary").json()["items"]] == ["Zorbexin"]
    assert [i["name"] for i in team["dr.rao"].get("/api/v1/formulary").json()["items"]] == ["Zorbexin"]   # any user may look
    r = team["adm.rao"].delete("/api/v1/formulary/1", headers=H)
    assert (r.status_code, r.json()) == (200, {"removed": 1, "name": "Zorbexin"})
    assert team["adm.rao"].get("/api/v1/formulary").json() == {"items": []}
    assert team["adm.rao"].delete("/api/v1/formulary/1", headers=H).status_code == 404            # already removed
    with clinic_conn("rao") as c:
        assert c.execute("SELECT detail FROM audit_log WHERE action = 'formulary.remove'").fetchone()[0] == '{"name": "Zorbexin"}'


def test_a_plain_doctor_cannot_remove_and_another_clinics_admin_gets_404(team):
    r = team["dr.rao"].delete("/api/v1/formulary/1", headers=H)
    assert (r.status_code, r.json()) == (403, {"error": "You are not allowed to do that"})
    r = team["adm.iyer"].delete("/api/v1/formulary/1", headers=H)                                # id 1 exists only in Rao's file
    assert (r.status_code, r.json()) == (404, {"error": "no such medicine"})
    assert team["adm.iyer"].get("/api/v1/formulary").json() == {"items": []}
    assert [i["id"] for i in team["adm.rao"].get("/api/v1/formulary").json()["items"]] == [1]    # nothing was removed


def test_signed_out_and_malformed_requests_are_rejected(team):
    assert team["anon"].get("/api/v1/formulary").status_code == 401
    assert team["anon"].delete("/api/v1/formulary/1", headers=H).status_code == 401
    assert team["adm.rao"].delete("/api/v1/formulary/0", headers=H).status_code == 422
    assert team["adm.rao"].delete("/api/v1/formulary/abc", headers=H).status_code == 422


def test_saving_never_fails_because_learning_failed(single, monkeypatch, caplog):
    def boom(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(fdb, "record_confirmation", boom)
    with caplog.at_level(logging.WARNING, logger=route_mod.__name__):
        assert save(single, "Anita").status_code == 200
    assert any("could not record" in r.getMessage() for r in caplog.records)
    assert single.get("/api/v1/formulary").json() == {"items": []}


def test_single_mode_tests_never_resolve_to_the_real_dev_database():
    """tests/conftest.py points DB_PATH at a per-test temp folder, so an app built in a test cannot write app.db."""
    assert dbmod.db_path() != dbmod.DEFAULT_DB_PATH and "single-db" in str(dbmod.db_path())
