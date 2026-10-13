# Dictation-first Prescription App — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the demo into a doctor-facing, dictation-first app: the doctor dictates the whole visit (including patient details), gets an always-editable prescription, and finishes with Save & Print (SQLite + PDF file).

**Architecture:** All work wraps around the existing deterministic pipeline (`normalize → ground → repair → validate` in `backend/determinism.py`) without changing its behavior. New backend modules stay small and single-purpose (`correction.py`, `safety.py`, `pdf.py`); persistence reuses the stdlib-sqlite `backend/db/` package and adds one migration. The frontend is rebuilt around one dictation control and an editable form.

**Tech Stack:** FastAPI, stdlib `sqlite3`, vanilla JS (no build step), pytest (offline). PDF via headless Chromium (Playwright), with browser print as the fallback.

**Spec:** `docs/superpowers/specs/2026-10-12-dictation-first-app-design.md`

## Global Constraints

- Target: Windows on ARM64 (Snapdragon X Elite). Python 3.12 in `.venv-arm64`. Any new dependency must be pure-Python or have an ARM64 wheel.
- The deterministic pipeline is a hard invariant: do not change the behavior of `normalize_transcript`, `correct_drugs`, `ground_rx`, `validate_structured`, `loop_should_continue`, or the cache.
- Tests are offline: they clear API keys and exercise the rules+lexicon fallback. Run with `.\.venv-arm64\Scripts\python -m pytest tests\ -q`.
- Cloud STT audio may leave the machine (accepted for v1). The **audio is never persisted**.
- Keep the "AI draft — doctor must verify" disclaimer.
- Cloud STT is the default engine; the local fallback is `small.en`, configurable only via `WHISPER_MODEL`. No engine/model choice in the UI.
- New DB access goes through `backend/db/__init__.py` helper functions; endpoints never write raw SQL.

## Review Focus

1. A dictated correction naming a medicine **not** in the current form must ADD a row — never be dropped.
2. A hand-edited row must lose its ✓ (no stale verification) — see `merge_form` and the frontend edit handler.
3. A correction whose STT returns empty text must NOT wipe the form.
4. Two patients sharing an OP number must not merge onto the wrong patient.
5. A whole-visit dictation near the ~5-min limit must not silently lose the transcript; the error must be visible.

Each line has its test in the owning task below.

---

### Task 1: Cloud-default STT; remove model selection

**Files:**
- Modify: `backend/main.py` (remove `AVAILABLE_MODELS`, `GET /api/models`, `POST /api/model`, and `_model_loading` reporting used only by them; keep `get_model()`, `_use_small_model()`, `WHISPER_MODEL`)
- Test: `tests/test_determinism.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `active_stt_engine()` unchanged (already cloud-first); `WHISPER_MODEL` remains the fallback model id.

- [ ] **Step 1: Write the failing test**

```python
def test_model_selection_endpoints_removed(monkeypatch):
    client = _client(monkeypatch)
    assert client.get("/api/models").status_code == 404
    assert client.post("/api/model", json={"model": "tiny.en"}).status_code == 404

def test_health_still_reports_engine(monkeypatch):
    h = _client(monkeypatch).get("/api/health").json()
    assert h["stt_engine_requested"] == "auto"
    assert "whisper_model" in h
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv-arm64\Scripts\python -m pytest tests/test_determinism.py::test_model_selection_endpoints_removed -v`
Expected: FAIL (200, not 404).

- [ ] **Step 3: Remove the endpoints + model list from `backend/main.py`**

Delete the `@app.get("/api/models")` and `@app.post("/api/model")` handlers and the `AVAILABLE_MODELS` list. Keep `get_model()` and `_use_small_model()` (the fallback still loads `small.en` on demand).

- [ ] **Step 4: Run tests**

Run: `.\.venv-arm64\Scripts\python -m pytest tests\ -q`
Expected: PASS; no test referenced the removed routes.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_determinism.py
git commit -m "feat(stt): cloud default, drop in-app model selection"
```

---

### Task 2: Patient lookup + upsert by OP number

**Files:**
- Modify: `backend/db/__init__.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces:
  - `find_patient_by_op(conn, op_no: str) -> sqlite3.Row | None`
  - `upsert_patient(conn, name: str, age_sex: str = "", op_no: str | None = None) -> int` — if `op_no` is non-empty and a patient with that `op_no` exists, update its `name`/`age_sex` and return the id; else insert a new patient.

- [ ] **Step 1: Write the failing tests**

```python
def test_find_patient_by_op(conn):
    pid = dbmod.create_patient(conn, "Anita", "45 / F", "OP-1234")
    assert dbmod.find_patient_by_op(conn, "OP-1234")["id"] == pid
    assert dbmod.find_patient_by_op(conn, "OP-9999") is None

def test_upsert_patient_updates_existing(conn):
    pid = dbmod.create_patient(conn, "Anita", "45 / F", "OP-1234")
    again = dbmod.upsert_patient(conn, "Anita Sharma", "46 / F", "OP-1234")
    assert again == pid
    row = dbmod.get_patient(conn, pid)
    assert row["name"] == "Anita Sharma" and row["age_sex"] == "46 / F"
    assert len(dbmod.list_patients(conn)) == 1

def test_upsert_patient_blank_op_always_inserts(conn):
    dbmod.upsert_patient(conn, "A", "", None)
    dbmod.upsert_patient(conn, "B", "", None)
    assert len(dbmod.list_patients(conn)) == 2
```

- [ ] **Step 2: Run to verify failure** → `pytest tests/test_db.py -k upsert -v` (FAIL: no attribute).

- [ ] **Step 3: Implement** `find_patient_by_op` (SELECT ... WHERE op_no = ? LIMIT 1) and `upsert_patient` in the patients section of `backend/db/__init__.py`.

- [ ] **Step 4: Run** `pytest tests/test_db.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/db/__init__.py tests/test_db.py
git commit -m "feat(db): patient lookup + upsert by OP number"
```

---

### Task 3: Dictated OP number in the schema

**Files:**
- Modify: `backend/determinism.py` (`validate_structured`), `backend/main.py` (`SYSTEM_PROMPT`, `fallback_format`)
- Test: `tests/test_determinism.py`

**Interfaces:**
- Produces: `validate_structured(...)` output gains `"opNo": str`.

- [ ] **Step 1: Failing tests**

```python
def test_validator_carries_op_no():
    out, _ = validate_structured({"opNo": "OP-1234"}, "")
    assert out["opNo"] == "OP-1234"

def test_fallback_extracts_op_no():
    out = fallback_format("patient name Anita 45 year old female OP 1234 right flank pain")
    assert out["opNo"].upper().endswith("1234")
```

- [ ] **Step 2: Verify failure** → `pytest tests/test_determinism.py -k op_no -v` (FAIL).

- [ ] **Step 3: Implement**
  - `validate_structured`: add `"opNo": str(d.get("opNo") or "")` to `out`.
  - `SYSTEM_PROMPT`: add an `"opNo"` field to the schema block and a rule that OP/registration numbers are copied verbatim, `""` if not dictated.
  - `fallback_format`: add a deterministic regex `\bop\s*(?:no|number|#)?[:\s]*([A-Za-z0-9-]+)` populating `opNo`.

- [ ] **Step 4: Run** `pytest tests\ -q` → PASS (golden cases unaffected: `opNo` defaults `""`).

- [ ] **Step 5: Commit**

```bash
git add backend/determinism.py backend/main.py tests/test_determinism.py
git commit -m "feat(extract): capture dictated OP number"
```

---

### Task 4: `merge_form` — apply a spoken correction

**Files:**
- Create: `backend/correction.py`
- Test: `tests/test_correction.py` (new)

**Interfaces:**
- Produces: `merge_form(current: dict, patch: dict) -> dict` — pure, deterministic. Scalars (`patientName`, `ageSex`, `opNo`, `review`) overwrite only when the patch value is non-empty. List fields (`diagnosis`, `complaints`, `investigations`, `advice`) replace only when the patch list is non-empty. `rx` merges by case-insensitive `name`: a patch row whose name matches replaces that row; a patch row with a new name is **appended**; rows not named in the patch are untouched.

- [ ] **Step 1: Failing tests (include Review Focus #1 and #3)**

```python
def test_correction_replaces_named_rx_row_and_keeps_others():
    cur = {"rx": [{"name": "Tamsulosin", "strength": "0.4 mg", "dose": "0-0-1"},
                  {"name": "Paracetamol", "strength": "650 mg", "dose": "SOS"}]}
    out = merge_form(cur, {"rx": [{"name": "tamsulosin", "strength": "0.4 mg", "dose": "1-0-0"}]})
    assert [r["name"] for r in out["rx"]] == ["Tamsulosin", "Paracetamol"]
    assert out["rx"][0]["dose"] == "1-0-0"

def test_correction_adds_new_medicine():  # Review Focus #1
    cur = {"rx": [{"name": "Tamsulosin"}]}
    out = merge_form(cur, {"rx": [{"name": "Pantoprazole", "strength": "40 mg"}]})
    assert [r["name"] for r in out["rx"]] == ["Tamsulosin", "Pantoprazole"]

def test_empty_patch_leaves_form_unchanged():  # Review Focus #3
    cur = {"patientName": "Anita", "rx": [{"name": "Tamsulosin"}]}
    assert merge_form(cur, {}) == cur

def test_empty_scalar_does_not_clear():
    out = merge_form({"patientName": "Anita", "ageSex": "45 / F"}, {"patientName": ""})
    assert out["patientName"] == "Anita"
```

- [ ] **Step 2: Verify failure** → `pytest tests/test_correction.py -v` (ImportError).

- [ ] **Step 3: Implement** `merge_form` in `backend/correction.py` (stdlib only; normalize names with `strip().lower()`). Return a new dict; never mutate `current`.

- [ ] **Step 4: Run** `pytest tests/test_correction.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/correction.py tests/test_correction.py
git commit -m "feat(correction): deterministic form merge for spoken corrections"
```

---

### Task 5: Correction endpoint (extract + merge + ground)

**Files:**
- Modify: `backend/correction.py`, `backend/main.py`
- Test: `tests/test_correction.py`

**Interfaces:**
- Produces:
  - `extract_correction(correction_text: str, current_form: dict) -> dict` — returns a *patch* form. Rules/offline path returns `{}`. LLM path sends the current form + `"Change ONLY what this correction states; leave every other field byte-identical"` and returns the model's partial form.
  - `POST /api/v1/correct` body `{"transcript": str, "current_form": dict}` → `{"structured": dict, "grounding": {...}, "engine": str}` where `structured = merge_form(current_form, confirmed_patch)` then re-validated via `validate_structured`.

- [ ] **Step 1: Failing test**

```python
def test_correct_endpoint_merges_offline(monkeypatch):
    client = _client(monkeypatch)  # keys cleared -> rules path
    cur = {"patientName": "Anita", "rx": [{"name": "Tamsulosin", "dose": "0-0-1"}]}
    j = client.post("/api/v1/correct", json={"transcript": "", "current_form": cur}).json()
    assert j["structured"]["rx"][0]["name"] == "Tamsulosin"  # empty correction never wipes
```

- [ ] **Step 2: Verify failure** → 404.

- [ ] **Step 3: Implement** `extract_correction` (reuse `llm_config`/`_complete` style; `{}` when unconfigured) and the endpoint, which merges then runs grounding so the `status` pills are recomputed for changed rows.

- [ ] **Step 4: Run** `pytest tests\ -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/correction.py backend/main.py tests/test_correction.py
git commit -m "feat(api): /api/v1/correct merges a spoken correction"
```

---

### Task 6: Verify gate + Save (persist) + audit

**Files:**
- Create: `backend/safety.py`
- Modify: `backend/main.py`
- Test: `tests/test_safety.py` (new)

**Interfaces:**
- Consumes: `dbmod.upsert_patient`, `dbmod.create_encounter`, `dbmod.save_document`, `dbmod.log_audit`.
- Produces:
  - `screen_unverified(structured: dict, confirmed_rows=None) -> list[dict]` — rows with `status != "verified"` whose index is not in `confirmed_rows`, as `{"index", "name", "status"}`.
  - `POST /api/v1/documents` body `{"structured": dict, "confirmed_rows": [int], "engine": str, "transcript_sha256": str}`:
    1. `screen_unverified` non-empty → `409 {"error": "unverified medicines", "block": [...]}`.
    2. Else upsert patient (from `structured`), create encounter, save document with `finalized_at`, `log_audit`.
    3. Returns `{"patient_id", "encounter_id", "document_id"}`.

- [ ] **Step 1: Failing tests (Review Focus #4)**

```python
def test_finalize_blocks_unverified(monkeypatch):
    c = _client(monkeypatch)
    r = c.post("/api/v1/documents", json={"structured": {"rx": [{"name": "Zzz", "status": "unknown-medicine"}]}, "confirmed_rows": []})
    assert r.status_code == 409 and r.json()["block"][0]["name"] == "Zzz"

def test_finalize_succeeds_when_all_verified(client_db):
    r = _client_after(client_db).post("/api/v1/documents", json={"structured": {"patientName": "Anita", "opNo": "OP-1", "rx": [{"name": "Tamsulosin", "status": "verified"}]}, "confirmed_rows": []})
    assert r.status_code == 200 and r.json()["encounter_id"]

def test_same_op_updates_same_patient(client_db):
    for _ in range(2):
        _client_after(client_db).post("/api/v1/documents", json={"structured": {"patientName": "Anita", "opNo": "OP-7", "rx": []}, "confirmed_rows": []})
    assert len(dbmod.list_patients(client_db)) == 1
```

- [ ] **Step 2: Verify failure** → 404.

- [ ] **Step 3: Implement** `screen_unverified` in `backend/safety.py` and the endpoint in `backend/main.py` (DB connection via `dbmod.get_conn()`; validate `structured` with `validate_structured` first).

- [ ] **Step 4: Run** `pytest tests\ -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/safety.py backend/main.py tests/test_safety.py
git commit -m "feat(safety): verify gate + Save persists encounter/document/audit"
```

---

### Task 7: Sheet HTML builders (PDF source + printable sheet)

**Files:**
- Create: `backend/pdf.py`
- Test: `tests/test_pdf.py` (new)

**Interfaces:**
- Produces: `build_sheet_html(structured: dict, meta: dict) -> str` — pure; the same sections as the on-screen sheet (diagnosis, complaint history, investigations, Rx table with a Check column, advice, review, disclaimer). HTML-escapes all values.

- [ ] **Step 1: Failing tests**

```python
def test_sheet_html_escapes_and_has_sections():
    html = build_sheet_html({"patientName": "<b>x</b>", "rx": [{"name": "A", "status": "verified"}]}, {"date": "2026-10-12", "opNo": "OP-1"})
    assert "&lt;b&gt;x&lt;/b&gt;" in html and "MEDICATIONS" in html and "&lt;b&gt;" not in html.replace("&lt;b&gt;", "")

def test_sheet_html_empty_rx_placeholder():
    assert "—" in build_sheet_html({}, {})
```

- [ ] **Step 2: Verify failure** → ImportError.

- [ ] **Step 3: Implement** `build_sheet_html` (f-strings + an `escape` helper; no external deps).

- [ ] **Step 4: Run** `pytest tests/test_pdf.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/pdf.py tests/test_pdf.py
git commit -m "feat(pdf): pure sheet->HTML builder"
```

---

### Task 8: Render + save the PDF file

**Files:**
- Create: `backend/db/migrations/002_document_pdf.sql`
- Modify: `backend/db/__init__.py` (`save_document` accepts `pdf_path`), `backend/pdf.py` (`render_pdf`), `backend/main.py` (wire into `/api/v1/documents`)
- Test: `tests/test_pdf.py`, `tests/test_db.py`

**Interfaces:**
- Produces: `render_pdf(html: str, out_path) -> Path` using Playwright Chromium; raises `RuntimeError` with a clear message when the renderer is unavailable. `documents.pdf_path TEXT` column.

- [ ] **Step 1: Failing tests**

```python
def test_migration_adds_pdf_path(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(documents)")}
    assert "pdf_path" in cols

def test_render_pdf_writes_file_or_raises(tmp_path):
    html = build_sheet_html({"patientName": "Anita"}, {})
    try:
        p = render_pdf(html, tmp_path / "s.pdf")
        assert p.read_bytes()[:5] == b"%PDF-"
    except RuntimeError as e:
        assert "chromium" in str(e).lower()  # renderer not installed here
```

- [ ] **Step 2: Verify failure** → migration missing / no `render_pdf`.

- [ ] **Step 3: Implement** migration `002_document_pdf.sql` (`ALTER TABLE documents ADD COLUMN pdf_path TEXT;`), thread `pdf_path` through `save_document`, add `render_pdf` (Playwright; fail soft), and call it in `/api/v1/documents` after the gate passes, storing the returned path.

- [ ] **Step 4: Run** `pytest tests\ -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/db backend/pdf.py backend/main.py tests/
git commit -m "feat(pdf): render + save prescription PDF; record path"
```

---

### Task 9: Frontend rebuild — layout C (dictation-first, editable)

**Files:**
- Rewrite: `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
- Test: `node --check frontend/app.js`

**Interfaces:**
- Consumes: `POST /api/transcribe`, `POST /api/format`, `POST /api/v1/correct`, `POST /api/v1/documents`; `GET /api/health`.
- Produces: a page with (1) a patient row that starts empty, (2) one mic control toggling record/stop with a timer, (3) a sheet that renders after stop and is inline-editable, (4) a "Save & Print" action.

- [ ] **Step 1: Write the failing check** — `node --check frontend/app.js` passes only once the file is syntactically valid; before rewriting, capture the current baseline.

- [ ] **Step 2: Rewrite `index.html`** — remove `#modelSel`, `#exampleBtn`, `#copyBtn`, `#formatBtn`, `#busy`, the verbose hint, and the four manual inputs; keep the sheet sections and the disclaimer.

- [ ] **Step 3: Rewrite `app.js`**
  - Mic toggle records via `MediaRecorder`, uploads to `/api/transcribe`, then calls `/api/format`.
  - Render the sheet into contenteditable cells; each Rx row keeps its pill.
  - A "Dictate correction" path posts `{transcript, current_form}` to `/api/v1/correct` and re-renders (Review Focus #2: a hand-edited cell clears its own row's pill before the next ground pass).
  - "Save & Print" posts to `/api/v1/documents`; on `409` it lists the blocked rows and lets the doctor confirm or re-dictate.
  - Raise the transcribe abort from 180s to 300s (Review Focus #5) and show a visible error if it aborts.

- [ ] **Step 4: Verify** `node --check frontend/app.js` → passes; load the page and dictate/format once against a running server.

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(ui): dictation-first screen, editable sheet, save & print"
```

---

### Task 10: Docs — privacy + setup

**Files:**
- Modify: `README.md`, `.env.example`

- [ ] **Step 1:** Correct the README: cloud STT is the default; **audio leaves the machine and is not saved**; local fallback is `small.en` (`WHISPER_MODEL`); remove the model-picker and `/api/models` references; document Save & Print and the verify gate.
- [ ] **Step 2:** `.env.example`: mark `STT_ENGINE=auto` (cloud-first) and `WHISPER_MODEL=small.en` as the only STT knobs.
- [ ] **Step 3: Commit**

```bash
git add README.md .env.example
git commit -m "docs: cloud STT default, audio/privacy, save & print"
```

---

## Self-Review

- **Spec coverage:** STT default + no picker → Task 1; dictated demographics → Task 3; editable form + corrections (type/voice/merge) → Tasks 4/5/9; verify gate → Task 6; SQLite user/patient/form → Tasks 2/6; PDF saved file → Tasks 7/8; local-now/cloud-later → out of scope; PHI/README → Task 10.
- **Placeholders:** none — each step names files, signatures, and exact test assertions.
- **Type consistency:** `merge_form`, `screen_unverified`, `build_sheet_html`, `render_pdf`, `upsert_patient`/`find_patient_by_op` are defined once and consumed with the same names.
- **Review Focus:** #1 → Task 4; #2 → Task 9; #3 → Tasks 4/5; #4 → Task 6; #5 → Task 9.
- **Proportion:** frontend rebuild is described by intent (it has no unit-test harness), the backend by signature + test.
