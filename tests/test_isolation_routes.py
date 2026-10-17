"""Route sweep (spec 13.1): as Clinic B, ask every route for ids only Clinic A has. Nothing of A comes back,
nothing of A changes, and B never even opens A's database file. Offline; seeded world from isolation_fixtures."""
import os
import re
import shutil

import pytest

from doctor_dictation.api import stt as api_stt
from doctor_dictation.config import override_settings
from doctor_dictation.scope import clinic_dir
from isolation_fixtures import (A, A_MARKERS, B, B_MARKERS, H, a_only_id, correct_body, fingerprint, leaks,
                                opened_files, pdf_text, save_body, upload, world)  # noqa: F401

WRITE = {"POST", "PUT", "DELETE", "PATCH"}
ID_TABLE = (("/api/v1/documents/", "documents"), ("/api/v1/templates/", "templates"), ("/api/v1/users/", "users"),
            ("/api/v1/patients/", "patients"), ("/api/v1/encounters/", "encounters"))
BODIES = {   # so an id route reaches its lookup instead of a 422 (A10, A11)
    ("PUT", "/api/v1/templates/{id}"): {"profile": {}, "lines": []},
    ("PUT", "/api/v1/templates/{id}/doctors"): {"mode": "all", "ids": []},
    ("POST", "/api/v1/templates/{id}/accept"): {"scope": "clinic"},
}
EXTRA_GETS = ("/api/v1/encounters/today?scope=clinic",)                     # A4


def _norm(path):
    return re.sub(r"\{[^}]+\}", "{id}", path)


ADMIN_ONLY = ("/api/v1/formulary/", "/api/v1/users/")      # admin-only routes: swept with admin clients in test_isolation_formulary.py, not with a doctor (a doctor gets 403 first)


def id_routes(app):
    out = []
    for path, ops in app.openapi()["paths"].items():
        if "{" in path and not path.startswith(ADMIN_ONLY):
            out.extend((m.upper(), path) for m in ops if m.upper() in WRITE | {"GET"})
    return sorted(out)


def plain_gets(app):
    return sorted(p for p, ops in app.openapi()["paths"].items() if "get" in ops and "{" not in p)


def table_for(path):
    assert path.count("{") == 1, f"{path}: the sweep handles one id per route; extend table_for"
    for prefix, table in ID_TABLE:
        if path.startswith(prefix):
            return table
    raise AssertionError(f"unmapped id route {path}: add its clinic table to ID_TABLE")


def _a_only_url(path):
    return re.sub(r"\{[^}]+\}", str(a_only_id(table_for(path))), path)


def test_the_world_signs_in_three_doctors_in_two_clinics(world):
    me = [getattr(world, who).get("/api/v1/auth/me").json() for who in ("rao", "mehta", "iyer")]
    assert [(m["clinic_slug"], m["username"]) for m in me] == [("rao", "dr.rao"), ("rao", "dr.mehta"), ("iyer", "dr.iyer")]
    assert [m["clinic_name"] for m in me] == ["Rao Clinic", "Rao Clinic", "Iyer Clinic"]


def test_every_route_with_an_id_is_mapped_to_a_clinic_table(world):
    routes = id_routes(world.app)
    assert len(routes) >= 7, routes
    for _method, path in routes:
        table_for(path)                       # raises, naming the route, when a new id route has no mapping


def _call(client, method, path):
    url = _a_only_url(path)
    return url, client.request(method, url, json=BODIES.get((method, _norm(path))), headers=H)


def test_every_id_route_answers_404_for_an_id_only_clinic_a_has(world):
    before = fingerprint(A)
    wrong, table = [], []
    routes = id_routes(world.app)
    for method, path in routes:
        url, r = _call(world.iyer, method, path)
        table.append(f"{method} {url} -> {r.status_code}")
        if r.status_code != 404 or leaks(r.text, A_MARKERS):
            wrong.append(f"{method} {url} -> {r.status_code} {r.text[:160]}")
    assert len(routes) == 8, routes      # the live count of doctor-sweepable id operations (the 3 user actions and the formulary DELETE are admin only); a new one must be reviewed here
    assert not wrong, wrong
    assert fingerprint(A) == before, table


def test_the_owner_gets_what_clinic_b_is_refused_on_every_id_route(world, tmp_path_factory):
    """Baseline: the same request from Rao is NOT a 404, so Iyer's 404 above is isolation, not a bad id or body.
    Each owner request may change A, so A's folder is restored from a copy after every one. The copy lives beside
    DATA_DIR, not inside it."""
    snap, root = tmp_path_factory.mktemp("owner-snapshot") / "A", clinic_dir(A)
    shutil.copytree(root, snap)
    table, bad = [], []
    for method, path in id_routes(world.app):
        url, r = _call(world.rao, method, path)
        table.append(f"{method} {url} -> {r.status_code}")
        if r.status_code >= 300:
            bad.append(f"{method} {url} -> {r.status_code} {r.text[:160]}")
        shutil.rmtree(root)
        shutil.copytree(snap, root)
    assert not bad, (bad, table)


def test_clinic_b_requests_never_open_a_clinic_a_database(world, monkeypatch):
    targets = [(method, _a_only_url(path), path) for method, path in id_routes(world.app)]   # ids looked up first
    with opened_files(monkeypatch) as seen:
        for method, url, path in targets:
            world.iyer.request(method, url, json=BODIES.get((method, _norm(path))), headers=H)
        for url in plain_gets(world.app):
            world.iyer.get(url)
    a_dir = str(clinic_dir(A)) + os.sep
    assert seen, "the spy saw no database opens"
    assert [p for _thread, p in seen if p.startswith(a_dir)] == []


def test_both_clinics_have_a_document_1_and_each_sees_its_own(world):
    a, b = world.rao.get("/api/v1/documents/1"), world.iyer.get("/api/v1/documents/1")
    assert (a.status_code, b.status_code) == (200, 200)
    assert (a.json()["structured"]["patientName"], b.json()["structured"]["patientName"]) == ("Asha Verma", "Bharat Menon")
    pa, pb = world.rao.get("/api/v1/documents/1/pdf"), world.iyer.get("/api/v1/documents/1/pdf")
    assert (pa.status_code, pb.status_code) == (200, 200)
    assert "Rao Clinic" in pdf_text(pa) and not leaks(pdf_text(pa), B_MARKERS)
    assert "Iyer Clinic" in pdf_text(pb) and not leaks(pdf_text(pb), A_MARKERS)


def test_no_list_or_page_shows_the_other_clinics_data(world):
    found = []
    for who, theirs in (("iyer", A_MARKERS), ("rao", B_MARKERS), ("mehta", B_MARKERS), ("iyer_admin", A_MARKERS), ("rao_admin", B_MARKERS)):
        client = getattr(world, who)
        for url in [*plain_gets(world.app), *EXTRA_GETS]:
            r = client.get(url)
            assert r.status_code < 500, (who, url, r.status_code)
            if leaks(r.text, theirs):
                found.append((who, url, leaks(r.text, theirs)))
    assert not found, found
    assert "Asha Verma" in world.rao.get("/api/v1/patients").text           # the lists are not simply empty
    assert "Bharat Menon" in world.iyer.get("/api/v1/patients").text


def test_ids_inside_bodies_and_queries_stay_in_the_callers_clinic(world):
    before = fingerprint(A)
    doc, patient = a_only_id("documents"), a_only_id("patients")
    r = world.iyer.post("/api/v1/documents", json=save_body("Bharat Menon", document_id=doc), headers=H)
    assert r.status_code == 404, r.text
    r = world.iyer.post("/api/v1/encounters", json={"patient_id": patient}, headers=H)
    assert r.status_code == 404, r.text
    r = world.iyer.get(f"/api/v1/encounters?patient_id={patient}")
    assert (r.status_code, r.json()) == (200, [])
    assert fingerprint(A) == before


def test_correct_with_a_document_id_only_clinic_a_has_leaks_nothing(world):
    """Iyer's own database has no such document, so the authorship check finds no author and allows it: the route
    answers 200 with a stateless merge of Iyer's own form. Assert that status, no A data in it, A untouched."""
    before = fingerprint(A)
    r = world.iyer.post("/api/v1/correct", json=correct_body(a_only_id("documents"), "Bharat Menon"), headers=H)
    assert r.status_code == 200, r.text
    assert "Bharat Menon" in r.text                                      # the caller's own form came back
    assert not leaks(r.text, A_MARKERS), leaks(r.text, A_MARKERS)
    assert fingerprint(A) == before


CLASSIFIED = {
    "POST /api/v1/correct": "test_correct_with_a_document_id_only_clinic_a_has_leaks_nothing",
    "POST /api/v1/documents": "test_ids_inside_bodies_and_queries_stay_in_the_callers_clinic",
    "GET /api/v1/encounters": "test_ids_inside_bodies_and_queries_stay_in_the_callers_clinic",
    "POST /api/v1/encounters": "test_ids_inside_bodies_and_queries_stay_in_the_callers_clinic",
    "GET /api/v1/encounters/today": "list: test_no_list_or_page_shows_the_other_clinics_data (EXTRA_GETS)",
    "GET /api/v1/patients": "list: test_no_list_or_page_shows_the_other_clinics_data",
    "POST /api/v1/patients": "test_writes_land_in_the_callers_clinic_only[patients]",
    "GET /api/v1/profile": "list-style GET: test_no_list_or_page_shows_the_other_clinics_data",
    "PUT /api/v1/profile": "test_writes_land_in_the_callers_clinic_only[profile]",
    "POST /api/v1/templates": "test_writes_land_in_the_callers_clinic_only[upload]",
    "GET /api/v1/templates/active": "list: test_no_list_or_page_shows_the_other_clinics_data",
    "GET /api/v1/templates/current": "list: test_no_list_or_page_shows_the_other_clinics_data",
    "POST /api/v1/templates/deactivate": "acts on the caller's own active letterhead; no id in the request",
    "GET /api/v1/templates/doctors": "list: test_no_list_or_page_shows_the_other_clinics_data",
    "GET /api/v1/users": "list: test_no_list_or_page_shows_the_other_clinics_data",
    "GET /api/v1/formulary": "list: test_no_list_or_page_shows_the_other_clinics_data; test_formulary_routes.py",
    "DELETE /api/v1/formulary/{entry_id}": "admin only: test_formulary_routes.py (404 for another clinic's id, 403 for a doctor)",
    "POST /api/v1/users": "test_writes_land_in_the_callers_clinic_only[users] (an admin client)",
    "POST /api/v1/users/{user_id}/disable": "admin only: test_isolation_formulary.py::test_the_admin_sweep_covers_every_admin_only_route_across_clinics",
    "POST /api/v1/users/{user_id}/enable": "admin only: test_isolation_formulary.py::test_the_admin_sweep_covers_every_admin_only_route_across_clinics",
    "POST /api/v1/users/{user_id}/reset-password": "admin only: test_isolation_formulary.py::test_the_admin_sweep_covers_every_admin_only_route_across_clinics",
    "POST /api/transcribe": "reads the caller's own clinic hints: test_transcribe_hints_come_from_the_callers_own_scope",
    "POST /api/format": "per-clinic result cache: test_the_format_cache_is_per_clinic",
    "POST /api/v1/rx/check-row": "reads the caller's own clinic layer via use_clinic_layer: test_formulary_routes.py (a clinic's names never reach another clinic)",
    "POST /api/v1/review-date": "stateless: no database, no clinic data (plan I2-b)",
    "GET /api/health": "public",
    "GET /health": "public",
    "GET /login": "public page",
    "POST /api/v1/auth/login": "public; auth tests",
    "POST /api/v1/auth/logout": "auth; session tests",
    "GET /api/v1/auth/me": "auth; test_the_world_signs_in_three_doctors_in_two_clinics",
    "POST /api/v1/auth/change-password": "auth; session tests",
}


def test_every_route_is_classified_in_the_isolation_suite(world):
    unclassified = []
    for path, ops in world.app.openapi()["paths"].items():
        for method in ops:
            key = f"{method.upper()} {path}"
            is_id = "{" in path
            if is_id and (method.upper(), path) in id_routes(world.app):
                continue          # swept; table_for() fails loudly when its table is unmapped
            if key not in CLASSIFIED:
                unclassified.append(key)
    live = {f"{m.upper()} {path}" for path, ops in world.app.openapi()["paths"].items() for m in ops}
    assert not set(CLASSIFIED) - live, f"stale CLASSIFIED entries: {sorted(set(CLASSIFIED) - live)}"
    assert not unclassified, f"classify these routes in CLASSIFIED (or sweep them): {unclassified}"


@pytest.mark.parametrize("what", ["patients", "users", "upload", "profile"])
def test_writes_land_in_the_callers_clinic_only(world, what):
    """Writes that take no id: as Iyer, each one changes Iyer's database (or folder) and leaves Clinic A untouched."""
    before_a, before_b = fingerprint(A), fingerprint(B)
    if what == "patients":
        r = world.iyer.post("/api/v1/patients", json={"name": "Write Probe", "age_sex": "30 / F"}, headers=H)
    elif what == "users":
        r = world.iyer_admin.post("/api/v1/users", json={"username": "dr.probe", "display_name": "Dr. Probe"}, headers=H)
    elif what == "upload":
        r = upload(world.iyer)
    else:
        r = world.iyer.put("/api/v1/profile", json={"clinic_name": "Iyer Clinic Renamed", "address": "9 New Road",
                                                    "phone": "044 9999 0000"}, headers=H)
    assert r.status_code < 300, (what, r.status_code, r.text)
    assert fingerprint(A) == before_a
    assert fingerprint(B) != before_b


def test_transcribe_hints_come_from_the_callers_own_scope(world, monkeypatch):
    """Dictation hints are the signed-in doctor's most-used medicines: Iyer's carry none of A's, Rao's carry A's."""
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, stt_chain=("stub",),
                      stt_use_hints=True, stt_trim_silence=False)
    seen, tops = {}, []

    def spy(top, limit):
        tops.append(list(top))
        return []

    monkeypatch.setattr(api_stt, "build_hints", spy)
    for who in ("iyer", "rao"):
        tops.clear()
        r = getattr(world, who).post("/api/transcribe", files={"audio": ("a.webm", b"x" * 64, "audio/webm")}, headers=H)
        assert r.status_code == 200, r.text
        seen[who] = tops[-1]
    assert seen["iyer"] and set(seen["iyer"]) <= {"Azithromycin", "Levocetirizine", "Pantoprazole"}, seen
    assert {"Paracetamol", "Amlodipine"} <= set(seen["rao"]) and not {"Azithromycin", "Pantoprazole"} & set(seen["rao"]), seen


def test_the_format_cache_is_per_clinic(world):
    """The same transcript from another clinic is never a cache hit, so one clinic cannot learn another dictated it."""
    body = {"transcript": "patient has fever, paracetamol 650 mg twice daily for three days"}
    ask = lambda who: getattr(world, who).post("/api/format", json=body, headers=H).json()   # noqa: E731
    first, again, other = ask("rao"), ask("rao"), ask("iyer")
    assert (first["cached"], again["cached"], other["cached"]) == (False, True, False)
    assert ask("iyer")["cached"] is True                       # Iyer's own second ask hits Iyer's own entry
