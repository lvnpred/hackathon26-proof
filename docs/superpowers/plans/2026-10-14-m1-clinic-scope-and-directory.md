# M1: Clinic Scope, Directory Database and Admin Command

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every clinic its own database folder, a small shared directory database listing the clinics, a fail-closed request scope that decides which folder the existing code opens, and an operator command that creates and adopts clinics.

**Architecture:** A new stdlib-only `scope.py` holds a `ContextVar` with the current `Scope(clinic_slug, ...)`. `db.db_path()` (and therefore `pdf_dir()`, `templates_dir()` and `get_conn()`, which already derive from it) reads that scope when `MULTI_CLINIC=1` and raises `NoScope` when there is none; with the flag off everything behaves as today. A `directory/` package owns `data/directory.db`; `clinics.py` provisions, migrates and iterates clinics; `admin.py` is the operator CLI. Nothing in M1 authenticates anyone: in multi-clinic mode an HTTP request has no scope until M2's login middleware sets one, so data routes answer 401.

**Tech Stack:** Python 3.11+, stdlib `sqlite3`, `contextvars`, `argparse`, FastAPI (existing), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-14-multi-clinic-multi-doctor-design.md` sections 5 (architecture), 11 (operator commands, partly) and 12 (rollout, partly).

**Plan 1 of 6 (M1 to M6, spec section 14).** Baseline is 443 passed, 1 skipped. Before the first task run `.venv/bin/python -m pytest tests/ -q` and note the count `N`; **this plan adds 28 tests**, so the count after it must be `N + 28`.

## Deliberate differences from the spec (agreed scope for M1)

- `create-clinic --first-user` and `adopt-existing`'s "create a first doctor" are **left to M2**: both need the scrypt password hashing and the `users` columns migration that M2 builds. M1's commands create the clinic folder, run migrations and register the clinic in the directory; they create no users.
- The directory's `login_index` and `login_attempts` tables are created now (one directory migration) but nothing reads or writes them until M2.
- `db.log_audit` filling `actor` from the scope is M2.
- `seed-demo` is M6.

## Global Constraints

- "No file over 500 lines": `doctor_dictation/db/__init__.py` is 475 lines, so edit it by at most ten lines; all new code goes in new modules. `tests/test_file_sizes.py` enforces this.
- Never run `git commit` or `git push` (user rule). Leave all changes in the working tree; each task ends with "leave uncommitted", and the last step lists the changed files.
- `MULTI_CLINIC` defaults to **off**. With it off, `DB_PATH`, `db_path()`, `pdf_dir()` and every existing test behave exactly as before. The existing 443 tests must pass unchanged.
- Environment variables are read at call time, never at import (monkeypatch-friendly, same as `DB_PATH` today). New variables: `MULTI_CLINIC` (`1`, `true`, `yes`, `on` enable it, case-insensitive) and `DATA_DIR` (root folder for `directory.db` and `clinics/`; default `doctor_dictation/data`).
- `scope.py` imports nothing from `doctor_dictation` (it sits under `db`, `directory` and `clinics`, so it must not import them).
- In multi-clinic mode `db_path()`, `pdf_dir()`, `templates_dir()` and `get_conn()` (without an explicit path) **raise `NoScope`** when there is no scope. They never fall back to a default database and never read `DB_PATH`.
- A clinic slug is 2 to 31 characters, `[a-z0-9]` first, then `[a-z0-9-]`; match with `re.fullmatch` (a trailing newline must fail). An OP prefix is 2 to 6 characters of `[A-Z0-9]`.
- The admin command is run by the operator on the host and is never exposed over HTTP.
- Tests never touch the network and never touch `doctor_dictation/data/`: every new test uses the `multi` fixture (temp `DATA_DIR`, `MULTI_CLINIC=1`, `DB_PATH` removed).

## Review Focus

Failure modes the spec implies that a person using this software is most likely to hit, most likely first. Each is pinned by a test named here.

1. **A malformed or hostile slug reaches the filesystem** (`../x`, `RAO`, `rao\n`, `a`, empty, `/abs`): must raise, never build a path. Task 1 `test_unsafe_slugs_are_rejected`, Task 4 `test_provision_rejects_bad_input_and_duplicates_without_touching_disk`.
2. **`DB_PATH` left in the environment while `MULTI_CLINIC=1`**: must not be used as a fallback. Task 3 `test_multi_mode_fails_closed_without_scope`.
3. **A request with no scope** (before M2 exists, or if the middleware is ever bypassed): must answer 401 and must not create a database. Task 4 `test_route_without_scope_answers_401_and_creates_nothing`.
4. **One clinic's database is corrupt at startup**: the other clinics must still migrate and the app must still boot. Task 4 `test_migrate_all_continues_after_a_failing_clinic`.
5. **`adopt-existing` run while the app still holds the database open (WAL data not yet in `app.db`)**: no data may be lost and a busy database must refuse. Task 5 `test_adopt_existing_moves_everything_even_with_the_old_db_open`.

---

### Task 1: Request scope module

**Files:**
- Create: `doctor_dictation/scope.py`, `tests/conftest.py`, `tests/test_scope.py`

**Interfaces:**
- Produces (all in `doctor_dictation.scope`): `NoScope(RuntimeError)`; frozen dataclass `Scope(clinic_slug: str, user_id: int | None = None, username: str = "system", role: str = "system")` which raises `ValueError` for an invalid slug; `multi_clinic_enabled() -> bool`; `data_root() -> Path`; `valid_slug(slug) -> bool`; `clinic_dir(slug: str) -> Path` (`data_root()/"clinics"/slug`, `ValueError` for an invalid slug); `current_scope() -> Scope | None`; `require_scope() -> Scope` (raises `NoScope`); context manager `use_scope(scope)` which sets and restores the scope. Constants `MULTI_CLINIC_ENV`, `DATA_DIR_ENV`.
- Produces (in `tests/conftest.py`): fixture `multi(tmp_path, monkeypatch) -> Path` returning the temp data root with the flag on.

- [ ] **Step 1: Write the fixture and the failing tests**

`tests/conftest.py`:

```python
"""Shared fixtures. Only the multi-clinic tests use `multi`; every other test is unaffected."""
import pytest


@pytest.fixture()
def multi(tmp_path, monkeypatch):
    """Multi-clinic mode on, data under a temp folder, DB_PATH removed so it cannot leak in."""
    monkeypatch.setenv("MULTI_CLINIC", "1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DB_PATH", raising=False)
    return tmp_path
```

`tests/test_scope.py`:

```python
"""Request scope: flag, slug safety, context handling and thread behaviour. Offline."""
import asyncio
import threading

import pytest

from doctor_dictation import scope as S


def test_multi_clinic_flag_defaults_off_and_reads_env_at_call_time(monkeypatch):
    monkeypatch.delenv("MULTI_CLINIC", raising=False)
    assert S.multi_clinic_enabled() is False
    for on in ("1", "true", "YES", "On"):
        monkeypatch.setenv("MULTI_CLINIC", on)
        assert S.multi_clinic_enabled() is True, on
    for off in ("", "0", "no", "false", "banana"):
        monkeypatch.setenv("MULTI_CLINIC", off)
        assert S.multi_clinic_enabled() is False, off


def test_data_root_follows_data_dir_env(tmp_path, monkeypatch):
    monkeypatch.delenv("DATA_DIR", raising=False)
    assert S.data_root() == S.DEFAULT_DATA_DIR
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert S.data_root() == tmp_path
    assert S.clinic_dir("rao") == tmp_path / "clinics" / "rao"


def test_unsafe_slugs_are_rejected():
    bad = ["", "a", "RAO", "rao\n", "../x", "a/b", "/abs", "-rao", "rao_clinic", "r" * 32, "rao clinic", "räo", None, 7]
    for slug in bad:
        assert S.valid_slug(slug) is False, slug
        with pytest.raises(ValueError):
            S.Scope(slug)
        with pytest.raises(ValueError):
            S.clinic_dir(slug)
    assert S.valid_slug("rao") and S.valid_slug("iyer-2") and S.valid_slug("r" * 31)


def test_use_scope_sets_and_restores_including_nested():
    assert S.current_scope() is None
    outer, inner = S.Scope("rao", 1, "dr.rao", "doctor"), S.Scope("iyer")
    with S.use_scope(outer):
        assert S.require_scope() is outer
        with S.use_scope(inner):
            assert S.require_scope() is inner
            assert inner.username == "system"
        assert S.current_scope() is outer
    assert S.current_scope() is None


def test_require_scope_raises_without_scope():
    with pytest.raises(S.NoScope):
        S.require_scope()
    assert issubclass(S.NoScope, RuntimeError)


def test_scope_survives_to_thread_but_not_a_bare_thread():
    async def go():
        with S.use_scope(S.Scope("rao")):
            via_to_thread = await asyncio.to_thread(S.current_scope)
            box = []
            t = threading.Thread(target=lambda: box.append(S.current_scope()))
            t.start()
            t.join()
            return via_to_thread, box[0]

    via_to_thread, via_bare = asyncio.run(go())
    assert via_to_thread == S.Scope("rao")
    assert via_bare is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_scope.py -q`
Expected: FAIL (collection error: `cannot import name 'scope'`).

- [ ] **Step 3: Write the implementation**

`doctor_dictation/scope.py`:

```python
"""Request scope: which clinic (and user) the current work belongs to.

Stdlib only and imports nothing from ``doctor_dictation``: ``db``, ``directory`` and
``clinics`` all sit on top of it. The scope lives in a ``ContextVar``, so it follows
``asyncio.to_thread`` and anyio worker threads (they copy the context) but NOT a bare
``threading.Thread`` or a ``ThreadPoolExecutor`` (they start empty); anything running
there fails closed with ``NoScope`` instead of guessing a clinic.
"""
from __future__ import annotations

import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

MULTI_CLINIC_ENV = "MULTI_CLINIC"
DATA_DIR_ENV = "DATA_DIR"
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"
SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]{1,30}")  # always used with fullmatch: "$" would accept a trailing newline


class NoScope(RuntimeError):
    """Raised when clinic data is touched with no clinic scope (multi-clinic mode)."""


def valid_slug(slug) -> bool:
    return isinstance(slug, str) and SLUG_RE.fullmatch(slug) is not None


@dataclass(frozen=True)
class Scope:
    clinic_slug: str
    user_id: int | None = None
    username: str = "system"
    role: str = "system"

    def __post_init__(self):
        if not valid_slug(self.clinic_slug):
            raise ValueError(f"invalid clinic slug: {self.clinic_slug!r}")


_scope: ContextVar[Scope | None] = ContextVar("dd_scope", default=None)


def multi_clinic_enabled() -> bool:
    return os.getenv(MULTI_CLINIC_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def data_root() -> Path:
    env = os.getenv(DATA_DIR_ENV, "").strip()
    return Path(env) if env else DEFAULT_DATA_DIR


def clinic_dir(slug: str) -> Path:
    if not valid_slug(slug):
        raise ValueError(f"invalid clinic slug: {slug!r}")
    return data_root() / "clinics" / slug


def current_scope() -> Scope | None:
    return _scope.get()


def require_scope() -> Scope:
    scope = _scope.get()
    if scope is None:
        raise NoScope("no clinic scope: sign in first")
    return scope


@contextmanager
def use_scope(scope: Scope):
    token = _scope.set(scope)
    try:
        yield scope
    finally:
        _scope.reset(token)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_scope.py -q`
Expected: 6 passed.

- [ ] **Step 5: Leave uncommitted** (user rule). No commit.

---

### Task 2: Directory database

**Files:**
- Create: `doctor_dictation/directory/__init__.py`, `doctor_dictation/directory/migrations/001_directory.sql`, `tests/test_directory.py`
- Modify: `pyproject.toml` (the `package-data` line)

**Interfaces:**
- Consumes: `scope.data_root()`, `scope.valid_slug()`; `db.get_conn(path)`, `db.migrate(conn, migrations_dir)`, `db._utcnow()` (existing).
- Produces (in `doctor_dictation.directory`): `DirectoryError(ValueError)`; `DIR_MIGRATIONS: Path`; `directory_path() -> Path` (`data_root()/"directory.db"`); `open_directory() -> sqlite3.Connection` (created and migrated, caller closes); `check_clinic_fields(slug, name, op_prefix="OP") -> None` (raises `DirectoryError`); `create_clinic(conn, slug, name, op_prefix="OP") -> int`; `get_clinic(conn, slug) -> Row | None`; `list_clinics(conn, active_only=False) -> list[Row]` ordered by slug. Rows expose `id, slug, name, status, op_prefix, created_at`.

- [ ] **Step 1: Write the failing tests**

`tests/test_directory.py`:

```python
"""Directory database: clinics, username index, throttling table. Offline."""
import sqlite3
from contextlib import closing

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation import directory as D


def test_open_directory_creates_the_tables_and_is_idempotent(multi):
    with closing(D.open_directory()) as conn:
        names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert dbmod.migrate(conn, D.DIR_MIGRATIONS) == []   # already applied
    assert {"clinics", "login_index", "login_attempts"} <= names
    assert (multi / "directory.db").is_file()
    with closing(D.open_directory()):
        pass                                                  # reopening is fine


def test_directory_holds_no_patient_data_tables(multi):
    with closing(D.open_directory()) as conn:
        names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {n for n in names if not n.startswith("sqlite_")} == {"clinics", "login_index", "login_attempts", "schema_migrations"}


def test_create_and_list_clinics(multi):
    with closing(D.open_directory()) as conn:
        a = D.create_clinic(conn, "rao", "  Rao Clinic ", "RAO")
        D.create_clinic(conn, "iyer", "Iyer Clinic")
        assert isinstance(a, int)
        row = D.get_clinic(conn, "rao")
        assert (row["slug"], row["name"], row["status"], row["op_prefix"]) == ("rao", "Rao Clinic", "active", "RAO")
        assert D.get_clinic(conn, "nope") is None
        assert [r["slug"] for r in D.list_clinics(conn)] == ["iyer", "rao"]
        conn.execute("UPDATE clinics SET status='disabled' WHERE slug='iyer'")
        assert [r["slug"] for r in D.list_clinics(conn, active_only=True)] == ["rao"]
        assert D.get_clinic(conn, "iyer")["op_prefix"] == "OP"


def test_create_clinic_rejects_bad_input_and_duplicates(multi):
    with closing(D.open_directory()) as conn:
        for slug, name, prefix in [("../x", "X", "OP"), ("RAO", "X", "OP"), ("rao", "   ", "OP"),
                                   ("rao", "X", "op"), ("rao", "X", "O"), ("rao", "X", "TOOLONG1")]:
            with pytest.raises(D.DirectoryError):
                D.create_clinic(conn, slug, name, prefix)
        D.create_clinic(conn, "rao", "Rao Clinic")
        with pytest.raises(D.DirectoryError, match="already exists"):
            D.create_clinic(conn, "rao", "Other")
        assert len(D.list_clinics(conn)) == 1


def test_usernames_are_unique_system_wide_ignoring_case(multi):
    with closing(D.open_directory()) as conn:
        D.create_clinic(conn, "rao", "Rao Clinic")
        conn.execute("INSERT INTO login_index(username, clinic_slug, user_id) VALUES ('Dr.Rao', 'rao', 1)")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO login_index(username, clinic_slug, user_id) VALUES ('dr.rao', 'rao', 2)")
        with pytest.raises(sqlite3.IntegrityError):   # foreign key: the clinic must exist
            conn.execute("INSERT INTO login_index(username, clinic_slug, user_id) VALUES ('x.y', 'ghost', 1)")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_directory.py -q`
Expected: FAIL (`cannot import name 'directory'`).

- [ ] **Step 3: Write the migration, the module and the packaging line**

`doctor_dictation/directory/migrations/001_directory.sql`:

```sql
-- Directory database: which clinics exist, who may log in where, login throttling.
-- It never stores patient data, passwords or profile content.
CREATE TABLE IF NOT EXISTS clinics (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    slug       TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    op_prefix  TEXT NOT NULL DEFAULT 'OP',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS login_index (
    username    TEXT PRIMARY KEY COLLATE NOCASE,
    clinic_slug TEXT NOT NULL REFERENCES clinics(slug),
    user_id     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS login_attempts (
    username     TEXT NOT NULL COLLATE NOCASE,
    ip           TEXT NOT NULL,
    failed_count INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (username, ip)
);
```

`doctor_dictation/directory/__init__.py`:

```python
"""Directory database (``<DATA_DIR>/directory.db``): the list of clinics and, from M2, the
username index and login throttling. No patient data lives here.

Reuses the numbered-SQL migration runner in ``db`` with this package's own migrations folder.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from doctor_dictation import db as dbmod
from doctor_dictation.scope import data_root, valid_slug

DIR_MIGRATIONS = Path(__file__).resolve().parent / "migrations"
PREFIX_RE = re.compile(r"[A-Z0-9]{2,6}")


class DirectoryError(ValueError):
    """A clinic registration problem the operator can fix (bad field, duplicate)."""


def directory_path() -> Path:
    return data_root() / "directory.db"


def open_directory() -> sqlite3.Connection:
    """Open (creating and migrating on first use) the directory database. Caller closes."""
    conn = dbmod.get_conn(directory_path())
    dbmod.migrate(conn, DIR_MIGRATIONS)
    return conn


def check_clinic_fields(slug, name, op_prefix="OP") -> None:
    if not valid_slug(slug):
        raise DirectoryError("slug must be 2-31 characters: lowercase letters, digits and hyphens, starting with a letter or digit")
    if not isinstance(name, str) or not name.strip():
        raise DirectoryError("clinic name is required")
    if not isinstance(op_prefix, str) or PREFIX_RE.fullmatch(op_prefix) is None:
        raise DirectoryError("OP prefix must be 2-6 uppercase letters or digits")


def create_clinic(conn, slug, name, op_prefix="OP") -> int:
    check_clinic_fields(slug, name, op_prefix)
    try:
        cur = conn.execute(
            "INSERT INTO clinics(slug, name, op_prefix, created_at) VALUES (?, ?, ?, ?)",
            (slug, name.strip(), op_prefix, dbmod._utcnow()),
        )
    except sqlite3.IntegrityError:
        raise DirectoryError(f"clinic '{slug}' already exists") from None
    conn.commit()
    return cur.lastrowid


def get_clinic(conn, slug):
    return conn.execute("SELECT * FROM clinics WHERE slug = ?", (slug,)).fetchone()


def list_clinics(conn, active_only=False) -> list:
    sql = "SELECT * FROM clinics" + (" WHERE status = 'active'" if active_only else "") + " ORDER BY slug"
    return conn.execute(sql).fetchall()
```

In `pyproject.toml`, change the `package-data` line to:

```toml
doctor_dictation = ["core/lexicon/*.json", "db/migrations/*.sql", "directory/migrations/*.sql", "requirements*.txt"]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_directory.py tests/test_package_install.py -q`
Expected: 5 passed, plus the package-install test's result unchanged.

- [ ] **Step 5: Leave uncommitted.**

---

### Task 3: Scope-aware paths and fail-closed connections

**Files:**
- Modify: `doctor_dictation/db/__init__.py` (the import block and `db_path`, about lines 14 to 40)
- Test: `tests/test_clinic_paths.py`

**Interfaces:**
- Consumes: `scope.multi_clinic_enabled()`, `scope.require_scope()`, `scope.clinic_dir()`.
- Produces: unchanged signatures `db.db_path() -> Path`, `db.pdf_dir() -> Path`, `db.get_conn(path=None)`, `templates.service.templates_dir() -> Path`. New behaviour: in multi-clinic mode all four resolve inside `clinic_dir(<scope slug>)` and raise `NoScope` without a scope. `pdf_dir()` and `templates_dir()` already derive from `db_path().parent`, so they need no edit.

- [ ] **Step 1: Write the failing tests**

`tests/test_clinic_paths.py`:

```python
"""Per-clinic paths, fail-closed connections, and thread behaviour. Offline."""
import threading

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation import scope as S
from doctor_dictation.pdf import renderer as R
from doctor_dictation.templates import service


def test_single_mode_paths_are_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("MULTI_CLINIC", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "x" / "app.db"))
    assert dbmod.db_path() == tmp_path / "x" / "app.db"
    assert dbmod.pdf_dir() == tmp_path / "x" / "pdfs"
    assert service.templates_dir() == tmp_path / "x" / "templates"
    monkeypatch.delenv("DB_PATH")
    assert dbmod.db_path() == dbmod.DEFAULT_DB_PATH


def test_multi_mode_paths_follow_the_scope(multi):
    for slug in ("rao", "iyer"):
        with S.use_scope(S.Scope(slug)):
            root = multi / "clinics" / slug
            assert dbmod.db_path() == root / "app.db"
            assert dbmod.pdf_dir() == root / "pdfs"
            assert service.templates_dir() == root / "templates"


def test_multi_mode_fails_closed_without_scope(multi, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(multi / "stray.db"))      # must never be used as a fallback
    for call in (dbmod.db_path, dbmod.pdf_dir, service.templates_dir, dbmod.get_conn):
        with pytest.raises(S.NoScope):
            call()
    assert not (multi / "stray.db").exists()
    assert not (multi / "clinics").exists()
    with dbmod.get_conn(multi / "explicit.db") as conn:        # an explicit path is still allowed (tests, tools)
        conn.execute("SELECT 1")


def test_get_conn_in_a_bare_thread_fails_closed(multi):
    seen = []

    def work():
        try:
            dbmod.get_conn()
        except Exception as exc:  # noqa: BLE001 - recording the type is the point
            seen.append(type(exc))

    with S.use_scope(S.Scope("rao")):
        t = threading.Thread(target=work)
        t.start()
        t.join()
    assert seen == [S.NoScope]
    assert not (multi / "clinics").exists()


def test_pdf_worker_thread_has_no_scope(multi):
    seen = []

    def launcher():                       # runs on the pdf-worker thread
        seen.append(S.current_scope())
        raise RuntimeError("stop here")

    renderer = R.ChromiumPoolRenderer(launcher)
    try:
        with S.use_scope(S.Scope("rao")):
            with pytest.raises(RuntimeError):
                renderer.render("<p>x</p>", multi / "x.pdf")
    finally:
        renderer.close()
    assert seen == [None]                 # the worker renders HTML and must never open a database


def test_two_clinics_never_see_each_other(multi):
    for slug, patient in (("rao", "Asha"), ("iyer", "Bharat")):
        with S.use_scope(S.Scope(slug)):
            dbmod.init_db()
            conn = dbmod.get_conn()
            dbmod.create_patient(conn, patient, "30 / F")
            conn.close()
            dbmod.pdf_dir().mkdir(parents=True, exist_ok=True)
            (dbmod.pdf_dir() / "p.pdf").write_bytes(slug.encode())
    for slug, mine, theirs in (("rao", "Asha", "Bharat"), ("iyer", "Bharat", "Asha")):
        with S.use_scope(S.Scope(slug)):
            conn = dbmod.get_conn()
            names = [r["name"] for r in conn.execute("SELECT name FROM patients")]
            conn.close()
            assert names == [mine] and theirs not in names
            assert (dbmod.pdf_dir() / "p.pdf").read_bytes() == slug.encode()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_clinic_paths.py -q`
Expected: the multi-mode tests FAIL (`db_path()` returns `DB_PATH`/default, no `NoScope`); `test_single_mode_paths_are_unchanged` passes.

- [ ] **Step 3: Write the implementation**

In `doctor_dictation/db/__init__.py`, add the import after `from pathlib import Path`:

```python
from doctor_dictation.scope import clinic_dir, multi_clinic_enabled, require_scope
```

Replace `db_path` with:

```python
def db_path() -> Path:
    """Resolve the DB path at call time (monkeypatch-friendly).

    Multi-clinic mode (``MULTI_CLINIC=1``): the scoped clinic's ``app.db``; ``NoScope`` when
    there is no scope. ``DB_PATH`` is ignored there and nothing falls back to a default.
    """
    if multi_clinic_enabled():
        return clinic_dir(require_scope().clinic_slug) / "app.db"
    env = os.getenv(DB_PATH_ENV)
    return Path(env) if env else DEFAULT_DB_PATH
```

Nothing else changes: `pdf_dir()`, `get_conn()` and `templates.service.templates_dir()` already call `db_path()`. Check the file stays under 500 lines: `wc -l doctor_dictation/db/__init__.py` (expect about 483).

- [ ] **Step 4: Run the tests, then the whole suite**

Run: `.venv/bin/python -m pytest tests/test_clinic_paths.py -q`
Expected: 6 passed.
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 17` passed (443 + 6 + 5 + 6), 1 skipped; no existing test changed.

- [ ] **Step 5: Leave uncommitted.**

---

### Task 4: Clinic lifecycle, multi-clinic startup, and the no-scope answer

**Files:**
- Create: `doctor_dictation/clinics.py`, `tests/test_clinics.py`
- Modify: `doctor_dictation/api/app.py` (imports, `lifespan`, `create_app`), `.env.example`

**Interfaces:**
- Consumes: Task 1 `scope.*`; Task 2 `directory.*`; `db.init_db(path)`.
- Produces (in `doctor_dictation.clinics`): `migrate_clinic(slug) -> list[str]` (applies pending clinic migrations to `clinic_dir(slug)/"app.db"`, independent of the flag; returns versions applied); `provision_clinic(slug, name, op_prefix="OP") -> int` (validates, refuses duplicates before touching disk, creates the folder and database, registers the clinic; returns the directory id); `migrate_all() -> tuple[dict[str, list[str]], dict[str, str]]` (done, failed; includes disabled clinics; never raises for one clinic's failure); `for_each_clinic()` generator yielding each **active** clinic's slug with `Scope(slug)` set for the loop body.
- Produces (in `api/app.py`): `lifespan` migrates and purges per clinic in multi mode; a `NoScope` handler answering `401 {"error": "sign in required"}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_clinics.py`:

```python
"""Clinic lifecycle, startup in multi-clinic mode and the no-scope answer. Offline."""
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import clinics
from doctor_dictation import db as dbmod
from doctor_dictation import directory as D
from doctor_dictation import scope as S


def _versions(path):
    with closing(dbmod.get_conn(path)) as conn:
        return [r["version"] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]


def test_provision_clinic_creates_folder_database_and_directory_row(multi):
    clinics.provision_clinic("rao", "Rao Clinic", "RAO")
    assert (multi / "clinics" / "rao" / "app.db").is_file()
    assert _versions(multi / "clinics" / "rao" / "app.db")[0] == "001_init.sql"
    with closing(D.open_directory()) as d:
        row = D.get_clinic(d, "rao")
    assert (row["name"], row["op_prefix"], row["status"]) == ("Rao Clinic", "RAO", "active")


def test_provision_rejects_bad_input_and_duplicates_without_touching_disk(multi):
    for slug, name, prefix in [("../x", "X", "OP"), ("RAO", "X", "OP"), ("rao\n", "X", "OP"), ("rao", "", "OP"), ("rao", "X", "op")]:
        with pytest.raises(D.DirectoryError):
            clinics.provision_clinic(slug, name, prefix)
    assert not (multi / "clinics").exists()
    clinics.provision_clinic("rao", "Rao Clinic")
    marker = multi / "clinics" / "rao" / "marker.txt"
    marker.write_text("keep")
    with pytest.raises(D.DirectoryError, match="already exists"):
        clinics.provision_clinic("rao", "Again")
    assert marker.read_text() == "keep"


def test_for_each_clinic_sets_the_scope_and_skips_disabled_clinics(multi):
    for slug in ("rao", "iyer", "nair"):
        clinics.provision_clinic(slug, slug.title())
    with closing(D.open_directory()) as d:
        d.execute("UPDATE clinics SET status='disabled' WHERE slug='nair'")
        d.commit()
    seen = []
    for slug in clinics.for_each_clinic():
        seen.append((slug, S.require_scope().clinic_slug, dbmod.db_path().parent.name))
    assert seen == [("iyer", "iyer", "iyer"), ("rao", "rao", "rao")]
    assert S.current_scope() is None


def test_migrate_all_continues_after_a_failing_clinic(multi):
    for slug in ("rao", "iyer"):
        clinics.provision_clinic(slug, slug.title())
    (multi / "clinics" / "iyer" / "app.db").write_bytes(b"this is not a database" * 50)
    done, failed = clinics.migrate_all()
    assert done == {"rao": []}                       # already migrated, nothing new to apply
    assert list(failed) == ["iyer"] and failed["iyer"]


def test_app_starts_in_multi_mode_migrates_each_clinic_and_serves_health(multi):
    from doctor_dictation.api.app import create_app

    clinics.provision_clinic("rao", "Rao Clinic")
    with TestClient(create_app()) as client:
        assert client.get("/api/health").status_code == 200
    assert (multi / "directory.db").is_file()
    assert _versions(multi / "clinics" / "rao" / "app.db")
    assert not (multi / "app.db").exists()           # no default database was created


def test_route_without_scope_answers_401_and_creates_nothing(multi):
    from doctor_dictation.api.app import create_app

    with TestClient(create_app()) as client:
        res = client.get("/api/v1/profile")
    assert res.status_code == 401
    assert res.json() == {"error": "sign in required"}
    assert list(multi.rglob("app.db")) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_clinics.py -q`
Expected: FAIL (`cannot import name 'clinics'`).

- [ ] **Step 3: Write `clinics.py`**

`doctor_dictation/clinics.py`:

```python
"""Clinic lifecycle: provision, migrate, iterate. Used by the operator command and app startup;
request code never imports this. ``migrate_clinic`` takes an explicit path so it works whether or
not ``MULTI_CLINIC`` is on (the operator runs it from a shell)."""
from __future__ import annotations

from contextlib import closing

from doctor_dictation import db as dbmod
from doctor_dictation.directory import DirectoryError, check_clinic_fields, create_clinic, get_clinic, list_clinics, open_directory
from doctor_dictation.scope import Scope, clinic_dir, use_scope


def migrate_clinic(slug: str) -> list[str]:
    """Create the clinic's folder and database if needed and apply pending migrations."""
    return dbmod.init_db(clinic_dir(slug) / "app.db")


def provision_clinic(slug: str, name: str, op_prefix: str = "OP") -> int:
    """Validate, refuse duplicates before touching the disk, build the clinic, then register it.

    A crash between the database and the registration leaves an unregistered folder; running the
    same command again succeeds because the migration is idempotent.
    """
    check_clinic_fields(slug, name, op_prefix)
    with closing(open_directory()) as d:
        if get_clinic(d, slug) is not None:
            raise DirectoryError(f"clinic '{slug}' already exists")
        migrate_clinic(slug)
        return create_clinic(d, slug, name, op_prefix)


def migrate_all() -> tuple[dict[str, list[str]], dict[str, str]]:
    """Migrate every registered clinic (disabled ones too, so re-enabling works).

    Returns ``(done, failed)``: slug to versions applied, slug to error text. One clinic's
    failure never stops the others.
    """
    with closing(open_directory()) as d:
        slugs = [r["slug"] for r in list_clinics(d)]
    done, failed = {}, {}
    for slug in slugs:
        try:
            done[slug] = migrate_clinic(slug)
        except Exception as exc:  # noqa: BLE001 - report and carry on with the other clinics
            failed[slug] = f"{type(exc).__name__}: {exc}"
    return done, failed


def for_each_clinic():
    """Yield each active clinic's slug with its ``Scope`` set for the body of the loop.

    The only legitimate way to run clinic work outside a request (startup purge, maintenance).
    Meaningful in multi-clinic mode; with the flag off ``db_path()`` ignores the scope.
    """
    with closing(open_directory()) as d:
        slugs = [r["slug"] for r in list_clinics(d, active_only=True)]
    for slug in slugs:
        with use_scope(Scope(slug)):
            yield slug
```

- [ ] **Step 4: Wire startup and the 401 into `api/app.py`**

Add to the imports in `doctor_dictation/api/app.py`:

```python
import sys

from fastapi.responses import JSONResponse

from doctor_dictation import clinics
from doctor_dictation.scope import NoScope, multi_clinic_enabled
```

Replace `lifespan` with:

```python
def _startup() -> None:
    """Single mode: migrate the one database. Multi-clinic: migrate every clinic (one bad clinic
    is reported, not fatal), then purge each clinic's expired template drafts."""
    if not multi_clinic_enabled():
        dbmod.init_db()
        templates_api.purge_on_startup()
        return
    _done, failed = clinics.migrate_all()
    for slug, why in failed.items():
        print(f"warning: clinic {slug} was not migrated: {why}", file=sys.stderr)
    for _slug in clinics.for_each_clinic():
        templates_api.purge_on_startup()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _startup()
    yield
    close_renderer()   # nothing starts at startup; Chromium launches on the first Save
```

In `create_app`, after `app = FastAPI(...)`, add:

```python
    # Multi-clinic mode with no scope (before login exists, or a bypassed middleware): never a 500 and never a default database.
    @app.exception_handler(NoScope)
    async def _no_scope(_request, _exc):
        return JSONResponse(status_code=401, content={"error": "sign in required"})
```

Append to `.env.example`:

```
# --- Multi-clinic (off by default) ---
# MULTI_CLINIC=1 gives each clinic its own folder under DATA_DIR (directory.db + clinics/<slug>/).
# DB_PATH is ignored in that mode. Create clinics with: python -m doctor_dictation.admin create-clinic --slug rao --name "Rao Clinic"
MULTI_CLINIC=0
# DATA_DIR=/var/lib/doctor-dictation
```

- [ ] **Step 5: Run the tests, then the whole suite**

Run: `.venv/bin/python -m pytest tests/test_clinics.py -q`
Expected: 6 passed.
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 23` passed, 1 skipped. `tests/test_api_app.py` (route table, no module-level settings) must still pass unchanged.

- [ ] **Step 6: Leave uncommitted.**

---

### Task 5: Operator command line

**Files:**
- Create: `doctor_dictation/admin.py`, `tests/test_admin.py`

**Interfaces:**
- Consumes: Task 4 `clinics.*`; Task 2 `directory.*`; `scope.clinic_dir`; `db.DB_PATH_ENV`, `db.DEFAULT_DB_PATH`.
- Produces: `python -m doctor_dictation.admin <command>` and `admin.main(argv=None) -> int` (exit code 0 ok, 1 on an operator-fixable error or any failed migration). Commands: `create-clinic --slug S --name N [--op-prefix OP]`, `list-clinics`, `migrate-all`, `adopt-existing --slug S [--name N]` (clinic name defaults to the saved profile's `clinic_name`, else the slug).

- [ ] **Step 1: Write the failing tests**

`tests/test_admin.py`:

```python
"""Operator command: create, list, migrate, adopt. Offline; calls main() directly."""
from contextlib import closing

from doctor_dictation import admin
from doctor_dictation import clinics
from doctor_dictation import db as dbmod
from doctor_dictation import directory as D
from doctor_dictation import scope as S


def test_create_and_list_clinics(multi, capsys):
    assert admin.main(["create-clinic", "--slug", "rao", "--name", "Rao Clinic", "--op-prefix", "RAO"]) == 0
    assert admin.main(["create-clinic", "--slug", "iyer", "--name", "Iyer Clinic"]) == 0
    assert (multi / "clinics" / "rao" / "app.db").is_file()
    capsys.readouterr()
    assert admin.main(["list-clinics"]) == 0
    out = capsys.readouterr().out
    assert "rao" in out and "Rao Clinic" in out and "RAO" in out and "iyer" in out and "active" in out


def test_create_clinic_reports_bad_input_and_duplicates_on_stderr(multi, capsys):
    assert admin.main(["create-clinic", "--slug", "../x", "--name", "X"]) == 1
    assert "error:" in capsys.readouterr().err
    assert admin.main(["create-clinic", "--slug", "rao", "--name", "Rao"]) == 0
    assert admin.main(["create-clinic", "--slug", "rao", "--name", "Again"]) == 1
    assert "already exists" in capsys.readouterr().err
    assert not (multi / "x").exists()                      # the "../x" slug never became a path


def test_migrate_all_exits_nonzero_when_a_clinic_fails(multi, capsys):
    clinics.provision_clinic("rao", "Rao Clinic")
    clinics.provision_clinic("iyer", "Iyer Clinic")
    assert admin.main(["migrate-all"]) == 0
    (multi / "clinics" / "iyer" / "app.db").write_bytes(b"garbage" * 100)
    capsys.readouterr()
    assert admin.main(["migrate-all"]) == 1
    out = capsys.readouterr()
    assert "rao" in out.out and "iyer" in out.err


def _old_install(tmp_path, monkeypatch):
    """A single-database install: app.db with a patient and profile, plus pdfs/ and templates/."""
    old = tmp_path / "old"
    monkeypatch.setenv("DB_PATH", str(old / "app.db"))
    dbmod.init_db()
    conn = dbmod.get_conn()
    dbmod.create_patient(conn, "Asha", "30 / F")
    dbmod.save_profile(conn, clinic_name="Rao Clinic", doctor_name="Dr A. Rao")
    (old / "pdfs").mkdir()
    (old / "pdfs" / "encounter_1.pdf").write_bytes(b"%PDF-old")
    (old / "templates").mkdir()
    (old / "templates" / "1_logo.jpg").write_bytes(b"jpg")
    return old, conn


def test_adopt_existing_moves_everything_even_with_the_old_db_open(tmp_path, monkeypatch):
    old, live = _old_install(tmp_path, monkeypatch)        # `live` stays open: its writes may still sit in the WAL
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    try:
        assert admin.main(["adopt-existing", "--slug", "rao"]) == 0
    finally:
        live.close()
    target = tmp_path / "data" / "clinics" / "rao"
    assert not (old / "app.db").exists() and not (old / "pdfs").exists() and not (old / "templates").exists()
    assert (target / "pdfs" / "encounter_1.pdf").read_bytes() == b"%PDF-old"
    assert (target / "templates" / "1_logo.jpg").exists()
    monkeypatch.setenv("MULTI_CLINIC", "1")
    monkeypatch.delenv("DB_PATH")
    with S.use_scope(S.Scope("rao")):
        with closing(dbmod.get_conn()) as conn:
            assert [r["name"] for r in conn.execute("SELECT name FROM patients")] == ["Asha"]
    with closing(D.open_directory()) as d:
        assert D.get_clinic(d, "rao")["name"] == "Rao Clinic"      # taken from the saved profile


def test_adopt_existing_refuses_a_missing_source_a_taken_slug_and_an_existing_folder(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "none" / "app.db"))
    assert admin.main(["adopt-existing", "--slug", "rao"]) == 1
    assert "no database" in capsys.readouterr().err
    old, live = _old_install(tmp_path, monkeypatch)
    live.close()
    clinics.provision_clinic("rao", "Taken")
    assert admin.main(["adopt-existing", "--slug", "rao"]) == 1
    assert "already exists" in capsys.readouterr().err
    (tmp_path / "data" / "clinics" / "nair").mkdir(parents=True)
    assert admin.main(["adopt-existing", "--slug", "nair"]) == 1
    assert (old / "app.db").exists()                       # nothing was moved by any refusal
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_admin.py -q`
Expected: FAIL (`cannot import name 'admin'`).

- [ ] **Step 3: Write the implementation**

`doctor_dictation/admin.py`:

```python
"""Operator command line: ``python -m doctor_dictation.admin <command>``. Run on the host, never over HTTP.

M1 commands: create-clinic, list-clinics, migrate-all, adopt-existing. Users and passwords arrive
with M2 (``--first-user``); nothing here creates a user.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from doctor_dictation import clinics
from doctor_dictation import db as dbmod
from doctor_dictation.directory import DirectoryError, check_clinic_fields, create_clinic, get_clinic, list_clinics, open_directory
from doctor_dictation.scope import clinic_dir


def _create(args) -> int:
    clinics.provision_clinic(args.slug, args.name, args.op_prefix)
    print(f"created clinic '{args.slug}' ({args.name}) at {clinic_dir(args.slug)}")
    print("no users yet: user creation arrives with the login plan (M2)")
    return 0


def _list(_args) -> int:
    with closing(open_directory()) as d:
        rows = list_clinics(d)
    if not rows:
        print("no clinics yet")
    for r in rows:
        print(f"{r['slug']:<20} {r['name']:<30} {r['status']:<9} {r['op_prefix']}")
    return 0


def _migrate_all(_args) -> int:
    done, failed = clinics.migrate_all()
    for slug, applied in done.items():
        print(f"{slug}: {', '.join(applied) if applied else 'up to date'}")
    for slug, why in failed.items():
        print(f"{slug}: FAILED {why}", file=sys.stderr)
    return 1 if failed else 0


def _prepare_source(src_db: Path) -> str:
    """Flush the write-ahead log into app.db (refusing if the database is busy) and return the saved clinic name."""
    conn = sqlite3.connect(str(src_db))
    try:
        busy = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]
        if busy:
            raise DirectoryError("the database is in use: stop the app, then run this again")
        try:
            row = conn.execute("SELECT clinic_name FROM clinic_profile WHERE id = 1").fetchone()
        except sqlite3.Error:
            row = None
        return (row[0] if row else "") or ""
    finally:
        conn.close()


def _adopt(args) -> int:
    src_db = Path(os.getenv(dbmod.DB_PATH_ENV) or dbmod.DEFAULT_DB_PATH)
    src_root = src_db.parent
    if not src_db.is_file():
        raise DirectoryError(f"no database at {src_db}")
    check_clinic_fields(args.slug, args.name or args.slug)
    target = clinic_dir(args.slug)
    with closing(open_directory()) as d:
        if get_clinic(d, args.slug) is not None:
            raise DirectoryError(f"clinic '{args.slug}' already exists")
    if target.exists():
        raise DirectoryError(f"{target} already exists")
    saved_name = _prepare_source(src_db)          # also flushes the WAL; refuses when busy
    name = args.name or saved_name or args.slug
    target.mkdir(parents=True)
    shutil.move(str(src_db), str(target / "app.db"))
    for sub in ("pdfs", "templates"):
        if (src_root / sub).exists():
            shutil.move(str(src_root / sub), str(target / sub))
    clinics.migrate_clinic(args.slug)
    with closing(open_directory()) as d:
        create_clinic(d, args.slug, name)
    print(f"adopted {src_db} as clinic '{args.slug}' ({name}) at {target}")
    return 0


COMMANDS = {"create-clinic": _create, "list-clinics": _list, "migrate-all": _migrate_all, "adopt-existing": _adopt}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m doctor_dictation.admin")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-clinic", help="create a clinic folder, database and directory entry")
    c.add_argument("--slug", required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--op-prefix", default="OP")
    sub.add_parser("list-clinics", help="list registered clinics")
    sub.add_parser("migrate-all", help="apply pending migrations to every clinic")
    a = sub.add_parser("adopt-existing", help="move today's single database, pdfs/ and templates/ into a clinic (stop the app first)")
    a.add_argument("--slug", required=True)
    a.add_argument("--name", help="clinic name (default: the saved profile's clinic name, else the slug)")
    args = parser.parse_args(argv)
    try:
        return COMMANDS[args.cmd](args)
    except ValueError as exc:      # DirectoryError and an invalid slug from clinic_dir
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests, then the whole suite and the size check**

Run: `.venv/bin/python -m pytest tests/test_admin.py -q`
Expected: 5 passed.
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 28` passed, 1 skipped (that is 471 passed if `N` is 443).
Run: `.venv/bin/python -m pytest tests/test_file_sizes.py -q`
Expected: 2 passed.

- [ ] **Step 5: Smoke the real command on a throwaway folder**

Run:

```bash
D=$(mktemp -d) && DATA_DIR=$D .venv/bin/python -m doctor_dictation.admin create-clinic --slug rao --name "Rao Clinic" --op-prefix RAO \
 && DATA_DIR=$D .venv/bin/python -m doctor_dictation.admin list-clinics && DATA_DIR=$D .venv/bin/python -m doctor_dictation.admin migrate-all && ls $D $D/clinics/rao
```

Expected: a "created clinic" line, one table row for `rao`, `rao: up to date`, then `directory.db` and `clinics` at the top and `app.db` inside `clinics/rao`.

- [ ] **Step 6: Leave uncommitted and list the changed files.** Run `git status --short`; expected new files: `doctor_dictation/scope.py`, `doctor_dictation/clinics.py`, `doctor_dictation/admin.py`, `doctor_dictation/directory/` (init and migration), `tests/conftest.py`, `tests/test_scope.py`, `tests/test_directory.py`, `tests/test_clinic_paths.py`, `tests/test_clinics.py`, `tests/test_admin.py`; modified: `doctor_dictation/db/__init__.py`, `doctor_dictation/api/app.py`, `pyproject.toml`, `.env.example`.

---

## Self-review (against the spec)

- **Spec 5.1 directory database:** Task 2 (all three tables; no patient data pinned by a test).
- **Spec 5.2 clinic databases:** Task 4 `provision_clinic` / `migrate_clinic` (the existing migrations run per clinic file).
- **Spec 5.3 request scope, fail closed, threads, `for_each_clinic`, `MULTI_CLINIC`:** Tasks 1, 3, 4 (to_thread keeps scope, bare thread and PDF worker fail closed, flag defaults off).
- **Spec 11 operator commands:** Task 5 covers `create-clinic`, `list-clinics`, `migrate-all`, `adopt-existing` (without users, see the differences section); `reset-password` and `seed-demo` belong to M2 and M6.
- **Spec 12 rollout:** existing tests keep running in single-database mode (Task 3 full-suite run); the `package-data` line ships the directory migration.
- **Placeholder scan:** none; every step shows its code or command.
- **Type consistency:** `Scope`, `clinic_dir`, `use_scope`, `open_directory`, `create_clinic`, `migrate_clinic`, `provision_clinic`, `migrate_all`, `for_each_clinic`, `check_clinic_fields` have the same names and signatures in every task that uses them.
- **Test count:** Task 1: 6, Task 2: 5, Task 3: 6, Task 4: 6, Task 5: 5 = 28.
