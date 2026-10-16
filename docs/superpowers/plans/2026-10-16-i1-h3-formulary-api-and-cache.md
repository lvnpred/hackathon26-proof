# Clinic Formulary, Part 3: Loading, Learning, Cache Key and Admin Routes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load each clinic's layer per request, learn names when a prescription is saved, make the `/api/format` cache notice a changed list, and give clinic admins `GET /api/v1/formulary` and `DELETE /api/v1/formulary/{entry_id}`.

**Architecture:** `api/formulary.py` loads the layer (`load_layer`, run in a thread) and sets it active through an async FastAPI dependency `use_clinic_layer` declared on the name-matching routes. The save route calls `learn_from_save` after the document is stored. The cache key gains the layer's version. A new policy action `formulary.manage` limits removal to `admin`.

**Tech Stack:** Python 3 / FastAPI / sqlite3 (stdlib), vanilla JS, pytest. No new dependency.

**Spec:** `docs/superpowers/plans/2026-10-16-medication-name-accuracy.md` section 2d ("Clinic formulary") and table row "Clinic formulary"; contracts in `docs/superpowers/plans/2026-10-16-i1-00-index-and-contracts.md` (facts 1, 2, 5, 6; sections 4.1, 4.2, 4.3).

**Assumptions about earlier plans** (re-find every anchor with `grep -n`; line numbers below are from the repository as it stood before I1-a..I1-g)**:**
- I1-h1 and I1-h2 are applied. Used exactly: `core.formulary.ClinicLayer(items)`, `.version`, `activate`, `active_layer`, `learnable(structured, confirmed_rows)`, `key(name)`; `db.formulary.record_confirmation(conn, key, name, generic, document_id, user_id) -> int`, `list_active(conn) -> list[dict]`, `remove(conn, entry_id) -> str | None`; rows carry `source`.
- I1-c: `dose-check` never fires for a row with no lexicon match (clinic names are `cannot-check`). I1-d is applied (the per-row block lives in `rowcheck.ground_with_notes`, where I1-h2 put `row_extras`); `api/rx.py` exists and gets the dependency in Step 6.

**Produces (consumed by I1-h4):** `api.formulary`: `router`, `load_layer() -> ClinicLayer`, `async use_clinic_layer() -> None`, `learn_from_save(conn, structured, confirmed_rows, document_id, user_id) -> None` (never raises); `GET /api/v1/formulary -> {"items": [...]}`; `DELETE /api/v1/formulary/{entry_id} -> {"removed": id, "name": name}` with `403 {"error": "You are not allowed to do that"}`, `404 {"error": "no such medicine"}`, `422` for ids below 1 or not integers; policy action `formulary.manage`; `use_clinic_layer` on `/api/format`, `/api/v1/correct`, `/api/transcribe`; the cache key `clinic:layer-version:key`; `tests/test_formulary_routes.py`.

## Global Constraints

- `core/` stays pure (`tests/test_core_purity.py`): `core/formulary.py` imports only the standard library and `core.candidates`/`core.determinism` (lazily). Per-clinic data comes in as data.
- Changes to `core/determinism.py`: at most 4 net lines (this plan: +1). No source file over 500 lines (`db/__init__.py` is 487 lines, so the new SQL lives in `db/formulary.py`).
- Existing endpoints keep their status codes and JSON shapes; rows gain only `source` (and `lookalike` for a clinic name flagged as a look-alike). `preserve_untouched_rx_status` also restores `source` (`core/correction.py:273`).
- A clinic name is verified for its NAME only: no strength options, dose check `cannot-check`. Another clinic never sees a name: every query runs on the scoped clinic database (`db/__init__.py:35-44`).
- Tests offline: stub LLM (`STUB_LLM_JSON`), fake PDF renderer, no network. Test command `.venv/bin/python -m pytest tests/ -q`. No commits: every "commit" step is "leave uncommitted".

## Review Focus

- A cached `/api/format` answer must not hide a newly learned (or newly removed) name. Pinned in Task 1 (`test_two_saved_prescriptions_teach_a_name_and_the_format_cache_notices`).
- A doctor must not be able to remove names (403), an admin of another clinic must not see or remove them (404), a signed-out caller is refused (401), a bad id is a 422. Pinned in Task 1.
- Saving must never fail because learning failed (`learn_from_save` swallows and logs), and an unconfirmed row is still blocked by the existing gate. Pinned in Task 1.

## Decisions (and why)

1. **Trigger.** `api/persistence.py:194` already blocks any row not `verified` unless its index is in `confirmed_rows`. The hook runs after the document is stored (after the audit call, `:289-299`) and learns from rows whose index is in `confirmed_rows` AND whose name the lexicon does not know (`_canonical_lookup`, `core/determinism.py:226`). The row's `status` text is not used: the client could send anything. Names are read from `structured["rx"]` BEFORE `validate_structured` (which drops empty rows and shifts indexes).
6. **How the layer reaches the matcher.** Passing a layer through `ground_rx -> validate_structured -> _ground_row -> _canonical_lookup` would cost about 8 lines in `determinism.py`. Instead `formulary.activate(layer)` sets a `ContextVar` in a FastAPI dependency (`use_clinic_layer`, async so the value stays in the request's context); `asyncio.to_thread` copies the context (`scope.py:5-6` relies on the same). `core` functions still accept data only; tests call `activate()` directly.
7. **Cache.** `/api/format` caches per `clinic:key` (`api/format.py:89`). The key becomes `clinic:layer-version:key:rawhash` once I1-a's raw-wording hash is there (the final form, one key, both parts); the version is a hash of the sorted names ("0" when empty), so adding or removing a name changes it.
9. **Admin.** `policy.py` has roles in `Identity.role` (`doctor`, `assistant`, `admin`, `accounts.py:19`) but enforces none (`policy.py:1-2`). New action `formulary.manage` is true only for `admin`. Single-database mode has no sign-in and no roles (`api/authorship.py:17-19`), so there the Remove call is allowed, like every other call. The permission check runs before the lookup (as `api/users.py:32-39`): a doctor gets 403, an admin of another clinic 404.

## File Structure

| File | Change |
|---|---|
| `doctor_dictation/api/formulary.py` | NEW |
| `api/format.py`, `api/stt.py`, `api/persistence.py`, `api/app.py`, `policy.py` | dependency, cache key, hook, router, permission |
| `tests/test_formulary_routes.py` | NEW |
| `tests/test_api_app.py`, `tests/isolation_fixtures.py`, `tests/test_isolation_routes.py` | route table, fingerprint table list, admin-only route classified |

Adds 5 tests. Baseline: the suite as it stands after I1-h2; expect that count + 5.

---

### Task 1: Loading, learning, the cache key and the admin routes

**Files:** Create `doctor_dictation/api/formulary.py`, `tests/test_formulary_routes.py`; Modify `api/format.py`, `api/stt.py`, `api/persistence.py`, `api/app.py`, `policy.py`, `tests/test_api_app.py`.

**Interfaces:** Consumes `core.formulary`, `db.formulary`. Produces `load_layer() -> ClinicLayer`, `async use_clinic_layer() -> None` (FastAPI dependency), `learn_from_save(conn, structured, confirmed_rows, document_id, user_id) -> None` (never raises), `GET /api/v1/formulary -> {"items": [...]}`, `DELETE /api/v1/formulary/{entry_id} -> {"removed": id, "name": name}`; errors `403 {"error": "You are not allowed to do that"}`, `404 {"error": "no such medicine"}`, `422` for ids below 1 or not integers.

- [ ] **Step 1: Write the failing tests.** The first proves the cached sheet would still say unknown-medicine; the others cover 403, 404 (another clinic), 401 and 422.

```python
"""Learning on save, the /api/format cache, and the admin routes (plan I1-h). Offline: stub LLM, fake PDF renderer."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from authorship_fixtures import H, as_user, clinic_conn
from doctor_dictation import accounts, clinics
from doctor_dictation.api.app import create_app
from doctor_dictation.config import override_settings
from doctor_dictation.core import determinism as D

TRANSCRIPT = "tablet Zorbexin 10 mg once daily for 5 days"
ROW = {"form": "Tab.", "name": "Zorbexin", "strength": "10 mg", "dose": "1-0-0", "timing": "", "duration": "5 days",
       "instructions": "", "status": "unknown-medicine"}


def _fake_pdf(monkeypatch):
    def fake(structured, meta, out_path, layout=None):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps({"rx": [ROW]}))
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True)
    D._FORMAT_CACHE.clear()


def save(client, patient, confirmed=(0,), document_id=None):
    body = {"structured": {"patientName": patient, "ageSex": "40 / M", "opNo": "", "rx": [dict(ROW)]},
            "confirmed_rows": list(confirmed), "document_id": document_id}
    return client.post("/api/v1/documents", json=body, headers=H)


@pytest.fixture()
def single(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "f.db"))
    _fake_pdf(monkeypatch)
    with TestClient(create_app()) as client:
        yield client


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


def test_every_route_that_matches_names_loads_the_clinic_layer():
    api = Path(__file__).resolve().parents[1] / "doctor_dictation" / "api"
    want = {"format.py": 2, "stt.py": 1, "rx.py": 1}             # /api/format and /api/v1/correct; /api/transcribe; I1-d
    for name, count in want.items():
        if (api / name).exists():
            assert (api / name).read_text(encoding="utf-8").count("dependencies=[Depends(use_clinic_layer)]") == count, name


@pytest.fixture()
def team(multi, monkeypatch):
    _fake_pdf(monkeypatch)
    clinics.provision_clinic("rao", "Rao Clinic")
    clinics.provision_clinic("iyer", "Iyer Clinic")
    ids = {}
    for slug, user, role in (("rao", "adm.rao", "admin"), ("rao", "dr.rao", "doctor"), ("iyer", "adm.iyer", "admin")):
        ids[user], _ = accounts.create_user(slug, user, role=role, password="a-long-password-1")
        with clinic_conn(slug) as c:
            c.execute("UPDATE users SET must_change_password = 0 WHERE id = ?", (ids[user],))
            c.commit()
    with clinic_conn("rao") as c:
        c.execute("INSERT INTO clinic_formulary(name_key, name, confirm_count, first_seen_at, last_seen_at)"
                  " VALUES ('zorbexin', 'Zorbexin', 2, '2026-10-01T00:00:00Z', '2026-10-02T00:00:00Z')")
        c.commit()
    app = create_app()
    with TestClient(app) as anon:
        yield {"app": app, "anon": anon, "ids": ids,
               **{u: as_user(TestClient(app), ids[u], s) for u, s in (("adm.rao", "rao"), ("dr.rao", "rao"), ("adm.iyer", "iyer"))}}


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
```

- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_formulary_routes.py -q`. Expected: FAIL (`assert {'detail': 'Not Found'} == {'items': []}`: the route does not exist yet).
- [ ] **Step 3: Write `api/formulary.py`.**

```python
"""The clinic's own drug list: learn it on save, serve it to name matching, list it, let an admin remove a name."""
import asyncio
import logging
import sqlite3
from contextlib import closing
from typing import Annotated

from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse

from doctor_dictation import db as dbmod
from doctor_dictation import policy
from doctor_dictation.api import authorship
from doctor_dictation.core import formulary
from doctor_dictation.db import formulary as fdb

router = APIRouter()
log = logging.getLogger(__name__)
DENIED = {"error": "You are not allowed to do that"}
EntryId = Annotated[int, Path(ge=1, le=2**63 - 1)]       # SQLite's INTEGER range; anything else is a 422


def load_layer() -> formulary.ClinicLayer:
    """This clinic's active names (the scope picks the database). Any database problem means an empty layer."""
    try:
        with closing(dbmod.get_conn()) as conn:
            return formulary.ClinicLayer(tuple((r["name"], r["generic"] or "") for r in fdb.list_active(conn)))
    except sqlite3.Error:
        log.warning("clinic formulary unavailable; matching without it", exc_info=True)
        return formulary.ClinicLayer()


async def use_clinic_layer() -> None:
    """FastAPI dependency: make this clinic's layer the active one for the request (threads inherit it)."""
    formulary.activate(await asyncio.to_thread(load_layer))


def learn_from_save(conn, structured, confirmed_rows, document_id, user_id) -> None:
    """Count the doctor's confirmed, unknown names once per saved document. Never blocks the save."""
    try:
        for name, generic in formulary.learnable(structured, confirmed_rows):
            fdb.record_confirmation(conn, formulary.key(name), name, generic, document_id, user_id)
    except Exception:  # noqa: BLE001 - learning is a convenience, the prescription is already saved
        log.warning("clinic formulary: could not record confirmations", exc_info=True)


@router.get("/api/v1/formulary")
def list_formulary():
    with closing(dbmod.get_conn()) as conn:
        return {"items": fdb.list_active(conn)}


@router.delete("/api/v1/formulary/{entry_id}")
def remove_entry(request: Request, entry_id: EntryId):
    """Clinic admins only. An id from another clinic is not in this database, so it answers 404."""
    ident = authorship.identity(request)
    if ident is not None and not policy.can(ident, "formulary.manage"):
        return JSONResponse(status_code=403, content=DENIED)
    with closing(dbmod.get_conn()) as conn:
        name = fdb.remove(conn, entry_id)
        if name is None:
            return JSONResponse(status_code=404, content={"error": "no such medicine"})
        dbmod.log_audit(conn, action="formulary.remove", entity="formulary", entity_id=str(entry_id), detail={"name": name})
    return {"removed": entry_id, "name": name}
```

- [ ] **Step 4: Permission and registration.** `policy.py` (an unknown action is denied, `policy.py:16-17`, so the action must be listed):

```diff
- "user.reset_password", "letterhead.manage"})
+ "user.reset_password", "letterhead.manage", "formulary.manage"})
```
```diff
-     if action == "letterhead.manage" and resource is not None:
+     if action == "formulary.manage":
+         return getattr(user, "role", "") == "admin"          # the clinic's medicine list: admins only
+     if action == "letterhead.manage" and resource is not None:
```

and `api/app.py` registers the router next to the others (`:79`):

```diff
- from doctor_dictation.api import auth, health, persistence, profile, stt
+ from doctor_dictation.api import auth, health, persistence, profile, stt
+ from doctor_dictation.api import formulary as formulary_api
```
```diff
-     for module in (auth, health, stt, format_api, profile, persistence, users_api):
+     for module in (auth, health, stt, format_api, profile, persistence, users_api, formulary_api):
```

- [ ] **Step 5: The save hook, the dependency on the name-matching routes and the cache key.** `api/persistence.py` (the closing lines of the `log_audit(...)` call, then the new line, then `return {`, `:289-300`), `api/format.py` (two routes and `:89`), `api/stt.py` (the route):

```diff
- from doctor_dictation.api import authorship
+ from doctor_dictation.api import authorship
+ from doctor_dictation.api.formulary import learn_from_save
```
```python
                "confirmed_rows": list(req.confirmed_rows),
            },
        )
        learn_from_save(conn, structured, req.confirmed_rows, document_id, ident.user_id if ident else None)
        return {
```
```diff
- from doctor_dictation.core.ops import apply_ops
+ from doctor_dictation.api.formulary import use_clinic_layer
+ from doctor_dictation.core import formulary
+ from doctor_dictation.core.ops import apply_ops
```
```diff
- from fastapi import APIRouter, Request
+ from fastapi import APIRouter, Depends, Request
```
```diff
- @router.post("/api/format")
+ @router.post("/api/format", dependencies=[Depends(use_clinic_layer)])
```
```diff
-     ckey = f"{sc.clinic_slug if sc else ''}:{key}:{transcript_sha(raw)[:16]}"   # I1-a: per clinic and raw wording
+     ckey = f"{sc.clinic_slug if sc else ''}:{formulary.active_layer().version}:{key}:{transcript_sha(raw)[:16]}"   # + the learned list
```
```diff
- @router.post("/api/v1/correct")
+ @router.post("/api/v1/correct", dependencies=[Depends(use_clinic_layer)])
```
```diff
- from fastapi import APIRouter, File, UploadFile
+ from fastapi import APIRouter, Depends, File, UploadFile
```
```diff
- from doctor_dictation.audio.trim import trim_silence
+ from doctor_dictation.api.formulary import use_clinic_layer
+ from doctor_dictation.audio.trim import trim_silence
```
```diff
- @router.post("/api/transcribe")
+ @router.post("/api/transcribe", dependencies=[Depends(use_clinic_layer)])
```

- [ ] **Step 6: I1-d's route.** Change `doctor_dictation/api/rx.py`'s `@router.post("/api/v1/rx/check-row")` to `@router.post("/api/v1/rx/check-row", dependencies=[Depends(use_clinic_layer)])` (import `Depends` and `from doctor_dictation.api.formulary import use_clinic_layer`). `test_every_route_that_matches_names_loads_the_clinic_layer` checks it.
- [ ] **Step 7: The route table test** (`tests/test_api_app.py:28` lists every route):

```diff
-     ("GET", "/api/v1/users"), ("POST", "/api/v1/users"),
+     ("GET", "/api/v1/formulary"), ("DELETE", "/api/v1/formulary/{entry_id}"),
+     ("GET", "/api/v1/users"), ("POST", "/api/v1/users"),
```

- [ ] **Step 8: Adapt the existing isolation sweep.** It walks every `{id}` route as a plain doctor (`tests/test_isolation_routes.py:30-35`, count at `:81`) and fails for an unclassified route (`:162`, test at `:195-207`). The new `DELETE` needs an admin, so `id_routes` skips it (plan I1-h4 Task 1 sweeps it with admin clients) and both new routes are classified; `fingerprint` (`tests/isolation_fixtures.py:41`) now covers the new table.

```diff
-           "schema_migrations")
+           "schema_migrations", "clinic_formulary")
```
```python
ADMIN_ONLY = ("/api/v1/formulary/",)      # swept with an admin client in test_isolation_formulary.py, not with a doctor


def id_routes(app):
    out = []
    for path, ops in app.openapi()["paths"].items():
        if "{" in path and not path.startswith(ADMIN_ONLY):
```
```diff
-     "GET /api/v1/users": "list: test_no_list_or_page_shows_the_other_clinics_data",
+     "GET /api/v1/users": "list: test_no_list_or_page_shows_the_other_clinics_data",
+     "GET /api/v1/formulary": "list: test_no_list_or_page_shows_the_other_clinics_data; test_isolation_formulary.py",
+     "DELETE /api/v1/formulary/{entry_id}": "admin only: test_isolation_formulary.py",
```

- [ ] **Step 9: Run.** Run: `.venv/bin/python -m pytest tests/ -q`. Expected: baseline + 5 passed, no failure (the I1-d classification text in `tests/test_isolation_routes.py` for `POST /api/v1/rx/check-row` says "stateless ... reads no clinic data"; with the dependency it now reads the clinic's layer: change it to `"reads the caller's own clinic layer via use_clinic_layer: test_isolation_formulary.py"`) (`test_formulary_routes.py`: 5 passed; the sweep still counts 11 id routes).
- [ ] **Step 10: Leave uncommitted.**

---

## Self-review

Loading, learning, cache key, admin routes and permission are each covered by a test in Task 1; names match I1-h2's Produces block. Not done here: the cross-clinic isolation file (I1-h4), the Team tab (I1-h4).
