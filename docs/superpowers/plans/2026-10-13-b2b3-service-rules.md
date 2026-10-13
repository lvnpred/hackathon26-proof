# B2b-3: Template Service Rules

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement rate limiting, draft expiry, edit, accept and discard.

**Architecture:** New package `doctor_dictation/templates/` (`images` cleans the file, `builder` calls the vision LLM and validates, `service` holds the rules: rate limit, TTL, accept, discard) behind `api/templates.py`. Storage is migration `004_templates.sql` plus `db/templates.py`. The document-save route passes the active layout to `render_prescription`. LLM output is untrusted: only the fixed vocabulary survives `validate_layout`.

**Tech Stack:** Python 3.12, FastAPI, sqlite3, Pillow, pillow-heif (new), pytest. No network in tests.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` section 7A (7A.1 to 7A.4, 7A.8) and 8.2; contracts `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md` sections 2, 4.1, 4.3 to 4.6.

**Plan 3 of 4 for B2b. Prerequisite: B2b-1 and B2b-2 applied.** Task numbers keep their original B2b numbering (this plan contains Tasks 4). **Adds 11 tests.** Before the first task, run `.venv/bin/python -m pytest tests/ -q` and note the count `N`; the count after this plan must be `N + 11`.

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

4. A bad-image upload must not use up the daily quota; a failed LLM call must (Task 4, `test_rate_limit_boundary`).

---

### Task 4: Service rules

**Files:**
- Create: `doctor_dictation/templates/service.py`, `tests/test_template_service.py`

**Interfaces:**
- Consumes: Tasks 1 to 3.
- Produces: `CLINIC`, `FIELDS`, `templates_dir() -> Path`, `original_path(id) -> Path`, `view(row) -> {id, status, layout, profile}`, `purge_expired(conn, settings, now=None) -> int`, `async upload(conn, raw, settings, actor=None, now=None) -> dict`, `edit(conn, id, profile, lines, actor=None) -> dict`, `accept(conn, id, actor=None) -> dict`, `discard(conn, id, actor=None) -> None`, `get_active(conn) -> dict | None`, `active_layout_for_save(conn) -> tuple[Layout | None, str | None]` (second item: the logo file path), `logo_data_uri(path) -> str | None`. Errors: `TemplateError` 400, 404, 409, 429 (plus those from Tasks 2 and 3).

- [ ] **Step 1: Write the failing tests**

```python
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation.config import get_settings, override_settings
from doctor_dictation.db import templates as tdb
from doctor_dictation.templates import TemplateError, service
from template_fixtures import GOOD_LAYOUT, make_jpeg, tconn  # noqa: F401


@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch):
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(GOOD_LAYOUT))
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True)


def _up(conn, actor=None, raw=None):
    return asyncio.run(service.upload(conn, raw or make_jpeg(), get_settings(), actor=actor))


def _audit(conn):
    return [(r["action"], r["actor"]) for r in conn.execute("SELECT action, actor FROM audit_log ORDER BY id")]


def test_upload_stores_draft_files_and_audit(tconn):
    v = _up(tconn, actor="demo")
    assert v["status"] == "draft" and v["profile"]["clinic_name"] == "Meridian Clinic" and "profile" not in v["layout"]
    row = tdb.get_template(tconn, v["id"])
    assert service.original_path(v["id"]).exists() and row["logo_path"] and (service.templates_dir() / f"{v['id']}_logo.jpg").exists()
    assert _audit(tconn) == [("template_upload", "demo")]


def test_invalid_llm_output_stores_nothing(tconn, monkeypatch):
    bad = json.loads(json.dumps(GOOD_LAYOUT))
    bad["body"] = {"top": 0.9, "bottom": 0.1}
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(bad))
    with pytest.raises(TemplateError) as e:
        _up(tconn)
    assert e.value.status == 502
    assert tconn.execute("SELECT COUNT(*) FROM templates").fetchone()[0] == 0
    assert not service.templates_dir().exists() or list(service.templates_dir().iterdir()) == []


def test_rate_limit_boundary(tconn, monkeypatch):
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, template_uploads_per_day=2)
    with pytest.raises(TemplateError) as e0:   # a bad image never reaches the quota
        _up(tconn, raw=b"not an image")
    assert e0.value.status == 400
    _up(tconn)
    _up(tconn)
    with pytest.raises(TemplateError) as e:
        _up(tconn)
    assert e.value.status == 429
    assert tdb.count_uploads_since(tconn, "default", "2000-01-01T00:00:00Z") == 2


def test_failed_llm_call_still_counts_toward_limit(tconn, monkeypatch):
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, template_uploads_per_day=1)
    monkeypatch.setenv("STUB_LLM_JSON", "{}")
    with pytest.raises(TemplateError):
        _up(tconn)
    with pytest.raises(TemplateError) as e:
        _up(tconn)
    assert e.value.status == 429


def test_purge_expired_removes_row_and_files_keeps_active(tconn):
    v = _up(tconn)
    keep = _up(tconn)
    tdb.set_template_active(tconn, keep["id"])
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
    tconn.execute("UPDATE templates SET created_at = ?", (old,))
    tconn.commit()
    assert service.purge_expired(tconn, get_settings()) == 1
    assert tdb.get_template(tconn, v["id"]) is None and not service.original_path(v["id"]).exists()
    assert not (service.templates_dir() / f"{v['id']}_logo.jpg").exists()
    assert tdb.get_template(tconn, keep["id"])["status"] == "active"


def test_upload_purges_lazily(tconn):
    v = _up(tconn)
    old = (datetime.now(timezone.utc) - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    tconn.execute("UPDATE templates SET created_at = ? WHERE id = ?", (old, v["id"]))
    tconn.commit()
    _up(tconn)
    assert tdb.get_template(tconn, v["id"]) is None


def test_accept_archives_previous_saves_profile_deletes_original(tconn):
    first, second = _up(tconn), _up(tconn)
    service.accept(tconn, first["id"], actor="demo")
    out = service.accept(tconn, second["id"], actor="demo")
    assert out["status"] == "active" and tdb.get_template(tconn, first["id"])["status"] == "archived"
    assert dbmod.get_profile(tconn)["clinic_name"] == "Meridian Clinic"
    assert not service.original_path(second["id"]).exists()
    assert (service.templates_dir() / f"{second['id']}_logo.jpg").exists()   # the small logo crop is kept
    assert ("template_accept", "demo") in _audit(tconn)
    assert service.get_active(tconn)["id"] == second["id"]


def test_accept_or_edit_non_draft_is_409_and_missing_is_404(tconn):
    v = _up(tconn)
    service.accept(tconn, v["id"])
    for call in (lambda: service.accept(tconn, v["id"]), lambda: service.edit(tconn, v["id"], {}, [])):
        with pytest.raises(TemplateError) as e:
            call()
        assert e.value.status == 409
    with pytest.raises(TemplateError) as e:
        service.accept(tconn, 999)
    assert e.value.status == 404


def test_discard_deletes_row_files_and_audits(tconn):
    v = _up(tconn)
    service.discard(tconn, v["id"], actor="demo")
    assert tdb.get_template(tconn, v["id"]) is None and not service.original_path(v["id"]).exists()
    assert ("template_discard", "demo") in _audit(tconn)
    with pytest.raises(TemplateError) as e:
        service.discard(tconn, v["id"])
    assert e.value.status == 404


def test_edit_profile_and_literal_line_revalidated(tconn):
    v = _up(tconn)
    out = service.edit(tconn, v["id"], {"phone": " 99999 "}, [{"section": "header", "index": 2, "text": "Open daily"}])
    assert out["profile"]["phone"] == "99999" and out["layout"]["header"][2]["text"] == "Open daily"
    for profile, lines in (({"ssn": "x"}, []), ({}, [{"section": "header", "index": 1, "text": "x"}]),
                           ({}, [{"section": "header", "index": 9, "text": "x"}]),
                           ({}, [{"section": "header", "index": 2, "text": "y" * 201}]),
                           ({}, [{"section": "profile", "index": 0, "text": "x"}])):
        with pytest.raises(TemplateError) as e:
            service.edit(tconn, v["id"], profile, lines)
        assert e.value.status == 400
    assert service.view(tdb.get_template(tconn, v["id"]))["layout"]["header"][2]["text"] == "Open daily"


def test_active_layout_for_save_falls_back_when_stored_layout_is_invalid(tconn):
    assert service.active_layout_for_save(tconn) == (None, None)
    v = _up(tconn)
    service.accept(tconn, v["id"])
    layout, logo = service.active_layout_for_save(tconn)
    assert layout is not None and logo.endswith(f"{v['id']}_logo.jpg")
    assert service.logo_data_uri(logo).startswith("data:image/jpeg;base64,") and service.logo_data_uri("/no/such.jpg") is None
    tconn.execute("UPDATE templates SET layout_json = '{\"body\": 5}' WHERE id = ?", (v["id"],))
    tconn.commit()
    assert service.active_layout_for_save(tconn) == (None, None)
```

- [ ] **Step 2: Run, see failure**

Run: `.venv/bin/python -m pytest tests/test_template_service.py -q`
Expected: `ImportError: cannot import name 'service'`.

- [ ] **Step 3: Implement `doctor_dictation/templates/service.py`**

```python
"""Template rules: quota, TTL, edit, accept, discard. Callers own the connection."""
from __future__ import annotations

import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from doctor_dictation import db as dbmod
from doctor_dictation.db import templates as tdb
from doctor_dictation.pdf import LayoutError, validate_layout
from doctor_dictation.templates import TemplateError
from doctor_dictation.templates.builder import PROFILE_FIELDS as FIELDS, build_draft
from doctor_dictation.templates.images import clean_image

CLINIC = "default"
_FMT = "%Y-%m-%dT%H:%M:%SZ"


def templates_dir() -> Path:
    """Private folder next to the DB; never under frontend/ or any static mount."""
    return dbmod.db_path().parent / "templates"


def original_path(template_id: int) -> Path:
    return templates_dir() / f"{template_id}_original.jpg"


def _unlink(*paths) -> None:
    for p in paths:
        if p:
            Path(p).unlink(missing_ok=True)


def view(row) -> dict:
    lay = json.loads(row["layout_json"])
    return {"id": row["id"], "status": row["status"],
            "layout": {k: v for k, v in lay.items() if k != "profile"}, "profile": lay.get("profile", {})}


def purge_expired(conn, settings, now=None) -> int:
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=settings.template_draft_ttl_hours)).strftime(_FMT)
    rows = tdb.purge_expired_drafts(conn, cutoff)
    for r in rows:
        _unlink(r["logo_path"], original_path(r["id"]))
    return len(rows)


async def upload(conn, raw: bytes, settings, actor=None, now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    purge_expired(conn, settings, now)
    jpeg = await asyncio.to_thread(clean_image, raw, max_bytes=settings.template_max_image_bytes,
                                   max_pixels=settings.template_max_pixels)
    since = now.replace(hour=0, minute=0, second=0, microsecond=0).strftime(_FMT)
    if tdb.count_uploads_since(conn, CLINIC, since) >= settings.template_uploads_per_day:
        raise TemplateError(429, "daily template upload limit reached")
    # Logged before the LLM call: each attempt costs a call, so a failure still counts.
    dbmod.log_audit(conn, actor=actor, action="template_upload", entity="template",
                    detail={"clinic": CLINIC, "bytes": len(raw)}, at=now.strftime(_FMT))
    draft = await build_draft(jpeg, settings)
    tid = tdb.create_template_draft(conn, draft.layout, CLINIC, created_at=now.strftime(_FMT))
    templates_dir().mkdir(parents=True, exist_ok=True)
    original_path(tid).write_bytes(jpeg)
    if draft.logo_jpeg:
        logo = templates_dir() / f"{tid}_logo.jpg"
        logo.write_bytes(draft.logo_jpeg)
        tdb.set_template_logo(conn, tid, str(logo))
    return view(tdb.get_template(conn, tid))


def _draft(conn, template_id):
    row = tdb.get_template(conn, template_id)
    if row is None:
        raise TemplateError(404, "template not found")
    if row["status"] != "draft":
        raise TemplateError(409, "only a draft can be changed")
    return row


def edit(conn, template_id: int, profile: dict, lines: list, actor=None) -> dict:
    row = _draft(conn, template_id)
    lay = json.loads(row["layout_json"])
    for key, value in (profile or {}).items():
        if key not in FIELDS or not isinstance(value, str):
            raise TemplateError(400, f"unknown or non-text profile field: {key}")
        lay["profile"][key] = value.strip()
    for ln in lines or []:
        section, index = ln.get("section"), ln.get("index")
        if section not in ("header", "footer") or not isinstance(index, int) or not 0 <= index < len(lay[section]):
            raise TemplateError(400, "no such line")
        block = lay[section][index]
        if block.get("type") != "text" or "text" not in block:
            raise TemplateError(400, "only literal text lines can be edited")
        block["text"] = str(ln.get("text", "")).strip()
    try:
        validate_layout(lay)
    except LayoutError as exc:
        raise TemplateError(400, f"edit rejected: {exc}") from None
    tdb.update_template_layout(conn, template_id, lay)
    return view(tdb.get_template(conn, template_id))


def accept(conn, template_id: int, actor=None) -> dict:
    row = _draft(conn, template_id)
    prof = json.loads(row["layout_json"]).get("profile", {})
    tdb.set_template_active(conn, template_id)
    dbmod.save_profile(conn, **{k: prof.get(k, "") for k in FIELDS})
    _unlink(original_path(template_id))
    dbmod.log_audit(conn, actor=actor, action="template_accept", entity="template",
                    entity_id=str(template_id), detail={"clinic": row["clinic"]})
    return view(tdb.get_template(conn, template_id))


def discard(conn, template_id: int, actor=None) -> None:
    row = _draft(conn, template_id)
    tdb.delete_template(conn, template_id)
    _unlink(row["logo_path"], original_path(template_id))
    dbmod.log_audit(conn, actor=actor, action="template_discard", entity="template",
                    entity_id=str(template_id), detail={"clinic": row["clinic"]})


def get_active(conn) -> dict | None:
    row = tdb.get_active_template(conn, CLINIC)
    return view(row) if row else None


def active_layout_for_save(conn):
    """(Layout, logo_path) of the active template, or (None, None) so saves use the built-in layout."""
    row = tdb.get_active_template(conn, CLINIC)
    if row is None:
        return None, None
    try:
        return validate_layout(json.loads(row["layout_json"])), row["logo_path"]
    except (LayoutError, ValueError):
        return None, None


def logo_data_uri(path) -> str | None:
    """The stored logo crop as a data URI for the PDF builder, or None when missing."""
    try:
        return "data:image/jpeg;base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")
    except (OSError, TypeError):
        return None
```

- [ ] **Step 4: Run, see pass**

Run: `.venv/bin/python -m pytest tests/test_template_service.py -q`
Expected: `11 passed`.

- [ ] **Step 5:** Leave uncommitted.

---
