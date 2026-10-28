# Plan: Phase 0 Hardening (auth, secrets, persistence, safety, versioning, observability, backups, compliance, CI)

Status: execution-ready plan. Decomposes Phase 0 of
`C:\Users\lvnar\.opencode\plan\productionize.md` into independently shippable
units. The deterministic pipeline (`normalize → ground → repair → validate →
cache` in `backend/determinism.py`) is a hard invariant — production work wraps
around it and never alters its behavior.

> **Progress (2026-10-12, HEAD `d5301a8`):** P0-2 **DONE**, P0-4 **DONE**,
> P0-1 **PARTIAL** (git init + `.gitignore` done; CI workflow open). P0-3, P0-5,
> P0-6, P0-7, P0-8, P0-9 **open**. §2 below is a pre-implementation snapshot —
> line numbers have shifted and several claims are now false (marked [FIXED]).

---

## 1. Goal + acceptance criteria

**Goal.** Make the single-process demo safe to run with real (clinic) data: a
login with roles, secrets outside `.env`, durable persistence with an audit
trail, a Finalize safety gate that blocks unverified medications, versioned
`/api/v1` routes with deprecated aliases, observability endpoints, backups, and
a DPDP-compliance baseline — all verified by CI.

**Acceptance criteria (measurable).**
- `/api/v1/auth/login` issues a JWT; every `/api/v1/*` route rejects unauthenticated
  requests with 401; role `doctor` is required to Finalize/print (403 otherwise);
  `assistant` can dictate + draft; `admin` can manage users.
- No secret value appears in `.env` or any committed file; `/api/health` reports
  key **presence** only (`*_configured: true/false`), never values; a grep over
  the repo for the configured keys returns nothing.
- `patients`, `encounters`, `documents`, `audit_log` exist in SQLite and survive
  a process restart; every Finalize/print and every unverified-row confirmation
  writes an `audit_log` row (who/when/from-where).
- `POST /api/v1/encounters/{id}/finalize` returns 409 with a per-row block list
  when any `rx` row `status != "verified"`; it succeeds only after each flagged
  row is explicitly confirmed (recorded in `audit_log`).
- Old `/api/*` paths still respond (deprecated alias, logs a warning header);
  frontend calls `/api/v1/*`.
- `/readyz` returns 200 only when DB + STT/LLM config are sane; `/metrics`
  exposes request count / STT seconds / LLM calls; logs are structured JSON with
  a request id.
- Backups: a runbook + script for nightly DB + document snapshot, and one
  tested restore.
- DPDP baseline: consent flag on encounter, retention policy + cleanup job,
  access-log coverage, and the "AI draft — doctor must verify" banner retained.

---

## 2. Current state (verified by reading code)

- **Single process, no auth/users. [PARTLY FIXED]** `backend/main.py` is one
  FastAPI app, CORS `allow_origins=["*"]`, still **no auth middleware** (P0-3
  open). **[FIXED]** a SQLite DB now exists (`backend/db/`, WAL,
  `migrations/001_init.sql`) and `backend/config.py` centralizes settings, so
  `_FORMAT_CACHE` is no longer the only state.
- **Secrets. [FIXED]** Keys now resolve via `backend/secret_loader.py`
  (env-present → `backend/secrets.json` → absent), surfaced through
  `backend/config.py`; `.env` is gitignored (`.gitignore:7`) and **the repo is
  now git** (`a706ce6`). `/api/health` reports presence booleans only
  (`openai_configured` / `deepseek_configured`).
- **Persistence. [FIXED]** SQLite layer + migrations exist (`backend/db/`, P0-4)
  with `/api/v1/patients` and `/api/v1/encounters` (`main.py:773–802`).
  OP numbers are still random in the browser (`frontend/app.js`) — server
  assignment not done.
- **No Finalize.** `frontend/index.html:12` only has a raw `window.print()`
  button; there is no server-side "finalize" concept and no per-row confirmation.
  The safety notion today is the grounding `status` field
  (`determinism.py:22–25`, `388–405`) and the on-screen disclaimer
  (`index.html:57`).
- **Versioning. [PARTLY FIXED]** `/api/v1/patients` + `/api/v1/encounters` exist
  (P0-4); format/transcribe/health/models are still bare `/api/…`. Full
  versioning + deprecated aliases = P0-6 (open). Original bare routes were
  `main.py:403, 456, 480, 496, 593` (line refs now shifted).
- **Observability.** `GET /api/health` (now `main.py:429–462`) reports
  `lexicon_version`, `lexicon_entries`, `stt_engine_active`, `llm_configured`,
  `onnx_stt`, plus `openai_configured` / `deepseek_configured`. No `/readyz`, no
  `/metrics`, no structured logs (P0-7 open).
- **Tests.** `tests/test_determinism.py` plus, since this snapshot,
  `tests/test_db.py` (P0-4) and `tests/test_secrets.py` (P0-2). Offline; forces
  rules+lexicon fallback by clearing keys. Re-measure the pass count (was 31).
- **Frontend.** Vanilla JS, no build step (`frontend/index.html:60` versioned
  `app.js?v=5`); print-CSS only (`frontend/styles.css:42–48`).

---

## 3. Decisions needed

| # | Decision | Options | Proposed default | Blocks |
|---|---|---|---|---|
| P-1 | Hosting | (a) on-prem clinic server (PHI stays in clinic), (b) cloud VPS | **(a) on-prem** | P0-2, P0-8, P0-9 |
| P-2 | Secrets store | (a) env + `backend/secrets.json` (0600, gitignored), (b) Docker secrets, (c) cloud secret manager | **(a) secrets file + env override** now; Docker secrets when containerized | P0-2 |
| P-3 | Auth model | (a) per-user accounts, (b) one shared clinic login | **(a) per-user**, roles `doctor/assistant/admin` | P0-3 |
| P-4 | Token TTL | (a) access 15m + refresh 7d, (b) access 1h no refresh | **(a) 15m access / 7d refresh** | P0-3 |
| P-5 | Password hashing | (a) stdlib `hashlib.pbkdf2_hmac` (sha256, 600k iters), (b) `bcrypt`, (c) `argon2-cffi` | **(a) stdlib pbkdf2** (no native dep; bcrypt/argon2 Windows-ARM64 wheels uncertain) | P0-3 |
| P-6 | JWT lib | (a) `PyJWT` (pure Python), (b) `python-jose`, (c) hand-rolled HMAC | **(a) PyJWT** (pure Python, ARM64+x64) | P0-3 |
| P-7 | DB now | (a) stdlib `sqlite3` + repo layer + SQL migration files, (b) SQLAlchemy+Alembic now | **(a) stdlib sqlite3** now; adopt SQLAlchemy/Alembic at the Postgres cutover | P0-4 |
| P-8 | Old API lifecycle | (a) keep `/api/*` as deprecated aliases 1 release then drop, (b) drop immediately | **(a) alias + `X-Deprecated` header + log**, drop after 1 release | P0-6 |
| P-9 | Metrics backend | (a) in-memory counters exposed as JSON, (b) Prometheus (`prometheus-client`) | **(a) in-memory JSON** v1; Prometheus optional later | P0-7 |
| P-10 | Retention (DPDP) | audio/transcript/PDF retention durations | **audio 30d auto-delete; transcript+PDF 3y; void-not-delete** | P0-9 |
| P-11 | Consent capture | (a) required checkbox on encounter recorded to audit, (b) separate consent form | **(a) required checkbox on encounter** | P0-9 |
| P-12 | DPDP legal sign-off | (a) block real-data go-live until legal review, (b) proceed | **(a) block on sign-off** (keeps the AI-draft banner regardless) | P0-9 |
| P-13 | Filenames (forward) | (a) ID-only + name inside PDF, (b) full name in filename | **(a) `{YYYYMMDD}_{OPNo}_{DocId}.pdf`** | Phase 1 (not Phase 0) |
| P-14 | Share targets (forward) | SMB / Drive / SharePoint / S3 / DMS | **SMB folder first**, one cloud target after | Phase 1 (not Phase 0) |

---

## 4. Task table

IDs: `P0-*`. "Effort" in hours (h) / days (d). New dependencies are called out
inline and re-checked in §6.

| ID | Task | Files | Depends on | Effort | Verify command |
|---|---|---|---|---|---|
| P0-1 (partial) | **CI + git init.** `git init`; `.gitignore` (venvs, `.env`, `secrets.json`, `__pycache__`, `.pytest_cache`); `.github/workflows/ci.yml`: setup-python 3.12 → `pip install -r backend/requirements.txt` → `python backend/lexicon/build.py --merge backend/lexicon/seed_extra.json --check` → `pytest tests/ -q` → setup-node → `node --check frontend/app.js`. **Coordinate with determinism D6** (same file). | `.github/workflows/ci.yml` (new), `.gitignore` (new) | P-1 (remote needed to activate) | 0.5 d | `node --check frontend/app.js`; `python -m pytest tests/ -q` |
| P0-2 ✅ | **Secrets out of `.env`.** New `backend/config.py` (settings dataclass) + `backend/secrets.py` loader: env var → else `backend/secrets.json` (0600, gitignored) → else absent. Never log values; add key-**presence** booleans to `/api/health`. Rewrite `main.py` env reads (52–65, 384–400) to use `config`. Update `.env.example` to reference the secrets file. | `backend/config.py` (new), `backend/secrets.py` (new), `backend/main.py`, `.env.example`, `tests/test_secrets.py` (new) | P-2 | 0.5 d | `.\.venv-arm64\Scripts\python -m pytest tests/ -q`; grep keys == none |
| P0-3 | **AuthN/Z.** `backend/auth.py`: password hash (stdlib pbkdf2), JWT issue/verify (PyJWT), `get_current_user` / `require_role` deps, `POST /api/v1/auth/login`, user bootstrap (`admin` from env on first run). Protect `/api/v1/*` (except `/auth/login`, `/readyz`, `/health`). Frontend login form + token in `fetch` header + role-gated Finalize button. | `backend/auth.py` (new), `backend/main.py`, `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`, `tests/test_auth.py` (new) | P0-4 (users table), P-3/P-4/P-5/P-6 | 1 d | `.\.venv-arm64\Scripts\python -m pytest tests/test_auth.py -q` |
| P0-4 ✅ | **Persistence (SQLite).** `backend/db.py`: stdlib `sqlite3`, `backend/db/migrations/` SQL files, connection factory (WAL, foreign keys), repo functions. Tables: `patients`, `encounters` (patient_id, doctor_id, op_no, status, consent_at, created_at), `documents` (encounter_id, transcript_sha, structured_json, engine, model_versions, finalized_by/at), `audit_log` (actor, role, action, entity, detail, ip, at), `users`. Add `/api/v1/patients`, `/api/v1/encounters` read/create. | `backend/db.py` (new), `backend/db/migrations/*.sql` (new), `backend/main.py`, `tests/test_db.py` (new) | P-7 | 1 d | `.\.venv-arm64\Scripts\python -m pytest tests/test_db.py -q` |
| P0-5 | **Safety gate (Finalize).** `backend/safety.py`: `POST /api/v1/encounters/{id}/finalize` (doctor-only) → 409 with per-row block list when any `rx.status != "verified"`; per-row explicit confirmation (`confirm_row`) recorded to `audit_log`; on full confirm, mark encounter `finalized`. Frontend: Finalize button (doctor-only), per-row checkbox, disabled-print-until-finalized. Retain disclaimer. | `backend/safety.py` (new), `backend/main.py`, `frontend/app.js`, `frontend/index.html`, `frontend/styles.css`, `tests/test_safety.py` (new) | P0-3, P0-4 | 1 d | `.\.venv-arm64\Scripts\python -m pytest tests/test_safety.py -q` |
| P0-6 | **API versioning.** Mount `/api/v1/*` routers (auth, patients, encounters, finalize, format, transcribe, models, health); keep `/api/*` as deprecated aliases returning `X-Deprecated` header + structured log line. Update `frontend/app.js` to `/api/v1`. Update `tests/test_determinism.py` endpoint paths. | `backend/main.py`, `backend/routers/*.py` (new), `frontend/app.js`, `tests/test_determinism.py`, `tests/test_versioning.py` (new) | P0-3, P-8 | 0.5 d | `.\.venv-arm64\Scripts\python -m pytest tests/ -q` |
| P0-7 | **Observability.** `backend/observability.py`: stdlib JSON log formatter + request-id middleware; `/readyz` (DB + STT/LLM config + lexicon); `/metrics` (in-memory counters: requests, STT seconds, LLM calls/loop rounds, cache hits). Wire middleware into `main.py`. | `backend/observability.py` (new), `backend/main.py`, `tests/test_observability.py` (new) | P-4, P-9 | 0.5 d | `.\.venv-arm64\Scripts\python -m pytest tests/test_observability.py -q` |
| P0-8 | **Backups.** `scripts/backup.ps1` + `scripts/restore.ps1`: nightly SQLite `.backup` + `documents` snapshot to a configurable dir (P-1), retention rotation; one documented + exercised restore test. | `scripts/backup.ps1` (new), `scripts/restore.ps1` (new), `docs/backup-runbook.md` (new) | P0-4, P-1 | 0.5 d | run `scripts/restore.ps1` against a sample backup; assert rows restored |
| P0-9 | **DPDP baseline.** `backend/compliance.py`: consent flag on encounter (P-11), purpose-limitation + retention config (P-10), scheduled cleanup job (delete audio > N days; never delete transcripts/PDFs, only void), access-log coverage via `audit_log`. Keep AI-draft banner. Add a `docs/compliance.md` checklist. | `backend/compliance.py` (new), `backend/main.py` (wire cleanup scheduler), `docs/compliance.md` (new), `tests/test_compliance.py` (new) | P0-4, P0-5, P-10/P-11/P-12 | 0.5 d | `.\.venv-arm64\Scripts\python -m pytest tests/test_compliance.py -q` |

**Total effort: ~5.5–6 days** (matches the "~1 week" Phase 0 estimate).

**New dependencies.**
- `PyJWT` (P0-3) — pure Python, no compiled extensions → works on Python 3.12
  ARM64 **and** x64. Add to `backend/requirements.txt`.
- Everything else uses stdlib (`sqlite3`, `hashlib.pbkdf2_hmac`, `logging`,
  `hmac`, `json`) or already-installed packages (`fastapi.security`, `httpx`,
  `pydantic`).
- **Not used** (call out): `bcrypt`/`argon2-cffi` (Windows-ARM64 wheels
  uncertain), `prometheus-client` (deferred), `SQLAlchemy`/`Alembic` (deferred
  to Postgres cutover). All are x64-safe; ARM64 wheel status is why they're
  deferred rather than used.

---

## 5. Execution DAG

**Foundational, run first (parallel):**
- `P0-1` (CI/git) — independent.
- `P0-2` (secrets) — independent.
- `P0-4` (persistence) — independent; it is the *foundation* for P0-3/P0-5/P0-8/P0-9.

```
P0-1 ──────────────────────────────────────► (merge gate, no downstream deps)
P0-2 ──────────────────────────────────────► (no downstream deps)
P0-4 ──► P0-3 ──► P0-5 ──► P0-9
      └──► P0-8
P0-4 ──► P0-7
P0-3 ──► P0-6
```

- **Wave 1 (parallel, no shared files):** `P0-1`, `P0-2`, `P0-4`. Each creates
  its own files and only P0-2 touches `main.py` in this wave.
- **Wave 2 (parallel after P0-4):** `P0-3` (auth), `P0-7` (observability),
  `P0-8` (backups). File check: P0-3 edits `frontend/*` + `backend/auth.py`;
  P0-7 edits `backend/observability.py`; P0-8 edits only `scripts/*` + a doc.
  **No shared files** → safe. P0-3 and P0-7 both touch `main.py` (wiring) —
  **serialize the `main.py` wiring** or split: P0-3 owns auth wiring, P0-7 owns
  middleware wiring in separate PRs; do not run both's `main.py` edits in the
  same commit.
- **Wave 3:** `P0-5` (safety gate) needs P0-3 (roles) + P0-4 (audit_log). Then
  `P0-9` (compliance) needs P0-4 + P0-5.
- **Wave 4:** `P0-6` (versioning) is last because it rewrites endpoint paths in
  `frontend/app.js` **and** `tests/test_determinism.py`; running it before
  P0-3/P0-5 would force them to rebase their frontend work.

**Explicit file-conflict table (do NOT parallelize tasks sharing a row):**

| File | Edited by (serialize these) |
|---|---|
| `backend/main.py` | P0-2, P0-3, P0-4, P0-5, P0-6, P0-7, P0-9 → **edit in one integration commit per wave; never two workers concurrently** |
| `frontend/app.js` | P0-3, P0-5, P0-6 → strictly sequential |
| `frontend/index.html` | P0-3, P0-5 → sequential |
| `frontend/styles.css` | P0-3, P0-5 → sequential |
| `tests/test_determinism.py` | P0-6 (and determinism-plan D3/D5) → coordinate across plans |
| `.github/workflows/ci.yml` | P0-1 (and determinism-plan D6) → **coordinate; single owner** |
| `backend/requirements.txt` | P0-3 (adds PyJWT) → update before P0-3 merge |

---

## 6. Risks / rollback

- **`main.py` is the contention point.** Mitigation: push all logic into new
  modules (`config`, `secrets`, `auth`, `db`, `safety`, `observability`,
  `compliance`, `routers/`) and limit `main.py` edits to import/wire/mount —
  reviewed as one integration diff. Rollback: each module is independently
  revertible without touching the deterministic pipeline.
- **JWT / password libs on ARM64.** `PyJWT` + stdlib pbkdf2 are pure Python →
  zero wheel risk. If bcrypt is later demanded, verify a Windows-ARM64 wheel
  before adopting.
- **Versioning breaks offline tests.** `test_determinism.py` posts to `/api/format`
  (`:119, :211, :409`); P0-6 must update these or the offline gate goes red.
  Rollback: revert alias removal (old paths stay available per P-8 anyway).
- **Safety gate UX friction.** Requiring per-row confirmation before print could
  block legitimate workflows. Mitigation: Finalize is gated, but Print of an
  un-finalized draft remains allowed with the disclaimer (decision to be
  confirmed — flag if stricter blocking is wanted).
- **DPDP/legal.** This is a compliance posture, not legal advice (P-12). Do not
  store real patient data until sign-off. Rollback: compliance module is
  config-flagged; disable via env to return to demo mode.
- **Backups untested on ARM64.** `sqlite3` `.backup` is stdlib and portable;
  the only risk is Windows path/quoting in PowerShell scripts — test on the
  target machine (P-1).

---

## 7. Definition of Done

- [ ] `POST /api/v1/auth/login` → JWT; `/api/v1/*` enforce 401/403 by role;
      doctor-only Finalize/print.
- [x] No secret values in `.env`/committed files; `/api/health` reports presence
      only; keys load from env → `secrets.json`. **DONE (P0-2)** — note: POSIX
      0600 is a deliberate no-op on Windows (use ACLs; see `secret_loader.py`).
- [x] SQLite `patients`/`encounters`/`documents`/`audit_log` schema exists and
      survives restart. **Schema DONE (P0-4)** — writing `documents`/`audit_log`
      rows on Finalize + row-confirmation is still open (P0-5/P0-9).
- [ ] `/api/v1/encounters/{id}/finalize` blocks on any `status != verified` with
      a per-row list until explicit confirmation.
- [ ] `/api/v1/*` live with `/api/*` deprecated aliases (`X-Deprecated`); frontend
      on `/api/v1`.
- [ ] `/readyz` (DB+config+lexicon), structured JSON logs with request id,
      `/metrics` counters.
- [ ] `scripts/backup.ps1` + `scripts/restore.ps1` + runbook; one tested restore.
- [ ] DPDP baseline: consent flag, retention + cleanup, access logs, banner kept.
- [ ] CI green (`pytest` + `node --check` + lexicon `--check`).
- [ ] Deterministic pipeline behavior unchanged (no `determinism.py` logic diffs).
