# B2b-1: Template Settings and Storage

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the template settings, the `templates` table migration and the database helpers.

**Architecture:** New package `doctor_dictation/templates/` (`images` cleans the file, `builder` calls the vision LLM and validates, `service` holds the rules: rate limit, TTL, accept, discard) behind `api/templates.py`. Storage is migration `004_templates.sql` plus `db/templates.py`. The document-save route passes the active layout to `render_prescription`. LLM output is untrusted: only the fixed vocabulary survives `validate_layout`.

**Tech Stack:** Python 3.12, FastAPI, sqlite3, Pillow, pillow-heif (new), pytest. No network in tests.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` section 7A (7A.1 to 7A.4, 7A.8) and 8.2; contracts `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md` sections 2, 4.1, 4.3 to 4.6.

**Plan 1 of 4 for B2b (the original single plan was split to respect the 500-line rule).** Task numbers keep their original B2b numbering (this plan contains Tasks 1). **Adds 7 tests.** Before the first task, run `.venv/bin/python -m pytest tests/ -q` and note the count `N`; the count after this plan must be `N + 7`.

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

None specific to this plan; the risks this feature carries are pinned in B2b-2 (images, injection), B2b-3 (quota) and B2b-4 (save fallback). The migration must be idempotent: Task 1 re-runs it and expects no error.

---

### Task 1: Settings, dependencies, migration and db helpers

**Files:**
- Create: `doctor_dictation/db/migrations/004_templates.sql`, `doctor_dictation/db/templates.py`, `tests/template_fixtures.py`, `tests/test_template_db.py`
- Modify: `doctor_dictation/config.py` (class `Settings`, function `build_settings`), `pyproject.toml`

**Interfaces:**
- Produces: `Settings.template_uploads_per_day, template_draft_ttl_hours, template_max_image_bytes, template_max_pixels`; `db.templates`: `create_template_draft(conn, layout, clinic="default", created_at=None) -> int`, `get_template(conn, id)`, `update_template_layout(conn, id, layout) -> bool`, `set_template_logo(conn, id, path)`, `set_template_active(conn, id, accepted_at=None) -> bool`, `delete_template(conn, id) -> bool`, `purge_expired_drafts(conn, cutoff_iso) -> list[Row]`, `count_uploads_since(conn, clinic, since_iso) -> int`, `get_active_template(conn, clinic="default")`.

- [ ] **Step 1: Write the shared fixtures and the failing tests**

`tests/template_fixtures.py` (no `test_` prefix, imported by the template test modules; pytest puts `tests/` on `sys.path`):

```python
"""Shared helpers for the template tests. Offline: stub LLM only."""
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from doctor_dictation import db as dbmod
from doctor_dictation.config import override_settings

PROFILE = {"doctor_name": "Dr A. Rao", "qualifications": "MBBS, MD", "reg_no": "TS-12345",
           "clinic_name": "Meridian Clinic", "address": "12 MG Road, Hyderabad", "phone": "040 1234 5678"}
GOOD_LAYOUT = {
    "header": [
        {"type": "logo", "crop": [0.05, 0.02, 0.25, 0.10], "align": "left"},
        {"type": "text", "field": "doctor_name", "role": "title", "align": "center", "color": "#1a3c6e"},
        {"type": "text", "text": "Open Mon to Sat", "role": "small", "align": "center"},
        {"type": "rule", "color": "#1a3c6e", "thickness": "thin"},
    ],
    "footer": [{"type": "text", "field": "address", "role": "small", "align": "center"}],
    "body": {"top": 0.22, "bottom": 0.92},
    "profile": PROFILE,
}


def make_jpeg(size=(800, 1000), color=(240, 240, 255)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "JPEG")
    return b.getvalue()


@pytest.fixture()
def tconn(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    c = dbmod.get_conn()
    dbmod.migrate(c)
    yield c
    c.close()


@pytest.fixture()
def tclient(tmp_path, monkeypatch):
    """App with the stub LLM returning GOOD_LAYOUT; temp DB; lifespan runs."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(GOOD_LAYOUT))
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True)
    from doctor_dictation.api.app import create_app
    with TestClient(create_app()) as c:
        yield c
```

`tests/test_template_db.py`:

```python
import json
import sqlite3

import pytest

from doctor_dictation.config import get_settings
from doctor_dictation.db import templates as tdb
from template_fixtures import GOOD_LAYOUT, tconn  # noqa: F401


def test_settings_defaults():
    s = get_settings()
    assert (s.template_uploads_per_day, s.template_draft_ttl_hours) == (10, 24)
    assert s.template_max_image_bytes == 8 * 1024 * 1024 and s.template_max_pixels == 40_000_000


def test_migration_creates_table_and_status_check(tconn):
    cols = {r["name"] for r in tconn.execute("PRAGMA table_info(templates)")}
    assert {"id", "clinic", "layout_json", "logo_path", "status", "created_at", "accepted_at"} <= cols
    with pytest.raises(sqlite3.IntegrityError):
        tconn.execute("INSERT INTO templates(layout_json, status, created_at) VALUES ('{}', 'bogus', 'x')")


def test_create_get_update_layout(tconn):
    tid = tdb.create_template_draft(tconn, GOOD_LAYOUT)
    row = tdb.get_template(tconn, tid)
    assert row["status"] == "draft" and json.loads(row["layout_json"]) == GOOD_LAYOUT
    assert tdb.update_template_layout(tconn, tid, {"x": 1}) is True
    assert json.loads(tdb.get_template(tconn, tid)["layout_json"]) == {"x": 1}
    assert tdb.update_template_layout(tconn, 999, {}) is False


def test_set_active_archives_previous_and_scopes_to_clinic(tconn):
    a, b = (tdb.create_template_draft(tconn, GOOD_LAYOUT) for _ in range(2))
    other = tdb.create_template_draft(tconn, GOOD_LAYOUT, clinic="other")
    assert tdb.set_template_active(tconn, a) and tdb.set_template_active(tconn, other)
    assert tdb.set_template_active(tconn, b)
    status = {r["id"]: r["status"] for r in tconn.execute("SELECT id, status FROM templates")}
    assert status == {a: "archived", b: "active", other: "active"}
    assert tdb.get_active_template(tconn)["id"] == b
    assert tdb.set_template_active(tconn, a) is False  # archived is not a draft


def test_get_active_none_when_empty(tconn):
    assert tdb.get_active_template(tconn) is None


def test_delete_and_purge_only_expired_drafts(tconn):
    old = tdb.create_template_draft(tconn, GOOD_LAYOUT, created_at="2026-10-01T00:00:00Z")
    fresh = tdb.create_template_draft(tconn, GOOD_LAYOUT, created_at="2026-10-13T00:00:00Z")
    act = tdb.create_template_draft(tconn, GOOD_LAYOUT, created_at="2026-09-01T00:00:00Z")
    tdb.set_template_active(tconn, act)
    gone = tdb.purge_expired_drafts(tconn, "2026-10-12T00:00:00Z")
    assert [r["id"] for r in gone] == [old]
    assert tdb.get_template(tconn, fresh) and tdb.get_template(tconn, act)
    assert tdb.delete_template(tconn, fresh) is True and tdb.delete_template(tconn, fresh) is False


def test_count_uploads_since_counts_audit_rows_per_clinic(tconn):
    from doctor_dictation import db as dbmod
    for clinic, at in [("default", "2026-10-13T01:00:00Z"), ("default", "2026-10-12T23:59:59Z"), ("other", "2026-10-13T02:00:00Z")]:
        dbmod.log_audit(tconn, action="template_upload", entity="template", detail={"clinic": clinic}, at=at)
    assert tdb.count_uploads_since(tconn, "default", "2026-10-13T00:00:00Z") == 1
```

- [ ] **Step 2: Run, see failures**

Run: `.venv/bin/python -m pytest tests/test_template_db.py -q`
Expected: collection error `ModuleNotFoundError: doctor_dictation.db.templates`.

- [ ] **Step 3: Implement**

`doctor_dictation/db/migrations/004_templates.sql` (exactly contract 4.4):

```sql
CREATE TABLE IF NOT EXISTS templates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    clinic      TEXT NOT NULL DEFAULT 'default',
    layout_json TEXT NOT NULL,
    logo_path   TEXT,
    status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','archived')),
    created_at  TEXT NOT NULL,
    accepted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_templates_status ON templates(clinic, status);
```

`doctor_dictation/db/templates.py`:

```python
"""Template storage helpers (contract 4.4). Callers own the connection."""
import json

from doctor_dictation.db import _utcnow


def create_template_draft(conn, layout: dict, clinic="default", created_at=None) -> int:
    cur = conn.execute(
        "INSERT INTO templates(clinic, layout_json, status, created_at) VALUES (?, ?, 'draft', ?)",
        (clinic, json.dumps(layout, ensure_ascii=False), created_at or _utcnow()))
    conn.commit()
    return cur.lastrowid


def get_template(conn, template_id):
    return conn.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()


def update_template_layout(conn, template_id, layout: dict) -> bool:
    cur = conn.execute("UPDATE templates SET layout_json = ? WHERE id = ?",
                       (json.dumps(layout, ensure_ascii=False), template_id))
    conn.commit()
    return cur.rowcount > 0


def set_template_logo(conn, template_id, logo_path) -> None:
    conn.execute("UPDATE templates SET logo_path = ? WHERE id = ?", (logo_path, template_id))
    conn.commit()


def set_template_active(conn, template_id, accepted_at=None) -> bool:
    """Draft -> active; the clinic's previous active row becomes archived (one commit)."""
    row = get_template(conn, template_id)
    if row is None or row["status"] != "draft":
        return False
    conn.execute("UPDATE templates SET status = 'archived' WHERE clinic = ? AND status = 'active'",
                 (row["clinic"],))
    conn.execute("UPDATE templates SET status = 'active', accepted_at = ? WHERE id = ?",
                 (accepted_at or _utcnow(), template_id))
    conn.commit()
    return True


def delete_template(conn, template_id) -> bool:
    cur = conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))
    conn.commit()
    return cur.rowcount > 0


def purge_expired_drafts(conn, cutoff_iso: str) -> list:
    """Delete drafts created before ``cutoff_iso``; return the deleted rows (id, logo_path)."""
    rows = conn.execute("SELECT id, logo_path FROM templates WHERE status = 'draft' AND created_at < ?",
                        (cutoff_iso,)).fetchall()
    conn.execute("DELETE FROM templates WHERE status = 'draft' AND created_at < ?", (cutoff_iso,))
    conn.commit()
    return rows


def count_uploads_since(conn, clinic: str, since_iso: str) -> int:
    """Uploads are counted from audit_log, so discarding or purging a draft cannot reset the quota."""
    return conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE action = 'template_upload'"
        " AND json_extract(detail, '$.clinic') = ? AND at >= ?", (clinic, since_iso)).fetchone()[0]


def get_active_template(conn, clinic="default"):
    return conn.execute("SELECT * FROM templates WHERE clinic = ? AND status = 'active'", (clinic,)).fetchone()
```

In `doctor_dictation/config.py`, append to `Settings` (defaults keep the dataclass valid after any default-bearing fields from earlier plans):

```python
    template_uploads_per_day: int = 10
    template_draft_ttl_hours: int = 24
    template_max_image_bytes: int = 8 * 1024 * 1024
    template_max_pixels: int = 40_000_000
```

and in `build_settings()` add to the `Settings(...)` call:

```python
        template_uploads_per_day=_int_env("TEMPLATE_UPLOADS_PER_DAY", 10),
        template_draft_ttl_hours=_int_env("TEMPLATE_DRAFT_TTL_HOURS", 24),
        template_max_image_bytes=_int_env("TEMPLATE_MAX_IMAGE_BYTES", 8 * 1024 * 1024),
        template_max_pixels=_int_env("TEMPLATE_MAX_PIXELS", 40_000_000),
```

In `pyproject.toml` add to `dependencies`: `"pillow>=11,<13",` and `"pillow-heif>=1.0",`. Install: `.venv/bin/pip install "pillow>=11,<13" "pillow-heif>=1.0"`.

- [ ] **Step 4: Run, see pass**

Run: `.venv/bin/python -m pytest tests/test_template_db.py -q`
Expected: `7 passed`. Then the full suite: count is `N + 7`, no regressions (the migration list test in `tests/test_db.py` may enumerate tables or migration versions; if it asserts the exact set, add `templates` / `004_templates.sql` to that expectation only).

- [ ] **Step 5:** Leave uncommitted.

---
