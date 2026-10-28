# B2d: Stop Using an Accepted Letterhead Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a clinic switch back to the built-in prescription layout after it has accepted a letterhead, with one route and one button.

**Architecture:** One db helper and one service function archive the clinic's active template (the draft flow is untouched); one `POST /api/v1/templates/deactivate` route exposes it; one button in the Letterhead panel calls it. Nothing is deleted: the archived template and its logo crop stay on disk.

**Tech Stack:** Python 3.12, FastAPI, sqlite3, pytest, vanilla JS. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` section 7A.1 ("if the clinic never accepts one, PDFs use the built-in layout") and the user's request for a fallback to the profile details. Contract: `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md` section 4.6 (the `deactivate` row). B2c found that contract 4.6 had no way to undo an accepted template; this plan closes that gap.

**Adds 6 tests.** Before Task 1, run `.venv/bin/python -m pytest tests/ -q` and note the count `N`; the final count must be `N + 6`.

## Assumptions about earlier plans

Locate each with `grep -n` before use; if a name differs, change only that line.
- B2b-1: `doctor_dictation/db/templates.py` (helpers `get_template`, `set_template_active`, `get_active_template`, each taking an open `conn`), and `tests/template_fixtures.py` with `GOOD_LAYOUT`, `make_jpeg`, `tconn`, `tclient`.
- B2b-3: `doctor_dictation/templates/service.py` has `CLINIC`, `upload`, `accept`, `get_active`, `active_layout_for_save`, and imports `dbmod` and `tdb`; audit rows go through `dbmod.log_audit(conn, actor=..., action=..., entity=..., entity_id=..., detail=...)`.
- B2b-4: `doctor_dictation/api/templates.py` has `router`, `_open()`, `_actor(request)` and the `GET /active` route.
- B2c: `frontend/letterhead.js` (one IIFE) with `el`, `call`, `showErr`, `setBusy`, `httpMessage`, `netMessage`, `refreshStatus`, `API`, and the markup in `frontend/index.html` (`#lhStatus`, `#lhDone`).

## Global Constraints

- No file over 500 lines. Never run `git commit` or `git push` (user rule); every task ends with "leave uncommitted".
- Tests never touch the network: the stub LLM provider (`STUB_LLM_JSON`) with `allow_stub_providers`. A real key sits in `.env` and is loaded by `load_dotenv()`.
- Routes and services read `get_settings()` at call time, never at import.
- Existing status codes and JSON shapes do not change; the new route only adds.

## Review Focus

1. Deactivating when nothing is active must succeed quietly: `{"deactivated": false}`, no audit row (Task 1 and Task 2).
2. A pending draft must not be touched by deactivating the active template (Task 1).
3. After deactivating, a save must use the built-in layout, not the archived one (Task 1).

---

### Task 1: Database helper and service function

**Files:**
- Modify: `doctor_dictation/db/templates.py` (append after `get_active_template`)
- Modify: `doctor_dictation/templates/service.py` (append after `get_active`)
- Create: `tests/test_template_deactivate.py`

**Interfaces:**
- Consumes: `tdb.get_active_template(conn, clinic)`, `service.CLINIC`, `dbmod.log_audit`.
- Produces: `tdb.deactivate_templates(conn, clinic="default") -> int` (rows archived), `service.deactivate(conn, actor=None) -> bool` (True when a template was archived).

- [ ] **Step 1: Write the failing tests** — create `tests/test_template_deactivate.py`:

```python
import asyncio
import json

import pytest

from doctor_dictation.config import get_settings, override_settings
from doctor_dictation.db import templates as tdb
from doctor_dictation.templates import service
from template_fixtures import GOOD_LAYOUT, make_jpeg, tclient, tconn  # noqa: F401

URL = "/api/v1/templates"


@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch):
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(GOOD_LAYOUT))
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True)


def _draft(conn):
    return asyncio.run(service.upload(conn, make_jpeg(), get_settings(), actor=None))["id"]


def _accepted(conn):
    tid = _draft(conn)
    service.accept(conn, tid)
    return tid


def _audit(conn):
    return [(r["action"], r["actor"], r["entity_id"])
            for r in conn.execute("SELECT action, actor, entity_id FROM audit_log ORDER BY id")]


def test_deactivate_archives_the_active_template_and_audits(tconn):
    tid = _accepted(tconn)
    assert service.deactivate(tconn, actor="demo") is True
    assert service.get_active(tconn) is None
    assert tdb.get_template(tconn, tid)["status"] == "archived"
    assert ("template_deactivate", "demo", str(tid)) in _audit(tconn)


def test_deactivate_without_an_active_template_is_false_and_writes_no_audit(tconn):  # Review Focus #1
    before = _audit(tconn)
    assert service.deactivate(tconn) is False
    assert _audit(tconn) == before


def test_deactivate_leaves_a_pending_draft_alone(tconn):  # Review Focus #2
    _accepted(tconn)
    draft = _draft(tconn)
    service.deactivate(tconn)
    assert tdb.get_template(tconn, draft)["status"] == "draft"


def test_saves_use_the_builtin_layout_after_deactivate(tconn):  # Review Focus #3
    _accepted(tconn)
    assert service.active_layout_for_save(tconn)[0] is not None
    service.deactivate(tconn)
    assert service.active_layout_for_save(tconn) == (None, None)
```

- [ ] **Step 2: Run, see failure**

Run: `.venv/bin/python -m pytest tests/test_template_deactivate.py -q`
Expected: 4 failed with `AttributeError: module 'doctor_dictation.templates.service' has no attribute 'deactivate'`.

- [ ] **Step 3: Implement.** Append to `doctor_dictation/db/templates.py`:

```python
def deactivate_templates(conn, clinic="default") -> int:
    """Active -> archived for the clinic (drafts are untouched); returns the rows changed."""
    cur = conn.execute("UPDATE templates SET status = 'archived' WHERE clinic = ? AND status = 'active'", (clinic,))
    conn.commit()
    return cur.rowcount
```

Append to `doctor_dictation/templates/service.py`:

```python
def deactivate(conn, actor=None) -> bool:
    """Stop using the accepted letterhead: saves print on the built-in layout again."""
    row = tdb.get_active_template(conn, CLINIC)
    if row is None:
        return False
    tdb.deactivate_templates(conn, CLINIC)
    dbmod.log_audit(conn, actor=actor, action="template_deactivate", entity="template",
                    entity_id=str(row["id"]), detail={"clinic": CLINIC})
    return True
```

- [ ] **Step 4: Run, see pass**

Run: `.venv/bin/python -m pytest tests/test_template_deactivate.py -q`
Expected: `4 passed`.

- [ ] **Step 5:** Leave uncommitted.

---

### Task 2: The route

**Files:**
- Modify: `doctor_dictation/api/templates.py` (insert directly after the `get_active` route; locate with `grep -n "def get_active" doctor_dictation/api/templates.py`)
- Modify: `tests/test_template_deactivate.py` (append)

**Interfaces:**
- Consumes: `service.deactivate`, `_open()`, `_actor(request)`.
- Produces: `POST /api/v1/templates/deactivate` returning `{"deactivated": bool}` with status 200 in both cases.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_template_deactivate.py`:

```python
def test_route_deactivate_then_no_active_template(tclient):
    tid = tclient.post(URL, files={"image": ("p.jpg", make_jpeg(), "image/jpeg")}).json()["id"]
    assert tclient.post(f"{URL}/{tid}/accept").status_code == 200
    assert tclient.get(URL + "/active").status_code == 200
    r = tclient.post(URL + "/deactivate")
    assert r.status_code == 200 and r.json() == {"deactivated": True}
    assert tclient.get(URL + "/active").status_code == 404


def test_route_deactivate_twice_is_idempotent(tclient):
    assert tclient.post(URL + "/deactivate").json() == {"deactivated": False}
    assert tclient.post(URL + "/deactivate").status_code == 200
```

- [ ] **Step 2: Run, see failure**

Run: `.venv/bin/python -m pytest tests/test_template_deactivate.py -q -k route`
Expected: 2 failed on the status code (404 or 405: the route does not exist).

- [ ] **Step 3: Implement.** Insert in `doctor_dictation/api/templates.py` after the `get_active` function:

```python
@router.post("/deactivate")
def deactivate(request: Request):
    conn = _open()
    try:
        return {"deactivated": service.deactivate(conn, actor=_actor(request))}
    finally:
        conn.close()
```

- [ ] **Step 4: Run, see pass**

Run: `.venv/bin/python -m pytest tests/test_template_deactivate.py -q` then `.venv/bin/python -m pytest tests/ -q`
Expected: `6 passed`, then `N + 6` passed in total.

- [ ] **Step 5:** Leave uncommitted.

---

### Task 3: The button in the Letterhead panel

**Files:**
- Modify: `frontend/index.html` (button after `#lhStatus`; script version), `frontend/letterhead.js` (`refreshStatus`, new `stopUsing`, listener), `frontend/letterhead.css` (append one rule)

**Interfaces:**
- Consumes: `POST /api/v1/templates/deactivate`; the B2c helpers listed above.
- Produces: element `#lhStopBtn`, visible only while an active template exists.

- [ ] **Step 1: Markup and style.** In `frontend/index.html` directly after the line `<p id="lhStatus" class="lh-current" role="status" aria-live="polite"></p>` add:

```html
      <button id="lhStopBtn" type="button" class="lh-act lh-stop" hidden>Stop using this letterhead</button>
```

Bump the cache-busting numbers: `letterhead.js?v=1` becomes `letterhead.js?v=2` and `letterhead.css?v=1` becomes `letterhead.css?v=2`. Append to `frontend/letterhead.css`:

```css
.lh-stop { margin: 0 0 .75rem; }
```

- [ ] **Step 2: Status and handler.** In `frontend/letterhead.js` replace `refreshStatus` with:

```js
  async function refreshStatus() {
    try {
      const r = await call(API + "/active");
      el("lhStopBtn").hidden = r.status !== 200;
      status(r.status === 200 ? "Your own letterhead is active: prescriptions print on it."
        : r.status === 404 ? "Using the built-in layout (no letterhead is active)."
        : "Could not check the current letterhead (code " + r.status + ").");
    } catch (e) { el("lhStopBtn").hidden = true; status("Could not check the current letterhead. " + netMessage(e)); }
  }
```

Insert directly above the line `el("letterheadOpenBtn").addEventListener("click", openPanel);`:

```js
  async function stopUsing() {
    if (!window.confirm("Prescriptions will print on the built-in layout again. Your accepted letterhead is kept but no longer used. Continue?")) return;
    showErr(""); setBusy(true, "Switching to the built-in layout…");
    try {
      const r = await call(API + "/deactivate", { method: "POST" });
      if (!r.ok) { showErr(httpMessage(r.status, "stop")); return; }
      await refreshStatus();
      el("lhDone").hidden = false;
      el("lhDone").textContent = "Done. Prescriptions now print on the built-in layout with your clinic details.";
    } catch (e) { showErr(netMessage(e)); } finally { setBusy(false); }
  }
```

and next to the other listeners add `el("lhStopBtn").addEventListener("click", stopUsing);`.

- [ ] **Step 3: Browser check (look at every screenshot).** Start the server and walk the flow exactly as plan B2c Task 2 does (stub provider with `ALLOW_STUB_PROVIDERS=1 LLM_PROVIDER=stub STUB_LLM_JSON=<the layout JSON from that plan>`, the generated `pad.png`, a free port). Then, with the Playwright browser tools at 1280x720:
  1. Open the Letterhead panel before any template exists. Expected: status says "Using the built-in layout (no letterhead is active).", and `#lhStopBtn` is hidden.
  2. Upload, Accept. Expected: status "Your own letterhead is active: ...", and `#lhStopBtn` visible under it. Screenshot: the button is readable and not clipped.
  3. Click `#lhStopBtn`, and dismiss the confirm dialog with Cancel (`browser_handle_dialog` with accept false). Expected: nothing changes (status unchanged).
  4. Click it again and accept the dialog. Expected: `#lhDone` reads "Done. Prescriptions now print on the built-in layout ...", the status line reads "Using the built-in layout (no letterhead is active).", and the button is hidden again.
  5. Run `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:<port>/api/v1/templates/active`. Expected: `404`.
  6. Keyboard: reload, upload and accept again, press Tab until `#lhStopBtn` has a visible focus ring, press Enter, accept the dialog. Expected: same result as step 4.

- [ ] **Step 4:** Leave uncommitted.

---

### Task 4: Final verification

- [ ] **Step 1: Full suite.** Run `.venv/bin/python -m pytest tests/ -q`. Expected: `N + 6` passed, no network (`grep -rn "api.openai.com" tests/test_template_deactivate.py` prints nothing).
- [ ] **Step 2: Size rule.** Run `wc -l doctor_dictation/templates/service.py doctor_dictation/api/templates.py doctor_dictation/db/templates.py frontend/letterhead.js`. Expected: every file under 500 lines.
- [ ] **Step 3: One live pass.** With the running app and a real accepted template, save a document through the page, stop using the letterhead, save again, and compare the two PDFs by eye (the second uses the built-in layout with the clinic details). State in the report if you could not do this.
- [ ] **Step 4: Report** the changed files (`doctor_dictation/db/templates.py`, `doctor_dictation/templates/service.py`, `doctor_dictation/api/templates.py`, `frontend/index.html`, `frontend/letterhead.js`, `frontend/letterhead.css`, `tests/test_template_deactivate.py`), the test count, and anything not verified. Do not commit.
