# B2b-4: Template Routes and Save Path

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the template routes, switch the save route to the active layout, and verify all of B2b.

**Architecture:** New package `doctor_dictation/templates/` (`images` cleans the file, `builder` calls the vision LLM and validates, `service` holds the rules: rate limit, TTL, accept, discard) behind `api/templates.py`. Storage is migration `004_templates.sql` plus `db/templates.py`. The document-save route passes the active layout to `render_prescription`. LLM output is untrusted: only the fixed vocabulary survives `validate_layout`.

**Tech Stack:** Python 3.12, FastAPI, sqlite3, Pillow, pillow-heif (new), pytest. No network in tests.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` section 7A (7A.1 to 7A.4, 7A.8) and 8.2; contracts `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md` sections 2, 4.1, 4.3 to 4.6.

**Plan 4 of 4 for B2b. Prerequisite: B2b-1 to B2b-3 applied.** Task numbers keep their original B2b numbering (this plan contains Tasks 5-7). **Adds 18 tests.** Before the first task, run `.venv/bin/python -m pytest tests/ -q` and note the count `N`; the count after this plan must be `N + 18`.

## Assumptions about earlier plans

Locate each with `grep -n` before use; if a name differs, change only that line.
- B1a: package `doctor_dictation`, `pyproject.toml` with a `dependencies` list, DB default `doctor_dictation/data/app.db`, `db/__init__.py` exports `get_conn, migrate, log_audit, get_profile, save_profile, db_path, pdf_dir, _utcnow` as today.
- B1c: `doctor_dictation.config.override_settings(monkeypatch, **fields)` and `get_settings()`.
- B1d (contract 4.3): `providers.llm.make_llm(settings, vision=True)` returns `None` without a key, or the stub when `llm_provider == "stub"` and `allow_stub_providers`; the stub's `complete_json` returns the dict in `STUB_LLM_JSON`, read at call time; `Settings.llm_vision_model` exists.
- B1e: `api/app.py` has `create_app()` that calls `app.include_router(...)` per router and runs `init_db()` in its lifespan; the save route lives in `api/persistence.py` and still calls `render_pdf(build_sheet_html(...))`; `api/profile.py` exposes `_profile_dict`-equivalent output. The frontend is served by a `StaticFiles` mount at `/`.
- B2a (contract 4.5): `from doctor_dictation.pdf import Layout, LayoutError, PdfUnavailable, validate_layout, render_prescription`. The renderer takes the logo as `meta["logo"]`, a `data:image/jpeg;base64,...` URI that B2a's sheet builder embeds for `logo` blocks. This plan builds that URI from the stored crop with `service.logo_data_uri(path)` (B2b-3) and passes it at save and preview time (B2b-4).
- D0a (later): `db.log_audit` fills a missing `actor` from the logged-in user (a request-scoped variable), so routes and services here pass `actor=None` and need no wiring.

## Global Constraints

- "No file over 500 lines": `db/__init__.py` is 437 lines, so the template helpers go in a new `db/templates.py`.
- Never run `git commit` or `git push` (user rule). Leave all changes in the working tree; each task ends with "leave uncommitted".
- Tests never touch the network: they use the stub provider (`STUB_LLM_JSON`) or a recording fake patched over `doctor_dictation.templates.builder.make_llm`. A real key sits in `.env` and is loaded by `load_dotenv()`.
- Routes and services read `get_settings()` at call time, never at import.
- Uploaded images live under `db_path().parent / "templates"`, never under `frontend/` or any static mount. Responses never include image bytes, keys or file paths.
- Existing status codes and JSON shapes do not change. If an existing save test patches `render_pdf` in the persistence module, change only that setup line.

## Review Focus

5. An accepted layout that later fails validation must fall back to the built-in layout at save time, not break Save (Task 6).

---

### Task 5: Routes

**Files:**
- Create: `doctor_dictation/api/templates.py`, `tests/test_template_routes.py`
- Modify: `doctor_dictation/api/app.py` (register router, startup purge)

**Interfaces:**
- Consumes: `service`, `render_prescription`, `PdfUnavailable`. Produces: the six routes of contract 4.6. Extra statuses beyond the contract: `PUT` 400 invalid edit, 404, 409 not a draft; `accept`/`DELETE` 404 and 409; `DELETE` answers 204.

- [ ] **Step 1: Write the failing tests**

```python
import json
from pathlib import Path

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation.config import override_settings
from template_fixtures import GOOD_LAYOUT, PROFILE, make_jpeg, tclient  # noqa: F401

URL = "/api/v1/templates"


def _post(c, data=None, name="pad.jpg"):
    return c.post(URL, files={"image": (name, data or make_jpeg(), "image/jpeg")})


def _fake_render(monkeypatch, seen=None):
    def fake(structured, meta, out_path, layout=None):
        if seen is not None:
            seen.update(structured=structured, meta=meta, layout=layout)
        Path(out_path).write_bytes(b"%PDF-1.4 fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.templates.render_prescription", fake)


def test_post_201_shape(tclient):
    r = _post(tclient)
    body = r.json()
    assert r.status_code == 201 and body["status"] == "draft" and body["profile"] == PROFILE
    assert set(body) == {"id", "status", "layout", "profile"} and "profile" not in body["layout"]


def test_post_without_image_or_with_text_is_400(tclient):
    assert tclient.post(URL).status_code == 400
    assert _post(tclient, b"just words", "photo.jpg").status_code == 400


def test_post_too_large_is_413(tclient, monkeypatch):
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, template_max_image_bytes=100)
    assert _post(tclient).status_code == 413


def test_post_over_daily_limit_is_429(tclient, monkeypatch):
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, template_uploads_per_day=1)
    assert _post(tclient).status_code == 201
    assert _post(tclient).status_code == 429


def test_post_invalid_layout_is_502_and_nothing_stored(tclient, monkeypatch):
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps({"header": [], "footer": [], "body": {"top": 1, "bottom": 0}}))
    assert _post(tclient).status_code == 502
    assert tclient.get(URL + "/active").status_code == 404
    conn = dbmod.get_conn()
    assert conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0] == 0
    conn.close()


def test_post_without_llm_is_503(tclient, monkeypatch):
    override_settings(monkeypatch, llm_provider="openai", allow_stub_providers=False, openai_api_key="", deepseek_api_key="")
    assert _post(tclient).status_code == 503


def test_preview_pdf_renders_sample_with_draft_layout(tclient, monkeypatch):
    seen = {}
    _fake_render(monkeypatch, seen)
    tid = _post(tclient).json()["id"]
    r = tclient.get(f"{URL}/{tid}/preview.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert seen["layout"] is not None and seen["meta"]["profile"]["clinic_name"] == "Meridian Clinic"
    assert seen["structured"]["rx"] and seen["meta"]["logo"].startswith("data:image/jpeg;base64,")


def test_preview_missing_is_404_and_renderer_missing_is_503(tclient, monkeypatch):
    assert tclient.get(f"{URL}/999/preview.pdf").status_code == 404
    from doctor_dictation.pdf import PdfUnavailable

    def boom(*a, **k):
        raise PdfUnavailable("no chromium")
    monkeypatch.setattr("doctor_dictation.api.templates.render_prescription", boom)
    tid = _post(tclient).json()["id"]
    assert tclient.get(f"{URL}/{tid}/preview.pdf").status_code == 503


def test_put_edits_and_rejects(tclient):
    tid = _post(tclient).json()["id"]
    ok = tclient.put(f"{URL}/{tid}", json={"profile": {"phone": "111"}, "lines": [{"section": "header", "index": 2, "text": "Open daily"}]})
    assert ok.status_code == 200 and ok.json()["profile"]["phone"] == "111"
    assert tclient.put(f"{URL}/{tid}", json={"profile": {"ssn": "1"}, "lines": []}).status_code == 400
    assert tclient.put(f"{URL}/999", json={"profile": {}, "lines": []}).status_code == 404


def test_accept_then_active_and_profile_saved(tclient):
    assert tclient.get(URL + "/active").status_code == 404
    tid = _post(tclient).json()["id"]
    assert tclient.post(f"{URL}/{tid}/accept").status_code == 200
    act = tclient.get(URL + "/active")
    assert act.status_code == 200 and act.json()["id"] == tid and act.json()["status"] == "active"
    assert tclient.get("/api/v1/profile").json()["doctor_name"] == "Dr A. Rao"
    assert tclient.post(f"{URL}/{tid}/accept").status_code == 409
    assert tclient.put(f"{URL}/{tid}", json={"profile": {}, "lines": []}).status_code == 409
    assert tclient.post(f"{URL}/999/accept").status_code == 404


def test_accept_second_template_archives_first(tclient):
    a, b = (_post(tclient).json()["id"] for _ in range(2))
    tclient.post(f"{URL}/{a}/accept")
    tclient.post(f"{URL}/{b}/accept")
    assert tclient.get(URL + "/active").json()["id"] == b
    assert tclient.delete(f"{URL}/{a}").status_code == 409  # archived is not a draft


def test_delete_discards_draft(tclient):
    tid = _post(tclient).json()["id"]
    assert tclient.delete(f"{URL}/{tid}").status_code == 204
    assert tclient.delete(f"{URL}/{tid}").status_code == 404
    assert tclient.get(f"{URL}/{tid}/preview.pdf").status_code == 404


def test_every_action_writes_an_audit_row(tclient):
    a, b = (_post(tclient).json()["id"] for _ in range(2))
    tclient.post(f"{URL}/{a}/accept")
    tclient.delete(f"{URL}/{b}")
    conn = dbmod.get_conn()
    actions = [r[0] for r in conn.execute("SELECT action FROM audit_log ORDER BY id")]
    conn.close()
    assert actions == ["template_upload", "template_upload", "template_accept", "template_discard"]


def test_expired_drafts_purged_at_startup(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from doctor_dictation.api.app import create_app
    from doctor_dictation.db import templates as tdb
    monkeypatch.setenv("DB_PATH", str(tmp_path / "boot.db"))
    dbmod.init_db()
    conn = dbmod.get_conn()
    tid = tdb.create_template_draft(conn, GOOD_LAYOUT, created_at="2020-01-01T00:00:00Z")
    conn.close()
    with TestClient(create_app()):
        pass
    conn = dbmod.get_conn()
    assert tdb.get_template(conn, tid) is None
    conn.close()


def test_uploads_never_written_under_a_public_path(tclient):
    tid = _post(tclient).json()["id"]
    conn = dbmod.get_conn()
    logo = Path(conn.execute("SELECT logo_path FROM templates WHERE id = ?", (tid,)).fetchone()[0]).resolve()
    conn.close()
    frontend = Path(__file__).resolve().parents[1] / "frontend"
    assert frontend not in logo.parents and logo.parent.name == "templates"
    for name in (f"{tid}_logo.jpg", f"{tid}_original.jpg", f"templates/{tid}_logo.jpg"):
        assert tclient.get("/" + name).status_code == 404
```

- [ ] **Step 2: Run, see failure**

Run: `.venv/bin/python -m pytest tests/test_template_routes.py -q`
Expected: failures (`404` for every POST: router not registered).

- [ ] **Step 3: Implement**

`doctor_dictation/api/templates.py`:

```python
"""Letterhead template routes (contract 4.6)."""
from __future__ import annotations

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from doctor_dictation import db as dbmod
from doctor_dictation.config import get_settings
from doctor_dictation.db import templates as tdb
from doctor_dictation.pdf import PdfUnavailable, render_prescription, validate_layout
from doctor_dictation.templates import TemplateError, service

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])

SAMPLE = {
    "patientName": "Sample Patient", "ageSex": "34 / F", "opNo": "OP-0001", "review": "Review after 5 days",
    "rx": [
        {"form": "Tab.", "name": "Paracetamol", "strength": "500 mg", "dose": "1-0-1", "timing": "After food",
         "duration": "3 days", "instructions": "", "status": "verified"},
        {"form": "Syr.", "name": "Ascoril", "strength": "", "dose": "5 ml 1-0-1", "timing": "",
         "duration": "5 days", "instructions": "", "status": "verified"},
    ],
}


class EditBody(BaseModel):
    profile: dict[str, str] = Field(default_factory=dict)
    lines: list[dict] = Field(default_factory=list)


def _open():
    """New connection; lazily purge expired drafts (and their files) on every templates request."""
    conn = dbmod.get_conn()
    service.purge_expired(conn, get_settings())
    return conn


def _actor(request: Request):
    return getattr(request.state, "username", None)


def _err(exc: TemplateError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"error": str(exc)})


def purge_on_startup() -> None:
    _open().close()


@router.post("", status_code=201)
async def upload_template(request: Request, image: UploadFile | None = File(None)):
    if image is None:
        return JSONResponse(status_code=400, content={"error": "image file is required"})
    settings = get_settings()
    raw = await image.read(settings.template_max_image_bytes + 1)
    conn = _open()
    try:
        return JSONResponse(status_code=201, content=await service.upload(conn, raw, settings, actor=_actor(request)))
    except TemplateError as exc:
        return _err(exc)
    finally:
        conn.close()


@router.get("/active")
def get_active():
    conn = _open()
    try:
        active = service.get_active(conn)
        return active if active else JSONResponse(status_code=404, content={"error": "no active template"})
    finally:
        conn.close()


@router.get("/{template_id}/preview.pdf")
def preview(template_id: int):
    conn = _open()
    try:
        row = tdb.get_template(conn, template_id)
        if row is None or row["status"] == "archived":
            return JSONResponse(status_code=404, content={"error": "template not found"})
        v = service.view(row)
        out = service.templates_dir() / f"preview_{template_id}.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        meta = {"date": dbmod._utcnow()[:10], "opNo": SAMPLE["opNo"], "patientName": SAMPLE["patientName"],
                "profile": v["profile"], "logo": service.logo_data_uri(row["logo_path"])}
        try:
            layout = validate_layout({**v["layout"], "profile": v["profile"]})
            render_prescription(SAMPLE, meta, out, layout=layout)
        except PdfUnavailable:
            return JSONResponse(status_code=503, content={"error": "PDF renderer unavailable"})
        return FileResponse(out, media_type="application/pdf", background=BackgroundTask(out.unlink, missing_ok=True))
    finally:
        conn.close()


@router.put("/{template_id}")
def edit_template(template_id: int, body: EditBody, request: Request):
    conn = _open()
    try:
        return service.edit(conn, template_id, body.profile, body.lines, actor=_actor(request))
    except TemplateError as exc:
        return _err(exc)
    finally:
        conn.close()


@router.post("/{template_id}/accept")
def accept_template(template_id: int, request: Request):
    conn = _open()
    try:
        return service.accept(conn, template_id, actor=_actor(request))
    except TemplateError as exc:
        return _err(exc)
    finally:
        conn.close()


@router.delete("/{template_id}")
def discard_template(template_id: int, request: Request):
    conn = _open()
    try:
        service.discard(conn, template_id, actor=_actor(request))
        return Response(status_code=204)
    except TemplateError as exc:
        return _err(exc)
    finally:
        conn.close()
```

In `doctor_dictation/api/app.py` (find with `grep -n "include_router\|init_db" doctor_dictation/api/app.py`): add `from doctor_dictation.api import templates as templates_api`, then `app.include_router(templates_api.router)` **before** the `StaticFiles` mount at `/`, and in the lifespan, directly after `init_db()`, add `templates_api.purge_on_startup()`.

- [ ] **Step 4: Run, see pass**

Run: `.venv/bin/python -m pytest tests/test_template_routes.py -q`
Expected: `15 passed`. Note `test_accept_second_template_archives_first`: DELETE on an archived row returns 409 (covers the "only drafts can be discarded" rule at route level).

- [ ] **Step 5:** Leave uncommitted.

---

### Task 6: Save path uses the active layout

**Files:**
- Modify: `doctor_dictation/api/persistence.py` (the `try:` block that calls `build_sheet_html` and `render_pdf`; locate with `grep -n "render_pdf\|build_sheet_html" doctor_dictation/api/persistence.py`)
- Create: `tests/test_template_save.py`

**Interfaces:**
- Consumes: `service.active_layout_for_save`, `render_prescription`. Produces: saves render with `layout=<active Layout>` or `layout=None`; failure stays fail-soft (`pdf_path = None`).

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from doctor_dictation import db as dbmod
from doctor_dictation.db import templates as tdb
from template_fixtures import GOOD_LAYOUT, make_jpeg, tclient  # noqa: F401

SAVE = {"structured": {"patientName": "Anita", "opNo": "OP-1", "rx": [{"name": "Tamsulosin", "status": "verified"}]},
        "confirmed_rows": []}


def _capture(monkeypatch):
    seen = {}

    def fake(structured, meta, out_path, layout=None):
        seen.update(meta=meta, layout=layout)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-1.4 fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)
    return seen


def _accept(c):
    tid = c.post("/api/v1/templates", files={"image": ("p.jpg", make_jpeg(), "image/jpeg")}).json()["id"]
    assert c.post(f"/api/v1/templates/{tid}/accept").status_code == 200
    return tid


def test_save_passes_active_layout_and_logo(tclient, monkeypatch):
    seen = _capture(monkeypatch)
    tid = _accept(tclient)
    assert tclient.post("/api/v1/documents", json=SAVE).status_code == 200
    assert seen["layout"] is not None and seen["meta"]["logo"].startswith("data:image/jpeg;base64,")
    assert seen["meta"]["profile"]["clinic_name"] == "Meridian Clinic" and seen["meta"]["patientName"] == "Anita"


def test_save_without_active_template_uses_builtin_layout(tclient, monkeypatch):
    seen = _capture(monkeypatch)
    assert tclient.post("/api/v1/documents", json=SAVE).status_code == 200
    assert seen["layout"] is None


def test_save_falls_back_when_stored_layout_is_invalid(tclient, monkeypatch):
    seen = _capture(monkeypatch)
    tid = _accept(tclient)
    conn = dbmod.get_conn()
    conn.execute("UPDATE templates SET layout_json = '{\"body\": 5}' WHERE id = ?", (tid,))
    conn.commit()
    conn.close()
    assert tclient.post("/api/v1/documents", json=SAVE).status_code == 200
    assert seen["layout"] is None
```

- [ ] **Step 2: Run, see failure**

Run: `.venv/bin/python -m pytest tests/test_template_save.py -q`
Expected: `AttributeError: ... has no attribute 'render_prescription'` (the persistence module still calls `render_pdf`).

- [ ] **Step 3: Implement**

In `api/persistence.py`, import `from doctor_dictation.pdf import render_prescription` and `from doctor_dictation.templates import service as template_service`, and replace the body of the existing fail-soft `try:` (the lines that call `build_sheet_html(...)` then `render_pdf(sheet, ...)`) with:

```python
            layout, logo_path = template_service.active_layout_for_save(conn)
            meta = {
                "date": dbmod._utcnow()[:10],
                "opNo": validated.get("opNo") or "",
                "patientName": validated.get("patientName") or "",
                "profile": _profile_dict(dbmod.get_profile(conn)),
            }
            if logo_path:
                meta["logo"] = template_service.logo_data_uri(logo_path)
            rendered = render_prescription(
                validated, meta, dbmod.pdf_dir() / f"encounter_{encounter_id}.pdf", layout=layout
            )
            pdf_path = str(rendered)
```

Keep the surrounding `except Exception: pdf_path = None` untouched. Remove the now-unused `build_sheet_html`/`render_pdf` imports from that module only if nothing else there uses them (`grep -n` first). If an existing test patches `render_pdf` in this module, change only its `monkeypatch.setattr` target line to `render_prescription` and make the fake accept `(*a, **k)`.

- [ ] **Step 4: Check the logo key against B2a, then run**

Run: `grep -n "logo" doctor_dictation/pdf/sheet.py`. Expected: the sheet builder reads `meta["logo"]` as a `data:image/...` URI (B2a). If it uses another key, change it in `api/persistence.py`, `api/templates.py` (`meta` in `preview`) and the two assertions above; nothing else.
Run: `.venv/bin/python -m pytest tests/test_template_save.py -q`
Expected: `3 passed`. Then the full suite; existing save tests (`tests/test_safety.py`) must still pass unchanged apart from any patched-name setup line.

- [ ] **Step 5:** Leave uncommitted.

---

### Task 7: Final verification

- [ ] **Step 1: Full suite.** Run `.venv/bin/python -m pytest tests/ -q`. Expected: `N + 58` passed (7 + 12 + 10 + 11 + 15 + 3), zero failures, no network (`grep -rn "api.openai.com" tests/test_template_*.py` prints nothing).
- [ ] **Step 2: Count check.** Run `.venv/bin/python -m pytest tests/test_template_*.py -q --co | tail -1`. Expected: `58 tests collected`. If the number differs, correct the "Adds 58 tests" line in this header and the expected final count, and say so in the report.
- [ ] **Step 3: Size rule.** Run `wc -l doctor_dictation/templates/*.py doctor_dictation/api/templates.py doctor_dictation/db/templates.py doctor_dictation/api/persistence.py`. Expected: every file under 500 lines.
- [ ] **Step 4: Run the app and exercise the flow once.** Create a phone-style photo and start the app against a scratch DB with the stub LLM:

```bash
S=$(mktemp -d)
.venv/bin/python -c "
from PIL import Image; im=Image.new('RGB',(1200,1600),(250,250,245)); im.save('$S/pad.jpg','JPEG')"
DB_PATH=$S/app.db LLM_PROVIDER=stub ALLOW_STUB_PROVIDERS=true \
STUB_LLM_JSON='{"header":[{"type":"text","field":"clinic_name","role":"title","align":"center"}],"footer":[],"body":{"top":0.2,"bottom":0.9},"profile":{"clinic_name":"Demo Clinic"}}' \
.venv/bin/uvicorn doctor_dictation.main:app --port 8001 &
sleep 3
curl -s -F image=@$S/pad.jpg localhost:8001/api/v1/templates -w ' %{http_code}\n'
curl -s -o $S/p.pdf -w '%{http_code}\n' localhost:8001/api/v1/templates/1/preview.pdf
curl -s -X POST localhost:8001/api/v1/templates/1/accept -w ' %{http_code}\n'
curl -s localhost:8001/api/v1/templates/active -w ' %{http_code}\n'
curl -s -o /dev/null -w '%{http_code}\n' localhost:8001/1_logo.jpg
ls $S/templates; kill %1
```

Expected: `201` with `status: draft`; preview `200` and `file $S/p.pdf` says `PDF document` (or `503` with "PDF renderer unavailable" if Chromium is not installed here; say which in the report); accept `200`; active `200`; the static URL `404`; `$S/templates` lists only `1_logo.jpg` (the original is gone after accept; this stub layout has no logo block, so the folder may be empty, which is also correct).
- [ ] **Step 5: Leave uncommitted** and list the changed files: `pyproject.toml`, `doctor_dictation/config.py`, `doctor_dictation/db/migrations/004_templates.sql`, `doctor_dictation/db/templates.py`, `doctor_dictation/templates/{__init__,images,builder,service}.py`, `doctor_dictation/api/{templates,app,persistence}.py`, `tests/template_fixtures.py`, `tests/test_template_{db,images,builder,service,routes,save}.py`.
- [ ] **Step 6: Report** anything not verified: a real vision model was not called (stub only); a real preview needs Chromium; the D0a `request.state.username` hook is untested until D0a.
