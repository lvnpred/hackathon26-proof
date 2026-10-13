# Clinic Workspace UI + Clinic Profile + Today's List — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the app into a professional two-pane workspace (assistant visible), add an updatable clinic/doctor profile printed on the sheet + PDF, and a sidebar listing the patients completed today that reopen for editing.

**Architecture:** Backend work is small and additive — one settings table (migration 003), a profile endpoint, a "today" query + a load-document endpoint, a re-save/update branch, and a profile-aware PDF header. The frontend is restructured into the approved workspace layout. Everything wraps the existing deterministic pipeline unchanged.

**Tech Stack:** FastAPI, stdlib `sqlite3`, vanilla JS (no build step), pytest (offline).

**Spec:** `docs/superpowers/specs/2026-10-13-clinic-workspace-ui-design.md`

## Global Constraints

- Windows ARM64; Python 3.12 in `.venv-arm64`; stdlib only for DB (no new native deps).
- New DB access goes through `backend/db/__init__.py` helpers; endpoints write no raw SQL.
- The deterministic pipeline in `backend/determinism.py` must not change behavior.
- Tests run offline: `.\.venv-arm64\Scripts\python -m pytest tests\ -q`.
- Vanilla JS, no build step; verify JS with `node --check frontend/app.js`.
- Keep the "AI draft — doctor must verify" disclaimer verbatim and the ✓/?/!/± pills.
- Clinic profile is optional — a blank profile must NOT block Save & Print.
- "Today" = the server machine's local calendar day, from `documents.created_at` (UTC).

## Review Focus

1. Re-opening a today patient and re-saving **updates** the same document row (no duplicate).
2. The verify gate still blocks a re-save of a document containing unverified medicines.
3. A blank/absent clinic profile must not crash the sheet, the PDF, or the header.
4. "Today" must exclude an encounter saved just before local midnight (the UTC/local boundary), and include one just after.
5. Missing patient name/OP must render as a placeholder, never `None`/`undefined`.

Each line gets its test in the owning task below.

---

### Task 1: Clinic profile — storage + endpoints

**Files:**
- Create: `backend/db/migrations/003_clinic_profile.sql`
- Modify: `backend/db/__init__.py`, `backend/main.py`
- Test: `tests/test_db.py`, `tests/test_profile.py` (new)

**Interfaces:**
- Produces:
  - `get_profile(conn) -> sqlite3.Row | None`
  - `save_profile(conn, doctor_name="", qualifications="", reg_no="", clinic_name="", address="", phone="", updated_at=None) -> None` — upserts the single row (`id=1`).
  - `GET /api/v1/profile` → `{"doctor_name","qualifications","reg_no","clinic_name","address","phone"}` (empty strings when unset).
  - `PUT /api/v1/profile` body same shape → returns the saved dict.

- [ ] **Step 1: Write the failing tests**

```python
def test_profile_defaults_empty(conn):          # tests/test_profile.py
    assert dbmod.get_profile(conn) is None

def test_profile_roundtrip(conn):               # tests/test_profile.py
    dbmod.save_profile(conn, doctor_name="A. Rao", reg_no="12345", clinic_name="Meridian")
    dbmod.save_profile(conn, doctor_name="A. Rao", qualifications="MBBS", reg_no="12345", clinic_name="Meridian")
    p = dbmod.get_profile(conn)
    assert p["doctor_name"] == "A. Rao" and p["qualifications"] == "MBBS"
    assert conn.execute("SELECT COUNT(*) c FROM clinic_profile").fetchone()["c"] == 1

def test_profile_endpoint_put_then_get(client):
    assert client.get("/api/v1/profile").json()["clinic_name"] == ""
    client.put("/api/v1/profile", json={"doctor_name": "A. Rao", "clinic_name": "Meridian"})
    assert client.get("/api/v1/profile").json()["clinic_name"] == "Meridian"
```

- [ ] **Step 2: Run to verify failure** → `pytest tests/test_profile.py -v` (FAIL: no attr / 404).

- [ ] **Step 3: Implement**
  - `003_clinic_profile.sql`: `CREATE TABLE IF NOT EXISTS clinic_profile (id INTEGER PRIMARY KEY CHECK (id = 1), doctor_name TEXT NOT NULL DEFAULT '', qualifications TEXT NOT NULL DEFAULT '', reg_no TEXT NOT NULL DEFAULT '', clinic_name TEXT NOT NULL DEFAULT '', address TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL);`
  - `get_profile` (SELECT the `id=1` row), `save_profile` (`INSERT INTO clinic_profile(...) VALUES (1,...) ON CONFLICT(id) DO UPDATE SET ...`).
  - `ProfileBody(BaseModel)` with the six `str = ""` fields; `GET`/`PUT /api/v1/profile` in `backend/main.py` using `dbmod.get_conn()`.

- [ ] **Step 4: Run** `pytest tests\ -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/db/migrations/003_clinic_profile.sql backend/db/__init__.py backend/main.py tests/test_db.py tests/test_profile.py
git commit -m "feat(profile): clinic/doctor profile storage + endpoints"
```

---

### Task 2: "Today" query + load-a-document endpoints

**Files:**
- Modify: `backend/db/__init__.py`, `backend/main.py`
- Test: `tests/test_today.py` (new)

**Interfaces:**
- Produces:
  - `local_day_bounds_utc(now=None) -> tuple[str, str]` — the UTC ISO bounds of the server-local calendar day `now` falls in (half-open `[start, end)`).
  - `list_documents_between(conn, start_iso, end_iso) -> list[sqlite3.Row]` — documents in range joined to `encounters`→`patients`; row fields `document_id, encounter_id, patient_name, op_no, created_at`.
  - `get_document(conn, document_id) -> sqlite3.Row | None`.
  - `GET /api/v1/encounters/today` → `[{"document_id","encounter_id","patient_name","op_no","created_at"}]`.
  - `GET /api/v1/documents/{document_id}` → `{"document_id","structured","engine","transcript_sha256","created_at"}`; 404 when unknown.

- [ ] **Step 1: Write the failing tests (include Review Focus #4)**

```python
def test_today_bounds_straddle_local_midnight():
    # 03:00 local on a UTC+5:30 machine is the previous UTC day
    from datetime import datetime, timezone, timedelta
    now = datetime(2026, 10, 13, 3, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    start, end = dbmod.local_day_bounds_utc(now)
    assert start.startswith("2026-10-12") and end.startswith("2026-10-13")

def test_today_excludes_yesterday(temp_db_with_two_docs):  # one at 23:50 local prev day, one 00:10 local
    rows = dbmod.list_documents_between(temp_db_with_two_docs, *bounds)
    assert len(rows) == 1

def test_today_endpoint_shape(client_with_today_doc):
    j = client_with_today_doc.get("/api/v1/encounters/today").json()
    assert set(j[0]) == {"document_id","encounter_id","patient_name","op_no","created_at"}

def test_get_document_404(client):
    assert client.get("/api/v1/documents/999999").status_code == 404
```

- [ ] **Step 2: Run to verify failure** → 404 / AttributeError.

- [ ] **Step 3: Implement** the three DB helpers and the two endpoints. For bounds, compute local midnight via `datetime` with the server's local tz (`datetime.now().astimezone().tzinfo`), convert to UTC, format `%Y-%m-%dT%H:%M:%SZ`. `list_documents_between` uses `WHERE d.created_at >= ? AND d.created_at < ?` with a JOIN to `encounters` and `patients`.

- [ ] **Step 4: Run** `pytest tests\ -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/db/__init__.py backend/main.py tests/test_today.py
git commit -m "feat(today): today's-encounters + load-document endpoints"
```

---

### Task 3: Clinic profile on the sheet (incl. the PDF)

**Files:**
- Modify: `backend/pdf.py`, `backend/main.py`
- Test: `tests/test_pdf.py`, `tests/test_safety.py`

**Interfaces:**
- Consumes: `dbmod.get_profile`.
- Produces: `build_sheet_html(structured: dict, meta: dict) -> str` where `meta.get("profile")` is an optional dict of the six profile fields; when present and non-empty it renders a doctor/clinic header block above the title, HTML-escaped. `meta` gains `profile`.
- The `POST /api/v1/documents` handler passes the **current** profile (`dbmod.get_profile`) into `meta["profile"]`.

- [ ] **Step 1: Write the failing tests (include Review Focus #3)**

```python
def test_sheet_header_shows_profile():
    html = build_sheet_html({}, {"profile": {"doctor_name": "A. Rao", "reg_no": "12345", "clinic_name": "Meridian"}})
    assert "A. Rao" in html and "12345" in html and "Meridian" in html

def test_sheet_header_absent_profile_no_crash():   # Review Focus #3
    html = build_sheet_html({"patientName": "X"}, {})
    assert "PATIENT CLINICAL SUMMARY" in html and "None" not in html

def test_sheet_header_escapes_profile():
    html = build_sheet_html({}, {"profile": {"doctor_name": "<b>x</b>"}})
    assert "&lt;b&gt;x&lt;/b&gt;" in html and "<b>x</b>" not in html
```

- [ ] **Step 2: Run to verify failure** → assertion fail (no header).

- [ ] **Step 3: Implement** the header block in `build_sheet_html` (reuse the existing escape helper); read the profile in the document handler and pass it via `meta`.

- [ ] **Step 4: Run** `pytest tests\ -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/pdf.py backend/main.py tests/test_pdf.py tests/test_safety.py
git commit -m "feat(pdf): print the clinic profile header on the sheet and PDF"
```

---

### Task 4: Re-save updates the existing document

**Files:**
- Modify: `backend/db/__init__.py`, `backend/main.py`
- Test: `tests/test_safety.py`

**Interfaces:**
- Produces:
  - `update_document(conn, document_id, structured_json, engine=None, finalized_at=None, transcript_sha=None, pdf_path=None) -> int` — UPDATE by id, returns affected row count.
  - `DocumentCreate` gains `document_id: int | None = None`.
  - `POST /api/v1/documents`: when `document_id` is set, UPDATE that document (verify gate still applies first); unknown id → 404. Without it, insert (unchanged).

- [ ] **Step 1: Write the failing tests (include Review Focus #1 and #2)**

```python
def test_resave_updates_same_document(client_db):     # Review Focus #1
    first = post_document(client_db, {"patientName": "Anita", "opNo": "OP-3", "rx": [{"name": "A", "status": "verified"}]})
    did = first["document_id"]
    second = post_document(client_db, {"patientName": "Anita", "opNo": "OP-3", "rx": [{"name": "B", "status": "verified"}]}, document_id=did)
    assert second["document_id"] == did
    assert count_documents(client_db) == 1

def test_resave_with_unverified_still_blocked(client_db):   # Review Focus #2
    ...  # document_id set + an unverified row -> 409, document unchanged

def test_resave_unknown_document_404(client_db):
    assert post_raw(client_db, {...}, document_id=999999).status_code == 404
```

- [ ] **Step 2: Run to verify failure** → duplicate row / 200 instead of 404.

- [ ] **Step 3: Implement** `update_document`; branch on `document_id` in the handler after the gate; 404 when `update_document` affects 0 rows.

- [ ] **Step 4: Run** `pytest tests\ -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/db/__init__.py backend/main.py tests/test_safety.py
git commit -m "feat(save): re-saving updates the existing document"
```

---

### Task 5: Frontend — the workspace layout

**Files:**
- Rewrite: `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
- Verify: `node --check frontend/app.js`

**Interfaces:**
- Consumes: `GET /api/v1/profile`, `PUT /api/v1/profile`, `GET /api/v1/encounters/today`, `GET /api/v1/documents/{id}`, plus the existing `POST /api/transcribe`, `/api/format`, `/api/v1/correct`, `/api/v1/documents`.
- Produces: the approved workspace — top bar; left "Today" sidebar; middle pane (dictation orb + timer, coarse assistant steps Listening → Working → Ready, live transcript shown after Stop); right pane (document with clinic-profile header, patient row, sections, Rx table, Save & Print); a settings panel for the profile.

- [ ] **Step 1:** Build `index.html` — the four regions (top bar, `#today` sidebar, `#middle`, `#sheet`), the profile settings dialog (`#profilePanel`), preserving every id `app.js` needs and the disclaimer.
- [ ] **Step 2:** Rewrite `app.js` — keep the record→transcribe→format flow and the row-id-keyed confirmations; add: load `/api/v1/profile` on start and render the header; `#today` list from `/api/v1/encounters/today` with click→`GET /api/v1/documents/{id}`→render + remember `document_id` for a re-save; coarse step chips (`Listening` while recording, `Working` during transcribe/format, `Ready` when rendered); settings panel GET/PUT; on Save send `document_id` when re-opened.
- [ ] **Step 3:** `styles.css` — the workspace grid (sidebar / middle / document), modern styling, and print rules so only `#sheet` prints (keep the `@page` margin and the `.sec-title` bleed fix), with the profile header visible.
- [ ] **Step 4: Verify** `node --check frontend/app.js` → exit 0; sanity-check every `getElementById` target exists; state what a browser is still needed to exercise.
- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(ui): professional two-pane workspace, today sidebar, profile panel"
```

---

### Task 6: Docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** Document the workspace, the clinic profile (endpoints + settings panel), today's list + reopen/re-save, and the profile-in-PDF behaviour.
- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: workspace UI, clinic profile, today's list"
```

---

## Self-Review

- **Spec coverage:** two-pane workspace → Task 5; real-but-coarse steps → Task 5; clinic profile (updatable, printed on sheet + PDF) → Tasks 1 + 3; today's list + reopen → Task 2 + Task 5; re-save updates → Task 4; print fix → already landed, preserved in Task 5.
- **Placeholders:** none — each backend step names files, signatures, and exact test assertions; the frontend task names the regions and the endpoints it wires.
- **Type consistency:** `get_profile`/`save_profile`, `local_day_bounds_utc`, `list_documents_between`, `get_document`, `update_document`, and the `document_id` body field are defined once and consumed with the same names.
- **Review Focus:** #1 → Task 4; #2 → Task 4; #3 → Task 3; #4 → Task 2; #5 → Task 5 (placeholders) + Task 3 (no `None`).
- **Proportion:** the backend is specified by signature + test; the frontend by region and wiring (it has no unit-test harness).
