# Multi-clinic, multi-doctor support: design

**Date:** 2026-10-14. **Status:** draft for user review (brainstormed and approved section by section in chat; nothing built yet).
**Builds on:** `2026-10-13-platform-foundation-design.md` (section 14 "D2 — many clinics" is pulled forward here in a slim form) and replaces the single shared login planned in `docs/superpowers/plans/2026-10-13-d0a-auth-and-hardening.md`.

## 1. Goal

Demonstrate, with real login, that the app can serve **one clinic with two doctors** and **two clinics**, and that data never overlaps: patients, encounters, prescriptions, the Today list, profile, letterhead, PDFs, OP numbers and the audit log stay specific to each clinic and, where it matters, to each doctor.

Success looks like the demo in section 13: two browser windows, two clinics, three doctors, no leakage, and an automated isolation suite that proves it.

## 2. Decisions taken (user, in the brainstorm)

| # | Decision |
|---|---|
| 1 | Inside a clinic: **shared patient registry and OP numbers; prescriptions are owned by their author.** Today defaults to "My prescriptions" with a "Whole clinic" toggle. |
| 2 | A doctor can **view and reprint** a colleague's prescription but **not edit, correct or re-save** it. Only the author can. |
| 3 | **Real username and password login only.** No demo picker, no "who am I" dropdown. |
| 4 | Each clinic has users who manage their own clinic's doctors in a **Users ("Team") screen**. Clinics themselves and the first user are created by an **operator command**. |
| 5 | **No RBAC for now.** The data model carries `role`, and one function (`can()`) is the single place where permission rules go later. |
| 6 | **One database file per clinic**, plus a small shared directory database. Chosen because isolation holds by construction and the shape ports to Postgres (schema or database per clinic) later. |
| 7 | **Letterhead is a choice, not a rule.** Default: one shared clinic letterhead. A doctor may opt in to their own. The doctors it lists are also a choice: only the author, all doctors, or a chosen subset. |
| 8 | The Users screen is open to every signed-in user of the clinic (no role check), with safeguards (section 8). |

## 3. Non-goals

RBAC rules, a super-admin screen, SSO, MFA, email password reset, per-clinic provider keys (STT and LLM keys stay shared), cross-clinic reporting, patient merge across clinics, the Postgres port itself, per-clinic backup tooling beyond "copy the folder".

## 4. Current state (what the code does today)

- `users` table exists (`db/migrations/001_init.sql`: `id, username, password_hash, role CHECK(doctor|assistant|admin), is_active, created_at`) and is unused. No login.
- `encounters.doctor_id` exists but is never set by the save route; `documents.finalized_by` is never set either (`api/persistence.py`).
- `clinic_profile` (`003_clinic_profile.sql`) is one row (`CHECK id = 1`) mixing clinic fields (clinic name, address, phone) and doctor fields (doctor name, qualifications, registration no.).
- Templates carry a `clinic` column, hard-coded to `'default'` (`templates/service.py`).
- OP numbers come from one sequence per day (`db/opno.py`), patients are matched by OP number across the whole database (`upsert_patient`).
- Paths come from `db_path()`, `pdf_dir()` (`db/__init__.py`) and `templates_dir()` (`templates/service.py`); `get_conn()` opens `db_path()`.
- `top_medicines(conn)` (ACC2 hints) reads all finalized documents, not one doctor's.
- Audit rows take an `actor` argument; nothing fills it from a session.

## 5. Architecture

```
data/
  directory.db                  clinics + username index + login attempts (no patient data)
  clinics/
    <slug>/
      app.db                    today's schema, plus the migrations in section 12
      pdfs/
      templates/                letterhead uploads and logos
```

### 5.1 Directory database

Tables (new `directory/` module with its own tiny migration runner):

- `clinics(id, slug UNIQUE, name, status 'active'|'disabled', op_prefix DEFAULT 'OP', created_at)`
- `login_index(username PRIMARY KEY COLLATE NOCASE, clinic_slug, user_id)` — usernames are unique system-wide, so the login form needs no clinic picker.
- `login_attempts(username, ip, failed_count, locked_until, updated_at)` — throttling state, shared.

It never stores patient data, passwords, or profile content.

### 5.2 Clinic databases

Each `clinics/<slug>/app.db` is exactly the current schema (migrations run per clinic file). Users, patients, encounters, documents, templates, audit and the profile all live there, so existing foreign keys (`encounters.doctor_id`, `documents.finalized_by`, `audit_log`) keep working inside one file.

### 5.3 Request scope

A `Scope` value `(clinic_slug, user_id, username, role)` travels in a `ContextVar` (`doctor_dictation/scope.py`) set by the auth middleware. The existing helpers read it:

- `db_path()` → `data/clinics/<slug>/app.db`; `pdf_dir()` → `.../pdfs`; `templates_dir()` → `.../templates`.
- `get_conn()` keeps its signature, so most call sites do not change.
- `db.log_audit` fills a missing `actor` from the scope (this was already planned for D0a).

**Fail closed.** In multi-clinic mode, `db_path()`, `pdf_dir()`, `templates_dir()` and `get_conn()` raise `NoScope` when there is no scope. They never fall back to a default database. Work that legitimately runs outside a request (startup migration, the expired-draft purge) iterates the clinics explicitly through a `for_each_clinic()` helper that sets the scope itself.

**Threads.** `asyncio.to_thread` copies the context, so DB work in worker threads keeps its scope. The PDF worker thread (a `ThreadPoolExecutor` in `pdf/renderer.py`) does **not** copy context; it renders HTML and must never open a database. A test pins that.

**Single-database mode.** An env flag (`MULTI_CLINIC=0`, the default for the existing test suite) keeps today's behaviour (`DB_PATH`), so current tests and the dev setup are unaffected. The demo and deployment run with `MULTI_CLINIC=1`.

### 5.4 Postgres path

Each clinic file maps to a Postgres schema (or database), the directory maps to a shared schema. Code only asks for "the current clinic's connection" (`get_conn()`), so the change stays inside the connection and path layer.

## 6. Identity and login

### 6.1 Users table (per clinic) additions

Migration `005_users_profile.sql` adds: `display_name`, `doctor_name`, `qualifications`, `reg_no` (the doctor fields moved out of `clinic_profile`), `session_version INTEGER DEFAULT 0`, `must_change_password INTEGER DEFAULT 1`, `last_login_at`. `role` stays and defaults to `doctor` for every demo user. **No role is enforced.**

### 6.2 Login flow

- `POST /api/v1/auth/login {username, password}`: look the username up in the directory, open that clinic's database, verify the password. Hashing uses `hashlib.scrypt` from the standard library (no new dependency), with a per-user salt and encoded parameters so they can be raised later.
- Unknown usernames still run a dummy hash comparison so response time does not reveal which usernames exist.
- **Throttling:** 5 failed attempts for a `(username, ip)` pair locks it for 5 minutes, stored in `login_attempts`. The error message is the same for wrong user, wrong password and locked.
- **Cookie** `dd_session`: `HttpOnly`, `SameSite=Lax`, `Secure` when the request arrived over HTTPS (`X-Forwarded-Proto`), 12-hour life. Payload `{clinic, uid, ver, iat, exp, sid}` signed with HMAC-SHA256 using `SESSION_SECRET` from the environment. Outside a dev flag the app refuses to start without a real secret (at least 32 characters).
- **Every request** verifies the signature and expiry, loads the user row from the clinic database, and requires `is_active` and `session_version` to match. A disabled user or a password reset therefore ends that session immediately.
- Failures answer 401 JSON for API paths and redirect HTML paths to `/login`.
- `POST /api/v1/auth/logout` clears the cookie and revokes that session's `sid` in the directory (`revoked_sessions`, purged after the cookie's 12-hour life), so a copied cookie is dead on the server while the user's other sessions keep working (reset/change-password still end all of them via `session_version`). `GET /api/v1/auth/me` returns clinic name and the user's display fields for the top bar. `POST /api/v1/auth/change-password` (current password required; bumps `session_version`; clears `must_change_password`). A first login with a temporary password forces the change.
- **CSRF:** every state-changing request (POST, PUT, DELETE) must carry the header `X-DD-Client: 1`; the browser cannot send a custom header cross-site without a CORS preflight, and CORS stays on an allow-list. The frontend adds the header in its one request helper (and in the multipart upload).
- **Public paths:** `/login`, its assets, `/api/v1/auth/login`, `/api/health`. Everything else needs a session.

### 6.3 RBAC-ready, not RBAC

New module `doctor_dictation/policy.py` with one function `can(user, action, resource=None) -> bool`. Routes that change data call it with a named action (`document.edit`, `document.reprint`, `document.view`, `user.create`, `user.disable`, `letterhead.manage`, …). Today it returns true, except the **ownership rule**: `document.edit` requires `resource.author_id == user.id`. Later RBAC adds rules inside this function (for example "an admin may edit any document") with no route changes. The audit log already records actor and action, so rules can be tested against history.

## 7. Doctor-level behaviour (inside one clinic)

### 7.1 Authorship

- First save sets `encounters.doctor_id` to the signed-in user and `documents.finalized_by` likewise. A re-save keeps the original author as `doctor_id` and records the saver in `finalized_by`.
- **Edit, correct, re-save** of a document require `can(user, "document.edit", doc)`; a non-author gets **403** `{"error": "This prescription belongs to <author name>. You can view and reprint it."}`. The server enforces this; the UI only reflects it.
- **View, load and reprint** (`GET /documents/{id}`, `GET /documents/{id}/pdf`) are allowed for any user of the clinic.
- The frontend, when it opens a colleague's prescription, marks the sheet read-only: mic and Save disabled, edits blocked, Print enabled, a banner "Dr. Mehta's prescription: view only". The author may continue to correct and re-save their own as today.

### 7.2 Today list

`GET /api/v1/encounters/today?scope=mine|clinic` (default `mine`). Rows gain `doctor_name`. The sidebar gets a "My prescriptions / Whole clinic" toggle; clinic rows show the author's name.

### 7.3 Hints and recent medicines

`top_medicines(conn, limit, doctor_id=None)` filters through `encounters.doctor_id`; the STT hint builder passes the signed-in doctor. A doctor's hints never include a colleague's habits, and never another clinic's (they are in another file).

### 7.4 Audit

`audit_log.actor` is the signed-in username, filled automatically. New audit actions: `login`, `login_failed` (directory side counters only, no password data), `logout`, `user_create`, `user_disable`, `user_enable`, `password_reset`, `password_change`, `letterhead_scope_change`.

## 8. Profile split and the Users screen

### 8.1 Profile

The Profile dialog shows two parts:

- **Clinic details** (clinic name, address, phone, OP prefix): shared, stored in `clinic_profile`; any signed-in user of the clinic may edit.
- **My details** (doctor name, qualifications, registration no.): the signed-in user's own, stored on their `users` row.

`GET/PUT /api/v1/profile` return and accept both parts. Migration `005` copies the existing doctor fields into the first doctor created for an adopted clinic (section 12). Printing resolves doctor fields from the **author** and clinic fields from the **clinic**, never from the viewer.

### 8.2 Users ("Team") screen

A "Team" button in the top bar, open to every signed-in user (no role check). It lists the clinic's users (display name, username, active, last login) and supports:

- **Add user:** username (unique system-wide), display name, optional doctor fields. A generated temporary password is shown **once** and `must_change_password` is set.
- **Disable / enable** a user (never delete: prescriptions keep their author).
- **Reset password:** new temporary password shown once; bumps `session_version`.
- **Safeguards:** you cannot disable yourself or the last active user; the username check and the directory write happen first and are rolled back if the clinic write fails; every action is audited; usernames are 3–40 characters of letters, digits, `.`, `_`, `-`.

Routes: `GET /api/v1/users`, `POST /api/v1/users`, `POST /api/v1/users/{id}/disable|enable|reset-password`.

## 9. Letterhead

### 9.1 Scope is a choice

`templates` gets `owner_user_id INTEGER NULL` (empty means clinic-wide) via migration. Resolution for a prescription, in this order:

1. The author's own **active** letterhead, if the author has opted in and has one.
2. Otherwise the clinic's active letterhead.
3. Otherwise the built-in layout.

Nothing changes for a clinic where nobody opts in: everyone uses the clinic letterhead. At **Accept** the doctor chooses "For the whole clinic" (default) or "For my prescriptions only". The Profile → Letterhead section shows both states ("Clinic letterhead: active", "My own letterhead: none / active") with "Use the clinic letterhead" to switch back. Each scope keeps at most one active template; the existing stop-using and upload quota stay and are counted per clinic (the clinic file).

### 9.2 Which doctors a letterhead lists is a choice

The layout vocabulary (`pdf/layout.py`) gains a **`doctors` block**: `{"type": "doctors", "role": ..., "align": ...}`. Where it sits, the renderer prints one entry per doctor (name, qualifications, registration no.). The *selection* lives on the template row as `doctors_mode` (`author` default | `all` | `selected`) and `doctors_ids` (JSON list, used for `selected`). Existing `field` blocks (`doctor_name`, `qualifications`, `reg_no`) keep meaning "the author", so current layouts work unchanged.

- `author`: only the doctor who wrote the prescription.
- `all`: every **active** doctor in the clinic, in a stable order.
- `selected`: the ticked subset; disabled or unknown ids are skipped.
- The mode and ids are set in the review screen and editable on an active template without re-uploading (`PUT /api/v1/templates/{id}/doctors`).
- The vision model never guesses which user a printed name belongs to. Names it reads from the pad appear as hints on the review screen; the human chooses the mode.

### 9.3 Guard against wrong names on a pad

The vision prompt must put a person's name and qualifications into doctor fields or the doctors block, never into a literal text line. The review screen additionally warns on any literal line that looks like a doctor's name (contains "Dr", "MBBS", "MD", "MS", "DNB" as whole words). This is a heuristic, not a guarantee; the human reviews every line before accepting.

### 9.4 Render-time resolution

The sheet builder receives `meta.profile` (clinic fields from the clinic row, doctor fields from the author) and `meta.doctors` (the resolved list for the doctors block). Live values win over the layout's stored profile snapshot when non-blank, so a reprint by a colleague still shows the author.

## 10. OP numbers

OP numbers stay per clinic (each clinic file has its own sequence). `clinics.op_prefix` (default `OP`, stored in the directory and mirrored in `clinic_profile`) replaces the hard-coded `OP-`: `RAO-20261014-001`. Two clinics creating their first patient on the same day then show different strings. The prefix is 2–6 uppercase letters or digits, set at clinic creation and editable in Clinic details (existing numbers are not rewritten).

## 11. Operator command line

`python -m doctor_dictation.admin <command>` (run by the operator, never exposed over HTTP):

- `create-clinic --slug rao --name "Rao Clinic" --op-prefix RAO --first-user dr.rao`: creates the folder, runs migrations, inserts the clinic, creates the first user with a printed temporary password.
- `list-clinics`, `reset-password --user NAME`, `migrate-all`.
- `adopt-existing --slug NAME`: moves today's `doctor_dictation/data/app.db`, `pdfs/`, `templates/` into `clinics/<slug>/`, creates a first doctor from the saved profile (temporary password), indexes the username.
- `seed-demo`: two clinics (Rao Clinic: Dr. Rao, Dr. Mehta; Iyer Clinic: Dr. Iyer), each with a few fake patients and prescriptions (including one "document 1" in each), and per-clinic letterhead settings. Refuses to run unless `DEMO_MODE=1`.

## 12. Migrations and rollout

- Clinic database migrations: `005_users_profile.sql` (users columns, as in 6.1 and 8.1), `006_templates_scope.sql` (`owner_user_id`, `doctors_mode`, `doctors_ids`), `007_clinic_profile_prefix.sql` (`op_prefix`; clinic-only fields). All idempotent. Existing rows stay valid.
- Directory migrations are separate and numbered on their own.
- D0a: the shared basic-auth middleware is dropped; its CORS allow-list, security headers and demo banner remain and sit behind the session middleware. D0b (Docker, proxy, load test) continues; the Caddy config passes cookies and sets `X-Forwarded-Proto`.
- The existing test suite keeps running in single-database mode; new tests run in multi-clinic mode.

## 13. Testing and the demo

### 13.1 Automated isolation proof

Seeded fixture: Clinic A (Rao, Mehta) and Clinic B (Iyer).

- **Route sweep:** enumerate every route from `app.openapi()`; as a Clinic B user request Clinic A's ids and assert 404 or 403, never A's data. Both clinics have a "document 1", so the sweep also asserts B receives B's own record, and that an id existing only in A returns 404 in B.
- **Files:** A's PDFs, logos and uploads are unreadable through B's session (includes traversal and symlink attempts; reuse the existing confinement tests).
- **Fail-closed:** a database or path call with no scope raises, inside a request and in a bare thread; the PDF worker thread never touches a database.
- **Doctor level:** Mehta can view and reprint Rao's prescription and the PDF carries Rao's details; edit, correct and re-save return 403; hints are per doctor; Today `mine` versus `clinic` differ.
- **Auth:** login success and failure, throttling, tampered and expired cookie, disabled user ends the session, password reset ends the session, missing CSRF header is rejected, unknown-user timing does not diverge badly (loose bound, not an exact timing test).
- **Letterhead:** clinic default, doctor opt-in override and switch back, doctors block in all three modes, disabled doctor skipped, review warning for a doctor-like literal line.
- **OP numbers:** both clinics produce a `-001` the same day with different prefixes and no collision; concurrency inside one clinic still yields distinct numbers.
- **Browser:** two Playwright contexts side by side (different clinics), with screenshots read by a person.

### 13.2 Demo script (about 5 minutes)

1. Two windows: Dr. Rao (Clinic A) and Dr. Iyer (Clinic B); different Today lists.
2. Rao dictates and saves: it appears only in A; both clinics show "document 1".
3. Dr. Mehta (A) switches Today to "Whole clinic", opens and reprints Rao's prescription (Rao's name prints), and sees edit refused.
4. Show A's shared letterpad listing both doctors, and B's own letterhead.
5. Paste A's PDF link while signed in as Iyer: 404.
6. Show per-clinic audit actors and the data folder with two separate database files.

## 14. Build order (each its own plan, subagent-driven)

| Plan | Delivers |
|---|---|
| M1 | Directory database, per-clinic paths, fail-closed `Scope`, `for_each_clinic`, `MULTI_CLINIC` flag, admin command (`create-clinic`, `adopt-existing`, `migrate-all`) |
| M2 | Users columns migration, scrypt login, cookie, throttling, CSRF header, `/login` page, `policy.py`, audit actor from scope |
| M3 | Authorship (`doctor_id`/`finalized_by`), 403 rules, view-only UI, Profile split, Today scopes, per-doctor hints |
| M4 | Letterhead scope (`owner_user_id`), doctors block and modes, review warning, `PUT .../doctors`, render-time resolution, OP prefix |
| M5 | Team (Users) screen and routes |
| M6 | Isolation suite, `seed-demo`, demo script, browser evidence |

## 15. Risks and unverified items

- Request scope surviving thread boundaries is the central risk: pinned by tests (section 13.1), not assumed.
- SQLite with dozens of clinic files is fine; thousands would not be. Cross-clinic queries are intentionally impossible.
- Backup is "copy the clinic folder" (flush the write-ahead log first); no tooling in this scope.
- Stateless cookies mean "sign out everywhere" works only through the per-user `session_version` check on each request.
- Without RBAC, any signed-in user of a clinic can add or disable colleagues. The safeguards in 8.2 limit accidents, not abuse; real roles come later through `policy.py`.
- Still unverified from earlier work: a real vision model, a real iPhone HEIC, real printing through the PDF iframe in Chrome and Safari.

## 16. Open items for review

1. Session lifetime (12 h) and lockout (5 failures, 5 minutes) are proposals.
2. Username rules (section 8.2) and minimum password length (proposal: 10 characters on change; temporary passwords are generated, 16 characters).
3. Whether Clinic details may be edited by every user (current plan) or only by the first user until RBAC exists.
