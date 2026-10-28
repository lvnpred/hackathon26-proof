# M5: Team (Users) screen and routes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every signed-in user of a clinic can open a "Team" panel from the top bar, see the clinic's users (display name, username, active, last sign-in), add a colleague (temporary password shown once), disable or enable a colleague (never delete) and reset a colleague's password (temporary password shown once, all their sessions end). Users of other clinics are invisible and untouchable.

**Architecture:** Account logic stays in `doctor_dictation/accounts.py`, which already creates users with the directory/clinic rollback and resets passwords (`accounts.py:44-97`). This plan adds `list_users`, `get_user`, `set_active` and a clinic-scoped `reset_user_password` there, plus a `NoSuchUser` error. A NEW router `doctor_dictation/api/users.py` exposes five routes; each one asks `policy.can(...)` first and works only on `identity.clinic_slug`, the signed-in user's own clinic file, so an id from another clinic is simply not found (404). The panel is NEW `frontend/team.js` + `frontend/team.css`; `team.js` builds its own `<dialog>`, so `index.html` gains only one button, one `<link>` and one `<script>`.

**Tech Stack:** FastAPI/Starlette (installed: 0.143), pydantic 2, stdlib `sqlite3` (3.53 locally), vanilla JS, pytest + `TestClient`. No new dependencies, no migrations.

**Spec:** `docs/superpowers/specs/2026-10-14-multi-clinic-multi-doctor-design.md` section 8.2 (Team screen, routes, safeguards), 6.3 (`can()` with `user.create`, `user.disable`), 6.2 ("a disabled user or a password reset therefore ends that session immediately"), 7.4 (audit actions `user_create`, `user_disable`, `user_enable`, `password_reset`), 13.1 Auth bullet (disabled user and password reset end the session). **Requires M2 (M2a + M2b) done**, committed as `ae5864c`. M2c (logout `sid`) is independent: nothing here reads `Identity.sid`.

**Plan 6 of 7 (M5).** Before the first task run `.venv/bin/python -m pytest tests/ -q` and note the count `N` (597 passed, 1 skipped at `ae5864c`, plus whatever M2c, M3 and M4 have added by the time this runs). **This plan adds 32 tests** (12 + 12 + 8) and edits one existing assertion (the route table in `tests/test_api_app.py`), so after it the suite is `597 + earlier plans + 32` passed, 1 skipped.

## Deliberate differences from the spec

- **Disabling also bumps `session_version`.** The spec ends a disabled user's sessions through the `is_active` check (`authn.py:76` at `ae5864c`, `:78` after M2c). That check alone would let an old cookie work again the moment the user is re-enabled, for the rest of its 12-hour life. Bumping the version on disable means an old cookie stays dead: re-enabled users sign in again.
- **You cannot reset your own password from the Team screen.** The spec is silent. A self-reset would end your own session the moment the temporary password is displayed. The route answers 400 "Ask a colleague to reset it". The main app has no voluntary change-password screen (the change form in `login.js` is only the forced first-login step); that is out of scope here.
- **Two more policy action names: `user.view` (list) and `user.reset_password`.** The spec's list in 6.3 ends with "…". Enable uses `user.disable`: one permission covers active status in both directions. `can()` still returns True for all of them, so behaviour does not change; later RBAC rules have one name per route to hang on.
- **The order of the two writes when adding a user is the M2a one.** The spec says "username check and directory write first, rolled back if the clinic write fails". The directory row needs the new `user_id`, so `accounts.create_user` checks the directory first, inserts the clinic row, indexes the username, and deletes the clinic row if indexing fails (`accounts.py:54-77`, recorded in the M2a plan's own differences). This plan reuses it unchanged and proves the rollback through HTTP.
- **Disabling an already disabled user, or enabling an active one, is a no-op**: 200 with the current row, no audit row (nothing happened).
- **"Last active user" protects against a stale identity, not the normal path.** A signed-in user is always active (`authn.py:76`) and cannot disable themselves, so through the route there is always one other active user: the caller. The rule matters when the caller was disabled by someone else a moment ago. It is checked inside the same `BEGIN IMMEDIATE` write lock as the update, so two concurrent disables cannot both pass.
- **The Add form offers no role.** Spec 6.1: "No role is enforced". New users get `doctor`, the `create_user` default (`accounts.py:45`).

## Global Constraints

- Keep files under 500 lines (`tests/test_file_sizes.py`): `accounts.py` goes from 120 to about 190 lines; `api/users.py` is about 115; `team.js` about 200.
- Never run `git commit`, `git add` or `git push` (user rule). Each task ends with "leave uncommitted".
- No migrations: every column used (`is_active`, `session_version`, `must_change_password`, `last_login_at`, `display_name`) exists after clinic migrations `001` and `005`.
- Temporary passwords are generated by `passwords.temp_password()` (16 characters), are returned **once** in a response with `Cache-Control: no-store`, and never appear in audit rows, logs, list responses or exception text.
- Every route works only on `request.state.identity.clinic_slug`; no route takes a clinic from the client.
- Validate at the boundary: path ids are `int` in `1..2**63-1` (422 otherwise, which also avoids sqlite's `OverflowError` on huge ints); body strings have `max_length`; usernames go through `accounts.check_username`.
- The browser renders names with `textContent` only (display names are typed by users).
- Tests are offline, never touch `doctor_dictation/data/`, and the multi-clinic ones use the `multi` fixture (`tests/conftest.py:12-19`).

## Shared-file edits (keep them this small so M3/M4/M6 still apply)

Apply by anchor, not by line number: M3/M4 may have edited these files first.

| File | Anchor | Edit |
|---|---|---|
| `doctor_dictation/policy.py` | the `ACTIONS = frozenset({...})` set (line 5 at `ae5864c`) | add `"user.view"` and `"user.reset_password"`; keep every other entry |
| `doctor_dictation/api/app.py` | the import block (lines 17-20) and the `for module in (...)` router tuple (line 78) | one import line, one tuple entry `users_api` |
| `tests/test_api_app.py` | `EXPECTED_ROUTES` (lines 13-27) | five tuples |
| `frontend/index.html` | the `letterhead.css` link (line 8), the `profileOpenBtn` button (line 23), the `letterhead.js` script (line 206) | one `<link>` after, one `<button>` after, one `<script>` after |

## Review Focus

1. **Another clinic's ids: 404 and untouched.** User ids repeat across clinic files (each has its own `AUTOINCREMENT`), so the same number in another clinic is a different person. Task 1 `test_ids_from_another_clinic_raise_no_such_user_and_change_nothing`, Task 2 `test_ids_from_another_clinic_are_404_and_untouched`.
2. **Disable ends sessions now, and enable never revives an old cookie.** Task 1 `test_enable_restores_sign_in_but_never_revives_an_old_cookie`, Task 2 `test_disable_ends_the_session_at_once_and_enable_does_not_revive_it`. Reset ends sessions too: Task 2 `test_reset_password_ends_the_session_and_the_new_temp_password_forces_a_change`.
3. **Temporary password exposure.** It is returned once with `no-store` and never shows up in the list or the audit log: Task 2 `test_add_user_shows_a_temporary_password_once_and_it_signs_in_with_a_forced_change` and `test_every_team_action_is_audited_with_the_signed_in_actor_and_no_password`. The browser forgets it when the panel closes: Task 3 `test_temporary_password_is_shown_once_with_a_copy_button_and_a_warning`.
4. **Self and last-active safeguards are checked under the write lock.** Task 1 `test_the_last_active_user_cannot_be_disabled`, `test_you_cannot_disable_yourself`; Task 2 `test_you_cannot_disable_or_reset_yourself`.
5. **Every route goes through `policy.can` before acting.** Task 2 `test_every_team_route_asks_policy_can_and_a_denial_is_403`.
6. **No HTML injection from display names.** Task 3 `test_team_js_never_turns_user_data_into_html` (plus manual check 10).

---

### Task 1: Account operations for the Team screen (`accounts.py`, `policy.py`)

**Files:**
- Modify: `doctor_dictation/accounts.py` (add `NoSuchUser` after `AccountError` at lines 22-23; replace `reset_password` at lines 83-97; append new functions after `change_password`, which ends at line 120)
- Modify: `doctor_dictation/policy.py` (the `ACTIONS` set)
- Create: `tests/test_accounts_team.py`

**Interfaces:**
- Consumes: `accounts.clinic_conn`, `accounts.create_user` (`accounts.py:32-80`), `passwords.temp_password` / `hash_password`, `dbmod.log_audit(conn, actor, role, action, entity, entity_id, detail)` (`db/__init__.py:260-280`; fills `actor`/`role` from the scope only when `actor` is None), `sessions.Identity(clinic_slug, user_id, username, role, ...)`, `authn.load_identity`, `authn.authenticate`.
- Produces (`doctor_dictation.accounts`):
  - `NoSuchUser(AccountError)`: the id or username is not in that clinic.
  - `list_users(clinic_slug) -> list[dict]`, ordered by id; each dict is exactly `{"id", "username", "display_name", "role", "is_active": bool, "last_login_at": str | None, "must_change_password": bool}` (`display_name` falls back to the username).
  - `get_user(clinic_slug, user_id) -> dict` (same shape) or raises `NoSuchUser`.
  - `set_active(identity, user_id, active: bool) -> dict`: returns the updated row. Raises `AccountError` for yourself (disable) or the last active user, and `NoSuchUser` for an unknown id. A disable sets `is_active = 0` and bumps `session_version`; an enable sets `is_active = 1`. The change is audited as `user_disable` / `user_enable` with the identity's username and role.
  - `reset_user_password(identity, user_id) -> str`: the new temporary password. Raises `AccountError` for yourself and `NoSuchUser` for an unknown id. Audited as `password_reset`.
  - `reset_password(username, actor=None) -> str`: unchanged behaviour (the operator CLI, `admin.py:57-58`); it now raises `NoSuchUser`, a subclass, so `admin.py:215`'s `except ValueError` and the existing tests still match.
- Produces (`doctor_dictation.policy`): `ACTIONS` also contains `"user.view"` and `"user.reset_password"`.

- [ ] **Step 1: Write the failing tests**

`tests/test_accounts_team.py`:

```python
"""Team account operations: list, disable/enable, clinic-scoped reset, safeguards. Offline."""
from contextlib import closing

import pytest

from doctor_dictation import accounts as A
from doctor_dictation import authn, clinics, policy, sessions
from doctor_dictation import db as dbmod
from doctor_dictation import passwords as P
from doctor_dictation.scope import clinic_dir
from doctor_dictation.sessions import Identity

PW = "a-long-password-1"


@pytest.fixture()
def team(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    clinics.provision_clinic("iyer", "Iyer Clinic")
    rao, _ = A.create_user("rao", "dr.rao", display_name="Dr. Rao", password=PW)
    mehta, _ = A.create_user("rao", "dr.mehta", display_name="Dr. Mehta", password=PW)
    shah, _ = A.create_user("rao", "dr.shah", password=PW)
    iyer, _ = A.create_user("iyer", "dr.iyer", display_name="Dr. Iyer", password=PW)
    return {"rao": rao, "mehta": mehta, "shah": shah, "iyer": iyer}


def _me(team, name="rao", slug="rao"):
    return Identity(slug, team[name], "dr." + name, "doctor")


def _conn(slug):
    return dbmod.get_conn(clinic_dir(slug) / "app.db")


def _row(slug, uid):
    with closing(_conn(slug)) as c:
        return c.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def _audits(slug, action):
    with closing(_conn(slug)) as c:
        return c.execute("SELECT actor, role, entity_id, detail FROM audit_log WHERE action = ? ORDER BY id",
                         (action,)).fetchall()


def test_list_users_returns_public_fields_in_id_order_for_one_clinic_only(team):
    rows = A.list_users("rao")
    assert [r["username"] for r in rows] == ["dr.rao", "dr.mehta", "dr.shah"]
    assert rows[0] == {"id": team["rao"], "username": "dr.rao", "display_name": "Dr. Rao", "role": "doctor",
                       "is_active": True, "last_login_at": None, "must_change_password": True}
    assert rows[2]["display_name"] == "dr.shah"                 # no display name given: the username
    assert [r["username"] for r in A.list_users("iyer")] == ["dr.iyer"]


def test_get_user_for_an_unknown_id_raises_no_such_user(team):
    assert A.get_user("rao", team["mehta"])["username"] == "dr.mehta"
    with pytest.raises(A.NoSuchUser):
        A.get_user("rao", 99)
    assert issubclass(A.NoSuchUser, A.AccountError)


def test_disable_bumps_the_session_version_audits_and_ends_sign_in(team):
    cookie = sessions.sign("rao", team["mehta"], 0)
    assert authn.load_identity(cookie) is not None
    user = A.set_active(_me(team), team["mehta"], False)
    row = _row("rao", team["mehta"])
    assert user["is_active"] is False and (row["is_active"], row["session_version"]) == (0, 1)
    assert authn.load_identity(cookie) is None
    assert authn.authenticate("dr.mehta", PW, "127.0.0.1") is None
    assert [tuple(a)[:3] for a in _audits("rao", "user_disable")] == [("dr.rao", "doctor", str(team["mehta"]))]


def test_enable_restores_sign_in_but_never_revives_an_old_cookie(team):
    cookie = sessions.sign("rao", team["mehta"], 0)
    A.set_active(_me(team), team["mehta"], False)
    user = A.set_active(_me(team), team["mehta"], True)
    assert user["is_active"] is True and _row("rao", team["mehta"])["session_version"] == 1
    assert authn.load_identity(cookie) is None                  # issued before the disable: stays dead
    assert authn.authenticate("dr.mehta", PW, "127.0.0.1") is not None
    assert [tuple(a)[:3] for a in _audits("rao", "user_enable")] == [("dr.rao", "doctor", str(team["mehta"]))]


def test_you_cannot_disable_yourself(team):
    with pytest.raises(A.AccountError, match="your own account"):
        A.set_active(_me(team), team["rao"], False)
    assert _row("rao", team["rao"])["is_active"] == 1 and _audits("rao", "user_disable") == []


def test_the_last_active_user_cannot_be_disabled(team):
    with closing(_conn("rao")) as c:                            # Rao was disabled by a colleague a moment ago
        c.execute("UPDATE users SET is_active = 0 WHERE id IN (?, ?)", (team["rao"], team["shah"]))
        c.commit()
    with pytest.raises(A.AccountError, match="last active user"):
        A.set_active(_me(team), team["mehta"], False)
    assert _row("rao", team["mehta"])["is_active"] == 1 and _audits("rao", "user_disable") == []


def test_disabling_twice_changes_and_audits_once(team):
    A.set_active(_me(team), team["mehta"], False)
    A.set_active(_me(team), team["mehta"], False)
    A.set_active(_me(team), team["shah"], True)                 # already active: nothing to do
    assert _row("rao", team["mehta"])["session_version"] == 1
    assert len(_audits("rao", "user_disable")) == 1 and _audits("rao", "user_enable") == []


def test_ids_from_another_clinic_raise_no_such_user_and_change_nothing(team):
    iyer = _me(team, "iyer", "iyer")
    assert team["iyer"] == team["rao"] == 1                     # ids repeat across clinic files
    calls = (lambda: A.set_active(iyer, team["shah"], False), lambda: A.set_active(iyer, team["shah"], True),
             lambda: A.reset_user_password(iyer, team["shah"]))
    for call in calls:
        with pytest.raises(A.NoSuchUser):
            call()
    row = _row("rao", team["shah"])
    assert (row["is_active"], row["session_version"]) == (1, 0)
    assert _audits("iyer", "user_disable") == [] and _audits("iyer", "password_reset") == []


def test_reset_user_password_bumps_version_forces_a_change_and_audits_the_actor(team):
    with closing(_conn("rao")) as c:
        c.execute("UPDATE users SET must_change_password = 0 WHERE id = ?", (team["mehta"],))
        c.commit()
    temp = A.reset_user_password(_me(team), team["mehta"])
    row = _row("rao", team["mehta"])
    assert len(temp) == 16 and P.verify_password(temp, row["password_hash"])
    assert not P.verify_password(PW, row["password_hash"])
    assert (row["session_version"], row["must_change_password"]) == (1, 1)
    audit = _audits("rao", "password_reset")
    assert [tuple(a)[:3] for a in audit] == [("dr.rao", "doctor", str(team["mehta"]))]
    assert temp not in (audit[0]["detail"] or "")


def test_reset_user_password_refuses_yourself_and_unknown_ids(team):
    with pytest.raises(A.AccountError, match="your own password"):
        A.reset_user_password(_me(team), team["rao"])
    with pytest.raises(A.NoSuchUser):
        A.reset_user_password(_me(team), 99)
    assert _row("rao", team["rao"])["session_version"] == 0 and _audits("rao", "password_reset") == []


def test_the_operator_reset_by_username_still_works_and_raises_no_such_user(team):
    temp = A.reset_password("DR.MEHTA", actor="operator")
    assert P.verify_password(temp, _row("rao", team["mehta"])["password_hash"])
    assert _audits("rao", "password_reset")[0]["actor"] == "operator"
    with pytest.raises(A.NoSuchUser):
        A.reset_password("nobody")


def test_policy_knows_the_team_actions(team):
    for action in ("user.view", "user.create", "user.disable", "user.reset_password"):
        assert policy.can(_me(team), action, {"user_id": team["mehta"]}) is True, action
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_accounts_team.py -q`
Expected: 12 failed (`AttributeError: module 'doctor_dictation.accounts' has no attribute 'list_users'` / `'set_active'` / `'NoSuchUser'` / `'reset_user_password'`; the policy test fails on `user.view`).

- [ ] **Step 3: Add `NoSuchUser`**

In `doctor_dictation/accounts.py`, directly after the `AccountError` class (lines 22-23), insert:

```python


class NoSuchUser(AccountError):
    """The user id (or username) is not in that clinic. The Team routes answer 404."""
```

- [ ] **Step 4: Replace `reset_password` with a shared helper and two entry points**

Replace the whole `reset_password` function (lines 83-97, from `def reset_password(username, actor=None) -> str:` to its `return secret`) with:

```python
def _reset(clinic_slug, user_id, actor=None, role=None) -> str:
    secret = temp_password()
    with clinic_conn(clinic_slug) as conn:
        cur = conn.execute("UPDATE users SET password_hash = ?, must_change_password = 1, session_version = session_version + 1"
                           " WHERE id = ?", (hash_password(secret), user_id))
        conn.commit()
        if cur.rowcount != 1:                              # unknown id, or the directory points at a missing row
            raise NoSuchUser("no such user")
        dbmod.log_audit(conn, actor=actor, role=role, action="password_reset", entity="user", entity_id=str(user_id))
    return secret


def reset_password(username, actor=None) -> str:
    """Operator reset by username (any clinic): a new temporary password, a forced change at next sign-in,
    and every open session of that user ends."""
    with closing(open_directory()) as d:
        entry = lookup_username(d, username)
    if entry is None:
        raise NoSuchUser("no such user")
    return _reset(entry["clinic_slug"], entry["user_id"], actor)


def reset_user_password(identity, user_id) -> str:
    """Team reset of a colleague in the signed-in user's own clinic (an id from another clinic is not there)."""
    if user_id == identity.user_id:
        raise AccountError("You cannot reset your own password here. Ask a colleague to reset it.")
    return _reset(identity.clinic_slug, user_id, identity.username, identity.role)
```

- [ ] **Step 5: Append the list and active-status operations**

At the end of `doctor_dictation/accounts.py` (after `change_password`), append:

```python


_PUBLIC = "id, username, display_name, role, is_active, last_login_at, must_change_password"


def _public(row) -> dict:
    """The fields the Team screen may show. Never the password hash."""
    return {"id": row["id"], "username": row["username"], "display_name": row["display_name"] or row["username"],
            "role": row["role"], "is_active": bool(row["is_active"]), "last_login_at": row["last_login_at"],
            "must_change_password": bool(row["must_change_password"])}


def list_users(clinic_slug) -> list[dict]:
    with clinic_conn(clinic_slug) as conn:
        rows = conn.execute(f"SELECT {_PUBLIC} FROM users ORDER BY id").fetchall()
    return [_public(r) for r in rows]


def get_user(clinic_slug, user_id) -> dict:
    with clinic_conn(clinic_slug) as conn:
        row = conn.execute(f"SELECT {_PUBLIC} FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise NoSuchUser("no such user")
    return _public(row)


def set_active(identity, user_id, active: bool) -> dict:
    """Disable or enable a colleague in the signed-in user's clinic (never delete: prescriptions keep their author).

    A disable also bumps ``session_version``: open sessions end now and stay ended if the user is enabled again.
    The checks and the write share one ``BEGIN IMMEDIATE`` lock, so two concurrent disables cannot both pass
    the last-active-user rule."""
    active = bool(active)
    if not active and user_id == identity.user_id:
        raise AccountError("You cannot disable your own account")
    with clinic_conn(identity.clinic_slug) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute("SELECT is_active FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                raise NoSuchUser("no such user")
            changed = bool(row["is_active"]) != active
            if changed and not active:
                others = conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 1 AND id != ?", (user_id,)).fetchone()[0]
                if others == 0:
                    raise AccountError("You cannot disable the last active user")
                conn.execute("UPDATE users SET is_active = 0, session_version = session_version + 1 WHERE id = ?", (user_id,))
            elif changed:
                conn.execute("UPDATE users SET is_active = 1 WHERE id = ?", (user_id,))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        if changed:
            dbmod.log_audit(conn, actor=identity.username, role=identity.role,
                            action="user_enable" if active else "user_disable", entity="user", entity_id=str(user_id))
    return get_user(identity.clinic_slug, user_id)
```

(`BEGIN IMMEDIATE` works with Python's default legacy transaction mode: the module issues no implicit `BEGIN` while a transaction is open, and `commit()` / `rollback()` end it. `sqlite3.connect`'s default 5-second timeout makes a second writer wait instead of failing.)

- [ ] **Step 6: Add the two action names to the policy**

In `doctor_dictation/policy.py`, add `"user.view"` and `"user.reset_password"` to the `ACTIONS` set and keep every other entry (including any M3/M4 added). At `ae5864c` the result is:

```python
ACTIONS = frozenset({"document.view", "document.reprint", "document.edit", "user.view", "user.create", "user.disable",
                     "user.reset_password", "letterhead.manage"})
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_accounts_team.py tests/test_accounts.py tests/test_policy_audit.py tests/test_admin.py -q`
Expected: all pass: 12 new + 14 + 7 + the existing `test_admin.py` count (it exercises `reset_password` through the CLI). No existing test is edited.

- [ ] **Step 8: Leave uncommitted.**

---

### Task 2: Team routes (`api/users.py`) and router wiring

**Files:**
- Create: `doctor_dictation/api/users.py`, `tests/test_users_routes.py`
- Modify: `doctor_dictation/api/app.py` (one import, one router-tuple entry), `tests/test_api_app.py` (`EXPECTED_ROUTES`: five tuples)

**Interfaces:**
- Consumes: Task 1's `accounts.list_users`, `get_user`, `set_active`, `reset_user_password`, `NoSuchUser`, `AccountError`; `accounts.create_user(clinic_slug, username, display_name="", doctor_name="", qualifications="", reg_no="", role="doctor", password=None, actor=None) -> (user_id, password)` (`accounts.py:44-80`); `policy.can(user, action, resource=None)`; `request.state.identity` (a `sessions.Identity`, set by `SessionMiddleware` at `api/session.py:60` for every non-public path, inside `use_scope(...)` at `:61`); `scope.multi_clinic_enabled()`.
- Produces (HTTP, multi-clinic mode; every route answers `404 {"error": "sign-in is not enabled"}` in single mode, like `api/auth.py`):

| Route | `can()` action | Success | Errors |
|---|---|---|---|
| `GET /api/v1/users` | `user.view` | 200 `{"users": [<public user>...], "me": <caller id>}` | 403, 503 |
| `POST /api/v1/users` body `{username, display_name?, doctor_name?, qualifications?, reg_no?}` | `user.create` | 201 `{"user": <public user>, "temporary_password": "<16 chars>"}`, `Cache-Control: no-store` | 400 `{"error": ...}` (bad or taken username, directory failure), 403, 422 (oversized), 503 |
| `POST /api/v1/users/{user_id}/disable` | `user.disable` | 200 `{"user": <public user>}` | 400 (yourself, last active), 403, 404 `{"error": "no such user"}`, 422 (bad id), 503 |
| `POST /api/v1/users/{user_id}/enable` | `user.disable` | 200 `{"user": <public user>}` | 403, 404, 422, 503 |
| `POST /api/v1/users/{user_id}/reset-password` | `user.reset_password` | 200 `{"ok": true, "temporary_password": "<16 chars>"}`, `Cache-Control: no-store` | 400 (yourself), 403 `{"error": "You are not allowed to do that"}`, 404, 422, 503 |

  `<public user>` is the Task 1 dict. The CSRF header and 401 for no session come from the existing middleware (`api/session.py:41-53`); `tests/test_closed_by_default.py` walks `app.openapi()` and so covers the new routes automatically.

- [ ] **Step 1: Write the failing tests**

`tests/test_users_routes.py`:

```python
"""Team routes through the real app: list, add, disable, enable, reset; clinic isolation, sessions, audit. Offline."""
import json
from contextlib import ExitStack, closing, contextmanager

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import accounts as A
from doctor_dictation import clinics
from doctor_dictation import db as dbmod
from doctor_dictation.api import users as users_api
from doctor_dictation.api.app import create_app
from doctor_dictation.directory import DirectoryError
from doctor_dictation.scope import clinic_dir

H = {"X-DD-Client": "1"}
PW = "a-long-password-1"


def _conn(slug):
    return dbmod.get_conn(clinic_dir(slug) / "app.db")


def _make(slug, username, display):
    uid, _ = A.create_user(slug, username, display_name=display, password=PW)
    with closing(_conn(slug)) as c:                                 # skip the forced first-login change
        c.execute("UPDATE users SET must_change_password = 0 WHERE id = ?", (uid,))
        c.commit()
    return uid


@pytest.fixture()
def world(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    clinics.provision_clinic("iyer", "Iyer Clinic")
    return {"rao": _make("rao", "dr.rao", "Dr. Rao"), "mehta": _make("rao", "dr.mehta", "Dr. Mehta"),
            "shah": _make("rao", "dr.shah", "Dr. Shah"), "iyer": _make("iyer", "dr.iyer", "Dr. Iyer")}


def _login(c, username, pw=PW):
    return c.post("/api/v1/auth/login", json={"username": username, "password": pw}, headers=H)


@contextmanager
def _signed_in(*usernames):
    """One TestClient per username (each its own cookie jar) on one app, each signed in."""
    app = create_app()
    with ExitStack() as stack:
        clients = []
        for name in usernames:
            c = stack.enter_context(TestClient(app, follow_redirects=False))
            r = _login(c, name)
            assert r.status_code == 200, r.text
            clients.append(c)
        yield clients


def _names(c):
    return [u["username"] for u in c.get("/api/v1/users").json()["users"]]


def test_users_routes_are_404_in_single_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "single.db"))
    c = TestClient(create_app())                                    # no `with`: no lifespan, no database touched
    assert c.get("/api/v1/users").status_code == 404
    for path in ("/api/v1/users", "/api/v1/users/1/disable", "/api/v1/users/1/enable", "/api/v1/users/1/reset-password"):
        assert c.post(path, json={"username": "dr.x"}).status_code == 404, path


def test_list_shows_only_this_clinic_with_public_fields_and_who_i_am(world):
    with _signed_in("dr.mehta", "dr.iyer") as (mehta, iyer):
        ra, rb = mehta.get("/api/v1/users"), iyer.get("/api/v1/users")
    a, b = ra.json(), rb.json()
    assert a["me"] == world["mehta"] and [u["username"] for u in a["users"]] == ["dr.rao", "dr.mehta", "dr.shah"]
    assert b["me"] == world["iyer"] and [u["username"] for u in b["users"]] == ["dr.iyer"]
    row = a["users"][1]
    assert set(row) == {"id", "username", "display_name", "role", "is_active", "last_login_at", "must_change_password"}
    assert (row["display_name"], row["is_active"], row["must_change_password"]) == ("Dr. Mehta", True, False)
    assert row["last_login_at"] is not None and a["users"][0]["last_login_at"] is None
    assert "password_hash" not in ra.text and "scrypt$" not in ra.text


def test_add_user_shows_a_temporary_password_once_and_it_signs_in_with_a_forced_change(world):
    with _signed_in("dr.rao") as (rao,):
        r = rao.post("/api/v1/users", json={"username": "dr.new", "display_name": " Dr. New ", "doctor_name": "Dr N. New",
                                            "qualifications": "MBBS", "reg_no": "TS-9"}, headers=H)
        listing = rao.get("/api/v1/users")
    assert r.status_code == 201 and r.headers["cache-control"] == "no-store"
    body = r.json()
    temp = body["temporary_password"]
    assert len(temp) == 16 and (body["user"]["username"], body["user"]["display_name"]) == ("dr.new", "Dr. New")
    assert body["user"]["must_change_password"] is True and body["user"]["is_active"] is True
    assert temp not in listing.text
    with closing(_conn("rao")) as c:
        row = c.execute("SELECT doctor_name, qualifications, reg_no, role FROM users WHERE username = 'dr.new'").fetchone()
    assert tuple(row) == ("Dr N. New", "MBBS", "TS-9", "doctor")
    with TestClient(create_app(), follow_redirects=False) as fresh:
        r = _login(fresh, "dr.new", temp)
    assert (r.status_code, r.json()["must_change_password"]) == (200, True)


def test_add_user_rejects_bad_taken_and_oversized_usernames(world):
    with _signed_in("dr.rao") as (rao,):
        bad = rao.post("/api/v1/users", json={"username": "a b"}, headers=H)
        taken = rao.post("/api/v1/users", json={"username": "DR.IYER"}, headers=H)     # Iyer Clinic's user, other case
        huge = rao.post("/api/v1/users", json={"username": "x" * 65}, headers=H)
        names = _names(rao)
    assert bad.status_code == 400 and "3 to 40" in bad.json()["error"]
    assert taken.status_code == 400 and "taken" in taken.json()["error"]
    assert huge.status_code == 422
    assert names == ["dr.rao", "dr.mehta", "dr.shah"]


def test_add_user_leaves_no_clinic_row_when_the_directory_write_fails(world, monkeypatch):
    def boom(*_a, **_k):
        raise DirectoryError("directory is down")

    monkeypatch.setattr(A, "index_username", boom)
    with _signed_in("dr.rao") as (rao,):
        r = rao.post("/api/v1/users", json={"username": "dr.new"}, headers=H)
        names = _names(rao)
    assert r.status_code == 400 and "temporary_password" not in r.json()
    assert "dr.new" not in names


def test_disable_ends_the_session_at_once_and_enable_does_not_revive_it(world):
    with _signed_in("dr.rao", "dr.mehta") as (rao, mehta):
        assert mehta.get("/api/v1/auth/me").status_code == 200
        r = rao.post(f"/api/v1/users/{world['mehta']}/disable", headers=H)
        assert r.status_code == 200 and r.json()["user"]["is_active"] is False
        assert mehta.get("/api/v1/auth/me").status_code == 401
        assert _login(mehta, "dr.mehta").status_code == 401
        r = rao.post(f"/api/v1/users/{world['mehta']}/enable", headers=H)
        assert r.status_code == 200 and r.json()["user"]["is_active"] is True
        assert mehta.get("/api/v1/auth/me").status_code == 401          # the old cookie stays dead
        assert _login(mehta, "dr.mehta").status_code == 200
        assert mehta.get("/api/v1/auth/me").status_code == 200


def test_reset_password_ends_the_session_and_the_new_temp_password_forces_a_change(world):
    with _signed_in("dr.rao", "dr.mehta") as (rao, mehta):
        r = rao.post(f"/api/v1/users/{world['mehta']}/reset-password", headers=H)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        temp = r.json()["temporary_password"]
        assert len(temp) == 16
        assert mehta.get("/api/v1/auth/me").status_code == 401
        assert _login(mehta, "dr.mehta").status_code == 401             # the old password is gone
        r = _login(mehta, "dr.mehta", temp)
        assert (r.status_code, r.json()["must_change_password"]) == (200, True)


def test_you_cannot_disable_or_reset_yourself(world):
    with _signed_in("dr.rao") as (rao,):
        d = rao.post(f"/api/v1/users/{world['rao']}/disable", headers=H)
        p = rao.post(f"/api/v1/users/{world['rao']}/reset-password", headers=H)
        still = rao.get("/api/v1/auth/me").status_code
    assert d.status_code == 400 and "your own account" in d.json()["error"]
    assert p.status_code == 400 and "your own password" in p.json()["error"]
    assert still == 200


def test_ids_from_another_clinic_are_404_and_untouched(world):
    shah = world["shah"]                                            # id 3 exists only in Rao Clinic
    with _signed_in("dr.iyer") as (iyer,):
        answers = [iyer.post(f"/api/v1/users/{shah}/{verb}", headers=H) for verb in ("disable", "enable", "reset-password")]
        own_id = iyer.post(f"/api/v1/users/{world['rao']}/disable", headers=H)   # id 1 here is Iyer, not Rao
    assert [(r.status_code, r.json()) for r in answers] == [(404, {"error": "no such user"})] * 3
    assert world["rao"] == world["iyer"] and own_id.status_code == 400 and "your own account" in own_id.json()["error"]
    with closing(_conn("rao")) as c:
        rows = c.execute("SELECT is_active, session_version FROM users WHERE id IN (?, ?)", (shah, world["rao"])).fetchall()
        audits = c.execute("SELECT COUNT(*) FROM audit_log WHERE action IN ('user_disable', 'user_enable', 'password_reset')"
                           ).fetchone()[0]
    assert [tuple(r) for r in rows] == [(1, 0), (1, 0)] and audits == 0


def test_bad_ids_are_422(world):
    with _signed_in("dr.rao") as (rao,):
        codes = {p: rao.post(f"/api/v1/users/{p}/disable", headers=H).status_code for p in ("0", "-1", "abc", str(2**64))}
    assert set(codes.values()) == {422}, codes


def test_every_team_action_is_audited_with_the_signed_in_actor_and_no_password(world):
    with _signed_in("dr.rao") as (rao,):
        created = rao.post("/api/v1/users", json={"username": "dr.new"}, headers=H).json()
        rao.post(f"/api/v1/users/{world['mehta']}/disable", headers=H)
        rao.post(f"/api/v1/users/{world['mehta']}/enable", headers=H)
        reset = rao.post(f"/api/v1/users/{world['mehta']}/reset-password", headers=H).json()
    with closing(_conn("rao")) as c:
        rows = c.execute("SELECT actor, role, action, entity_id, detail FROM audit_log WHERE actor IS NOT NULL AND action IN"
                         " ('user_create', 'user_disable', 'user_enable', 'password_reset') ORDER BY id").fetchall()
    mehta, new = str(world["mehta"]), str(created["user"]["id"])
    assert [(r["actor"], r["role"], r["action"], r["entity_id"]) for r in rows] == [
        ("dr.rao", "doctor", "user_create", new), ("dr.rao", "doctor", "user_disable", mehta),
        ("dr.rao", "doctor", "user_enable", mehta), ("dr.rao", "doctor", "password_reset", mehta)]
    secrets = (created["temporary_password"], reset["temporary_password"])
    assert not any(s in (r["detail"] or "") for r in rows for s in secrets)
    assert json.loads(rows[0]["detail"]) == {"username": "dr.new"}


def test_every_team_route_asks_policy_can_and_a_denial_is_403(world, monkeypatch):
    asked = []
    monkeypatch.setattr(users_api.policy, "can", lambda user, action, resource=None: asked.append(action) or False)
    with _signed_in("dr.rao") as (rao,):
        answers = [rao.get("/api/v1/users"), rao.post("/api/v1/users", json={"username": "dr.new"}, headers=H),
                   rao.post(f"/api/v1/users/{world['mehta']}/disable", headers=H),
                   rao.post(f"/api/v1/users/{world['mehta']}/enable", headers=H),
                   rao.post(f"/api/v1/users/{world['mehta']}/reset-password", headers=H)]
    assert [(r.status_code, r.json()) for r in answers] == [(403, {"error": "You are not allowed to do that"})] * 5
    assert asked == ["user.view", "user.create", "user.disable", "user.disable", "user.reset_password"]
    with closing(_conn("rao")) as c:
        assert c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3
        row = c.execute("SELECT is_active, session_version, password_hash FROM users WHERE id = ?", (world["mehta"],)).fetchone()
    assert (row["is_active"], row["session_version"]) == (1, 0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_users_routes.py -q`
Expected: collection error (`ImportError: cannot import name 'users' from 'doctor_dictation.api'`).

- [ ] **Step 3: Write the router**

`doctor_dictation/api/users.py`:

```python
"""Team (Users) routes, spec 8.2: list, add, disable, enable and reset the password of users in the signed-in
user's own clinic. Every action asks ``policy.can`` first and is audited by ``accounts``. An id from another
clinic is simply not in this clinic's database, so it answers 404. Everything is 404 when MULTI_CLINIC is off."""
import asyncio
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from doctor_dictation import accounts, policy
from doctor_dictation.scope import multi_clinic_enabled

router = APIRouter()
OFF = {"error": "sign-in is not enabled"}
DENIED = {"error": "You are not allowed to do that"}
NO_STORE = {"Cache-Control": "no-store"}           # responses carrying a temporary password are never cached
UserId = Annotated[int, Path(ge=1, le=2**63 - 1)]  # SQLite's INTEGER range; anything else is a 422


class NewUserBody(BaseModel):
    username: str = Field("", max_length=64)
    display_name: str = Field("", max_length=120)
    doctor_name: str = Field("", max_length=120)
    qualifications: str = Field("", max_length=120)
    reg_no: str = Field("", max_length=120)


def _gate(request: Request, action: str, resource=None):
    """``(identity, None)`` when the call may go ahead, else ``(None, error response)``."""
    if not multi_clinic_enabled():
        return None, JSONResponse(status_code=404, content=OFF)
    identity = request.state.identity                  # set by SessionMiddleware for every non-public path
    if not policy.can(identity, action, resource):
        return None, JSONResponse(status_code=403, content=DENIED)
    return identity, None


async def _call(fn, *args):
    """Run an accounts call off the event loop (the clinic scope follows ``to_thread``).
    Returns ``(result, None)`` or ``(None, error response)``."""
    try:
        return await asyncio.to_thread(fn, *args), None
    except accounts.NoSuchUser:                        # before AccountError: it is a subclass
        return None, JSONResponse(status_code=404, content={"error": "no such user"})
    except accounts.AccountError as exc:
        return None, JSONResponse(status_code=400, content={"error": str(exc)})
    except sqlite3.Error:
        return None, JSONResponse(status_code=503, content={"error": "try again"})


@router.get("/api/v1/users")
async def list_users(request: Request):
    identity, refused = _gate(request, "user.view")
    if refused is not None:
        return refused
    users, failed = await _call(accounts.list_users, identity.clinic_slug)
    if failed is not None:
        return failed
    return {"users": users, "me": identity.user_id}


@router.post("/api/v1/users", status_code=201)
async def create_user(request: Request, body: NewUserBody):
    identity, refused = _gate(request, "user.create")
    if refused is not None:
        return refused
    fields = {k: v.strip() for k, v in body.model_dump().items() if k != "username"}

    def _create():
        uid, secret = accounts.create_user(identity.clinic_slug, body.username, **fields)   # audit actor from the scope
        return accounts.get_user(identity.clinic_slug, uid), secret

    created, failed = await _call(_create)
    if failed is not None:
        return failed
    user, secret = created
    return JSONResponse(status_code=201, content={"user": user, "temporary_password": secret}, headers=NO_STORE)


async def _set_active(request: Request, user_id: int, active: bool):
    identity, refused = _gate(request, "user.disable", {"user_id": user_id})   # one permission covers both directions
    if refused is not None:
        return refused
    user, failed = await _call(accounts.set_active, identity, user_id, active)
    if failed is not None:
        return failed
    return {"user": user}


@router.post("/api/v1/users/{user_id}/disable")
async def disable_user(request: Request, user_id: UserId):
    return await _set_active(request, user_id, False)


@router.post("/api/v1/users/{user_id}/enable")
async def enable_user(request: Request, user_id: UserId):
    return await _set_active(request, user_id, True)


@router.post("/api/v1/users/{user_id}/reset-password")
async def reset_password(request: Request, user_id: UserId):
    identity, refused = _gate(request, "user.reset_password", {"user_id": user_id})
    if refused is not None:
        return refused
    secret, failed = await _call(accounts.reset_user_password, identity, user_id)
    if failed is not None:
        return failed
    return JSONResponse({"ok": True, "temporary_password": secret}, headers=NO_STORE)
```

Why the audit is right without passing an actor to `create_user`: its `log_audit(conn, actor=actor, ...)` (`accounts.py:78`) gets `actor=None`, so `log_audit` fills actor and role from the scope (`db/__init__.py:271`). The middleware set that scope (`api/session.py:61`) and `asyncio.to_thread` copies it into the worker thread. `create_user`'s own `role` parameter is the *new* user's role, so the caller's role cannot be passed explicitly there.

- [ ] **Step 4: Wire the router into the app**

In `doctor_dictation/api/app.py`, after the line `from doctor_dictation.api import templates as templates_api` (line 20), add:

```python
from doctor_dictation.api import users as users_api
```

and add `users_api` as the last entry of the router tuple (line 78 at `ae5864c`; keep any entries M3/M4 added):

```python
    for module in (auth, health, stt, format_api, profile, persistence, users_api):
```

- [ ] **Step 5: Extend the route table**

In `tests/test_api_app.py` `EXPECTED_ROUTES`, add this line before the closing `}` (keep any tuples M3/M4 added):

```python
    ("GET", "/api/v1/users"), ("POST", "/api/v1/users"), ("POST", "/api/v1/users/{user_id}/disable"),
    ("POST", "/api/v1/users/{user_id}/enable"), ("POST", "/api/v1/users/{user_id}/reset-password"),
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_users_routes.py tests/test_api_app.py tests/test_closed_by_default.py tests/test_auth_routes.py tests/test_file_sizes.py -q`
Expected: all pass: 12 new + 4 + 1 + the existing `test_auth_routes.py` count + 2. `test_closed_by_default` now also walks the five new routes and must still see 401 for each without a cookie.

- [ ] **Step 7: Leave uncommitted.**

---

### Task 3: Team panel in the browser (`team.js`, `team.css`, one button)

**Files:**
- Create: `frontend/team.js`, `frontend/team.css`, `tests/test_frontend_team.py`
- Modify: `frontend/index.html` (one `<link>`, one `<button>`, one `<script>`)

**Interfaces:**
- Consumes: Task 2's five routes; `auth.js`'s `window.fetch` wrapper (`frontend/auth.js:14-31`: adds `X-DD-Client: 1` on unsafe methods, sends a 401 to `/login`); `dialog.panel`, `.field`, `button.primary` and the colour variables from `frontend/styles.css:5-13, 165-175`.
- Produces: `#teamOpenBtn` in the top bar, hidden until `GET /api/v1/users` answers 200 (so it never shows in single mode, where the route is 404). It opens `#teamPanel`, a `<dialog>` that `team.js` builds itself, containing:
  - the users table, with rows built by `textContent` only;
  - per-row Disable/Enable and Reset password buttons, none on your own row, each risky action confirmed first;
  - the Add user form;
  - a one-time password box with a Copy button and a warning. The password is cleared on "Done" and whenever the dialog closes (Close button or Escape).

- [ ] **Step 1: Write the failing tests**

`tests/test_frontend_team.py`:

```python
"""Team panel wiring (team.js, team.css, the one button in index.html). Static checks; no browser."""
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def test_index_has_one_hidden_team_button_right_after_profile():
    html = _read("index.html")
    assert html.count('id="teamOpenBtn"') == 1
    tag = re.search(r'<button id="teamOpenBtn"[^>]*>', html).group(0)
    assert " hidden" in tag and 'type="button"' in tag
    assert html.index('id="profileOpenBtn"') < html.index('id="teamOpenBtn"') < html.index('id="signOutBtn"')


def test_team_assets_are_linked_once_and_team_js_loads_after_auth_js():
    html = _read("index.html")
    assert html.count("team.js") == 1 and html.count("team.css") == 1
    assert '<link rel="stylesheet" href="team.css' in html
    assert html.index("auth.js") < html.index("team.js")


def test_team_js_uses_every_users_route_and_posts_the_changes():
    js = _read("team.js")
    assert '"/api/v1/users"' in js
    for verb in ("/disable", "/enable", "/reset-password"):
        assert verb in js, verb
    assert js.count('method: "POST"') >= 3


def test_team_list_shows_name_username_status_and_last_sign_in():
    js = _read("team.js")
    for word in ("display_name", "username", "is_active", "last_login_at", "Last sign-in", "Never", "(you)"):
        assert word in js, word


def test_team_js_never_turns_user_data_into_html():
    js = _read("team.js")
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write", js)
    assert "textContent" in js


def test_temporary_password_is_shown_once_with_a_copy_button_and_a_warning():
    js = _read("team.js")
    assert "temporary_password" in js and "navigator.clipboard.writeText" in js
    assert "it will not be shown again" in js
    assert re.search(r'addEventListener\("close", clearSecret\)', js)      # closing the panel forgets it
    clear = js.split("function clearSecret()")[1].split("}")[0]
    assert 'textContent = ""' in clear


def test_team_js_confirms_risky_actions_and_offers_none_on_your_own_row():
    js = _read("team.js")
    assert js.count("window.confirm(") >= 2
    assert "u.id === t.me" in js and re.search(r"if \(!you\)", js)


def test_team_css_rules_are_scoped_to_the_team_panel():
    css = re.sub(r"/\*.*?\*/", "", _read("team.css"), flags=re.S)
    selectors = [s.strip() for block in re.findall(r"([^{}]+)\{", css) for s in block.split(",")]
    assert selectors and all(s.startswith((".team-panel", "dialog.team-panel")) for s in selectors), selectors
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_frontend_team.py -q`
Expected: 8 failed (`FileNotFoundError: .../frontend/team.js`, `team.css`, and the index assertions).

- [ ] **Step 3: Write `frontend/team.js`**

```javascript
"use strict";
// Team panel (spec 8.2): the clinic's users, add one, disable/enable, reset a password.
// Builds its own dialog, so index.html carries only the #teamOpenBtn button. Loaded after auth.js,
// whose fetch wrapper adds the X-DD-Client header and sends a 401 to the login page.
(function () {
  const API = "/api/v1/users";
  const t = { me: null, dialog: null };
  const el = (id) => document.getElementById(id);
  const FIELDS = [
    ["teamNewUsername", "Username (3 to 40 letters, digits, '.', '_' or '-')", "username"],
    ["teamNewDisplay", "Display name", "display_name"],
    ["teamNewDoctor", "Doctor name, as printed (optional)", "doctor_name"],
    ["teamNewQual", "Qualifications (optional)", "qualifications"],
    ["teamNewReg", "Registration no. (optional)", "reg_no"],
  ];

  function make(tag, attrs, text) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (k === "hidden") node.hidden = Boolean(v); else node.setAttribute(k, v);
    });
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function build() {
    const d = make("dialog", { id: "teamPanel", class: "panel team-panel no-print", "aria-labelledby": "teamTitle" });
    const head = make("div", { class: "team-head" });
    head.append(make("h2", { id: "teamTitle" }, "Team"), make("button", { id: "teamCloseBtn", type: "button" }, "Close"));
    const secretActions = make("div", { class: "team-secret-actions" });
    secretActions.append(make("button", { id: "teamCopyBtn", type: "button" }, "Copy"),
      make("button", { id: "teamSecretDoneBtn", type: "button" }, "Done, hide it"),
      make("span", { id: "teamCopyStatus", class: "team-copy-status" }));
    const secret = make("div", { id: "teamSecret", class: "team-secret", role: "status", hidden: true });
    secret.append(make("p", { id: "teamSecretFor", class: "team-secret-for" }),
      make("code", { id: "teamSecretValue", class: "team-secret-value" }),
      make("p", { class: "team-secret-warn" }, "Copy it now: it will not be shown again. Give it to them in person; " +
        "they must choose their own password when they first sign in."),
      secretActions);
    const hrow = make("tr");
    ["Name", "Username", "Status", "Last sign-in", "Actions"].forEach((h) => hrow.append(make("th", { scope: "col" }, h)));
    const thead = make("thead");
    thead.append(hrow);
    const table = make("table", { class: "team-table" });
    table.append(thead, make("tbody", { id: "teamRows" }));
    const tableBox = make("div", { class: "team-table-box" });
    tableBox.append(table);
    const form = make("form", { id: "teamAddForm", class: "team-add" });
    form.append(make("h3", {}, "Add a user"));
    FIELDS.forEach(([id, label, name]) => {
      const field = make("label", { class: "field" }, label);
      const input = make("input", { id, name, type: "text", autocomplete: "off", maxlength: name === "username" ? "40" : "120" });
      if (name === "username") input.required = true;
      field.append(input);
      form.append(field);
    });
    form.append(make("button", { id: "teamAddBtn", type: "submit", class: "primary" }, "Add user"));
    const box = make("div", { class: "team-body" });
    box.append(make("div", { id: "teamError", class: "team-error", role: "alert", hidden: true }), secret, tableBox, form);
    d.append(head, box);
    return d;
  }

  function showErr(m) { const e = el("teamError"); e.textContent = m || ""; e.hidden = !m; }
  function when(iso) {
    if (!iso) return "Never";
    const d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toLocaleString();
  }
  function showSecret(username, password) {
    el("teamSecretFor").textContent = "Temporary password for " + username + ":";
    el("teamSecretValue").textContent = password;
    el("teamCopyStatus").textContent = "";
    el("teamSecret").hidden = false;
    el("teamCopyBtn").focus();
  }
  function clearSecret() {
    el("teamSecretValue").textContent = "";
    el("teamSecret").hidden = true;
  }
  async function copySecret() {
    const value = el("teamSecretValue").textContent;
    try {
      await navigator.clipboard.writeText(value);
      el("teamCopyStatus").textContent = "Copied.";
    } catch (e) {                                 // no clipboard access (plain http, old browser): select it instead
      const range = document.createRange();
      range.selectNodeContents(el("teamSecretValue"));
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      el("teamCopyStatus").textContent = "Copy is blocked here. The password is selected: press Ctrl+C (Cmd+C on a Mac).";
    }
  }

  function busy(on) {
    t.dialog.setAttribute("aria-busy", on ? "true" : "false");
    t.dialog.querySelectorAll(".team-row-actions button, #teamAddBtn").forEach((b) => { b.disabled = on; });
  }
  async function send(url, opts) {
    busy(true);
    showErr("");
    try {
      const r = await fetch(url, opts);
      let b = {};
      try { b = await r.json(); } catch (e) { /* not JSON */ }
      if (r.ok) return b;
      showErr(r.status === 503 ? "The server is busy. Try again in a moment."
        : (b && b.error) || "Something went wrong (code " + r.status + "). Try again.");
    } catch (e) {
      showErr("Could not reach the server. Check your connection and try again.");
    } finally {
      busy(false);
    }
    return null;
  }

  function render(users) {
    const rows = el("teamRows");
    rows.replaceChildren();
    users.forEach((u) => {
      const you = u.id === t.me;
      const tr = make("tr", { class: u.is_active ? "team-on" : "team-off" });
      tr.append(make("td", {}, u.display_name + (you ? " (you)" : "")), make("td", {}, u.username),
        make("td", {}, u.is_active ? "Active" : "Disabled"), make("td", {}, when(u.last_login_at)));
      const cell = make("td", { class: "team-row-actions" });
      if (!you) {
        const toggle = make("button", { type: "button" }, u.is_active ? "Disable" : "Enable");
        toggle.addEventListener("click", () => setActive(u, !u.is_active));
        const reset = make("button", { type: "button" }, "Reset password");
        reset.addEventListener("click", () => resetPassword(u));
        cell.append(toggle, reset);
      }
      tr.append(cell);
      rows.append(tr);
    });
  }
  async function refresh() {
    const b = await send(API);
    if (b) { t.me = b.me; render(b.users); }
  }

  async function setActive(u, active) {
    if (!active && !window.confirm("Disable " + u.display_name + "? They are signed out at once and cannot sign in " +
      "until someone enables them again. Their prescriptions are kept.")) return;
    const b = await send(API + "/" + u.id + (active ? "/enable" : "/disable"), { method: "POST" });
    if (b) await refresh();
  }
  async function resetPassword(u) {
    if (!window.confirm("Reset the password for " + u.display_name + "? They are signed out at once and must sign in " +
      "with the new temporary password.")) return;
    const b = await send(API + "/" + u.id + "/reset-password", { method: "POST" });
    if (b) { showSecret(u.username, b.temporary_password); await refresh(); }
  }
  async function addUser(ev) {
    ev.preventDefault();
    const payload = {};
    FIELDS.forEach(([id, , name]) => { payload[name] = el(id).value.trim(); });
    const b = await send(API, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!b) return;
    el("teamAddForm").reset();
    showSecret(b.user.username, b.temporary_password);
    await refresh();
  }

  function openPanel() {
    clearSecret();
    showErr("");
    t.dialog.showModal();
    refresh();
  }

  document.addEventListener("DOMContentLoaded", async () => {
    const btn = el("teamOpenBtn");
    if (!btn) return;
    try {
      const r = await fetch(API);
      if (r.status !== 200) return;               // single mode (404) or not signed in: no Team button
    } catch (e) { return; }
    t.dialog = build();
    document.body.append(t.dialog);
    el("teamCloseBtn").addEventListener("click", () => t.dialog.close());
    t.dialog.addEventListener("close", clearSecret);   // Close or Escape: the temporary password is never shown twice
    el("teamCopyBtn").addEventListener("click", copySecret);
    el("teamSecretDoneBtn").addEventListener("click", clearSecret);
    el("teamAddForm").addEventListener("submit", addUser);
    btn.addEventListener("click", openPanel);
    btn.hidden = false;
  });
})();
```

- [ ] **Step 4: Write `frontend/team.css`**

```css
/* Team panel (team.js). Reuses dialog.panel, .field and button.primary from styles.css; every rule is scoped here. */
.team-panel [hidden] { display:none !important; }
dialog.team-panel { width:min(780px, 96vw); max-height:92vh; }
dialog.team-panel[open] { display:flex; flex-direction:column; }
.team-panel .team-head { display:flex; justify-content:space-between; align-items:center; padding:14px 20px; border-bottom:1px solid var(--soft); }
.team-panel .team-head h2 { margin:0; font-size:18px; }
.team-panel .team-body { padding:14px 20px; overflow-y:auto; display:flex; flex-direction:column; gap:14px; }
.team-panel .team-error { background:#fdecea; border:1px solid var(--bad); color:var(--bad); border-radius:8px; padding:10px 14px; font-size:14px; }
.team-panel .team-secret { background:#fff8e1; border:2px solid var(--warn); border-radius:8px; padding:12px 14px; display:flex; flex-direction:column; gap:8px; }
.team-panel .team-secret-for, .team-panel .team-secret-warn { margin:0; font-size:14px; }
.team-panel .team-secret-warn { font-weight:600; }
.team-panel .team-secret-value { align-self:flex-start; font-size:20px; letter-spacing:1px; padding:6px 10px; background:#fff; border:1px solid var(--soft); border-radius:6px; user-select:all; }
.team-panel .team-secret-actions { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.team-panel .team-copy-status { font-size:13px; color:var(--muted); }
.team-panel .team-table-box { overflow-x:auto; }
.team-panel .team-table { width:100%; border-collapse:collapse; font-size:14px; }
.team-panel .team-table th, .team-panel .team-table td { text-align:left; padding:8px 6px; border-bottom:1px solid var(--soft); vertical-align:middle; }
.team-panel .team-table tr.team-off td { color:var(--muted); }
.team-panel .team-row-actions button { margin:0 6px 4px 0; }
.team-panel form.team-add { padding:12px 0 0; border-top:1px solid var(--soft); display:flex; flex-direction:column; gap:8px; }
.team-panel form.team-add h3 { margin:0; font-size:14px; }
.team-panel form.team-add button { align-self:flex-start; }
.team-panel button:focus-visible, .team-panel input:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
```

(`.team-panel form.team-add` (specificity 0,2,1) beats `dialog.panel form` (0,1,2) at `styles.css:168`, so the add form loses that 20px padding.)

- [ ] **Step 5: Edit `frontend/index.html` (three lines, by anchor)**

After `<link rel="stylesheet" href="letterhead.css?v=5" />` (line 8) add:

```html
<link rel="stylesheet" href="team.css?v=1" />
```

After the `profileOpenBtn` button (line 23) add:

```html
    <button id="teamOpenBtn" type="button" hidden title="Your clinic's users: add a colleague, disable an account, reset a password">Team</button>
```

After `<script src="letterhead.js?v=5"></script>` (line 206) add:

```html
<script src="team.js?v=1"></script>
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_frontend_team.py tests/test_frontend_auth.py -q`
Expected: 19 passed (8 new + 11).

- [ ] **Step 7: Full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 32` passed, 1 skipped (`N` noted before Task 1).

- [ ] **Step 8: Manual browser checklist (a person runs it; record pass or fail per line in the task report)**

```bash
export MULTI_CLINIC=1 DEV_INSECURE_SESSION_SECRET=1 DATA_DIR="$(mktemp -d)"
.venv/bin/python -m doctor_dictation.admin create-clinic --slug rao --name "Rao Clinic" --op-prefix RAO --first-user dr.rao --display-name "Dr. Rao"
.venv/bin/python -m doctor_dictation.admin create-clinic --slug iyer --name "Iyer Clinic" --op-prefix IYR --first-user dr.iyer --display-name "Dr. Iyer"
.venv/bin/python -m uvicorn doctor_dictation.main:app --port 8000
```

1. Open `http://localhost:8000`, sign in as `dr.rao` with the printed temporary password, choose a new one. A "Team" button shows next to "Profile". (Restart without `MULTI_CLINIC`: no Team button.)
2. Open Team: one row, "Dr. Rao (you)", Active, last sign-in about now, no Disable or Reset buttons on that row.
3. Add `dr.mehta`, display name "Dr. Mehta". A yellow box shows a 16-character password with the warning; Copy says "Copied." on localhost. Close and reopen the panel: the password is gone.
4. In a private window sign in as `dr.mehta` with that password: the change-password step appears, then the app.
5. Back as Rao: Disable Mehta and accept the confirmation; the row shows Disabled. In Mehta's window reload: the login page appears and Mehta's password is refused.
6. Enable Mehta. Mehta's old window still lands on the login page; signing in again works.
7. Reset Mehta's password: a new temporary password shows once. Mehta's window drops to login; the old password is refused, and the new one works and forces a change.
8. As Rao, add `DR.IYER`: "that username is already taken". Add `a b`: the 3-to-40-characters message.
9. In a third browser profile sign in as `dr.iyer`: Team lists only Dr. Iyer. In that window's console run `fetch("/api/v1/users/2/disable", {method: "POST"}).then(r => r.status)`: `404`.
10. As Rao, add a user whose display name is `<img src=x onerror=alert(1)>`: it shows as literal text and no alert fires.
11. Keyboard only: Tab reaches every control in the panel, Escape closes it, and reopening shows no password.

- [ ] **Step 9: Leave uncommitted.**

---

## Self-review (against the spec)

- **8.2 list (display name, username, active, last login):** `accounts.list_users` (Task 1) and `GET /api/v1/users` (Task 2) feed `team.js` `render` (Task 3). Users of other clinics never appear because the list reads only the caller's clinic file (`test_list_shows_only_this_clinic_with_public_fields_and_who_i_am`).
- **8.2 add user:** the username is unique system-wide (case-insensitive directory index, reused from `create_user`; `test_add_user_rejects_bad_taken_and_oversized_usernames`). Display name and the optional doctor fields are stored. The temporary password is shown once, sent with `no-store`, and `must_change_password` is set (`test_add_user_shows_a_temporary_password_once_and_it_signs_in_with_a_forced_change`).
- **8.2 disable/enable, never delete:** there is no delete route, and `set_active` only flips `is_active`.
- **8.2 reset password:** the new temporary password is shown once and `session_version` is bumped (`test_reset_password_ends_the_session_and_the_new_temp_password_forces_a_change`).
- **8.2 safeguards:**
  - You cannot disable yourself, and the last active user cannot be disabled: Task 1 tests.
  - Directory check first and rollback on failure: reused, proven over HTTP by `test_add_user_leaves_no_clinic_row_when_the_directory_write_fails`.
  - Every action is audited: `test_every_team_action_is_audited_with_the_signed_in_actor_and_no_password`.
  - Username rules: reused `check_username`.
- **8.2 routes:** all five (Task 2), and the route table is pinned (`tests/test_api_app.py`).
- **6.3 `can()`:** every route calls it with a named action before acting (`test_every_team_route_asks_policy_can_and_a_denial_is_403`). Two action names are added (see differences).
- **6.2 a disabled user's or reset user's session ends immediately:** `test_disable_ends_the_session_at_once_and_enable_does_not_revive_it` and the reset test.
- **7.4 audit actions:** `user_create` (actor filled from the scope), `user_disable`, `user_enable`, `password_reset`, each with the signed-in username and role.
- **13.1 Auth bullet (disabled user and password reset end the session):** covered here at route level. M6's isolation sweep picks up the new routes from `app.openapi()` on its own.
- **Isolation (instruction):** two clinics, overlapping ids, 404 and untouched (Review Focus 1).
- **Placeholder scan:** every code block is complete; no "...".
- **Name check:** every name used was checked with grep against the real modules: `accounts.clinic_conn`, `create_user`, `check_username`, `index_username` (patched on `accounts`, as `tests/test_accounts.py:91` does), `passwords.temp_password` / `hash_password`, `dbmod.log_audit`, `dbmod.get_conn`, `clinics.provision_clinic`, `sessions.sign`, `authn.load_identity` / `authenticate`, `scope.clinic_dir` / `multi_clinic_enabled`, `DirectoryError`, `SessionMiddleware`'s `request.state.identity`.
- **Test count:** 12 (Task 1) + 12 (Task 2) + 8 (Task 3) = **32**, with one existing assertion edited (`EXPECTED_ROUTES`).
- **Dry run:** every code block of this plan was applied to a scratch copy of the working tree (M2c in progress) and run with `.venv/bin/python`: the 32 new tests pass, and so does the rest of the suite, except `test_package_install`, which fails only in a copy because the installed package points at the real repo. `node --check frontend/team.js` is clean. Resulting sizes: `accounts.py` 193 lines, `api/users.py` 110, `team.js` 190, `team.css` 23.

## Assumptions

1. M2c may or may not have landed. Nothing here reads `Identity.sid`, and `sessions.sign(clinic, uid, ver)` keeps working with and without its optional `sid` argument.
2. M3/M4 may already have edited `policy.ACTIONS`, the `app.py` router tuple, `EXPECTED_ROUTES` and `index.html`. The edits above go in by anchor and keep whatever is there.
3. No clinic migration (and no directory migration) is needed: the `users` columns from `001` and `005` cover everything. The cross-plan slot `009` stays unused.
4. The Team button decides whether to show by calling `GET /api/v1/users` once on page load. That adds one small request but needs no edit to `auth.js`.
5. New users are created with role `doctor`. Editing an existing user's names or doctor fields is the M3 "My details" part of Profile, not Team.

## Not in this plan

- Deleting users.
- Editing another user's display name or doctor fields.
- Choosing or changing roles (RBAC rules go inside `policy.can` later).
- A voluntary "change my password" screen in the main app.
- Operator CLI `disable-user` / `enable-user` commands.
- Rate limiting of Team actions, and pagination of the list.
- A per-user "sign out everywhere" button.
- Adding `team.js` / `team.css` to `tests/test_closed_by_default.py`'s `PAGES` (static files are gated by the same middleware rule as every non-public path).
- The M6 isolation sweep and seed data.
- Any change to `frontend/app.js`, `auth.js` or `letterhead.js`.
