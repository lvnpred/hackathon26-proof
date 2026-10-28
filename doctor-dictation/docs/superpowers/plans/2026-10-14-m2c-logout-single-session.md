# M2c: Logout ends only that browser's session

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** `POST /api/v1/auth/logout` must make the cookie that was used **unusable on the server**, while the same user's other sign-ins (another browser, another device) keep working. Today logout only clears the browser's cookie, so a copied cookie stays valid for 12 hours (M2b final-review finding m1). The user decided: logout ends that session only, not the other logins.

**Why not `session_version`:** bumping it (what reset and change-password do) ends **every** session of that user. Ending one session needs each session to be identifiable.

**Architecture:** each cookie gets a random session id `sid`. Logout writes that `sid` into a small `revoked_sessions` table in the **directory** database (`load_identity` already opens it on every request to check the clinic, so the lookup costs one indexed read and needs no clinic migration). `load_identity` rejects a cookie whose `sid` is revoked. Rows are purged once they are older than a cookie's maximum life.

**Tech Stack:** Python stdlib `secrets`, `sqlite3`; pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-14-multi-clinic-multi-doctor-design.md` section 6.2 (logout bullet) and section 15 (stateless cookies). Builds on M2a and M2b (committed as `ae5864c` on local `main`). Baseline: **597 passed, 1 skipped**; this plan adds about 12 tests (state the exact number in the report), nothing is committed (user rule: never `git commit` unless asked).

## Global Constraints

- Never run `git commit` / `git push` / `git add`. Leave all changes in the working tree.
- Standard library only. Environment read at call time. Files under 500 lines.
- Cookie payload becomes `{clinic, uid, ver, iat, exp, sid}`; `sid` is `secrets.token_urlsafe(16)` (22 chars of `[A-Za-z0-9_-]`); `verify` accepts only a `str` sid of 16 to 64 characters from that alphabet. A cookie with **no** sid (issued before this change) is invalid: those users sign in again (M2 is not deployed anywhere, so this costs nothing).
- `Identity` keeps its field order; the new field is appended: `sid: str = ""`. `authn.authenticate` still returns an Identity with `sid == ""`; only `load_identity` fills it (from the verified payload).
- Revocation lives in `directory.db` (migration `002_revoked_sessions.sql`), never in a clinic database.
- Logout failure must **fail closed**: if the revocation cannot be written (`sqlite3.Error`), return `503 {"error": "try again"}` and do **not** clear the cookie (the user retries; the session is still honestly valid).
- Reset password, change password, disable user and disable clinic keep working exactly as before (they use `session_version` / status and end all sessions).
- Single mode (`MULTI_CLINIC` off) is unchanged: logout still answers 404.
- Tests never touch the network or `doctor_dictation/data/`; use the `multi` fixture.

## Interfaces

- `sessions.sign(clinic_slug, user_id, session_version, now=None, sid=None) -> str` (generates a fresh `sid` when `None`); `sessions.verify(token, now=None) -> dict | None` (payload now contains `sid`).
- `sessions.Identity(..., session_version: int = 0, sid: str = "")`.
- New `doctor_dictation/directory/revocations.py`: `revoke_session(conn, sid, expires_at, now=None) -> None` (idempotent: `INSERT OR IGNORE`; also deletes rows whose `expires_at` is in the past); `is_revoked(conn, sid) -> bool`. `expires_at` is epoch seconds; `now` is epoch seconds (default `time.time()`).
- New `doctor_dictation/directory/migrations/002_revoked_sessions.sql`: `CREATE TABLE IF NOT EXISTS revoked_sessions (sid TEXT PRIMARY KEY, expires_at INTEGER NOT NULL)` and an index on `expires_at`.
- `authn.load_identity`: after the signature, clinic-status and failed-clinic checks and **inside the same directory connection**, return `None` if `is_revoked(d, payload["sid"])`; on success return the identity with `sid=payload["sid"]` (use `dataclasses.replace`).
- `api/auth.py` logout: revoke `request.state.identity.sid` with `expires_at = int(time.time()) + sessions.LIFETIME_SECONDS` (always at least the cookie's real expiry), in `asyncio.to_thread`; then the existing audit row and cookie clearing. If the identity has an empty sid (should not happen) treat it as a server error (500 is acceptable; do not silently skip).

## Task 1 (single task): session id, revocation table, logout

**Files:** modify `doctor_dictation/sessions.py`, `doctor_dictation/authn.py`, `doctor_dictation/api/auth.py`; create `doctor_dictation/directory/revocations.py`, `doctor_dictation/directory/migrations/002_revoked_sessions.sql`, `tests/test_revocations.py`; update the existing tests whose cookie-payload expectations change (`tests/test_sessions.py`, `tests/test_authn.py`, `tests/test_session_middleware.py`, `tests/test_auth_routes.py`; read each before editing and keep every assertion's intent); edit the docstring of `sessions.py` (it says revocation is only `session_version`) and spec section 6.2's logout bullet to say logout revokes that session's `sid` in the directory.

- [ ] **Step 1: Write the failing tests first** (`tests/test_revocations.py` unless noted; use the `multi` fixture and the `clinics.provision_clinic` / `accounts.create_user` setup used in `tests/test_authn.py`):
  1. `test_sign_gives_each_cookie_a_distinct_sid` (two `sign` calls for the same user have different `sid`; payload keys are exactly `clinic, uid, ver, iat, exp, sid`).
  2. `test_verify_rejects_a_missing_or_malformed_sid` (no `sid`, `sid` of `5`, `True`, `""`, 100 characters, characters outside the alphabet; build them with `sessions._encode`, validly signed).
  3. `test_revoke_and_is_revoked_roundtrip_and_are_idempotent`.
  4. `test_revoke_purges_rows_past_their_expiry` (a row with `expires_at` in the past is deleted by the next `revoke_session`; a future row stays).
  5. `test_load_identity_rejects_a_revoked_sid` and `test_other_sessions_of_the_same_user_survive_a_revocation` (**the user's requirement**: two cookies for one user, revoke one, the other still loads).
  6. `test_logout_ends_that_session_only` (tests/test_auth_routes.py style with `TestClient`: log in twice with two clients, set the permanent password via one, sign both in; log out one; the replayed cookie of the first gets 401 on `/api/v1/auth/me`; the second client's `/me` is still 200).
  7. `test_replayed_cookie_after_logout_is_dead_even_if_the_browser_ignored_the_clear` (copy the cookie value before logout, put it back in a fresh client, expect 401).
  8. `test_logout_that_cannot_revoke_is_503_and_keeps_the_cookie` (monkeypatch `revoke_session` in `api.auth` to raise `sqlite3.OperationalError`; expect 503, no cookie deletion header, and the session still works afterwards).
  9. `test_change_password_still_ends_every_session` (a second client's cookie dies after the first changes the password).
  10. `test_a_cookie_without_a_sid_is_refused` (sign a payload by hand without `sid`, `/api/v1/auth/me` gives 401).
  11. `test_two_logins_get_two_different_sids` (login twice, decode both cookies with `sessions.verify`, sids differ).
  12. `test_logout_in_single_mode_is_still_404` (already covered by M2b tests; keep that test passing, do not duplicate).
- [ ] **Step 2: Run them and confirm they fail for the right reason** (`.venv/bin/python -m pytest tests/test_revocations.py -q`).
- [ ] **Step 3: Implement** exactly as in Interfaces and Global Constraints.
- [ ] **Step 4: Fix the existing tests** whose payload expectation changed; run `.venv/bin/python -m pytest tests/ -q`; expect `597 + new` passed, 1 skipped, no new warnings.
- [ ] **Step 5: Leave uncommitted** and report the exact test count and the changed files.

## Self-review (against the user's decision)

- "Logout ends that session": Task 1 tests 5, 6, 7.
- "not the other logins": tests 5 and 6.
- Fail-closed logout: test 8.
- Old behaviours kept: test 9 and the existing M2a/M2b suites.

## Not in this plan

A "sign out everywhere" button (use reset password / change password today); listing active sessions; revocation cleanup beyond the purge on write; moving the table to a per-clinic database.
