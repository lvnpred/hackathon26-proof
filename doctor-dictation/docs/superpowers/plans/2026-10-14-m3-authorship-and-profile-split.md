# M3: Authorship, 403 rules, view-only UI, Profile split, Today scopes, per-doctor hints

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inside one clinic, every prescription has an author. The first save records the signed-in doctor; only the author may re-save or correct it (a colleague gets a 403 with one fixed message); any doctor of the clinic may view and reprint it, and the print carries the **author's** doctor details and the **clinic's** clinic details. Today lists "My prescriptions" or "Whole clinic", STT hints come from the signed-in doctor's own prescriptions, and the Profile splits into shared Clinic details and per-user My details. The browser opens a colleague's prescription read-only.

**Architecture:** Two small SQL modules (`db/details.py` for the profile split, `db/authorship.py` for author lookups, the print profile and the Today query) and one HTTP helper (`api/authorship.py`) that is the only place routes ask `policy.can` about a document and build the 403. Routes take `request: Request` and read `request.state.identity` (set by the M2 session middleware); when it is absent (single-database mode) every route behaves and answers exactly as today. Migration `006` copies the saved doctor fields onto a clinic's first user. The frontend gets one new file `frontend/authorship.js` and seven one-line hooks in `app.js`.

**Tech Stack:** FastAPI/Starlette, stdlib `sqlite3`, vanilla JS, pytest + `TestClient`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-14-multi-clinic-multi-doctor-design.md` sections 7.1 (authorship, 403, view-only), 7.2 (Today scopes), 7.3 (hints), 7.4 (audit actor), 8.1 (Profile split, print resolution), 6.3 (`can()` wiring) and 12 (clinic migration `006`, numbered per the cross-plan contract). Builds on M1, M2a, M2b (committed in `ae5864c`) and is compatible with M2c (in progress; it only appends `sid` to `sessions.Identity`).

**Plan 4 of 7 (M3).** Before the first task run `.venv/bin/python -m pytest tests/ -q` and note the count `N` (597 at `ae5864c`, plus whatever M2c added; 609 passed, 1 skipped on 2026-10-14 with M2c in the working tree). **This plan adds 35 tests** (9 + 10 + 5 + 5 + 6) and edits one existing assertion (the migration list in `tests/test_db.py`), so after it the suite is `N + 35` passed, 1 skipped.

## Deliberate differences from the spec

- **Single-database mode answers in the old shape.** Nobody signs in there, so there is no author: `GET /api/v1/encounters/today` ignores `scope` and returns the five old keys, `GET /api/v1/documents/{id}` adds no `author`/`can_edit`, `GET/PUT /api/v1/profile` keep the one shared row. This keeps `tests/test_today.py`, `tests/test_profile.py` and `tests/test_document_pdf.py` passing unchanged.
- **Migration `006` is a data copy, not the spec's "006_templates_scope".** The cross-plan contract gives `006` to M3 and shifts the spec's `006`/`007` to M4's `007`/`008`. The spec says migration `005` copies the doctor fields; `005` (M2a) only adds columns, and `admin adopt-existing --first-user` already copies them for a newly adopted clinic (`doctor_dictation/admin.py:118-127`, `171-172`). `006` covers clinics whose users existed before M3: it copies `clinic_profile`'s doctor fields onto the clinic's **first** user when that user has none. `clinic_profile` keeps its doctor columns (single mode and pre-M3 prescriptions still print from them).
- **Correct is checked only when the browser names the document.** `POST /api/v1/correct` is stateless (it merges a form the caller already holds and stores nothing). It gains an optional `document_id`; when present, a non-author gets the 403. The binding check is on re-save (`POST /api/v1/documents` with `document_id`). `POST /api/format` names no document (it starts a new draft, and the browser clears `documentId` for a fresh dictation, `frontend/app.js:502`), so it has no check.
- **A pre-M3 prescription (no author) stays author-less on re-save.** `encounters.doctor_id` stays NULL and `documents.finalized_by` records the saver, so it remains editable by anyone in the clinic (the M2a ruling, `doctor_dictation/policy.py:20-21`) and keeps printing the shared profile's doctor fields. It shows under "Whole clinic", not under anyone's "My prescriptions". (Open question 1 below offers the alternative.)
- **The 403 is checked before the verify gate on re-save,** so a colleague is told "belongs to Dr. Rao" rather than asked to confirm medicines first.

## Global Constraints

- Keep every source file under 500 lines (`tests/test_file_sizes.py`). `doctor_dictation/db/__init__.py` is 485 lines and grows by exactly 2 (to 487); all other new SQL goes in the new `db/details.py` and `db/authorship.py`. `doctor_dictation/api/persistence.py` grows from 374 to about 411. `frontend/app.js` is already 1246 lines (frontend files are not size-tested): it gets only seven one-line hooks; new browser logic lives in `frontend/authorship.js`.
- Never run `git commit`, `git add` or `git push` (user rule). Every task ends with "Leave uncommitted".
- The 403 body is exactly `{"error": "This prescription belongs to <author name>. You can view and reprint it."}` where `<author name>` is the author's doctor name, else display name, else username (`db/authorship.author_label`).
- Every route that loads, reprints, re-saves or corrects a saved document calls `policy.can` (through `api/authorship.check` / `check_document`) with `document.view`, `document.reprint` or `document.edit`. No route re-implements the ownership rule.
- Printing resolves doctor fields from the **author** (`encounters.doctor_id` -> `users`) and clinic fields from `clinic_profile`, never from the viewer (`db/authorship.print_profile`).
- Tests are offline and never touch `doctor_dictation/data/`; multi-clinic tests use the `multi` fixture (through `tests/authorship_fixtures.py`). The PDF renderer is always faked in route tests.
- File ownership (cross-plan contract): this plan touches `api/templates.py` only at `_actor` (`doctor_dictation/api/templates.py:49-50`, carry-over a). M4 owns the rest of that file, `templates/service.py` and `pdf/`.

## Review Focus

1. **A colleague's re-save writes and renders nothing.** The 403 must come before the verify gate, the PDF render and any UPDATE, with the exact body. Task 2 `test_colleague_resave_is_403_with_the_exact_message_and_changes_nothing`.
2. **Every document route really calls `can()`** (view, reprint, re-save, correct), so later RBAC rules need no route changes. Task 2 `test_every_document_route_asks_policy_can`.
3. **A reprint never uses the viewer's details.** Mehta reprinting Rao's prescription prints Rao's doctor fields and the clinic's fields. Task 2 `test_colleague_reprint_prints_the_authors_details_not_the_viewers`; Task 1 `test_print_profile_takes_doctor_fields_from_the_author_and_clinic_fields_from_the_clinic`.
4. **Pre-M3 prescriptions keep working:** editable by anyone, still printing the shared profile, still author-less after a re-save. Task 2 `test_legacy_document_prints_the_saved_profile_and_anyone_may_open_it_for_editing` and `test_author_resave_keeps_the_author_and_a_legacy_resave_records_the_saver`.
5. **Hints never include a colleague's habits.** Task 3 `test_hints_come_from_the_signed_in_doctors_own_prescriptions`.
6. **Profile PUT by one doctor never changes another doctor's details,** and migration `006` only fills the first user, never overwriting. Task 4 `test_put_shares_the_clinic_details_and_keeps_my_details_mine`; Task 1 `test_migration_006_copies_the_saved_doctor_fields_to_the_first_user_only`.

## Assumptions

1. **M4 seam (letterhead path).** M3 makes `meta["profile"]` correct (author + clinic) for every render through `_pdf_inputs(conn, structured, day, encounter_id)`. With an **active letterhead template**, the PDF header today prints the layout's stored snapshot (`layout.profile`, `doctor_dictation/pdf/sheet.py:105`) and ignores `meta["profile"]`, so until M4 a reprint under a letterhead still shows the doctor saved at Accept. M4 (spec 9.4) makes live `meta["profile"]` values win over the snapshot, picks the author's own letterhead (9.1) and adds `meta["doctors"]`; it should call `db/authorship.print_profile` and `encounter_author_id` rather than re-deriving the author. M3's guarantee is stated for the default (built-in) PDF path.
2. **M4 seam (letterhead Accept writes the profile).** `templates/service.py:140-146` (`_save_details`, used by Accept and use-details) writes all six fields into `clinic_profile`, and `api/templates.py:147` returns `profile_dict(get_profile(...))`. In multi mode the three doctor fields there are no longer what `GET /api/v1/profile` shows; M4 should send them to `db/details.save_my_details` for the accepting user and return the split profile. The OP prefix field in Clinic details (spec 8.1, migration `008`) is also M4's.
3. **Who counts as "signed in".** `request.state.identity` (set at `doctor_dictation/api/session.py:60`) is present exactly when `MULTI_CLINIC` is on and the request passed the middleware; every M3 route treats its absence as single-database mode.
4. **The test cookie.** Tests sign in by setting a genuinely signed cookie (`sessions.sign("rao", uid, 0)`) after setting `must_change_password = 0`; the real middleware and `authn.load_identity` validate it, as in `tests/test_session_middleware.py`.
5. **M6 (isolation suite) can rely on:** the 403 body above; `GET /api/v1/documents/{id}` adding `author: {user_id, name, doctor_name, qualifications, reg_no}` and `can_edit` when signed in; Today rows adding `author_id` and `doctor_name`; `?scope=` values `mine` (default) and `clinic`, anything else 400 `{"error": "scope must be mine or clinic"}`.
6. `POST /api/v1/encounters` still accepts a body `doctor_id` (`doctor_dictation/api/persistence.py:31-37`). It is not an edit path: a document is only ever created by `POST /api/v1/documents`, which makes its own encounter. Left as is (see Not in this plan).

## Open questions for the user

1. Pre-M3 prescriptions (no author): keep them author-less and editable by anyone (this plan), or let the first re-saver become the author?
2. Clinic details stay editable by every signed-in user (spec 16.3, current plan). No `policy.can` action exists for it (`doctor_dictation/policy.py:5`); adding `profile.edit` would be an M2 policy change, so it is not done here.

---

### Task 1: Migration 006, profile-split and authorship SQL, per-doctor `top_medicines`

**Files:**
- Create: `doctor_dictation/db/migrations/006_doctor_details_to_users.sql`, `doctor_dictation/db/details.py`, `doctor_dictation/db/authorship.py`, `tests/test_authorship_db.py`
- Modify: `doctor_dictation/db/__init__.py` (`top_medicines`, lines 378-385), `tests/test_db.py` (lines 88 and 97)

**Interfaces:**
- Consumes: `dbmod.get_profile`, `dbmod._utcnow`, `dbmod.discover_migrations`, `dbmod.migrate(conn, migrations_dir)` (`doctor_dictation/db/__init__.py:72-105`, `446-448`); the `users` columns from `005_users_profile.sql`.
- Produces (`doctor_dictation.db.details`): `CLINIC_KEYS`, `DOCTOR_KEYS`; `clinic_details(conn) -> dict`; `saved_doctor_details(conn) -> dict`; `my_details(conn, user_id) -> dict`; `save_clinic_details(conn, clinic_name="", address="", phone="", updated_at=None) -> None`; `save_my_details(conn, user_id, doctor_name="", qualifications="", reg_no="") -> int`.
- Produces (`doctor_dictation.db.authorship`): `UNKNOWN_AUTHOR = "another doctor"`; `author_label(row) -> str`; `encounter_author_id(conn, encounter_id) -> int | None`; `print_profile(conn, encounter_id) -> dict` (six keys, doctor fields first); `document_author(conn, document_id) -> dict | None` (`document_id, encounter_id, author_id, name, doctor_name, qualifications, reg_no`); `set_finalized_by(conn, document_id, user_id) -> int`; `list_today(conn, start_iso, end_iso, doctor_id=None) -> list[dict]` (`document_id, encounter_id, patient_name, op_no, created_at, author_id, doctor_name`).
- Produces (`doctor_dictation.db`): `top_medicines(conn, limit=30, doctor_id=None)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_authorship_db.py`:

```python
"""Authorship and profile-split SQL (M3 Task 1): migration 006, print profile, author lookup, Today rows,
per-doctor hints. Offline; each test uses its own temp database file."""
import shutil

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation.db import authorship as adb
from doctor_dictation.db import details


@pytest.fixture()
def conn(tmp_path):
    c = dbmod.get_conn(tmp_path / "m3.db")
    dbmod.migrate(c)
    yield c
    c.close()


def _user(conn, username, doctor_name="", display_name="", qualifications="", reg_no=""):
    uid = dbmod.create_user(conn, username, "x")
    conn.execute("UPDATE users SET doctor_name = ?, display_name = ?, qualifications = ?, reg_no = ? WHERE id = ?",
                 (doctor_name, display_name, qualifications, reg_no, uid))
    conn.commit()
    return uid


def _doc(conn, author_id, names=("Tamsulosin",), created_at="2026-10-14T05:00:00Z", patient="P"):
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, patient, "40 / M", None), doctor_id=author_id,
                                 op_no="OP-" + patient)
    return dbmod.save_document(conn, eid, "sha", {"rx": [{"name": n} for n in names]},
                               finalized_by=author_id, finalized_at=created_at, created_at=created_at)


def _db_before_006(tmp_path):
    old = tmp_path / "old_migrations"
    old.mkdir()
    for version, path in dbmod.discover_migrations():
        if version < "006":
            shutil.copy(path, old / version)
    c = dbmod.get_conn(tmp_path / "adopted.db")
    dbmod.migrate(c, old)
    return c


def test_migration_006_copies_the_saved_doctor_fields_to_the_first_user_only(tmp_path):
    c = _db_before_006(tmp_path)
    try:
        dbmod.save_profile(c, doctor_name="Dr. Rao", qualifications="MBBS", reg_no="R-111", clinic_name="Rao Clinic")
        first, second = dbmod.create_user(c, "dr.rao", "x"), dbmod.create_user(c, "dr.mehta", "x")
        assert dbmod.migrate(c) == ["006_doctor_details_to_users.sql"]
        assert details.my_details(c, first) == {"doctor_name": "Dr. Rao", "qualifications": "MBBS", "reg_no": "R-111"}
        assert details.my_details(c, second) == {"doctor_name": "", "qualifications": "", "reg_no": ""}
        assert details.saved_doctor_details(c)["doctor_name"] == "Dr. Rao"     # the shared row keeps its copy
    finally:
        c.close()


def test_migration_006_never_overwrites_details_and_is_a_no_op_without_users_or_profile(tmp_path):
    c = _db_before_006(tmp_path)
    try:
        dbmod.save_profile(c, doctor_name="Dr. Old")
        uid = dbmod.create_user(c, "dr.rao", "x")
        c.execute("UPDATE users SET reg_no = 'MINE' WHERE id = ?", (uid,))
        c.commit()
        dbmod.migrate(c)
        assert details.my_details(c, uid) == {"doctor_name": "", "qualifications": "", "reg_no": "MINE"}
    finally:
        c.close()
    bare = dbmod.get_conn(tmp_path / "bare.db")
    try:
        assert "006_doctor_details_to_users.sql" in dbmod.migrate(bare)   # no users, no profile: applies cleanly
        assert dbmod.migrate(bare) == []
    finally:
        bare.close()


def test_author_label_prefers_doctor_name_then_display_name_then_username(conn):
    a = _user(conn, "dr.a", doctor_name="  Dr. A  ", display_name="Alpha")
    b = _user(conn, "dr.b", display_name="Beta")
    c = _user(conn, "dr.c")
    rows = {r["id"]: r for r in conn.execute("SELECT * FROM users")}
    assert [adb.author_label(rows[i]) for i in (a, b, c)] == ["Dr. A", "Beta", "dr.c"]
    assert adb.author_label(None) == adb.UNKNOWN_AUTHOR == "another doctor"


def test_print_profile_takes_doctor_fields_from_the_author_and_clinic_fields_from_the_clinic(conn):
    dbmod.save_profile(conn, doctor_name="Old Shared", qualifications="OLD", reg_no="OLD-1",
                       clinic_name="Rao Clinic", address="1 Main Road", phone="040 111")
    rao = _user(conn, "dr.rao", doctor_name="Dr. Rao", qualifications="MBBS", reg_no="R-111")
    authored = dbmod.get_document(conn, _doc(conn, rao))["encounter_id"]
    legacy = dbmod.get_document(conn, _doc(conn, None))["encounter_id"]
    clinic = {"clinic_name": "Rao Clinic", "address": "1 Main Road", "phone": "040 111"}
    assert adb.print_profile(conn, authored) == {"doctor_name": "Dr. Rao", "qualifications": "MBBS", "reg_no": "R-111", **clinic}
    assert adb.print_profile(conn, legacy) == {"doctor_name": "Old Shared", "qualifications": "OLD", "reg_no": "OLD-1", **clinic}


def test_document_author_names_the_author_and_handles_legacy_and_missing_documents(conn):
    dbmod.save_profile(conn, doctor_name="Old Shared")
    mehta = _user(conn, "dr.mehta", doctor_name="Dr. Mehta", qualifications="MD", reg_no="M-222")
    doc = _doc(conn, mehta)
    a = adb.document_author(conn, doc)
    assert (a["document_id"], a["author_id"], a["name"]) == (doc, mehta, "Dr. Mehta")
    assert (a["doctor_name"], a["qualifications"], a["reg_no"]) == ("Dr. Mehta", "MD", "M-222")
    old = adb.document_author(conn, _doc(conn, None))
    assert (old["author_id"], old["name"], old["doctor_name"]) == (None, "", "Old Shared")
    assert adb.document_author(conn, 999) is None


def test_set_finalized_by_records_the_saver(conn):
    rao, mehta = _user(conn, "dr.rao"), _user(conn, "dr.mehta")
    doc = _doc(conn, rao)
    assert adb.set_finalized_by(conn, doc, mehta) == 1
    assert dbmod.get_document(conn, doc)["finalized_by"] == mehta
    assert adb.set_finalized_by(conn, 999, mehta) == 0


def test_list_today_mine_versus_clinic_with_doctor_names(conn):
    rao = _user(conn, "dr.rao", doctor_name="Dr. Rao")
    mehta = _user(conn, "dr.mehta", display_name="Mehta")
    _doc(conn, rao, patient="Asha", created_at="2026-10-14T05:00:00Z")
    _doc(conn, mehta, patient="Bala", created_at="2026-10-14T06:00:00Z")
    _doc(conn, None, patient="Chitra", created_at="2026-10-14T07:00:00Z")
    _doc(conn, rao, patient="Yesterday", created_at="2026-10-13T05:00:00Z")
    start, end = "2026-10-14T00:00:00Z", "2026-10-15T00:00:00Z"
    mine = adb.list_today(conn, start, end, rao)
    assert [(r["patient_name"], r["author_id"], r["doctor_name"]) for r in mine] == [("Asha", rao, "Dr. Rao")]
    clinic = adb.list_today(conn, start, end)
    assert [(r["patient_name"], r["doctor_name"]) for r in clinic] == [("Asha", "Dr. Rao"), ("Bala", "Mehta"), ("Chitra", "")]
    assert set(clinic[0]) == {"document_id", "encounter_id", "patient_name", "op_no", "created_at", "author_id", "doctor_name"}


def test_top_medicines_for_one_doctor_ignores_colleagues(conn):
    rao, mehta = _user(conn, "dr.rao"), _user(conn, "dr.mehta")
    _doc(conn, rao, ["Tamsulosin", "Tamsulosin"])
    _doc(conn, mehta, ["Paracetamol"])
    _doc(conn, None, ["Zincovit"])
    assert dbmod.top_medicines(conn, doctor_id=rao) == ["Tamsulosin"]
    assert dbmod.top_medicines(conn, doctor_id=mehta) == ["Paracetamol"]
    assert dbmod.top_medicines(conn) == ["Tamsulosin", "Zincovit", "Paracetamol"]
    assert dbmod.top_medicines(conn, doctor_id=999) == []


def test_clinic_details_save_keeps_the_doctor_columns_and_my_details_round_trip(conn):
    dbmod.save_profile(conn, doctor_name="Old Shared", qualifications="OLD", reg_no="OLD-1", clinic_name="Before")
    details.save_clinic_details(conn, "Rao Clinic", "1 Main Road", "040 111")
    assert details.clinic_details(conn) == {"clinic_name": "Rao Clinic", "address": "1 Main Road", "phone": "040 111"}
    assert details.saved_doctor_details(conn) == {"doctor_name": "Old Shared", "qualifications": "OLD", "reg_no": "OLD-1"}
    uid = _user(conn, "dr.rao")
    assert details.save_my_details(conn, uid, "Dr. Rao", "MBBS", "R-111") == 1
    assert details.my_details(conn, uid) == {"doctor_name": "Dr. Rao", "qualifications": "MBBS", "reg_no": "R-111"}
    assert details.save_my_details(conn, 999, "x", "y", "z") == 0
    assert details.my_details(conn, 999) == {"doctor_name": "", "qualifications": "", "reg_no": ""}
```

In `tests/test_db.py` (`test_init_db_idempotent`), the migration list at line 88 and the count at line 97 gain `006`. Replace

```python
    assert first == ["001_init.sql", "002_document_pdf.sql", "003_clinic_profile.sql", "004_templates.sql", "005_users_profile.sql"]
```

with

```python
    assert first == ["001_init.sql", "002_document_pdf.sql", "003_clinic_profile.sql", "004_templates.sql", "005_users_profile.sql",
                     "006_doctor_details_to_users.sql"]
```

and replace `    assert n == 5` with `    assert n == 6`. (M4 will append its own `007`/`008` here the same way.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_authorship_db.py tests/test_db.py -q`
Expected: collection ERROR for `tests/test_authorship_db.py` (`cannot import name 'authorship' from 'doctor_dictation.db'`) and `test_init_db_idempotent` FAILED (the list has no `006`).

- [ ] **Step 3: Write the implementation**

`doctor_dictation/db/migrations/006_doctor_details_to_users.sql`:

```sql
-- 006: the doctor fields move from the shared clinic profile to each user's own row (spec 8.1).
-- Copies the saved doctor name, qualifications and registration no. onto the clinic's first user when that
-- user has none yet. Idempotent: a user who already has any detail is never touched; no user, no change.
-- clinic_profile keeps its doctor columns: single-database mode and pre-authorship prescriptions print from them.
UPDATE users SET
    doctor_name    = (SELECT doctor_name    FROM clinic_profile WHERE id = 1),
    qualifications = (SELECT qualifications FROM clinic_profile WHERE id = 1),
    reg_no         = (SELECT reg_no         FROM clinic_profile WHERE id = 1)
WHERE id = (SELECT MIN(id) FROM users)
  AND doctor_name = '' AND qualifications = '' AND reg_no = ''
  AND EXISTS (SELECT 1 FROM clinic_profile WHERE id = 1);
```

`doctor_dictation/db/details.py`:

```python
"""Profile split (spec 8.1): clinic details live on ``clinic_profile``, a doctor's own details on their ``users`` row.

SQL only, like the rest of ``db``. Every getter returns plain dicts with "" for unset values.
"""
from doctor_dictation import db as dbmod

CLINIC_KEYS = ("clinic_name", "address", "phone")
DOCTOR_KEYS = ("doctor_name", "qualifications", "reg_no")


def clinic_details(conn) -> dict:
    row = dbmod.get_profile(conn)
    return {k: (row[k] if row is not None else "") or "" for k in CLINIC_KEYS}


def saved_doctor_details(conn) -> dict:
    """The doctor fields still stored on ``clinic_profile`` (single mode, and prescriptions with no author)."""
    row = dbmod.get_profile(conn)
    return {k: (row[k] if row is not None else "") or "" for k in DOCTOR_KEYS}


def my_details(conn, user_id) -> dict:
    row = conn.execute("SELECT doctor_name, qualifications, reg_no FROM users WHERE id = ?", (user_id,)).fetchone()
    return {k: (row[k] if row is not None else "") or "" for k in DOCTOR_KEYS}


def save_clinic_details(conn, clinic_name="", address="", phone="", updated_at=None) -> None:
    """Upsert the three clinic fields; the doctor columns of ``clinic_profile`` are left as they are."""
    conn.execute(
        "INSERT INTO clinic_profile(id, clinic_name, address, phone, updated_at) VALUES (1, ?, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET clinic_name = excluded.clinic_name, address = excluded.address,"
        " phone = excluded.phone, updated_at = excluded.updated_at",
        (clinic_name, address, phone, updated_at or dbmod._utcnow()))
    conn.commit()


def save_my_details(conn, user_id, doctor_name="", qualifications="", reg_no="") -> int:
    """Write the signed-in user's own doctor fields; returns rows changed (0 for an unknown user)."""
    cur = conn.execute("UPDATE users SET doctor_name = ?, qualifications = ?, reg_no = ? WHERE id = ?",
                       (doctor_name, qualifications, reg_no, user_id))
    conn.commit()
    return cur.rowcount
```

`doctor_dictation/db/authorship.py`:

```python
"""Who wrote a prescription (spec 7.1): ``encounters.doctor_id`` is the author, ``documents.finalized_by`` the
last saver. SQL only. A document saved before authorship existed has no author (``author_id`` None)."""
from doctor_dictation.db.details import clinic_details, my_details, saved_doctor_details

UNKNOWN_AUTHOR = "another doctor"


def author_label(row) -> str:
    """How a user is named on screen: doctor name, else display name, else username."""
    if row is None:
        return UNKNOWN_AUTHOR
    return (row["doctor_name"] or "").strip() or (row["display_name"] or "").strip() or row["username"] or UNKNOWN_AUTHOR


def _user(conn, user_id):
    return conn.execute("SELECT id, username, display_name, doctor_name FROM users WHERE id = ?", (user_id,)).fetchone()


def encounter_author_id(conn, encounter_id):
    row = conn.execute("SELECT doctor_id FROM encounters WHERE id = ?", (encounter_id,)).fetchone()
    return row["doctor_id"] if row is not None else None


def print_profile(conn, encounter_id) -> dict:
    """The six fields a prescription prints: clinic fields from the clinic, doctor fields from the AUTHOR.

    No author (single-database mode, or a pre-authorship prescription): the doctor fields saved on the clinic
    profile, exactly as before. Never the viewer's details.
    """
    author_id = encounter_author_id(conn, encounter_id)
    doctor = my_details(conn, author_id) if author_id is not None else saved_doctor_details(conn)
    return {**doctor, **clinic_details(conn)}


def document_author(conn, document_id):
    """``{document_id, encounter_id, author_id, name, doctor_name, qualifications, reg_no}`` or None (no document).

    ``name`` is "" when there is no author; the three doctor fields are what the prescription prints.
    """
    doc = conn.execute("SELECT id, encounter_id FROM documents WHERE id = ?", (document_id,)).fetchone()
    if doc is None:
        return None
    author_id = encounter_author_id(conn, doc["encounter_id"])
    profile = print_profile(conn, doc["encounter_id"])
    return {"document_id": doc["id"], "encounter_id": doc["encounter_id"], "author_id": author_id,
            "name": author_label(_user(conn, author_id)) if author_id is not None else "",
            **{k: profile[k] for k in ("doctor_name", "qualifications", "reg_no")}}


def set_finalized_by(conn, document_id, user_id) -> int:
    cur = conn.execute("UPDATE documents SET finalized_by = ? WHERE id = ?", (user_id, document_id))
    conn.commit()
    return cur.rowcount


def list_today(conn, start_iso, end_iso, doctor_id=None):
    """The Today rows in ``[start_iso, end_iso)``, oldest first, with ``author_id`` and ``doctor_name``.

    ``doctor_id`` keeps one author's prescriptions ("mine"); None keeps the whole clinic. ``doctor_name`` is ""
    for a prescription with no author.
    """
    mine, args = ("", ()) if doctor_id is None else (" AND e.doctor_id = ?", (doctor_id,))
    rows = conn.execute(
        "SELECT d.id AS document_id, d.encounter_id AS encounter_id, p.name AS patient_name, e.op_no AS op_no,"
        " d.created_at AS created_at, e.doctor_id AS author_id,"
        " u.username AS username, u.display_name AS display_name, u.doctor_name AS doctor_name"
        " FROM documents d JOIN encounters e ON e.id = d.encounter_id JOIN patients p ON p.id = e.patient_id"
        " LEFT JOIN users u ON u.id = e.doctor_id"
        " WHERE d.created_at >= ? AND d.created_at < ?" + mine + " ORDER BY d.created_at, d.id",
        (start_iso, end_iso, *args)).fetchall()
    return [{"document_id": r["document_id"], "encounter_id": r["encounter_id"], "patient_name": r["patient_name"],
             "op_no": r["op_no"], "created_at": r["created_at"], "author_id": r["author_id"],
             "doctor_name": author_label(r) if r["author_id"] is not None else ""} for r in rows]
```

In `doctor_dictation/db/__init__.py` replace the head of `top_medicines` (lines 378-385):

```python
def top_medicines(conn, limit: int = 30) -> list[str]:
    """Finalized documents' medicine names, most used first; malformed rows are skipped."""
    if limit <= 0:
        return []
    rows = conn.execute(
        "SELECT structured_json FROM documents"
        " WHERE finalized_at IS NOT NULL AND structured_json IS NOT NULL"
        " ORDER BY id DESC LIMIT ?", (TOP_MEDICINES_WINDOW,)).fetchall()
```

with

```python
def top_medicines(conn, limit: int = 30, doctor_id=None) -> list[str]:
    """Finalized documents' medicine names, most used first; malformed rows are skipped.
    ``doctor_id`` keeps only that doctor's prescriptions (their encounters); None keeps every one."""
    if limit <= 0:
        return []
    mine, args = ("", ()) if doctor_id is None else (" AND encounter_id IN (SELECT id FROM encounters WHERE doctor_id = ?)", (doctor_id,))
    rows = conn.execute(
        "SELECT structured_json FROM documents"
        " WHERE finalized_at IS NOT NULL AND structured_json IS NOT NULL" + mine +
        " ORDER BY id DESC LIMIT ?", (*args, TOP_MEDICINES_WINDOW)).fetchall()
```

The rest of the function (the counting loop) is unchanged. Check `wc -l doctor_dictation/db/__init__.py` prints 487.

- [ ] **Step 4: Run the tests, then the suite**

Run: `.venv/bin/python -m pytest tests/test_authorship_db.py tests/test_db.py tests/test_top_medicines.py -q`
Expected: all passed (9 new in `test_authorship_db.py`).
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 9` passed, 1 skipped.

- [ ] **Step 5: Leave uncommitted.** New: the migration, `db/details.py`, `db/authorship.py`, `tests/test_authorship_db.py`; modified: `db/__init__.py`, `tests/test_db.py`.

---

### Task 2: Authorship on save, the 403 rule on every document route, print from the author

**Files:**
- Create: `doctor_dictation/api/authorship.py`, `tests/authorship_fixtures.py`, `tests/test_authorship_routes.py`
- Modify: `doctor_dictation/api/persistence.py` (imports 8-19, `_pdf_inputs` 111-135, `create_document` 152-276, `get_document` 284-305, `get_document_pdf` 332-367), `doctor_dictation/api/format.py` (imports 4-8, `CorrectRequest` 166-168, `correct` 171-181)

**Interfaces:**
- Consumes: Task 1 `db.authorship.*`; `policy.can(user, action, resource)` (`doctor_dictation/policy.py:14-22`; `resource` may be a dict with `author_id`); `request.state.identity` (`doctor_dictation/api/session.py:60`); `sessions.sign` and `COOKIE_NAME` (`doctor_dictation/sessions.py:18`, `69-72`); `accounts.create_user` (`doctor_dictation/accounts.py:44-80`); `clinics.provision_clinic`.
- Produces (`doctor_dictation.api.authorship`): `identity(request)`; `forbidden(author_name) -> JSONResponse`; `check(conn, request, action, document_id) -> JSONResponse | None`; `check_document(request, action, document_id) -> JSONResponse | None` (own connection); `author_view(conn, request, document_id) -> dict` (`{}` in single mode, else `{"author": {...}, "can_edit": bool}`).
- Produces (HTTP, signed in): first save sets `encounters.doctor_id` and `documents.finalized_by`; re-save and correct with `document_id` by a non-author answer 403 with the fixed body; `GET /api/v1/documents/{id}` adds `author` and `can_edit`; PDFs print the author's details. `_pdf_inputs(conn, structured, day, encounter_id)` (new 4th argument, for M4).
- Produces (tests): `tests/authorship_fixtures.py` with `H`, `RAO`, `MEHTA`, `CLINIC`, `OLD`, `SAVE`, `clinic_conn`, `as_user`, `save`, `legacy_document` and the `team` fixture (used again by Tasks 3 and 4).

- [ ] **Step 1: Write the shared fixtures and the failing tests**

`tests/authorship_fixtures.py`:

```python
"""Shared helpers for the M3 route tests: one clinic ("rao"), two signed-in doctors, a fake PDF renderer.

Offline. A doctor is "signed in" by putting a genuinely signed session cookie on the client (``as_user``), so the
real session middleware loads the identity and sets the clinic scope on every request.
"""
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import accounts, clinics, sessions
from doctor_dictation import db as dbmod
from doctor_dictation.scope import clinic_dir

H = {"X-DD-Client": "1"}
RAO = {"doctor_name": "Dr. Rao", "qualifications": "MBBS", "reg_no": "R-111"}
MEHTA = {"doctor_name": "Dr. Mehta", "qualifications": "MBBS, MD", "reg_no": "M-222"}
CLINIC = {"clinic_name": "Rao Clinic", "address": "1 Main Road", "phone": "040 111"}
OLD = {"doctor_name": "Old Shared", "qualifications": "OLD", "reg_no": "OLD-1"}   # pre-M3 doctor fields on clinic_profile
SAVE = {"structured": {"patientName": "Anita", "opNo": "OP-1", "rx": [{"name": "Tamsulosin", "status": "verified"}]},
        "confirmed_rows": []}


def clinic_conn(slug="rao"):
    return closing(dbmod.get_conn(clinic_dir(slug) / "app.db"))


def as_user(client, uid, slug="rao"):
    client.cookies.set(sessions.COOKIE_NAME, sessions.sign(slug, uid, 0))
    return client


def save(client, body=SAVE):
    r = client.post("/api/v1/documents", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def legacy_document(patient="Old Patient"):
    """A prescription saved before authorship existed: no doctor_id, no finalized_by."""
    with clinic_conn() as conn:
        eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, patient, "50 / F", "OP-OLD"), op_no="OP-OLD",
                                     status="finalized")
        return dbmod.save_document(conn, eid, "sha-old", {"patientName": patient, "rx": []},
                                   finalized_at=dbmod._utcnow())


@pytest.fixture()
def team(multi, monkeypatch):
    clinics.provision_clinic("rao", "Rao Clinic")
    rao, _ = accounts.create_user("rao", "dr.rao", display_name="Rao", password="rao-password-1", **RAO)
    mehta, _ = accounts.create_user("rao", "dr.mehta", display_name="Mehta", password="mehta-password-1", **MEHTA)
    with clinic_conn() as conn:
        conn.execute("UPDATE users SET must_change_password = 0")
        conn.commit()
        dbmod.save_profile(conn, **OLD, **CLINIC)
    rendered = []

    def fake(structured, meta, out_path, layout=None):
        rendered.append(meta)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)
    from doctor_dictation.api.app import create_app
    with TestClient(create_app()) as c:
        yield SimpleNamespace(client=c, rao=rao, mehta=mehta, rendered=rendered)
```

`tests/test_authorship_routes.py`:

```python
"""Authorship through the real app (M3 Task 2, spec 7.1): who is recorded, who may edit, what prints. Offline."""
from doctor_dictation import db as dbmod
from doctor_dictation import policy
from authorship_fixtures import CLINIC, H, MEHTA, OLD, RAO, SAVE, as_user, clinic_conn, legacy_document, save, team  # noqa: F401

DENIED = {"error": "This prescription belongs to Dr. Rao. You can view and reprint it."}


def _rows(doc):
    with clinic_conn() as conn:
        d = dict(dbmod.get_document(conn, doc))
        e = dict(dbmod.get_encounter(conn, d["encounter_id"]))
        actions = [r["action"] for r in conn.execute("SELECT action FROM audit_log WHERE action IN ('finalize', 'resave')")]
    return d, e, actions


def _resave(c, doc, name="Anita"):
    body = {**SAVE, "structured": {**SAVE["structured"], "patientName": name}, "document_id": doc}
    return c.post("/api/v1/documents", json=body, headers=H)


def test_first_save_records_the_signed_in_doctor_as_author_and_saver(team):
    doc = save(as_user(team.client, team.mehta))
    d, e, _ = _rows(doc)
    assert (e["doctor_id"], d["finalized_by"]) == (team.mehta, team.mehta)


def test_author_resave_keeps_the_author_and_a_legacy_resave_records_the_saver(team):
    c = as_user(team.client, team.rao)
    doc = save(c)
    assert _resave(c, doc, "Anita R").status_code == 200
    d, e, _ = _rows(doc)
    assert (e["doctor_id"], d["finalized_by"]) == (team.rao, team.rao)
    old = legacy_document()
    assert _resave(as_user(c, team.mehta), old, "Old Patient").status_code == 200
    d, e, _ = _rows(old)
    assert (e["doctor_id"], d["finalized_by"]) == (None, team.mehta)     # still no author: stays editable by anyone


def test_colleague_resave_is_403_with_the_exact_message_and_changes_nothing(team):
    c = as_user(team.client, team.rao)
    doc = save(c)
    before, _, _ = _rows(doc)
    n = len(team.rendered)
    r = _resave(as_user(c, team.mehta), doc, "Hijacked")
    assert (r.status_code, r.json()) == (403, DENIED)
    after, _, actions = _rows(doc)
    assert after == before and len(team.rendered) == n and actions == ["finalize"]


def test_colleague_correct_is_403_but_the_author_and_an_unsaved_draft_may_correct(team):
    c = as_user(team.client, team.rao)
    doc = save(c)
    body = {"transcript": "", "current_form": SAVE["structured"]}
    assert c.post("/api/v1/correct", json={**body, "document_id": doc}, headers=H).status_code == 200
    as_user(c, team.mehta)
    r = c.post("/api/v1/correct", json={**body, "document_id": doc}, headers=H)
    assert (r.status_code, r.json()) == (403, DENIED)
    assert c.post("/api/v1/correct", json=body, headers=H).status_code == 200            # a fresh draft of his own


def test_any_doctor_may_view_and_the_answer_says_who_wrote_it(team):
    c = as_user(team.client, team.rao)
    doc = save(c)
    mine = c.get(f"/api/v1/documents/{doc}").json()
    assert mine["can_edit"] is True and mine["author"] == {"user_id": team.rao, "name": "Dr. Rao", **RAO}
    theirs = as_user(c, team.mehta).get(f"/api/v1/documents/{doc}")
    assert theirs.status_code == 200
    assert theirs.json()["can_edit"] is False and theirs.json()["author"]["name"] == "Dr. Rao"
    assert theirs.json()["structured"]["patientName"] == "Anita"


def test_colleague_reprint_prints_the_authors_details_not_the_viewers(team):
    c = as_user(team.client, team.rao)
    doc = save(c)
    with clinic_conn() as conn:
        conn.execute("UPDATE documents SET pdf_path = NULL WHERE id = ?", (doc,))   # force an on-demand render
        conn.commit()
    r = as_user(c, team.mehta).get(f"/api/v1/documents/{doc}/pdf")
    assert r.status_code == 200 and r.content == b"%PDF-fake"
    assert team.rendered[-1]["profile"] == {**RAO, **CLINIC}


def test_save_prints_the_savers_own_details_with_the_clinic_details(team):
    save(as_user(team.client, team.mehta))
    assert team.rendered[-1]["profile"] == {**MEHTA, **CLINIC}


def test_legacy_document_prints_the_saved_profile_and_anyone_may_open_it_for_editing(team):
    old = legacy_document()
    j = as_user(team.client, team.mehta).get(f"/api/v1/documents/{old}").json()
    assert j["can_edit"] is True and j["author"] == {"user_id": None, "name": "", **OLD}
    assert team.client.get(f"/api/v1/documents/{old}/pdf").status_code == 200
    assert team.rendered[-1]["profile"] == {**OLD, **CLINIC}


def test_every_document_route_asks_policy_can(team, monkeypatch):
    c = as_user(team.client, team.rao)
    doc = save(c)
    asked, real = [], policy.can
    monkeypatch.setattr(policy, "can", lambda user, action, resource=None: asked.append(action) or real(user, action, resource))
    c.get(f"/api/v1/documents/{doc}")
    c.get(f"/api/v1/documents/{doc}/pdf")
    _resave(c, doc)
    c.post("/api/v1/correct", json={"transcript": "", "current_form": {}, "document_id": doc}, headers=H)
    assert {"document.view", "document.reprint"} <= set(asked) and asked.count("document.edit") >= 2


def test_an_unknown_document_is_still_404_when_signed_in(team):
    c = as_user(team.client, team.mehta)
    assert c.get("/api/v1/documents/999").status_code == 404
    assert c.get("/api/v1/documents/999/pdf").status_code == 404
    assert _resave(c, 999).status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_authorship_routes.py -q`
Expected: 9 failed, 1 passed (`test_an_unknown_document_is_still_404_when_signed_in` already holds; it guards the 404 path the new checks must not break).

- [ ] **Step 3: Write the implementation**

`doctor_dictation/api/authorship.py` (a helper module, not a router; `api/app.py` is not touched):

```python
"""The ownership answer every document route gives (spec 7.1). Routes call ``policy.can`` through ``check``.

Single-database mode has no signed-in user (``request.state.identity`` is absent), so nothing is checked
and every response keeps its old shape.
"""
from contextlib import closing

from fastapi import Request
from fastapi.responses import JSONResponse

from doctor_dictation import db as dbmod
from doctor_dictation import policy
from doctor_dictation.db import authorship as adb


def identity(request: Request):
    """The signed-in ``sessions.Identity`` (multi-clinic mode), or None (single-database mode)."""
    return getattr(request.state, "identity", None)


def forbidden(author_name: str) -> JSONResponse:
    return JSONResponse(status_code=403, content={
        "error": f"This prescription belongs to {author_name}. You can view and reprint it."})


def check(conn, request: Request, action: str, document_id: int):
    """None when ``action`` is allowed on the document (or there is no such document: the caller answers 404,
    or no one is signed in); otherwise the 403 response to return."""
    ident = identity(request)
    if ident is None:
        return None
    author = adb.document_author(conn, document_id)
    if author is None or policy.can(ident, action, author):
        return None
    return forbidden(author["name"])


def check_document(request: Request, action: str, document_id: int):
    """``check`` with its own connection (sync routes, or ``asyncio.to_thread`` from async ones)."""
    if identity(request) is None:
        return None
    with closing(dbmod.get_conn()) as conn:
        return check(conn, request, action, document_id)


def author_view(conn, request: Request, document_id: int) -> dict:
    """The extra keys GET /documents/{id} returns when someone is signed in: who wrote it, and may I edit it."""
    ident = identity(request)
    if ident is None:
        return {}
    author = adb.document_author(conn, document_id)
    shown = {k: author[k] for k in ("doctor_name", "qualifications", "reg_no")}
    return {"author": {"user_id": author["author_id"], "name": author["name"], **shown},
            "can_edit": policy.can(ident, "document.edit", author)}
```

`doctor_dictation/api/persistence.py`, eight replacements (each `old` text appears exactly once):

1. Imports (lines 8-17). Replace

```python
from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from doctor_dictation import db as dbmod
from doctor_dictation.api.profile import profile_dict
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.determinism import validate_structured
from doctor_dictation.core.safety import screen_unverified
from doctor_dictation.db.opno import create_patient_with_new_op
```

with

```python
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from doctor_dictation import db as dbmod
from doctor_dictation.api import authorship
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.determinism import validate_structured
from doctor_dictation.core.safety import screen_unverified
from doctor_dictation.db import authorship as adb
from doctor_dictation.db.opno import create_patient_with_new_op
```

2. `_pdf_inputs` head (lines 111-123). Replace

```python
def _pdf_inputs(conn, structured, day):
    """Render meta + layout for a document: the ONE place save and re-print share.

    The clinic's active letterhead template supplies layout and logo; any
    template problem (corrupt row, missing logo, bad layout) drops to the plain
    profile header (``layout`` None, no logo).
    """
    meta = {
        "date": day.isoformat(),
        "opNo": structured.get("opNo") or "",
        "patientName": structured.get("patientName") or "",
        "profile": profile_dict(dbmod.get_profile(conn)),
    }
```

with

```python
def _pdf_inputs(conn, structured, day, encounter_id):
    """Render meta + layout for a document: the ONE place save and re-print share.

    ``meta["profile"]`` carries the clinic's fields and the AUTHOR's doctor fields (never the viewer's).
    The clinic's active letterhead template supplies layout and logo; any
    template problem (corrupt row, missing logo, bad layout) drops to the plain
    profile header (``layout`` None, no logo).
    """
    meta = {
        "date": day.isoformat(),
        "opNo": structured.get("opNo") or "",
        "patientName": structured.get("patientName") or "",
        "profile": adb.print_profile(conn, encounter_id),
    }
```

3. `create_document` signature (lines 152-153). Replace

```python
@router.post("/api/v1/documents")
def create_document(req: DocumentCreate):
```

with

```python
@router.post("/api/v1/documents")
def create_document(req: DocumentCreate, request: Request):
```

4. End of its docstring and the first statement (lines 164-166). Replace

```python
    is not upserted from the payload on this path.
    """
    structured = req.structured if isinstance(req.structured, dict) else {}
```

with

```python
    is not upserted from the payload on this path.

    Signed in: the first save records the saver as author (``encounters.doctor_id``) and saver
    (``documents.finalized_by``); a re-save needs ``document.edit`` (only the author; 403 otherwise),
    keeps the author and records the new saver.
    """
    ident = authorship.identity(request)
    if req.document_id is not None:
        denied = authorship.check_document(request, "document.edit", req.document_id)
        if denied is not None:
            return denied
    structured = req.structured if isinstance(req.structured, dict) else {}
```

5. The new encounter (lines 213-218). Replace

```python
            encounter_id = dbmod.create_encounter(
                conn,
                patient_id,
                op_no=validated.get("opNo") or None,
                status="finalized",
            )
```

with

```python
            encounter_id = dbmod.create_encounter(
                conn,
                patient_id,
                doctor_id=ident.user_id if ident else None,
                op_no=validated.get("opNo") or None,
                status="finalized",
            )
```

6. The render call (line 225). Replace

```python
        meta, layout = _pdf_inputs(conn, validated, datetime.now().astimezone().date())  # server-local day, same as the OP number
```

with

```python
        meta, layout = _pdf_inputs(conn, validated, datetime.now().astimezone().date(), encounter_id)  # server-local day, same as the OP number
```

7. The re-save and first-save branches (lines 245-257). Replace

```python
            document_id = req.document_id
            action = "resave"
```

with

```python
            document_id = req.document_id
            if ident is not None:
                adb.set_finalized_by(conn, document_id, ident.user_id)
            action = "resave"
```

and replace

```python
                engine=req.engine or None,
                finalized_at=dbmod._utcnow(),
                pdf_path=pdf_path,
            )
            action = "finalize"
```

with

```python
                engine=req.engine or None,
                finalized_by=ident.user_id if ident else None,
                finalized_at=dbmod._utcnow(),
                pdf_path=pdf_path,
            )
            action = "finalize"
```

8. `get_document` and `get_document_pdf`. Replace (lines 284-295)

```python
@router.get("/api/v1/documents/{document_id}")
def get_document(document_id: int):
    """Load a saved document back onto the sheet (re-open / re-print)."""
    conn = dbmod.get_conn()
    try:
        row = dbmod.get_document(conn, document_id)
        if row is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"document_id {document_id} not found"},
            )
        return {
```

with

```python
@router.get("/api/v1/documents/{document_id}")
def get_document(document_id: int, request: Request):
    """Load a saved document back onto the sheet (re-open / re-print).

    Any user of the clinic may view (``document.view``). Signed in, the answer adds ``author`` (who wrote it,
    with the doctor fields it prints) and ``can_edit``, so the sheet opens read-only for a colleague's.
    """
    conn = dbmod.get_conn()
    try:
        row = dbmod.get_document(conn, document_id)
        if row is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"document_id {document_id} not found"},
            )
        denied = authorship.check(conn, request, "document.view", document_id)
        if denied is not None:
            return denied
        return {
```

then replace (lines 301-303)

```python
            "transcript_sha256": row["transcript_sha"],
            "created_at": row["created_at"],
        }
```

with

```python
            "transcript_sha256": row["transcript_sha"],
            "created_at": row["created_at"],
            **authorship.author_view(conn, request, document_id),
        }
```

then replace (lines 332-343)

```python
@router.get("/api/v1/documents/{document_id}/pdf")
def get_document_pdf(document_id: int):
    """The saved document as a PDF: the stored file, else rendered on demand."""
    conn = dbmod.get_conn()
    try:
        row = dbmod.get_document(conn, document_id)
        if row is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"document_id {document_id} not found"},
            )
        stored = _stored_pdf(row)
```

with

```python
@router.get("/api/v1/documents/{document_id}/pdf")
def get_document_pdf(document_id: int, request: Request):
    """The saved document as a PDF: the stored file, else rendered on demand.

    Any user of the clinic may reprint (``document.reprint``); the doctor fields are the author's.
    """
    conn = dbmod.get_conn()
    try:
        row = dbmod.get_document(conn, document_id)
        if row is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"document_id {document_id} not found"},
            )
        denied = authorship.check(conn, request, "document.reprint", document_id)
        if denied is not None:
            return denied
        stored = _stored_pdf(row)
```

and finally replace (lines 349-350)

```python
            meta, layout = _pdf_inputs(conn, structured, created.astimezone().date())
            encounter_id = row["encounter_id"]
```

with

```python
            encounter_id = row["encounter_id"]
            meta, layout = _pdf_inputs(conn, structured, created.astimezone().date(), encounter_id)
```

(`profile_dict` is no longer imported here; `api/templates.py:14` still imports it from `api/profile.py`, which keeps it.)

`doctor_dictation/api/format.py`, three replacements. Replace the imports (lines 4-8)

```python
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from doctor_dictation.config import get_settings
```

with

```python
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from doctor_dictation.api import authorship
from doctor_dictation.config import get_settings
```

Replace (lines 166-172)

```python
class CorrectRequest(BaseModel):
    transcript: str = ""
    current_form: dict = {}


@router.post("/api/v1/correct")
async def correct(req: CorrectRequest):
```

with

```python
class CorrectRequest(BaseModel):
    transcript: str = ""
    current_form: dict = {}
    document_id: int | None = None   # the saved prescription being corrected; None for an unsaved draft


@router.post("/api/v1/correct")
async def correct(req: CorrectRequest, request: Request):
```

and replace (lines 179-181)

```python
    does not name keep their prior verification state.
    """
    current = req.current_form if isinstance(req.current_form, dict) else {}
```

with

```python
    does not name keep their prior verification state.

    Correcting a saved prescription (``document_id``) needs ``document.edit``: only its author (403 otherwise).
    """
    if req.document_id is not None:
        denied = await asyncio.to_thread(authorship.check_document, request, "document.edit", req.document_id)
        if denied is not None:
            return denied
    current = req.current_form if isinstance(req.current_form, dict) else {}
```

(`asyncio.to_thread` copies the context, so the clinic scope reaches `get_conn()` in the worker thread; `doctor_dictation/scope.py:4-7`.)

- [ ] **Step 4: Run the tests, then the suite and the size check**

Run: `.venv/bin/python -m pytest tests/test_authorship_routes.py tests/test_document_pdf.py tests/test_template_save.py tests/test_today.py tests/test_correction.py -q`
Expected: all passed (10 new; the single-mode PDF, save, Today and correction tests unchanged).
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 19` passed, 1 skipped.
Run: `.venv/bin/python -m pytest tests/test_file_sizes.py tests/test_api_app.py -q`
Expected: all passed (no new route; `persistence.py` about 405 lines).

- [ ] **Step 5: Leave uncommitted.** New: `api/authorship.py`, `tests/authorship_fixtures.py`, `tests/test_authorship_routes.py`; modified: `api/persistence.py`, `api/format.py`.

---

### Task 3: Today scopes and per-doctor STT hints

**Files:**
- Create: `tests/test_today_scope.py`
- Modify: `doctor_dictation/api/persistence.py` (`list_today_encounters`, lines 91-100 of the original file), `doctor_dictation/api/stt.py` (import line 15, `_doctor_top` lines 20-29)

**Interfaces:**
- Consumes: Task 1 `adb.list_today`, `dbmod.top_medicines(..., doctor_id=)`; Task 2 `authorship.identity` and `tests/authorship_fixtures.py`; `scope.current_scope()` (`doctor_dictation/scope.py:62-63`; the middleware sets `Scope(clinic, user_id, username, role)` at `api/session.py:61`).
- Produces: `GET /api/v1/encounters/today?scope=mine|clinic` (default `mine`; signed-in rows add `author_id`, `doctor_name`; other values 400; single mode unchanged). `_doctor_top(limit)` passes the scope's `user_id` as `doctor_id` (None in single mode).

- [ ] **Step 1: Write the failing tests**

`tests/test_today_scope.py`:

```python
"""Today scopes and per-doctor hints (M3 Task 3, spec 7.2 and 7.3). Offline."""
from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api import stt as stt_api
from doctor_dictation.config import override_settings
from doctor_dictation.providers.stt.base import Transcript
from authorship_fixtures import H, SAVE, as_user, clinic_conn, legacy_document, save, team  # noqa: F401


def _names(rows):
    return [(r["patient_name"], r["doctor_name"]) for r in rows]


def _save_for(c, patient):
    return save(c, {**SAVE, "structured": {**SAVE["structured"], "patientName": patient, "opNo": ""}})


def test_today_defaults_to_my_prescriptions(team):
    c = as_user(team.client, team.rao)
    _save_for(c, "Asha")
    _save_for(as_user(c, team.mehta), "Bala")
    mine = as_user(c, team.rao).get("/api/v1/encounters/today")
    assert mine.status_code == 200
    assert _names(mine.json()) == [("Asha", "Dr. Rao")]
    assert c.get("/api/v1/encounters/today?scope=mine").json() == mine.json()


def test_whole_clinic_shows_every_prescription_with_its_authors_name(team):
    c = as_user(team.client, team.rao)
    _save_for(c, "Asha")
    _save_for(as_user(c, team.mehta), "Bala")
    legacy_document("Chitra")
    rows = c.get("/api/v1/encounters/today?scope=clinic").json()
    assert _names(rows) == [("Asha", "Dr. Rao"), ("Bala", "Dr. Mehta"), ("Chitra", "")]
    assert [r["author_id"] for r in rows] == [team.rao, team.mehta, None]


def test_today_rejects_an_unknown_scope(team):
    r = as_user(team.client, team.rao).get("/api/v1/encounters/today?scope=everyone")
    assert (r.status_code, r.json()) == (400, {"error": "scope must be mine or clinic"})


def test_single_mode_today_ignores_scope_and_keeps_the_old_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "single.db"))
    from doctor_dictation.api.app import create_app
    with TestClient(create_app()) as c:
        conn = dbmod.get_conn()
        eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "Asha", "", "OP-7"), op_no="OP-7")
        dbmod.save_document(conn, eid, "sha", {"rx": []})
        conn.close()
        for url in ("/api/v1/encounters/today", "/api/v1/encounters/today?scope=mine", "/api/v1/encounters/today?scope=clinic"):
            rows = c.get(url).json()
            assert [r["patient_name"] for r in rows] == ["Asha"], url
            assert set(rows[0]) == {"document_id", "encounter_id", "patient_name", "op_no", "created_at"}


class _Recorder:
    name = "recorder"
    available = staticmethod(lambda: True)

    def __init__(self):
        self.hints = []

    async def transcribe(self, audio, filename, hints=()):
        self.hints.append(list(hints))
        return Transcript(text="hello", engine="recorder")


def test_hints_come_from_the_signed_in_doctors_own_prescriptions(team, monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(stt_api, "make_stt", lambda settings: rec)
    override_settings(monkeypatch, stt_use_hints=True, stt_trim_silence=False, stt_hint_limit=12)
    with clinic_conn() as conn:
        for author, names in ((team.rao, ["Tamsulosin", "Tamsulosin"]), (team.mehta, ["Paracetamol"])):
            eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "", None), doctor_id=author)
            dbmod.save_document(conn, eid, "sha", {"rx": [{"name": n} for n in names]}, finalized_at=dbmod._utcnow())
    audio = {"audio": ("note.webm", b"RAWBYTES", "audio/webm")}
    c = team.client
    assert as_user(c, team.mehta).post("/api/transcribe", files=audio, headers=H).status_code == 200
    assert as_user(c, team.rao).post("/api/transcribe", files=audio, headers=H).status_code == 200
    mehta_hints, rao_hints = rec.hints
    assert mehta_hints[0] == "Paracetamol"        # all prescriptions together would put Tamsulosin (2 uses) first
    assert rao_hints[0] == "Tamsulosin"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_today_scope.py -q`
Expected: 4 failed, 1 passed (`test_single_mode_today_ignores_scope_and_keeps_the_old_shape` already holds; it pins single mode).

- [ ] **Step 3: Write the implementation**

In `doctor_dictation/api/persistence.py` replace the Today route (lines 91-100 of the original file)

```python
@router.get("/api/v1/encounters/today")
def list_today_encounters():
    """Saved documents for the server-local calendar day (the "Today" sidebar)."""
    conn = dbmod.get_conn()
    try:
        start, end = dbmod.local_day_bounds_utc()
        rows = dbmod.list_documents_between(conn, start, end)
        return [dict(r) for r in rows]
    finally:
        conn.close()
```

with

```python
@router.get("/api/v1/encounters/today")
def list_today_encounters(request: Request, scope: str = "mine"):
    """Saved documents for the server-local calendar day (the "Today" sidebar).

    Signed in: ``scope=mine`` (default) keeps the signed-in doctor's prescriptions, ``scope=clinic`` the whole
    clinic; rows gain ``author_id`` and ``doctor_name``. Single-database mode: every row, in the old shape.
    """
    if scope not in ("mine", "clinic"):
        return JSONResponse(status_code=400, content={"error": "scope must be mine or clinic"})
    ident = authorship.identity(request)
    conn = dbmod.get_conn()
    try:
        start, end = dbmod.local_day_bounds_utc()
        if ident is None:
            return [dict(r) for r in dbmod.list_documents_between(conn, start, end)]
        return adb.list_today(conn, start, end, ident.user_id if scope == "mine" else None)
    finally:
        conn.close()
```

In `doctor_dictation/api/stt.py` replace line 15

```python
from doctor_dictation.scope import NoScope
```

with

```python
from doctor_dictation.scope import NoScope, current_scope
```

and replace the head of `_doctor_top` (lines 20-24)

```python
def _doctor_top(limit: int) -> list[str]:
    """The doctor's most-used medicines; any database problem means no personalisation."""
    try:
        with closing(dbmod.get_conn()) as conn:
            return dbmod.top_medicines(conn, min(30, limit))
```

with

```python
def _doctor_top(limit: int) -> list[str]:
    """The signed-in doctor's most-used medicines (every prescription in single-database mode, where no one
    signs in); any database problem means no personalisation."""
    sc = current_scope()
    try:
        with closing(dbmod.get_conn()) as conn:
            return dbmod.top_medicines(conn, min(30, limit), doctor_id=sc.user_id if sc is not None else None)
```

The `except NoScope: raise` and the generic `except` below it are unchanged, so `tests/test_startup.py::test_transcribe_without_a_scope_is_401_not_an_unpersonalised_success` still sees `NoScope`. (`_doctor_top` runs in `asyncio.to_thread`, which copies the scope, `api/stt.py:40`.)

- [ ] **Step 4: Run the tests, then the suite**

Run: `.venv/bin/python -m pytest tests/test_today_scope.py tests/test_today.py tests/test_transcribe_acc2.py tests/test_startup.py -q`
Expected: all passed (5 new).
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 24` passed, 1 skipped.

- [ ] **Step 5: Leave uncommitted.** New: `tests/test_today_scope.py`; modified: `api/persistence.py`, `api/stt.py`.

---

### Task 4: Profile split (Clinic details + My details) and the template audit actor

**Files:**
- Create: `tests/test_profile_split.py`
- Modify: `doctor_dictation/api/profile.py` (whole file, 51 lines), `doctor_dictation/api/templates.py` (`_actor`, lines 49-50 only)

**Interfaces:**
- Consumes: Task 1 `db.details.*`; Task 2 `api.authorship.identity` and `tests/authorship_fixtures.py`; `tests/template_fixtures.GOOD_LAYOUT`; `db.templates.create_template_draft` (`doctor_dictation/db/templates.py:7`); `sessions.Identity`.
- Produces: `GET /api/v1/profile` signed in = the user's three doctor fields + the clinic's three fields, same six flat keys and order; `PUT /api/v1/profile` signed in writes the clinic fields to `clinic_profile` (doctor columns untouched) and the doctor fields to the signed-in user's row; every field at most 300 characters (422 otherwise) in both modes; `profile_dict(row)` unchanged (still used by `api/templates.py:147`). `api/templates._actor(request)` returns `request.state.identity.username` or None.

- [ ] **Step 1: Write the failing tests**

`tests/test_profile_split.py`:

```python
"""Profile split (M3 Task 4, spec 8.1) and the template routes' audit actor. Offline."""
from fastapi.testclient import TestClient
from starlette.requests import Request

from doctor_dictation.api import templates as templates_api
from doctor_dictation.db import details
from doctor_dictation.db import templates as tdb
from doctor_dictation.sessions import Identity
from authorship_fixtures import CLINIC, H, MEHTA, OLD, RAO, as_user, clinic_conn, team  # noqa: F401
from template_fixtures import GOOD_LAYOUT

MINE = {"doctor_name": "Dr. M. Mehta", "qualifications": "MD", "reg_no": "M-999"}
NEW_CLINIC = {"clinic_name": "Rao & Mehta Clinic", "address": "2 Main Road", "phone": "040 222"}


def test_signed_in_profile_is_my_details_plus_the_clinic_details(team):
    for uid, me in ((team.rao, RAO), (team.mehta, MEHTA)):
        r = as_user(team.client, uid).get("/api/v1/profile")
        assert r.status_code == 200 and r.json() == {**me, **CLINIC}
        assert list(r.json()) == ["doctor_name", "qualifications", "reg_no", "clinic_name", "address", "phone"]


def test_put_shares_the_clinic_details_and_keeps_my_details_mine(team):
    c = as_user(team.client, team.mehta)
    r = c.put("/api/v1/profile", json={**MINE, **NEW_CLINIC}, headers=H)
    assert (r.status_code, r.json()) == (200, {**MINE, **NEW_CLINIC})
    assert as_user(c, team.rao).get("/api/v1/profile").json() == {**RAO, **NEW_CLINIC}
    with clinic_conn() as conn:
        assert details.my_details(conn, team.mehta) == MINE
        assert details.saved_doctor_details(conn) == OLD          # the shared row's doctor columns are untouched


def test_profile_fields_are_length_checked(team, tmp_path, monkeypatch):
    long = {**MINE, "address": "x" * 301}
    assert as_user(team.client, team.rao).put("/api/v1/profile", json=long, headers=H).status_code == 422
    monkeypatch.setenv("MULTI_CLINIC", "0")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "single.db"))
    from doctor_dictation.api.app import create_app
    with TestClient(create_app()) as c:
        assert c.put("/api/v1/profile", json=long).status_code == 422
        assert c.put("/api/v1/profile", json={**MINE, "address": "x" * 300}).status_code == 200


def _request(state):
    scope = {"type": "http", "method": "POST", "path": "/", "headers": []}
    if state is not None:
        scope["state"] = state
    return Request(scope)


def test_template_actor_is_the_signed_in_username_and_none_in_single_mode():
    me = Identity("rao", 7, "dr.mehta", "doctor")
    assert templates_api._actor(_request({"identity": me})) == "dr.mehta"
    assert templates_api._actor(_request({})) is None
    assert templates_api._actor(_request(None)) is None


def test_template_discard_is_audited_with_the_signed_in_username(team):
    with clinic_conn() as conn:
        tid = tdb.create_template_draft(conn, GOOD_LAYOUT)
    r = as_user(team.client, team.mehta).delete(f"/api/v1/templates/{tid}", headers=H)
    assert r.status_code == 204
    with clinic_conn() as conn:
        row = conn.execute("SELECT actor FROM audit_log WHERE action = 'template_discard'").fetchone()
    assert row["actor"] == "dr.mehta"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_profile_split.py -q`
Expected: 4 failed, 1 passed. `test_template_discard_is_audited_with_the_signed_in_username` already passes because `db.log_audit` fills a missing actor from the scope (`doctor_dictation/db/__init__.py:271-272`); it pins the end-to-end result, while the `_actor` unit test is the one that fails first (it returns None today: the middleware never sets `request.state.username`).

- [ ] **Step 3: Write the implementation**

Replace the whole of `doctor_dictation/api/profile.py` with:

```python
"""Profile endpoints: the six fields printed on the sheet.

Signed in (multi-clinic mode) they come from two places (spec 8.1): the clinic details (clinic name, address,
phone) are shared on ``clinic_profile``; "my details" (doctor name, qualifications, registration no.) are the
signed-in user's own ``users`` row. GET and PUT keep the same six flat keys in both modes. Single-database mode
(no one signs in) keeps the one shared row, exactly as before.
"""
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from doctor_dictation import db as dbmod
from doctor_dictation.api.authorship import identity
from doctor_dictation.db import details

router = APIRouter()
MAX_FIELD = 300


class ProfileBody(BaseModel):
    doctor_name: str = Field("", max_length=MAX_FIELD)
    qualifications: str = Field("", max_length=MAX_FIELD)
    reg_no: str = Field("", max_length=MAX_FIELD)
    clinic_name: str = Field("", max_length=MAX_FIELD)
    address: str = Field("", max_length=MAX_FIELD)
    phone: str = Field("", max_length=MAX_FIELD)


def profile_dict(row) -> dict:
    """Serialise a clinic-profile row, defaulting every field to "" (unset)."""
    keys = ("doctor_name", "qualifications", "reg_no", "clinic_name", "address", "phone")
    if row is None:
        return {k: "" for k in keys}
    return {k: row[k] for k in keys}


def _split(conn, user_id) -> dict:
    return {**details.my_details(conn, user_id), **details.clinic_details(conn)}


@router.get("/api/v1/profile")
def get_profile(request: Request):
    ident = identity(request)
    conn = dbmod.get_conn()
    try:
        if ident is None:
            return profile_dict(dbmod.get_profile(conn))
        return _split(conn, ident.user_id)
    finally:
        conn.close()


@router.put("/api/v1/profile")
def put_profile(req: ProfileBody, request: Request):
    ident = identity(request)
    conn = dbmod.get_conn()
    try:
        if ident is None:
            dbmod.save_profile(
                conn,
                doctor_name=req.doctor_name,
                qualifications=req.qualifications,
                reg_no=req.reg_no,
                clinic_name=req.clinic_name,
                address=req.address,
                phone=req.phone,
            )
            return profile_dict(dbmod.get_profile(conn))
        details.save_clinic_details(conn, req.clinic_name, req.address, req.phone)
        details.save_my_details(conn, ident.user_id, req.doctor_name, req.qualifications, req.reg_no)
        return _split(conn, ident.user_id)
    finally:
        conn.close()
```

In `doctor_dictation/api/templates.py` replace only (lines 49-50)

```python
def _actor(request: Request):
    return getattr(request.state, "username", None)
```

with

```python
def _actor(request: Request):
    """The signed-in username for the audit row (set by the session middleware); None in single-database mode."""
    ident = getattr(request.state, "identity", None)
    return ident.username if ident is not None else None
```

- [ ] **Step 4: Run the tests, then the suite**

Run: `.venv/bin/python -m pytest tests/test_profile_split.py tests/test_profile.py tests/test_template_routes.py tests/test_template_save.py -q`
Expected: all passed (5 new; `tests/test_profile.py` unchanged).
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 29` passed, 1 skipped.

- [ ] **Step 5: Leave uncommitted.** New: `tests/test_profile_split.py`; modified: `api/profile.py`, `api/templates.py`.

---

### Task 5: Browser: view-only sheet, Today toggle, Profile split

**Files:**
- Create: `frontend/authorship.js`, `tests/test_frontend_authorship.py`
- Modify: `frontend/index.html` (stylesheet line 7, sidebar line 31, doc pane line 74, Profile form lines 116-135, scripts lines 204-205), `frontend/app.js` (seven hooks at lines 244-246, 264, 316, 410, 540, 1015, 1214), `frontend/styles.css` (append at the end)

**Interfaces:**
- Consumes: Task 2 `GET /api/v1/documents/{id}` `author`/`can_edit` and the `document_id` field of `/api/v1/correct`; Task 3 `?scope=` and row `doctor_name`; Task 4 flat profile; `GET /api/v1/auth/me` (200 signed in, 404 single mode; `doctor_dictation/api/auth.py:99-106`); app.js globals `state`, `loadToday`, `renderProfileHeader` (`frontend/app.js:32`, `132`, `262`). Element ids `recBtn`, `saveBtn`, `confirmAllBtn`, `sheet`, `resaveNote`, `correctingCue`, `cDoctor`, `cReg` (`frontend/index.html`).
- Produces (`window.Authorship`): `onOpen(doc)`, `clear()`, `enforce()`, `isViewOnly()`, `todayQuery()`, `authorLabel(row)`. New element ids `viewOnlyBanner`, `todayScope`, `profClinicPart`, `profMinePart`.

The profile input ids (`profDoctor`, `profQual`, `profReg`, `profClinic`, `profAddress`, `profPhone`) do not change, so `letterhead.js` (its dirty check reads them, `frontend/letterhead.js:65-73`) and `fillProfileForm`/`saveProfile` (`frontend/app.js:146-212`) keep working; the M4 letterhead section of the dialog is untouched.

- [ ] **Step 1: Write the failing tests**

`tests/test_frontend_authorship.py`:

```python
"""Static checks for the M3 browser wiring (view-only sheet, Today toggle, Profile split). No browser needed;
the manual checklist in the M3 plan covers behaviour."""
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def test_authorship_js_loads_after_auth_js_and_before_app_js():
    html = _read("index.html")
    assert html.index("auth.js") < html.index("authorship.js") < html.index("app.js")


def test_index_has_the_banner_and_the_today_toggle():
    html = _read("index.html")
    assert 'id="viewOnlyBanner"' in html and html.index('id="viewOnlyBanner"') < html.index('id="sheet"')
    toggle = html.split('id="todayScope"')[1].split("</div>")[0]
    assert "hidden" in html.split('id="todayScope"')[1].split(">")[0]          # shown only once signed in
    assert 'data-scope="mine"' in toggle and "My prescriptions" in toggle
    assert 'data-scope="clinic"' in toggle and "Whole clinic" in toggle


def test_profile_dialog_is_split_into_clinic_details_and_my_details():
    html = _read("index.html")
    clinic = html.split('id="profClinicPart"')[1].split("</fieldset>")[0]
    mine = html.split('id="profMinePart"')[1].split("</fieldset>")[0]
    assert "Clinic details" in clinic and all(f'id="{i}"' in clinic for i in ("profClinic", "profAddress", "profPhone"))
    assert "My details" in mine and all(f'id="{i}"' in mine for i in ("profDoctor", "profQual", "profReg"))


def test_authorship_js_shows_the_banner_and_locks_the_sheet():
    js = _read("authorship.js")
    assert "'s prescription: view only" in js
    for needle in ('"recBtn"', '"saveBtn"', "contentEditable", "can_edit === false", "?scope=", "/api/v1/auth/me"):
        assert needle in js, needle
    assert re.search(r"return \{[^}]*onOpen[^}]*clear[^}]*enforce[^}]*isViewOnly[^}]*todayQuery[^}]*authorLabel", js)


def test_app_js_calls_authorship_only_through_a_guard():
    js = _read("app.js")
    calls = re.findall(r"Authorship\.(\w+)\(", js)
    assert sorted(set(calls)) == ["authorLabel", "clear", "enforce", "isViewOnly", "onOpen", "todayQuery"]
    for line in (ln for ln in js.splitlines() if "Authorship." in ln):
        assert "window.Authorship" in line, line


def test_a_correction_names_the_document_it_corrects():
    js = _read("app.js")
    assert re.search(r'postJson\("/api/v1/correct", \{[^}]*document_id: state\.documentId', js)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_frontend_authorship.py -q`
Expected: 6 failed.

- [ ] **Step 3: Write the implementation**

`frontend/authorship.js`:

```javascript
"use strict";
// Authorship in the browser (spec 7.1, 7.2). A colleague's prescription opens read-only (banner, mic and
// Save off, sheet not editable, Print on), and the Today list switches between "My prescriptions" and
// "Whole clinic". Loaded after auth.js and BEFORE app.js: app.js calls in only at run time, always through
// `window.Authorship`. The server enforces every rule (403); this file only reflects it. Single-database
// mode sends no author data, so nothing here changes the page there.
window.Authorship = (function () {
  const el = (id) => document.getElementById(id);
  const busy = () => typeof state !== "undefined" && !!state.working;   // app.js's state
  let viewOnly = null;      // the author's name while a colleague's prescription is on the sheet
  let scope = "mine";       // the Today list: "mine" | "clinic"

  // The sheet header shows the doctor who prints on this prescription: its author.
  function showAuthor(a) {
    const dr = el("cDoctor"), reg = el("cReg");
    if (dr) dr.textContent = [a.doctor_name || a.name, a.qualifications].filter(Boolean).join(" ");
    if (reg) reg.textContent = a.reg_no ? "Reg. No: " + a.reg_no : "";
  }

  // Re-applied from app.js refreshPrintButton(), which runs after every setWorking/setPrinting: those
  // re-enable the mic and Save, so view-only must win again each time.
  function enforce() {
    const banner = el("viewOnlyBanner");
    if (banner) {
      banner.hidden = !viewOnly;
      banner.textContent = viewOnly ? viewOnly + "'s prescription: view only" : "";
    }
    if (!viewOnly) return;
    ["recBtn", "saveBtn", "confirmAllBtn"].forEach((id) => { const b = el(id); if (b) b.disabled = true; });
    const sheet = el("sheet");
    if (sheet) {
      sheet.classList.add("view-only");
      sheet.querySelectorAll('[contenteditable="true"]').forEach((n) => { n.contentEditable = "false"; n.dataset.ro = "1"; });
      sheet.querySelectorAll(".x-btn, .confirm-btn").forEach((b) => { b.disabled = true; });
    }
    const note = el("resaveNote");
    if (note) note.hidden = true;
    const cue = el("correctingCue");
    if (cue) cue.hidden = true;
  }

  // Leave view-only (New patient, or opening a prescription you may edit).
  function clear() {
    const was = viewOnly;
    viewOnly = null;
    const sheet = el("sheet");
    if (sheet) {
      sheet.classList.remove("view-only");
      sheet.querySelectorAll('[data-ro="1"]').forEach((n) => { n.contentEditable = "true"; delete n.dataset.ro; });
      sheet.querySelectorAll(".x-btn, .confirm-btn").forEach((b) => { b.disabled = busy(); });
    }
    if (was) {
      ["recBtn", "saveBtn"].forEach((id) => { const b = el(id); if (b) b.disabled = busy(); });
      const all = el("confirmAllBtn");
      if (all) all.disabled = false;
    }
    if (typeof renderProfileHeader === "function" && typeof state !== "undefined") renderProfileHeader(state.profile || {});
    enforce();
  }

  // app.js openDocument() hands over the GET /api/v1/documents/{id} body once the sheet is rendered.
  function onOpen(doc) {
    clear();
    const a = doc && doc.author;
    if (!a) return;                                   // single-database mode: no author data
    showAuthor(a);
    if (doc.can_edit === false) viewOnly = a.name || "Another doctor";
    enforce();
  }

  function isViewOnly() { return viewOnly !== null; }
  function todayQuery() { return "?scope=" + scope; }
  // Whole clinic rows name their author; "My prescriptions" rows are all yours, so they do not.
  function authorLabel(row) { return scope === "clinic" && row && row.doctor_name ? row.doctor_name : ""; }

  function setScope(next) {
    scope = next === "clinic" ? "clinic" : "mine";
    document.querySelectorAll("#todayScope [data-scope]").forEach((b) => {
      b.setAttribute("aria-pressed", String(b.dataset.scope === scope));
    });
    if (typeof loadToday === "function") loadToday();
  }

  async function init() {
    const box = el("todayScope");
    if (!box) return;
    box.addEventListener("click", (e) => {
      const b = e.target && e.target.closest ? e.target.closest("[data-scope]") : null;
      if (b) setScope(b.dataset.scope);
    });
    let signedIn = false;
    try { signedIn = (await fetch("/api/v1/auth/me")).status === 200; } catch (e) { signedIn = false; }
    box.hidden = !signedIn;                           // single-database mode (404): no toggle
  }
  init();

  return { onOpen, clear, enforce, isViewOnly, todayQuery, authorLabel };
})();
```

Why `enforce()` lives in `refreshPrintButton`: `setWorking(false)` sets `recBtn.disabled`/`saveBtn.disabled` and then calls `refreshPrintButton()` (`frontend/app.js:116-118`), and `setPrinting` re-enables the mic before its own `refreshPrintButton()` (`frontend/app.js:1140-1142`); hooking there makes view-only win after both. `setWorking` re-enables the sheet's `.x-btn` after that call (`frontend/app.js:124`), which is why the CSS below also hides the delete and confirm buttons on a view-only sheet.

`frontend/index.html`, five replacements:

1. Line 7: `<link rel="stylesheet" href="styles.css?v=6" />` becomes `<link rel="stylesheet" href="styles.css?v=7" />`.

2. Line 31: replace

```html
    <h2 class="pane-title">Today</h2>
```

with

```html
    <h2 class="pane-title">Today</h2>
    <div id="todayScope" class="today-scope" role="group" aria-label="Which prescriptions to show" hidden>
      <button type="button" data-scope="mine" aria-pressed="true">My prescriptions</button>
      <button type="button" data-scope="clinic" aria-pressed="false">Whole clinic</button>
    </div>
```

3. Line 74: replace

```html
    <div id="resaveNote" class="resave-note no-print" hidden></div>
```

with

```html
    <div id="viewOnlyBanner" class="view-only-banner no-print" role="status" hidden></div>
    <div id="resaveNote" class="resave-note no-print" hidden></div>
```

4. Lines 116-135 (the dialog title and the six fields; the Letterhead section from line 136 on stays as it is): replace

```html
    <h2 id="profilePanelTitle">Clinic profile</h2>
    <p class="panel-hint">These details print at the top of every prescription.</p>
    <label class="field">Doctor name
      <input id="profDoctor" type="text" autocomplete="name" />
    </label>
    <label class="field">Qualifications
      <input id="profQual" type="text" />
    </label>
    <label class="field">Registration no.
      <input id="profReg" type="text" />
    </label>
    <label class="field">Clinic name
      <input id="profClinic" type="text" autocomplete="organization" />
    </label>
    <label class="field">Address
      <textarea id="profAddress" rows="2"></textarea>
    </label>
    <label class="field">Phone
      <input id="profPhone" type="tel" autocomplete="tel" />
    </label>
```

with

```html
    <h2 id="profilePanelTitle">Profile</h2>
    <p class="panel-hint">These details print at the top of every prescription.</p>
    <fieldset id="profClinicPart" class="prof-part">
      <legend>Clinic details</legend>
      <p class="panel-hint">Shared by everyone in this clinic.</p>
      <label class="field">Clinic name
        <input id="profClinic" type="text" autocomplete="organization" />
      </label>
      <label class="field">Address
        <textarea id="profAddress" rows="2"></textarea>
      </label>
      <label class="field">Phone
        <input id="profPhone" type="tel" autocomplete="tel" />
      </label>
    </fieldset>
    <fieldset id="profMinePart" class="prof-part">
      <legend>My details</legend>
      <p class="panel-hint">Yours only: they print on the prescriptions you write.</p>
      <label class="field">Doctor name
        <input id="profDoctor" type="text" autocomplete="name" />
      </label>
      <label class="field">Qualifications
        <input id="profQual" type="text" />
      </label>
      <label class="field">Registration no.
        <input id="profReg" type="text" />
      </label>
    </fieldset>
```

5. Lines 204-205: replace

```html
<script src="auth.js?v=1"></script>
<script src="app.js?v=18"></script>
```

with

```html
<script src="auth.js?v=1"></script>
<script src="authorship.js?v=1"></script>
<script src="app.js?v=19"></script>
```

`frontend/app.js`, seven hooks (each `old` text appears exactly once):

1. `loadToday` (line 264): replace

```javascript
    const r = await fetch("/api/v1/encounters/today");
```

with

```javascript
    const r = await fetch("/api/v1/encounters/today" + (window.Authorship ? Authorship.todayQuery() : ""));
```

2. `renderToday` (lines 245-246): replace

```javascript
    if (t) bits.push(t);
    meta.textContent = bits.join(" · ");
```

with

```javascript
    if (t) bits.push(t);
    const who = window.Authorship ? Authorship.authorLabel(row) : "";
    if (who) bits.push(who);
    meta.textContent = bits.join(" · ");
```

3. `openDocument` (lines 315-317): replace

```javascript
    renderSheet(state.structured);
    updateResaveNote();
    highlightToday();
```

with

```javascript
    renderSheet(state.structured);
    updateResaveNote();
    if (window.Authorship) Authorship.onOpen(j);   // a colleague's prescription opens view-only
    highlightToday();
```

4. End of `refreshPrintButton` (lines 409-411): replace

```javascript
    : state.dirty ? "Save your changes first"
    : "Print this prescription (letterhead PDF)";
}
```

with

```javascript
    : state.dirty ? "Save your changes first"
    : "Print this prescription (letterhead PDF)";
  if (window.Authorship) Authorship.enforce();      // setWorking/setPrinting re-enable the mic and Save
}
```

5. `applyCorrection` (line 540): replace

```javascript
    const j = await postJson("/api/v1/correct", { transcript, current_form: current }, CORRECT_TIMEOUT_MS);
```

with

```javascript
    const j = await postJson("/api/v1/correct", { transcript, current_form: current, document_id: state.documentId }, CORRECT_TIMEOUT_MS);
```

6. `saveDocument` (lines 1014-1015): replace

```javascript
async function saveDocument() {
  if (state.working) return;
```

with

```javascript
async function saveDocument() {
  if (state.working || (window.Authorship && Authorship.isViewOnly())) return;
```

7. `newPatient` (lines 1213-1215): replace

```javascript
  renderTranscript();
  updateResaveNote();
  sheetEl.classList.add("empty");
```

with

```javascript
  renderTranscript();
  updateResaveNote();
  if (window.Authorship) Authorship.clear();
  sheetEl.classList.add("empty");
```

A 403 from Save or a correction needs no new code: `postJson` throws the server's `error` text (`frontend/app.js:457-461`) and the callers show it with `showError`.

Append to the end of `frontend/styles.css` (after the closing `}` of the `@media print` block):

```css

/* Authorship (M3): Today scope toggle, view-only banner, Profile split into two parts. */
.today-scope { display:flex; gap:4px; margin:0 0 10px; }
.today-scope[hidden] { display:none; }
.today-scope button { flex:1; font-size:12px; padding:4px 6px; border-radius:6px; border:1px solid var(--soft); background:transparent; }
.today-scope button[aria-pressed="true"] { background:#eaf1ff; border-color:#bcd2ff; font-weight:600; }
.view-only-banner { font-size:13px; font-weight:600; color:#7a4b00; background:#fff6e0; border:1px solid #f0d28a; border-radius:8px; padding:6px 10px; margin-bottom:10px; }
#sheet.view-only .x-btn, #sheet.view-only .confirm-btn { display:none; }
.prof-part { border:1px solid var(--soft); border-radius:8px; margin:0; padding:8px 12px 12px; display:flex; flex-direction:column; gap:8px; }
.prof-part legend { font-size:13px; font-weight:600; color:var(--ink); padding:0 4px; }
```

(`.today-scope[hidden]` is needed because `display:flex` on the class would otherwise override the `hidden` attribute.)

- [ ] **Step 4: Run the tests, a syntax check, then the suite**

Run: `.venv/bin/python -m pytest tests/test_frontend_authorship.py tests/test_frontend_auth.py tests/test_closed_by_default.py -q`
Expected: all passed (6 new).
Run: `node -e "const fs=require('fs'); for (const f of ['frontend/authorship.js','frontend/app.js']) new Function(fs.readFileSync(f,'utf8')); console.log('syntax ok')"` (skip if `node` is not installed; say so in the report)
Expected: `syntax ok`.
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 35` passed, 1 skipped.

- [ ] **Step 5: Manual browser checklist (browser behaviour is not automated here; the Playwright skill can drive it).** Setup, from the repo root, in a throwaway data folder:

```bash
export MULTI_CLINIC=1 DATA_DIR=/tmp/dd-m3 DEV_INSECURE_SESSION_SECRET=1
.venv/bin/python -m doctor_dictation.admin create-clinic --slug rao --name "Rao Clinic" --first-user dr.rao --display-name "Dr. Rao"
.venv/bin/python -m doctor_dictation.admin create-user --clinic rao --username dr.mehta --display-name "Dr. Mehta"
.venv/bin/python -m uvicorn doctor_dictation.main:app --port 8765
```

Sign in as each user in a separate browser profile (each changes the temporary password once), then check:

1. Rao: Profile shows two sections, "Clinic details" and "My details". Enter clinic name/address/phone and "Dr. Rao", "MBBS", "R-111"; Save. Mehta's Profile shows the same clinic details and empty My details; Mehta enters "Dr. Mehta" details and saves; Rao's My details are unchanged after a reload.
2. Rao dictates (or types into a fresh sheet) and saves one prescription. Rao's Today shows it under "My prescriptions"; Mehta's "My prescriptions" is empty; Mehta's "Whole clinic" shows it with "Dr. Rao" in the row's meta line.
3. Mehta opens Rao's prescription: the banner reads "Dr. Rao's prescription: view only"; the sheet header shows Dr. Rao's name and registration no.; the mic and Save are disabled; clicking into the patient name or a medicine cell does not let him type; the delete (x) and Confirm buttons are hidden; Print is enabled and the PDF shows Dr. Rao's details and the clinic's details.
4. While still view-only, press Print, wait for it to finish, and confirm the mic and Save are still disabled (the `setPrinting` path).
5. Mehta presses "New patient": the banner disappears, the header shows his own details, the mic works, a new prescription saves under his name.
6. Rao opens his own prescription from Today: no banner, editable, Save updates it in place (the existing "Editing today's document" note shows).
7. Single mode still looks as before: stop the server, `unset MULTI_CLINIC DATA_DIR`, start it again: no Today toggle, no banner, the Profile dialog shows the two sections but saves all six fields to the one shared profile.

- [ ] **Step 6: Leave uncommitted.** New: `frontend/authorship.js`, `tests/test_frontend_authorship.py`; modified: `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`.

---

## Self-review (against the spec)

- **6.3 `can()` wiring:** every document route calls `policy.can` through `api/authorship.check`/`check_document`: view (`GET /documents/{id}`), reprint (`GET /documents/{id}/pdf`), edit (re-save, correct with `document_id`). Task 2 `test_every_document_route_asks_policy_can`. `policy.py` itself is unchanged.
- **7.1 authorship:** first save sets `encounters.doctor_id` and `documents.finalized_by` (Task 2); re-save keeps the author and records the saver (Task 2, `adb.set_finalized_by`); non-author edit/correct/re-save get the exact 403 (Task 2); view and reprint are open to the clinic (Task 2); the view-only sheet with the banner, mic and Save disabled, edits blocked and Print enabled (Task 5). Pre-M3 documents with no author stay editable by anyone (Task 2, legacy tests).
- **7.2 Today:** `?scope=mine|clinic`, default `mine`, rows gain `doctor_name` (and `author_id`) (Task 3); the sidebar toggle and author names on clinic rows (Task 5).
- **7.3 hints:** `top_medicines(conn, limit, doctor_id=None)` filters through `encounters.doctor_id` (Task 1); the STT hint builder passes the signed-in doctor via the scope (Task 3).
- **7.4 audit:** the actor already comes from the scope (`db/__init__.py:271-272`, M2a); M3 adds no new audit action (none of the spec's new actions belong to M3) and fixes the template routes' `_actor` to read the identity (Task 4). `finalize`/`resave` rows now carry the signed-in username through the scope.
- **8.1 Profile:** GET/PUT return and accept both parts with the same six keys (Task 4); clinic details shared on `clinic_profile`, my details on the user's row; the dialog shows two sections (Task 5). Printing resolves doctor fields from the author and clinic fields from the clinic (Task 1 `print_profile`, Task 2 route tests) on the default PDF path; the letterhead path is M4's (Assumption 1). OP prefix in Clinic details is M4's.
- **12 migrations:** `006_doctor_details_to_users.sql`, idempotent, existing rows stay valid (Task 1); `tests/test_db.py` migration list updated.
- **Carry-overs:** (a) `_actor` reads `request.state.identity`, tested (Task 4); (b) author-None documents stay editable (Task 2); (c) `can()` called by every route and the exact 403 body (Task 2); (d) doctor fields from the author, clinic fields from the clinic, seam to M4 stated (Assumption 1); (e) migration 006 plus GET/PUT split, single mode unchanged with `tests/test_profile.py` untouched (Tasks 1 and 4).
- **Placeholder scan:** none; every step shows its code or command.
- **Type consistency:** `document_author` returns a dict with `author_id`, which is exactly what `policy._author_id` reads (`doctor_dictation/policy.py:8-11`); `_pdf_inputs` takes `encounter_id` as its 4th argument at both call sites.
- **Test count:** 9 + 10 + 5 + 5 + 6 = 35 (counted by test function).

## Not in this plan

- The letterhead side of authorship: the author's own letterhead, the doctors block, render-time "live values win over the snapshot", Accept writing doctor fields to the user's row, the OP prefix field (all M4).
- The Team (Users) screen and its routes (M5); seed-demo and the isolation sweep (M6).
- A `profile.edit` policy action or any role rule (spec 3 non-goal; open question 2).
- Forcing `POST /api/v1/encounters` to ignore a body `doctor_id` (Assumption 6; not an edit path).
- Showing the author's name on the "My prescriptions" rows, or an author filter beyond mine/clinic.
- Automated browser tests (the manual checklist in Task 5 stands in; M6 adds browser evidence).
