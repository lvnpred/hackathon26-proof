# M2a: Authentication Primitives (passwords, sessions, throttling, accounts, policy, audit actor)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build everything login needs that is not HTTP: scrypt password hashing, signed session cookies, per-(username, ip) throttling in the directory database, a users migration, account operations (create, reset, change password), `authenticate` / `load_identity`, the `can()` policy function, and audit actor filling from the request scope.

**Architecture:** Small stdlib-only modules, each with one job: `passwords.py`, `sessions.py`, `directory/logins.py`, `accounts.py`, `authn.py`, `policy.py`. Account and login code opens a clinic's database **by path** (`clinic_dir(slug)/"app.db"`), so it works with `MULTI_CLINIC` on or off and needs no request scope; the operator CLI reuses it in M2b. Nothing here touches HTTP; M2b adds the middleware, routes, login page and admin commands on top.

**Tech Stack:** Python 3.11+, `hashlib.scrypt`, `hmac`, `sqlite3`, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-14-multi-clinic-multi-doctor-design.md` sections 6 (identity and login), 6.3 (`can()`), 7.4 (audit) and 8.2 (user safeguards, account part). Builds on `docs/superpowers/plans/2026-10-14-m1-clinic-scope-and-directory.md` (done, uncommitted).

**Plan 2 of 7 (M2a of M2a/M2b, then M3 to M6).** Baseline is 478 passed, 1 skipped. Before the first task run `.venv/bin/python -m pytest tests/ -q` and note the count `N`; **this plan adds 54 tests** (and edits one existing assertion), so the count after it must be `N + 54`.

## Values taken for the spec's open items (section 16), change before M2b if you disagree

Session life 12 hours; lockout 5 failed attempts for a `(username, ip)` pair for 5 minutes; usernames 3 to 40 characters of letters, digits, `.`, `_`, `-`; minimum password length 10 on change (maximum 200); temporary passwords generated, 16 characters. "Clinic details editable by every signed-in user" is an M3 matter.

## Deliberate differences from the spec

- **Order of the two writes in `create_user`.** The spec says directory first, then clinic, rolled back if the clinic write fails. The directory row needs the new `user_id`, which exists only after the clinic insert, so the order is: pre-check the directory, insert the clinic row, index the username, and **delete the clinic row if the index fails**. Same guarantee (no half-created user), same safeguards.
- **`login_failed` is not an audit row.** An unknown username has no clinic to write to, so failures live only in the directory's `login_attempts` counters (as the spec's section 7.4 already says). Successful logins, password changes and resets are audited in the clinic.
- **A document with no recorded author may be edited by anyone in the clinic** (`can()` returns True when `author_id` is None). Every pre-M3 document has no author; fail-closed here would lock them all. M3 revisits this when authorship exists.

## Global Constraints

- "Keep files under 500 lines": `doctor_dictation/db/__init__.py` is 483 lines and receives at most 5 more.
- Never run `git commit` or `git push` (user rule). Leave all changes in the working tree; each task ends with "leave uncommitted".
- Standard library only. Environment variables are read at call time, never at import.
- Password hashing is `hashlib.scrypt` with the parameters encoded in the stored string (`scrypt$16384$8$1$<salt>$<hash>`), a per-user random 16-byte salt, 32-byte output.
- Session cookie value: `base64url(JSON payload).base64url(HMAC-SHA256)`; payload `{clinic, uid, ver, iat, exp}`; life 12 hours; `SESSION_SECRET` must be at least 32 characters, the only exception being `DEV_INSECURE_SESSION_SECRET=1` (local development only).
- Throttling: 5 failed attempts for a `(username, ip)` pair lock it for 5 minutes; the response to the caller is identical for wrong user, wrong password and locked (the caller sees `None`).
- Usernames are unique system-wide, compared case-insensitively. Password hashes and temporary passwords never appear in audit rows, logs or exception text.
- Unknown, locked, disabled and failed-clinic logins all still spend one scrypt computation (`dummy_verify`) so response time does not reveal which usernames exist.
- Tests never touch the network and never touch `doctor_dictation/data/`: every new test that needs a clinic uses the `multi` fixture.

## Review Focus

1. **Hostile stored hash** (huge scrypt `n`, bad base64, wrong scheme, `None`): must return False, never hang or raise. Task 1 `test_verify_rejects_malformed_and_hostile_hashes_without_raising`.
2. **A validly signed cookie with bad field types** (`clinic` of `../x`, `uid` of `True`): must never reach a path. Task 2 `test_verified_payload_with_bad_field_types_is_rejected`.
3. **Username collisions that differ only by case, or across clinics**: Task 4 `test_create_user_rejects_taken_username_across_clinics_and_case`.
4. **Sessions must die** on password reset or change, user disable, clinic disable and a failed clinic: Task 5 `test_load_identity_ends_sessions_on_reset_disable_clinic_disable_and_failed_clinic`.
5. **Username enumeration by timing or by lockout state**: Task 5 `test_unknown_username_pays_for_a_hash_and_counts_a_failure` and `test_fifth_failure_locks_and_a_correct_password_is_then_refused`.

---

### Task 1: Password hashing

**Files:**
- Create: `doctor_dictation/passwords.py`, `tests/test_passwords.py`

**Interfaces:**
- Produces (`doctor_dictation.passwords`): `PasswordError(ValueError)`; constants `MIN_LENGTH = 10`, `MAX_LENGTH = 200`, `TEMP_LENGTH = 16`; `hash_password(password: str) -> str`; `verify_password(password: str, stored) -> bool` (never raises); `dummy_verify(password) -> bool` (always False, spends one scrypt); `temp_password() -> str`; `check_new_password(password) -> None` (raises `PasswordError`).

- [ ] **Step 0: Confirm scrypt is available**

Run: `.venv/bin/python -c "import hashlib; print(len(hashlib.scrypt(b'x', salt=b'y', n=2**14, r=8, p=1, dklen=32, maxmem=64*1024*1024)))"`
Expected: `32`. If it raises (`unsupported hash type scrypt`), stop and report BLOCKED: the interpreter's OpenSSL lacks scrypt.

- [ ] **Step 1: Write the failing tests**

`tests/test_passwords.py`:

```python
"""Password hashing: round trip, salts, hostile hashes, temporary passwords. Offline."""
import hashlib

import pytest

from doctor_dictation import passwords as P


def test_hash_and_verify_round_trip():
    h = P.hash_password("correct horse battery")
    assert h.startswith("scrypt$16384$8$1$")
    assert P.verify_password("correct horse battery", h) is True
    assert P.verify_password("correct horse batterY", h) is False


def test_each_hash_has_its_own_salt():
    a, b = P.hash_password("same password!"), P.hash_password("same password!")
    assert a != b
    assert P.verify_password("same password!", a) and P.verify_password("same password!", b)


def test_verify_rejects_malformed_and_hostile_hashes_without_raising():
    parts = P.hash_password("secret-pass-1").split("$")
    hostile = [
        "", "x", None, 7, "scrypt$1$1$1$a$b",
        "$".join(["scrypt", str(2**30), "8", "1", parts[4], parts[5]]),   # memory bomb
        "$".join(["scrypt", "16384", "8", "1", "***", parts[5]]),         # bad base64
        "$".join(["bcrypt"] + parts[1:]),                                 # wrong scheme
        "$".join(parts[:5]),                                              # digest missing
    ]
    for stored in hostile:
        assert P.verify_password("secret-pass-1", stored) is False, stored


def test_temp_password_shape():
    a, b = P.temp_password(), P.temp_password()
    assert len(a) == P.TEMP_LENGTH == 16 and a != b
    assert set(a) <= set(P._ALPHABET)
    assert not set(a) & set("0O1lI")          # no look-alike characters


def test_check_new_password_rules():
    P.check_new_password("x" * 10)
    P.check_new_password("x" * 200)
    for bad in ("", "x" * 9, "x" * 201, None, 123):
        with pytest.raises(P.PasswordError):
            P.check_new_password(bad)


def test_dummy_verify_runs_a_real_scrypt_and_returns_false(monkeypatch):
    calls, real = [], hashlib.scrypt
    monkeypatch.setattr(P.hashlib, "scrypt", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    P._dummy = None
    assert P.dummy_verify("whatever") is False
    assert len(calls) >= 2                    # one to build the cached dummy hash, one for the comparison
    calls.clear()
    assert P.dummy_verify("whatever") is False and len(calls) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_passwords.py -q`
Expected: FAIL (`cannot import name 'passwords'`).

- [ ] **Step 3: Write the implementation**

`doctor_dictation/passwords.py`:

```python
"""Password hashing and temporary passwords. Standard library only (scrypt).

The stored form carries its own parameters, so they can be raised later without breaking old hashes:
``scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>``.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

N, R, P, DKLEN, SALT_BYTES = 2**14, 8, 1, 32, 16
MAXMEM = 64 * 1024 * 1024
MIN_LENGTH, MAX_LENGTH, TEMP_LENGTH = 10, 200, 16
_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0/O, 1/l/I
_dummy: str | None = None


class PasswordError(ValueError):
    """A new password does not meet the rules."""


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=dklen, maxmem=MAXMEM)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _scrypt(password, salt, N, R, P, DKLEN)
    return "$".join(("scrypt", str(N), str(R), str(P), base64.b64encode(salt).decode(), base64.b64encode(digest).decode()))


def verify_password(password: str, stored) -> bool:
    """True only for a matching password. Any malformed or hostile ``stored`` value is simply False."""
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        n, r, p = int(n), int(r), int(p)
        if scheme != "scrypt" or not (2**10 <= n <= 2**15 and 1 <= r <= 8 and 1 <= p <= 4):
            return False
        want = base64.b64decode(digest, validate=True)
        got = _scrypt(password, base64.b64decode(salt, validate=True), n, r, p, len(want))
    except (ValueError, TypeError, AttributeError):
        return False
    return hmac.compare_digest(got, want)


def dummy_verify(password) -> bool:
    """Spend one scrypt computation and return False: used for unknown, locked and disabled logins."""
    global _dummy
    _dummy = _dummy or hash_password(secrets.token_urlsafe(8))
    verify_password(password, _dummy)
    return False


def temp_password() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(TEMP_LENGTH))


def check_new_password(password) -> None:
    if not isinstance(password, str) or not MIN_LENGTH <= len(password) <= MAX_LENGTH:
        raise PasswordError(f"password must be {MIN_LENGTH} to {MAX_LENGTH} characters")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_passwords.py -q`
Expected: 6 passed.

- [ ] **Step 5: Leave uncommitted.**

---

### Task 2: Session cookies

**Files:**
- Create: `doctor_dictation/sessions.py`, `tests/test_sessions.py`
- Modify: `tests/conftest.py` (the `multi` fixture and the autouse fixture)

**Interfaces:**
- Consumes: `scope.valid_slug`.
- Produces (`doctor_dictation.sessions`): `COOKIE_NAME = "dd_session"`, `LIFETIME_SECONDS = 43200`, `MIN_SECRET_LENGTH = 32`, `DEV_FLAG_ENV = "DEV_INSECURE_SESSION_SECRET"`; `SecretError(RuntimeError)`; frozen dataclass `Identity(clinic_slug: str, user_id: int, username: str, role: str, display_name: str = "", must_change_password: bool = False, session_version: int = 0)`; `session_secret() -> bytes`; `sign(clinic_slug, user_id, session_version, now: int | float | None = None) -> str`; `verify(token, now: int | float | None = None) -> dict | None` (payload dict or None, never raises except `SecretError`); `_encode(payload: dict) -> str`, `_b64(raw: bytes) -> str` (used by tests).

- [ ] **Step 1: Write the failing tests and extend the fixtures**

`tests/test_sessions.py`:

```python
"""Signed session cookie: round trip, tampering, expiry, hostile input, secret rules. Offline."""
import json

import pytest

from doctor_dictation import sessions as S


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s" * 40)
    monkeypatch.delenv(S.DEV_FLAG_ENV, raising=False)


def test_round_trip():
    token = S.sign("rao", 7, 3, now=1000)
    assert S.verify(token, now=1001) == {"clinic": "rao", "uid": 7, "ver": 3, "iat": 1000, "exp": 1000 + S.LIFETIME_SECONDS}


def test_tampered_payload_is_rejected():
    _body, sig = S.sign("rao", 7, 0, now=1000).split(".")
    forged = S._b64(json.dumps({"clinic": "iyer", "uid": 7, "ver": 0, "iat": 1000, "exp": 10**12}).encode())
    assert S.verify(f"{forged}.{sig}", now=1001) is None


def test_tampered_signature_is_rejected():
    body, sig = S.sign("rao", 7, 0, now=1000).split(".")
    bad = sig[:-2] + ("AA" if not sig.endswith("AA") else "BB")
    assert S.verify(f"{body}.{bad}", now=1001) is None


def test_expired_token_is_rejected():
    token = S.sign("rao", 7, 0, now=1000)
    assert S.verify(token, now=1000 + S.LIFETIME_SECONDS - 1) is not None
    assert S.verify(token, now=1000 + S.LIFETIME_SECONDS) is None


def test_token_signed_with_another_secret_is_rejected(monkeypatch):
    token = S.sign("rao", 7, 0, now=1000)
    monkeypatch.setenv("SESSION_SECRET", "z" * 40)
    assert S.verify(token, now=1001) is None


def test_garbage_tokens_return_none_without_raising():
    for token in (None, "", "a", "a.b", "..", "a.b.c", "é.é", "x" * 10000, 12):
        assert S.verify(token, now=1) is None, token


def test_verified_payload_with_bad_field_types_is_rejected():
    good = {"clinic": "rao", "uid": 1, "ver": 0, "iat": 1, "exp": 10**12}
    assert S.verify(S._encode(good), now=2) is not None
    for field, bad in (("clinic", "../x"), ("clinic", 5), ("uid", "1"), ("uid", True), ("ver", None), ("exp", "9"), ("exp", True)):
        assert S.verify(S._encode({**good, field: bad}), now=2) is None, (field, bad)
    assert S.verify(S._encode({"clinic": "rao"}), now=2) is None     # missing fields


def test_session_secret_needs_32_characters(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET")
    with pytest.raises(S.SecretError):
        S.session_secret()
    monkeypatch.setenv("SESSION_SECRET", "x" * 31)
    with pytest.raises(S.SecretError):
        S.session_secret()
    monkeypatch.setenv("SESSION_SECRET", "x" * 32)
    assert S.session_secret() == b"x" * 32


def test_dev_flag_allows_a_fixed_secret_only_when_exactly_1(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET")
    monkeypatch.setenv(S.DEV_FLAG_ENV, "true")
    with pytest.raises(S.SecretError):
        S.session_secret()
    monkeypatch.setenv(S.DEV_FLAG_ENV, "1")
    assert len(S.session_secret()) >= S.MIN_SECRET_LENGTH
```

Replace `tests/conftest.py` with:

```python
"""Shared fixtures. Only the multi-clinic tests use `multi`; every other test is unaffected."""
import pytest


@pytest.fixture(autouse=True)
def _clean_clinic_env(monkeypatch):
    """A developer's .env must not leak multi-clinic mode or secrets into the suite."""
    for name in ("MULTI_CLINIC", "DATA_DIR", "SESSION_SECRET", "DEV_INSECURE_SESSION_SECRET"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def multi(tmp_path, monkeypatch):
    """Multi-clinic mode on, data under a temp folder, a valid session secret, DB_PATH removed so it cannot leak in."""
    monkeypatch.setenv("MULTI_CLINIC", "1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-" + "x" * 24)
    monkeypatch.delenv("DB_PATH", raising=False)
    return tmp_path
```

(If the current `conftest.py` has extra fixtures, keep them and only add the `SESSION_SECRET` line in `multi` and the extended loop in the autouse fixture.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sessions.py -q`
Expected: FAIL (`cannot import name 'sessions'`).

- [ ] **Step 3: Write the implementation**

`doctor_dictation/sessions.py`:

```python
"""Signed session cookie: HMAC-SHA256 over a small JSON payload. Stateless; revocation is the per-user
``session_version`` check ``authn.load_identity`` does on every request."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

from doctor_dictation.scope import valid_slug

COOKIE_NAME = "dd_session"
LIFETIME_SECONDS = 12 * 60 * 60
MIN_SECRET_LENGTH = 32
DEV_FLAG_ENV = "DEV_INSECURE_SESSION_SECRET"
_DEV_SECRET = b"dev-only-insecure-session-secret!"   # 33 bytes; used only with DEV_INSECURE_SESSION_SECRET=1


class SecretError(RuntimeError):
    """SESSION_SECRET is missing or too short."""


@dataclass(frozen=True)
class Identity:
    clinic_slug: str
    user_id: int
    username: str
    role: str
    display_name: str = ""
    must_change_password: bool = False
    session_version: int = 0


def session_secret() -> bytes:
    secret = os.getenv("SESSION_SECRET", "")
    if len(secret) >= MIN_SECRET_LENGTH:
        return secret.encode("utf-8")
    if os.getenv(DEV_FLAG_ENV, "") == "1":
        return _DEV_SECRET
    raise SecretError(f"SESSION_SECRET must be set to at least {MIN_SECRET_LENGTH} characters "
                      f"(or set {DEV_FLAG_ENV}=1 for local development only)")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(body: str) -> str:
    return _b64(hmac.new(session_secret(), body.encode("ascii"), hashlib.sha256).digest())


def _encode(payload: dict) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{body}.{_mac(body)}"


def sign(clinic_slug: str, user_id: int, session_version: int, now=None) -> str:
    issued = int(time.time() if now is None else now)
    return _encode({"clinic": clinic_slug, "uid": user_id, "ver": session_version, "iat": issued, "exp": issued + LIFETIME_SECONDS})


def verify(token, now=None) -> dict | None:
    """The payload for a genuine, unexpired token with well-typed fields; otherwise None (never raises, except SecretError)."""
    try:
        body, sig = token.split(".")
        if not hmac.compare_digest(sig, _mac(body)):
            return None
        payload = json.loads(_unb64(body))
        current = time.time() if now is None else now
        if not (valid_slug(payload["clinic"]) and type(payload["uid"]) is int and type(payload["ver"]) is int
                and type(payload["exp"]) is int and payload["exp"] > current):
            return None
    except (ValueError, TypeError, KeyError, AttributeError):
        return None
    return payload
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `.venv/bin/python -m pytest tests/test_sessions.py -q`
Expected: 9 passed.
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 15` passed (6 + 9), 1 skipped.

- [ ] **Step 5: Leave uncommitted.**

---

### Task 3: Username index and login throttling

**Files:**
- Create: `doctor_dictation/directory/logins.py`, `tests/test_logins.py`

**Interfaces:**
- Consumes: `directory.DirectoryError`, the `login_index` and `login_attempts` tables (M1 migration `001_directory.sql`).
- Produces (`doctor_dictation.directory.logins`): `MAX_FAILURES = 5`, `LOCK_SECONDS = 300`; `index_username(conn, username, clinic_slug, user_id) -> None` (raises `DirectoryError` "that username is already taken" or "unknown clinic 'x'"); `lookup_username(conn, username) -> Row | None` (`clinic_slug`, `user_id`); `drop_username(conn, username) -> None`; `is_locked(conn, username, ip, now: datetime | None = None) -> bool`; `record_failure(conn, username, ip, now=None) -> None`; `clear_failures(conn, username, ip) -> None`. `now` is a timezone-aware `datetime`; `None` means the current UTC time. Attempt keys use the first 64 characters of the username.

- [ ] **Step 1: Write the failing tests**

`tests/test_logins.py`:

```python
"""Username index and login throttling in the directory database. Offline."""
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from doctor_dictation import directory as D
from doctor_dictation.directory import logins as L

T0 = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def d(multi):
    with closing(D.open_directory()) as conn:
        D.create_clinic(conn, "rao", "Rao Clinic")
        D.create_clinic(conn, "iyer", "Iyer Clinic")
        yield conn


def _attempt(d):
    return d.execute("SELECT failed_count, locked_until FROM login_attempts").fetchone()


def test_index_and_lookup_ignore_case(d):
    L.index_username(d, "Dr.Rao", "rao", 1)
    row = L.lookup_username(d, "dr.RAO")
    assert (row["clinic_slug"], row["user_id"]) == ("rao", 1)
    assert L.lookup_username(d, "nobody") is None


def test_a_taken_username_is_refused_whatever_its_case(d):
    L.index_username(d, "Dr.Rao", "rao", 1)
    with pytest.raises(D.DirectoryError, match="already taken"):
        L.index_username(d, "dr.rao", "iyer", 9)


def test_an_unknown_clinic_is_refused(d):
    with pytest.raises(D.DirectoryError, match="unknown clinic"):
        L.index_username(d, "dr.x", "ghost", 1)
    assert L.lookup_username(d, "dr.x") is None


def test_drop_username_frees_it(d):
    L.index_username(d, "dr.rao", "rao", 1)
    L.drop_username(d, "DR.RAO")
    assert L.lookup_username(d, "dr.rao") is None
    L.index_username(d, "dr.rao", "iyer", 2)


def test_five_failures_lock_and_four_do_not(d):
    for _ in range(4):
        L.record_failure(d, "dr.rao", "1.2.3.4", T0)
        assert L.is_locked(d, "dr.rao", "1.2.3.4", T0) is False
    L.record_failure(d, "dr.rao", "1.2.3.4", T0)
    assert L.is_locked(d, "dr.rao", "1.2.3.4", T0) is True


def test_lock_expires_after_five_minutes_and_the_count_restarts(d):
    for _ in range(5):
        L.record_failure(d, "dr.rao", "ip", T0)
    assert L.is_locked(d, "dr.rao", "ip", T0 + timedelta(seconds=299)) is True
    later = T0 + timedelta(seconds=300)
    assert L.is_locked(d, "dr.rao", "ip", later) is False
    L.record_failure(d, "dr.rao", "ip", later)
    row = _attempt(d)
    assert (row["failed_count"], row["locked_until"]) == (1, None)


def test_clear_failures_and_separate_keys_per_username_and_ip(d):
    for _ in range(5):
        L.record_failure(d, "dr.rao", "ip1", T0)
    assert L.is_locked(d, "dr.rao", "ip2", T0) is False
    assert L.is_locked(d, "dr.iyer", "ip1", T0) is False
    L.clear_failures(d, "DR.RAO", "ip1")
    assert L.is_locked(d, "dr.rao", "ip1", T0) is False


def test_failures_while_locked_do_not_extend_the_lock(d):
    for _ in range(5):
        L.record_failure(d, "dr.rao", "ip", T0)
    before = tuple(_attempt(d))
    L.record_failure(d, "dr.rao", "ip", T0 + timedelta(seconds=100))
    assert tuple(_attempt(d)) == before
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_logins.py -q`
Expected: FAIL (`cannot import name 'logins'`).

- [ ] **Step 3: Write the implementation**

`doctor_dictation/directory/logins.py`:

```python
"""Username index (system-wide unique, case-insensitive) and login throttling, in the directory database."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from doctor_dictation.directory import DirectoryError

MAX_FAILURES = 5
LOCK_SECONDS = 300
_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _now(now):
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc)


def _iso(moment) -> str:
    return moment.strftime(_FMT)


def _key(username) -> str:
    return str(username)[:64]


def index_username(conn, username, clinic_slug, user_id) -> None:
    try:
        conn.execute("INSERT INTO login_index(username, clinic_slug, user_id) VALUES (?, ?, ?)",
                     (username, clinic_slug, user_id))
    except sqlite3.IntegrityError:
        conn.rollback()
        if lookup_username(conn, username) is not None:
            raise DirectoryError("that username is already taken") from None
        raise DirectoryError(f"unknown clinic '{clinic_slug}'") from None
    conn.commit()


def lookup_username(conn, username):
    return conn.execute("SELECT * FROM login_index WHERE username = ?", (username,)).fetchone()


def drop_username(conn, username) -> None:
    conn.execute("DELETE FROM login_index WHERE username = ?", (username,))
    conn.commit()


def _row(conn, username, ip):
    return conn.execute("SELECT failed_count, locked_until FROM login_attempts WHERE username = ? AND ip = ?",
                        (_key(username), ip)).fetchone()


def is_locked(conn, username, ip, now=None) -> bool:
    row = _row(conn, username, ip)
    return bool(row and row["locked_until"] and row["locked_until"] > _iso(_now(now)))


def record_failure(conn, username, ip, now=None) -> None:
    moment = _now(now)
    row = _row(conn, username, ip)
    if row and row["locked_until"] and row["locked_until"] > _iso(moment):
        return                                            # already locked: never extend the lock
    count = 1 if row is None or row["locked_until"] else row["failed_count"] + 1   # an expired lock starts a fresh count
    locked_until = _iso(moment + timedelta(seconds=LOCK_SECONDS)) if count >= MAX_FAILURES else None
    conn.execute(
        "INSERT INTO login_attempts(username, ip, failed_count, locked_until, updated_at) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(username, ip) DO UPDATE SET failed_count = excluded.failed_count,"
        " locked_until = excluded.locked_until, updated_at = excluded.updated_at",
        (_key(username), ip, count, locked_until, _iso(moment)))
    conn.commit()


def clear_failures(conn, username, ip) -> None:
    conn.execute("DELETE FROM login_attempts WHERE username = ? AND ip = ?", (_key(username), ip))
    conn.commit()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_logins.py -q`
Expected: 8 passed.

- [ ] **Step 5: Leave uncommitted.**

---

### Task 4: Users migration and account operations

**Files:**
- Create: `doctor_dictation/db/migrations/005_users_profile.sql`, `doctor_dictation/accounts.py`, `tests/test_accounts.py`
- Modify: `tests/test_db.py` (one assertion, line 88)

**Interfaces:**
- Consumes: Task 1 `passwords.*`; Task 2 `sessions.Identity`; Task 3 `logins.index_username`, `logins.lookup_username`; M1 `directory.open_directory`, `directory.get_clinic`, `directory.DirectoryError`, `scope.clinic_dir`, `db.get_conn`, `db.log_audit`.
- Produces (`doctor_dictation.accounts`): `AccountError(ValueError)`; `ROLES = ("doctor", "assistant", "admin")`; `check_username(username) -> str`; context manager `clinic_conn(slug)` (opens `clinic_dir(slug)/"app.db"` by path, closes on exit; raises `AccountError` if the file does not exist); `create_user(clinic_slug, username, display_name="", doctor_name="", qualifications="", reg_no="", role="doctor", password=None, actor=None) -> tuple[int, str]` (user id, the password: generated when `password` is None); `reset_password(username, actor=None) -> str` (new temporary password); `change_password(identity, current, new) -> int` (the new `session_version`). New users get `must_change_password = 1`, `session_version = 0`, `is_active = 1`.

- [ ] **Step 1: Write the failing tests and update the migration-list assertion**

In `tests/test_db.py` line 88 change the expected list to:

```python
    assert first == ["001_init.sql", "002_document_pdf.sql", "003_clinic_profile.sql", "004_templates.sql", "005_users_profile.sql"]
```

`tests/test_accounts.py`:

```python
"""Account operations: create, reset, change password. Offline."""
import json
from contextlib import closing

import pytest

from doctor_dictation import accounts as A
from doctor_dictation import clinics
from doctor_dictation import db as dbmod
from doctor_dictation import directory as D
from doctor_dictation import passwords as P
from doctor_dictation.directory import logins
from doctor_dictation.scope import clinic_dir
from doctor_dictation.sessions import Identity


@pytest.fixture()
def two(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    clinics.provision_clinic("iyer", "Iyer Clinic")
    return multi


def _conn(slug):
    return dbmod.get_conn(clinic_dir(slug) / "app.db")


def _user(slug, username):
    with closing(_conn(slug)) as c:
        return c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def _audit(slug, action):
    with closing(_conn(slug)) as c:
        return c.execute("SELECT actor, action, entity_id, detail FROM audit_log WHERE action = ?", (action,)).fetchone()


def test_migration_005_adds_user_columns_with_defaults(two):
    with closing(_conn("rao")) as c:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(users)")}
        c.execute("INSERT INTO users(username, password_hash, created_at) VALUES ('legacy', 'x', '2026-01-01T00:00:00Z')")
        c.commit()
        row = c.execute("SELECT * FROM users WHERE username = 'legacy'").fetchone()
    assert {"display_name", "doctor_name", "qualifications", "reg_no", "session_version", "must_change_password", "last_login_at"} <= cols
    assert (row["session_version"], row["must_change_password"], row["display_name"], row["last_login_at"]) == (0, 1, "", None)


def test_create_user_hashes_password_indexes_username_and_returns_temp_once(two):
    uid, temp = A.create_user("rao", "dr.rao", display_name="Dr. Rao", doctor_name="Dr A. Rao", qualifications="MBBS", reg_no="TS-1")
    row = _user("rao", "dr.rao")
    assert row["id"] == uid and len(temp) == 16
    assert temp not in row["password_hash"] and P.verify_password(temp, row["password_hash"])
    assert (row["role"], row["is_active"], row["must_change_password"], row["session_version"]) == ("doctor", 1, 1, 0)
    assert (row["display_name"], row["doctor_name"], row["qualifications"], row["reg_no"]) == ("Dr. Rao", "Dr A. Rao", "MBBS", "TS-1")
    with closing(D.open_directory()) as d:
        entry = logins.lookup_username(d, "DR.RAO")
    assert (entry["clinic_slug"], entry["user_id"]) == ("rao", uid)


def test_create_user_audits_the_actor_without_leaking_the_password(two):
    _uid, temp = A.create_user("rao", "dr.rao", actor="admin-cli")
    row = _audit("rao", "user_create")
    assert row["actor"] == "admin-cli" and json.loads(row["detail"]) == {"username": "dr.rao"}
    assert temp not in (row["detail"] or "")


def test_create_user_rejects_bad_usernames_roles_and_unknown_clinics(two):
    for bad in ("", "ab", "a b", "../x", "x" * 41, "dr/rao", "dr.rao\n", None, 7):
        with pytest.raises(A.AccountError):
            A.create_user("rao", bad)
    with pytest.raises(A.AccountError):
        A.create_user("rao", "dr.rao", role="owner")
    with pytest.raises(A.AccountError, match="clinic"):
        A.create_user("ghost", "dr.rao")
    assert _user("rao", "dr.rao") is None


def test_create_user_rejects_taken_username_across_clinics_and_case(two):
    A.create_user("rao", "Dr.Rao")
    for slug, name in (("iyer", "dr.rao"), ("rao", "DR.RAO")):
        with pytest.raises(A.AccountError, match="taken"):
            A.create_user(slug, name)
    assert _user("iyer", "dr.rao") is None and _user("rao", "DR.RAO") is None


def test_create_user_removes_its_clinic_row_when_the_directory_index_fails(two, monkeypatch):
    def boom(*_a, **_k):
        raise D.DirectoryError("directory is down")

    monkeypatch.setattr(A, "index_username", boom)
    with pytest.raises(A.AccountError, match="directory is down"):
        A.create_user("rao", "dr.rao")
    assert _user("rao", "dr.rao") is None


def test_create_user_with_an_explicit_password_applies_the_password_rules(two):
    with pytest.raises(P.PasswordError):
        A.create_user("rao", "dr.rao", password="short")
    assert _user("rao", "dr.rao") is None
    _uid, pw = A.create_user("rao", "dr.rao", password="a-long-enough-pw")
    assert pw == "a-long-enough-pw" and P.verify_password(pw, _user("rao", "dr.rao")["password_hash"])


def test_reset_password_bumps_version_sets_must_change_and_audits(two):
    uid, _ = A.create_user("rao", "dr.rao", password="first-password-1")
    with closing(_conn("rao")) as c:
        c.execute("UPDATE users SET must_change_password = 0 WHERE id = ?", (uid,))
        c.commit()
    new = A.reset_password("DR.RAO", actor="admin-cli")
    row = _user("rao", "dr.rao")
    assert P.verify_password(new, row["password_hash"]) and not P.verify_password("first-password-1", row["password_hash"])
    assert (row["session_version"], row["must_change_password"]) == (1, 1)
    audit = _audit("rao", "password_reset")
    assert (audit["actor"], audit["entity_id"]) == ("admin-cli", str(uid)) and new not in (audit["detail"] or "")


def test_reset_password_for_an_unknown_user_raises(two):
    with pytest.raises(A.AccountError, match="no such user"):
        A.reset_password("nobody")


def test_change_password_checks_current_enforces_rules_bumps_version_clears_flag_and_audits(two):
    uid, temp = A.create_user("rao", "dr.rao")
    me = Identity("rao", uid, "dr.rao", "doctor", must_change_password=True)
    with pytest.raises(P.PasswordError):
        A.change_password(me, temp, "short")
    with pytest.raises(A.AccountError, match="different"):
        A.change_password(me, temp, temp)
    version = A.change_password(me, temp, "a-brand-new-password")
    row = _user("rao", "dr.rao")
    assert version == row["session_version"] == 1 and row["must_change_password"] == 0
    assert P.verify_password("a-brand-new-password", row["password_hash"])
    assert _audit("rao", "password_change")["actor"] == "dr.rao"


def test_change_password_with_a_wrong_current_password_changes_nothing(two):
    uid, temp = A.create_user("rao", "dr.rao")
    me = Identity("rao", uid, "dr.rao", "doctor")
    with pytest.raises(A.AccountError, match="Current password is incorrect"):
        A.change_password(me, "not-the-password-1", "a-brand-new-password")
    row = _user("rao", "dr.rao")
    assert row["session_version"] == 0 and P.verify_password(temp, row["password_hash"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_accounts.py tests/test_db.py -q`
Expected: FAIL (`cannot import name 'accounts'`, and the `test_db.py` migration-list assertion fails on the missing `005`).

- [ ] **Step 3: Write the migration and the module**

`doctor_dictation/db/migrations/005_users_profile.sql`:

```sql
-- 005: per-user identity fields and session control. Applied once per clinic database; recorded in schema_migrations.
ALTER TABLE users ADD COLUMN display_name          TEXT    NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN doctor_name           TEXT    NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN qualifications        TEXT    NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN reg_no                TEXT    NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN session_version       INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN must_change_password  INTEGER NOT NULL DEFAULT 1;
ALTER TABLE users ADD COLUMN last_login_at         TEXT;
```

`doctor_dictation/accounts.py`:

```python
"""Account operations on a clinic's ``users`` table and the directory's username index.

They take the clinic slug explicitly and open the clinic file by path, so they work with
``MULTI_CLINIC`` on or off and need no request scope (the operator CLI uses them too).
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import closing, contextmanager

from doctor_dictation import db as dbmod
from doctor_dictation.directory import DirectoryError, get_clinic, open_directory
from doctor_dictation.directory.logins import index_username, lookup_username
from doctor_dictation.passwords import check_new_password, hash_password, temp_password, verify_password
from doctor_dictation.scope import clinic_dir

USERNAME_RE = re.compile(r"[A-Za-z0-9._-]{3,40}")
ROLES = ("doctor", "assistant", "admin")


class AccountError(ValueError):
    """An account operation the caller can fix (bad username, taken, wrong current password)."""


def check_username(username) -> str:
    if not isinstance(username, str) or USERNAME_RE.fullmatch(username) is None:
        raise AccountError("username must be 3 to 40 characters: letters, digits, '.', '_' or '-'")
    return username


@contextmanager
def clinic_conn(slug):
    path = clinic_dir(slug) / "app.db"
    if not path.is_file():
        raise AccountError(f"clinic '{slug}' has no database")
    conn = dbmod.get_conn(path)
    try:
        yield conn
    finally:
        conn.close()


def create_user(clinic_slug, username, display_name="", doctor_name="", qualifications="", reg_no="",
                role="doctor", password=None, actor=None) -> tuple[int, str]:
    """Create a user and index the username system-wide. Returns ``(user_id, password)``; the password is
    generated when ``password`` is None and must be shown to the operator once, never stored in clear."""
    check_username(username)
    if role not in ROLES:
        raise AccountError(f"role must be one of {', '.join(ROLES)}")
    if password is not None:
        check_new_password(password)
    secret = password if password is not None else temp_password()
    with closing(open_directory()) as d:
        if get_clinic(d, clinic_slug) is None:
            raise AccountError(f"no such clinic '{clinic_slug}'")
        if lookup_username(d, username) is not None:
            raise AccountError("that username is already taken")
        with clinic_conn(clinic_slug) as conn:
            try:
                cur = conn.execute(
                    "INSERT INTO users(username, password_hash, role, is_active, created_at, display_name, doctor_name,"
                    " qualifications, reg_no, session_version, must_change_password) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, 0, 1)",
                    (username, hash_password(secret), role, dbmod._utcnow(), display_name or username, doctor_name,
                     qualifications, reg_no))
            except sqlite3.IntegrityError:
                raise AccountError("that username is already taken in this clinic") from None
            user_id = cur.lastrowid
            conn.commit()
            try:
                index_username(d, username, clinic_slug, user_id)
            except DirectoryError as exc:                  # undo our own insert: no half-created user
                conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
                conn.commit()
                raise AccountError(str(exc)) from None
            dbmod.log_audit(conn, actor=actor, action="user_create", entity="user", entity_id=str(user_id),
                            detail={"username": username})
    return user_id, secret


def reset_password(username, actor=None) -> str:
    """Set a new temporary password, force a change at next sign-in and end the user's sessions."""
    with closing(open_directory()) as d:
        entry = lookup_username(d, username)
    if entry is None:
        raise AccountError("no such user")
    secret = temp_password()
    with clinic_conn(entry["clinic_slug"]) as conn:
        conn.execute("UPDATE users SET password_hash = ?, must_change_password = 1, session_version = session_version + 1"
                     " WHERE id = ?", (hash_password(secret), entry["user_id"]))
        conn.commit()
        dbmod.log_audit(conn, actor=actor, action="password_reset", entity="user", entity_id=str(entry["user_id"]))
    return secret


def change_password(identity, current, new) -> int:
    """Change the signed-in user's own password; returns the new ``session_version`` (the caller re-issues the cookie)."""
    check_new_password(new)
    with clinic_conn(identity.clinic_slug) as conn:
        row = conn.execute("SELECT password_hash, session_version FROM users WHERE id = ?", (identity.user_id,)).fetchone()
        if row is None or not verify_password(current, row["password_hash"]):
            raise AccountError("Current password is incorrect")
        if verify_password(new, row["password_hash"]):
            raise AccountError("New password must be different from the current one")
        version = row["session_version"] + 1
        conn.execute("UPDATE users SET password_hash = ?, session_version = ?, must_change_password = 0 WHERE id = ?",
                     (hash_password(new), version, identity.user_id))
        conn.commit()
        dbmod.log_audit(conn, actor=identity.username, role=identity.role, action="password_change", entity="user",
                        entity_id=str(identity.user_id))
    return version
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `.venv/bin/python -m pytest tests/test_accounts.py tests/test_db.py -q`
Expected: all pass (`test_accounts.py`: 11).
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 34` passed (6 + 9 + 8 + 11), 1 skipped.

- [ ] **Step 5: Leave uncommitted.**

---

### Task 5: Login and per-request identity

**Files:**
- Create: `doctor_dictation/authn.py`, `tests/test_authn.py`

**Interfaces:**
- Consumes: Tasks 1 to 4; M1 `directory.*`, `scope.clinic_dir`.
- Produces (`doctor_dictation.authn`): `authenticate(username, password, ip, now: datetime | None = None, failed_clinics=frozenset()) -> Identity | None`; `load_identity(token, now: datetime | None = None, failed_clinics=frozenset()) -> Identity | None`; `clinic_name(slug) -> str`. `authenticate` strips surrounding whitespace from the username, counts failures per `(username, ip)`, never raises for a bad credential, and returns the same `None` for wrong user, wrong password, locked, disabled user, disabled clinic and failed clinic. `load_identity` returns an `Identity` only for a valid unexpired cookie whose user is active, whose `session_version` still matches, and whose clinic is active and not in `failed_clinics`.

- [ ] **Step 1: Write the failing tests**

`tests/test_authn.py`:

```python
"""authenticate / load_identity: success, every failure shape, lockout, session revocation. Offline."""
import shutil
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from doctor_dictation import accounts as A
from doctor_dictation import authn as N
from doctor_dictation import clinics
from doctor_dictation import db as dbmod
from doctor_dictation import directory as D
from doctor_dictation import sessions
from doctor_dictation.scope import clinic_dir
from doctor_dictation.sessions import Identity

T0 = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)
IP = "10.0.0.1"


@pytest.fixture()
def world(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    clinics.provision_clinic("iyer", "Iyer Clinic")
    rao, _ = A.create_user("rao", "dr.rao", display_name="Dr. Rao", password="rao-password-1")
    iyer, _ = A.create_user("iyer", "dr.iyer", password="iyer-password-1")
    return {"rao": rao, "iyer": iyer}


def _sql(slug, sql, *args):
    with closing(dbmod.get_conn(clinic_dir(slug) / "app.db")) as c:
        c.execute(sql, args)
        c.commit()


def _failures():
    with closing(D.open_directory()) as d:
        return d.execute("SELECT failed_count FROM login_attempts").fetchall()


def _count_dummy(monkeypatch):
    calls, real = [], N.passwords.dummy_verify
    monkeypatch.setattr(N.passwords, "dummy_verify", lambda pw: calls.append(1) or real(pw))
    return calls


def test_login_success_returns_identity_audits_and_updates_last_login(world):
    ident = N.authenticate("dr.rao", "rao-password-1", IP, T0)
    assert ident == Identity("rao", world["rao"], "dr.rao", "doctor", "Dr. Rao", True, 0)
    with closing(dbmod.get_conn(clinic_dir("rao") / "app.db")) as c:
        assert c.execute("SELECT last_login_at FROM users").fetchone()[0] is not None
        audit = c.execute("SELECT actor, role FROM audit_log WHERE action = 'login'").fetchone()
    assert (audit["actor"], audit["role"]) == ("dr.rao", "doctor")


def test_wrong_password_returns_none_and_counts_a_failure(world):
    assert N.authenticate("dr.rao", "wrong-password", IP, T0) is None
    assert [r["failed_count"] for r in _failures()] == [1]


def test_unknown_username_pays_for_a_hash_and_counts_a_failure(world, monkeypatch):
    calls = _count_dummy(monkeypatch)
    assert N.authenticate("nobody", "whatever-pass", IP, T0) is None
    assert calls == [1] and [r["failed_count"] for r in _failures()] == [1]


def test_fifth_failure_locks_and_a_correct_password_is_then_refused(world, monkeypatch):
    for _ in range(5):
        assert N.authenticate("dr.rao", "wrong-password", IP, T0) is None
    calls = _count_dummy(monkeypatch)
    assert N.authenticate("dr.rao", "rao-password-1", IP, T0 + timedelta(seconds=10)) is None
    assert calls == [1]                                      # a locked attempt still pays for one hash
    assert N.authenticate("dr.rao", "rao-password-1", "10.0.0.2", T0 + timedelta(seconds=10)) is not None   # the lock is per (username, ip)


def test_the_lock_expires_after_five_minutes(world):
    for _ in range(5):
        N.authenticate("dr.rao", "wrong-password", IP, T0)
    assert N.authenticate("dr.rao", "rao-password-1", IP, T0 + timedelta(seconds=300)) is not None


def test_success_clears_earlier_failures(world):
    for _ in range(3):
        N.authenticate("dr.rao", "wrong-password", IP, T0)
    assert N.authenticate("dr.rao", "rao-password-1", IP, T0) is not None
    assert _failures() == []


def test_a_disabled_user_is_refused_after_a_dummy_hash(world, monkeypatch):
    _sql("rao", "UPDATE users SET is_active = 0")
    calls = _count_dummy(monkeypatch)
    assert N.authenticate("dr.rao", "rao-password-1", IP, T0) is None
    assert calls == [1]


def test_a_disabled_clinic_is_refused(world):
    with closing(D.open_directory()) as d:
        d.execute("UPDATE clinics SET status = 'disabled' WHERE slug = 'rao'")
        d.commit()
    assert N.authenticate("dr.rao", "rao-password-1", IP, T0) is None
    assert N.authenticate("dr.iyer", "iyer-password-1", IP, T0) is not None


def test_a_clinic_that_failed_startup_is_refused(world):
    assert N.authenticate("dr.rao", "rao-password-1", IP, T0, failed_clinics=frozenset({"rao"})) is None


def test_username_is_case_insensitive_and_trimmed(world):
    assert N.authenticate("  DR.RAO ", "rao-password-1", IP, T0) is not None


def test_load_identity_accepts_a_fresh_cookie(world):
    token = sessions.sign("rao", world["rao"], 0, now=T0.timestamp())
    ident = N.load_identity(token, T0)
    assert (ident.username, ident.clinic_slug, ident.session_version, ident.must_change_password) == ("dr.rao", "rao", 0, True)


def test_load_identity_ends_sessions_on_reset_disable_clinic_disable_and_failed_clinic(world):
    token = sessions.sign("rao", world["rao"], 0, now=T0.timestamp())
    assert N.load_identity(token, T0) is not None
    assert N.load_identity(token, T0, failed_clinics=frozenset({"rao"})) is None
    A.reset_password("dr.rao")                                # session_version 0 -> 1
    assert N.load_identity(token, T0) is None
    token = sessions.sign("rao", world["rao"], 1, now=T0.timestamp())
    assert N.load_identity(token, T0) is not None
    _sql("rao", "UPDATE users SET is_active = 0")
    assert N.load_identity(token, T0) is None
    _sql("rao", "UPDATE users SET is_active = 1")
    with closing(D.open_directory()) as d:
        d.execute("UPDATE clinics SET status = 'disabled' WHERE slug = 'rao'")
        d.commit()
    assert N.load_identity(token, T0) is None


def test_load_identity_rejects_expired_garbage_unknown_user_and_missing_folder(world):
    old = sessions.sign("rao", world["rao"], 0, now=T0.timestamp() - sessions.LIFETIME_SECONDS - 1)
    assert N.load_identity(old, T0) is None
    assert N.load_identity("garbage", T0) is None and N.load_identity(None, T0) is None
    assert N.load_identity(sessions.sign("rao", 999, 0, now=T0.timestamp()), T0) is None
    token = sessions.sign("iyer", world["iyer"], 0, now=T0.timestamp())
    shutil.rmtree(clinic_dir("iyer"))
    assert N.load_identity(token, T0) is None and not clinic_dir("iyer").exists()   # nothing re-created
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_authn.py -q`
Expected: FAIL (`cannot import name 'authn'`).

- [ ] **Step 3: Write the implementation**

`doctor_dictation/authn.py`:

```python
"""Login and per-request identity. Every credential failure looks the same to the caller: ``None``."""
from __future__ import annotations

import sqlite3
from contextlib import closing

from doctor_dictation import db as dbmod
from doctor_dictation import passwords, sessions
from doctor_dictation.directory import get_clinic, open_directory
from doctor_dictation.directory.logins import clear_failures, is_locked, lookup_username, record_failure
from doctor_dictation.scope import clinic_dir
from doctor_dictation.sessions import Identity


def _norm(username) -> str:
    return username.strip() if isinstance(username, str) else ""


def _identity(slug, row) -> Identity:
    return Identity(slug, row["id"], row["username"], row["role"], row["display_name"] or row["username"],
                    bool(row["must_change_password"]), row["session_version"])


def _user_row(slug, user_id):
    path = clinic_dir(slug) / "app.db"
    if not path.is_file():
        return None
    try:
        with closing(dbmod.get_conn(path)) as conn:
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    except sqlite3.Error:
        return None


def _check_user(slug, user_id, password, now) -> Identity | None:
    row = _user_row(slug, user_id)
    if row is None or not row["is_active"]:
        passwords.dummy_verify(password)
        return None
    if not passwords.verify_password(password, row["password_hash"]):
        return None
    with closing(dbmod.get_conn(clinic_dir(slug) / "app.db")) as conn:
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (dbmod._utcnow(), user_id))
        conn.commit()
        dbmod.log_audit(conn, actor=row["username"], role=row["role"], action="login", entity="user", entity_id=str(user_id))
    return _identity(slug, row)


def authenticate(username, password, ip, now=None, failed_clinics=frozenset()) -> Identity | None:
    key = _norm(username)
    with closing(open_directory()) as d:
        locked = is_locked(d, key, ip, now)
        entry = None if locked else lookup_username(d, key)
        clinic = get_clinic(d, entry["clinic_slug"]) if entry else None
        usable = clinic is not None and clinic["status"] == "active" and clinic["slug"] not in failed_clinics
        identity = _check_user(entry["clinic_slug"], entry["user_id"], password, now) if usable else None
        if not usable:
            passwords.dummy_verify(password)                 # unknown, locked and unusable logins cost the same as a real one
        if identity is not None:
            clear_failures(d, key, ip)
            return identity
        if not locked:
            record_failure(d, key, ip, now)
        return None


def load_identity(token, now=None, failed_clinics=frozenset()) -> Identity | None:
    payload = sessions.verify(token, now.timestamp() if now else None)
    if payload is None or payload["clinic"] in failed_clinics:
        return None
    with closing(open_directory()) as d:
        clinic = get_clinic(d, payload["clinic"])
    if clinic is None or clinic["status"] != "active":
        return None
    row = _user_row(payload["clinic"], payload["uid"])
    if row is None or not row["is_active"] or row["session_version"] != payload["ver"]:
        return None
    return _identity(payload["clinic"], row)


def clinic_name(slug) -> str:
    with closing(open_directory()) as d:
        row = get_clinic(d, slug)
    return row["name"] if row else ""
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `.venv/bin/python -m pytest tests/test_authn.py -q`
Expected: 13 passed.
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 47` passed, 1 skipped.

- [ ] **Step 5: Leave uncommitted.**

---

### Task 6: Policy function and audit actor from the scope

**Files:**
- Create: `doctor_dictation/policy.py`, `tests/test_policy_audit.py`
- Modify: `doctor_dictation/db/__init__.py` (the `scope` import line and `log_audit`)

**Interfaces:**
- Consumes: `sessions.Identity`; `scope.current_scope()`.
- Produces: `policy.ACTIONS` (frozenset: `document.view`, `document.reprint`, `document.edit`, `user.create`, `user.disable`, `letterhead.manage`); `policy.can(user, action, resource=None) -> bool` where `user` has `.user_id`, and `resource` for `document.edit` has `author_id` (attribute or dict key). `db.log_audit` now fills a missing `actor` (and `role`) from the current scope; an explicit `actor` wins; with no scope nothing changes.

- [ ] **Step 1: Write the failing tests**

`tests/test_policy_audit.py`:

```python
"""can() and the audit actor taken from the request scope. Offline."""
from contextlib import closing
from types import SimpleNamespace as NS

from doctor_dictation import clinics
from doctor_dictation import db as dbmod
from doctor_dictation import policy
from doctor_dictation.scope import Scope, use_scope
from doctor_dictation.sessions import Identity


def _me(uid=1):
    return Identity("rao", uid, "dr.rao", "doctor")


def test_unknown_actions_are_denied():
    assert policy.can(_me(), "document.delete") is False
    assert policy.can(_me(), "") is False


def test_ordinary_actions_are_allowed_for_any_signed_in_user():
    for action in ("document.view", "document.reprint", "user.create", "user.disable", "letterhead.manage"):
        assert policy.can(_me(), action, NS(author_id=2)) is True, action


def test_only_the_author_may_edit_a_document():
    assert policy.can(_me(1), "document.edit", NS(author_id=1)) is True
    assert policy.can(_me(1), "document.edit", NS(author_id=2)) is False
    assert policy.can(_me(1), "document.edit", {"author_id": 2}) is False
    assert policy.can(_me(1), "document.edit", None) is False


def test_a_document_with_no_recorded_author_can_be_edited_by_anyone_in_the_clinic():
    assert policy.can(_me(5), "document.edit", NS(author_id=None)) is True


def test_log_audit_fills_actor_and_role_from_the_scope(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    with use_scope(Scope("rao", 5, "dr.rao", "doctor")):
        with closing(dbmod.get_conn()) as conn:
            dbmod.log_audit(conn, action="probe")
            row = conn.execute("SELECT actor, role FROM audit_log WHERE action = 'probe'").fetchone()
    assert (row["actor"], row["role"]) == ("dr.rao", "doctor")


def test_an_explicit_actor_wins_over_the_scope(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    with use_scope(Scope("rao", 5, "dr.rao", "doctor")):
        with closing(dbmod.get_conn()) as conn:
            dbmod.log_audit(conn, actor="admin-cli", role="system", action="probe")
            row = conn.execute("SELECT actor, role FROM audit_log WHERE action = 'probe'").fetchone()
    assert (row["actor"], row["role"]) == ("admin-cli", "system")


def test_no_scope_leaves_the_actor_empty_as_before(tmp_path):
    with closing(dbmod.get_conn(tmp_path / "a.db")) as conn:
        dbmod.migrate(conn)
        dbmod.log_audit(conn, action="probe")
        row = conn.execute("SELECT actor, role FROM audit_log WHERE action = 'probe'").fetchone()
    assert (row["actor"], row["role"]) == (None, None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_policy_audit.py -q`
Expected: FAIL (`cannot import name 'policy'`).

- [ ] **Step 3: Write the implementation**

`doctor_dictation/policy.py`:

```python
"""The one place permission rules live. No roles are enforced yet: every signed-in user of a clinic may do
everything except edit a colleague's prescription. Later role rules go inside ``can`` with no route changes."""
from __future__ import annotations

ACTIONS = frozenset({"document.view", "document.reprint", "document.edit", "user.create", "user.disable", "letterhead.manage"})


def _author_id(resource):
    if isinstance(resource, dict):
        return resource.get("author_id")
    return getattr(resource, "author_id", None)


def can(user, action: str, resource=None) -> bool:
    if action not in ACTIONS:
        return False                                  # unknown action: deny
    if action == "document.edit":
        if resource is None:
            return False                              # an edit always names the document
        author = _author_id(resource)
        return author is None or author == user.user_id   # a pre-authorship document (no author) stays editable
    return True
```

In `doctor_dictation/db/__init__.py` change the import to:

```python
from doctor_dictation.scope import clinic_dir, current_scope, multi_clinic_enabled, require_scope
```

and at the start of the body of `log_audit` (after the signature, before the `cur = conn.execute(`) add:

```python
    if actor is None and (sc := current_scope()) is not None:
        actor, role = sc.username, role or sc.role
```

Check `wc -l doctor_dictation/db/__init__.py` stays under 490.

- [ ] **Step 4: Run the tests, then the suite and the size check**

Run: `.venv/bin/python -m pytest tests/test_policy_audit.py -q`
Expected: 7 passed.
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 54` passed, 1 skipped (that is 532 if `N` is 478).
Run: `.venv/bin/python -m pytest tests/test_file_sizes.py -q`
Expected: 2 passed.

- [ ] **Step 5: Leave uncommitted and list the changed files.** `git status --short` should show new: `passwords.py`, `sessions.py`, `accounts.py`, `authn.py`, `policy.py`, `directory/logins.py`, `db/migrations/005_users_profile.sql`, `tests/test_passwords.py`, `test_sessions.py`, `test_logins.py`, `test_accounts.py`, `test_authn.py`, `test_policy_audit.py`; modified: `db/__init__.py`, `tests/conftest.py`, `tests/test_db.py`.

---

## Self-review (against the spec)

- **6.1 users columns:** Task 4 migration 005 (the doctor fields stay on `clinic_profile` too until M3 moves them).
- **6.2 login:** scrypt (Task 1), cookie format and secret rules (Task 2), throttling and one generic outcome (Tasks 3 and 5), per-request validation of signature, expiry, active flag and `session_version` (Task 5 `load_identity`), timing equalisation (Tasks 1 and 5). Routes, cookie flags, CSRF header and the login page are M2b.
- **6.3 `can()`:** Task 6 (wiring it into routes is M3).
- **7.4 audit:** actor from scope (Task 6); `login`, `password_change`, `password_reset`, `user_create` rows (Tasks 4 and 5); `logout` is written by the M2b route; `login_failed` stays in the directory counters (see differences).
- **8.2 account safeguards:** username rules, system-wide uniqueness, rollback if the index write fails (Task 4). Disable/enable and the "cannot disable yourself or the last active user" rules are M5.
- **Placeholder scan:** none; every step shows its code or command.
- **Type consistency:** `Identity` field order is `(clinic_slug, user_id, username, role, display_name, must_change_password, session_version)` everywhere; `now` is a timezone-aware `datetime` in `logins`/`authn`, epoch seconds only inside `sessions`.
- **Test count:** 6 + 9 + 8 + 11 + 13 + 7 = 54.

## Not in this plan

HTTP routes, the session middleware, CSRF header enforcement, the login page and the frontend, the admin commands `create-user` / `reset-password` / `--first-user` (all M2b); wiring `can()` into routes and per-doctor authorship (M3); the Team screen and disable/enable (M5); connection caching for the per-request identity lookup (two small SQLite opens per request, fine at demo scale).
