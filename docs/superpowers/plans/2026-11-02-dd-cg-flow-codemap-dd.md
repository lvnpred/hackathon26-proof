# Code map: Doctor Dictation (for the 2026-11-02 DD → CG flow plan)

Root `doctor-dictation/`. Checked against the code on 2026-11-02; re-check line numbers before editing.

## Save path — `doctor_dictation/api/persistence.py` (476 lines)
- `DocumentCreate` :139-146 — `structured`, `confirmed_rows`, `remember_generics`, `remember_investigations`, `engine`, `transcript_sha256`, `document_id`. No admit fields yet.
- Route :198-199 `create_document(req, request, _ix=Depends(use_investigations))`, sync `def`, no `BackgroundTasks` param (fastapi import at :7).
- Verify gate 409 :225-235. `resave = req.document_id is not None` :249.
- Commits: re-save `dbmod.update_document` :305; new `dbmod.save_document` :324-334; `log_audit` :336; learn_* :347-353. **Hook point: after :353, before the return.**
- Return :354-360 `{patient_id, encounter_id, document_id, op_no, visit_date}` — no `finalized_at`; stored in `documents.finalized_at` (`db/migrations/001_init.sql:47`), format `%Y-%m-%dT%H:%M:%SZ` (`db/__init__.py:119 _utcnow`).
- `GET /api/v1/documents/{id}` :370-401 → `{document_id, structured{patientName, ageSex, opNo, rx[...]}, engine, transcript_sha256, created_at, visit_date, past}` (+ `author`, `can_edit` when signed in). `finalized_at` via `dbmod.get_document(...)["finalized_at"]`.
- Multi-clinic scope is a ContextVar (`scope.py:44`); a bare thread raises NoScope. Build the payload dict inside the request; the background task does no DB-scope work except via an explicit path.

## DB — `doctor_dictation/db/__init__.py` (489 lines)
- `db_path()` :35 (`DB_PATH`), `get_conn()` :56 (caller closes), `migrate()` :80 (applies `db/migrations/*.sql`), `init_db()` :108.
- Latest migration `014_share_links.sql`. Adding `015_*.sql` requires updating `tests/test_db.py:88-90` (version list) and `:100` (`assert n == 14`).

## App / config
- `api/app.py` (96): `create_app()` :71, CORS `*` :82-87, router loop :89-91, startup `init_db` :43.
- `scope.py:47 multi_clinic_enabled()`.
- No module-level `get_settings()` in `api/*.py` (`tests/test_api_app.py:71-83`). Read env at call time.
- Route table pinned: `tests/test_api_app.py:13-40 EXPECTED_ROUTES`.
- `httpx>=0.27` already in `requirements.txt:5`.

## Frontend
- `frontend/index.html` (355): `#saveBtn` :104 in `.save-row`; `#status` :72.
- `frontend/app.js` (1404 — over the limit already; add new code in a new file): `setStatus` :74, `setWorking` ~:105, `postJson` :483, `saveDocument()` :1102-1183 (payload :1126-1134, POST :1135, success :1159-1162, 409 :1165-1174), listener :1185.

## Tests
- Flat `tests/test_*.py`. Autouse fixtures (`tests/conftest.py`): clean MULTI_CLINIC etc. :21, temp `DB_PATH` :28, blank keys :38; `multi` fixture :55.
- Minimal passing save: `tests/test_document_pdf.py:10` `SAVE = {"structured": {"patientName":"Anita","opNo":"OP-1","rx":[{"name":"Tamsulosin","status":"verified"}]}}`; fake PDF via `monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)` (`tests/test_investigations_save.py:14-19`).
- Run: `cd doctor-dictation && .venv/bin/python -m pytest tests/ -q`.

## Offline run (demo-check on 8300)
- Stub LLM `providers/llm/stub.py` (`STUB_LLM_JSON`), stub STT `providers/stt/stub.py` (`STUB_TRANSCRIPT`); need `ALLOW_STUB_PROVIDERS=1`, `LLM_PROVIDER=stub`, `STT_CHAIN=stub`. Ready env: `scripts/demo_browser.py:45-48`.
- Start: `DB_PATH=<dir>/app.db ALLOW_STUB_PROVIDERS=1 STT_CHAIN=stub LLM_PROVIDER=stub STUB_LLM_JSON='…' .venv/bin/python -m uvicorn doctor_dictation.main:app --port 8300` (MULTI_CLINIC unset).
