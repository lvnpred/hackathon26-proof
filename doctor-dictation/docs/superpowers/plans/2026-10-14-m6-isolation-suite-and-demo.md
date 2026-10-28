# M6: Isolation suite, seed-demo, demo script, browser evidence

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove, automatically and in a browser, that two clinics and three doctors never see each other's data: an operator `seed-demo` command that builds the demo world, an isolation test suite that sweeps every route and file path as the wrong clinic, the five-minute demo script, and a Playwright run that saves screenshots for a person to read.

**Architecture:** One new production module, `doctor_dictation/admin_demo.py` (the `seed-demo` command, registered in the existing CLI with one line). Everything else is tests and tooling. The suite shares one fixture module, `tests/isolation_fixtures.py`: it seeds the demo world with `admin_demo.seed_demo()`, signs in one `TestClient` per doctor, and puts a **fake Chromium behind the real PDF worker thread**. A stored "PDF" is therefore `%PDF-fake` plus the exact sheet HTML that would have printed, so tests can assert on printed names. Every interface this plan assumes from M3, M4 or M5 is one small helper in that module (or one function in `admin_demo.py`), tagged `A1`..`A15`; if a sibling plan named something differently, the implementer changes that helper, never the tests. The browser evidence is `scripts/demo_browser.py` (Playwright's Python API, already installed for PDF rendering). It drives three browser contexts through the section 13.2 demo against a running server and writes into the git-ignored `.superpowers/demo-evidence/`.

**Tech Stack:** Python 3.11+, pytest, FastAPI `TestClient`, stdlib `sqlite3`, Pillow (already a dependency) for the demo logos, Playwright (already in `.venv`, `requirements-pdf.txt`). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-14-multi-clinic-multi-doctor-design.md` sections 11 (`seed-demo`), 13.1 (automated isolation proof), 13.2 (demo script) and 14 (M6 row). **Requires M3, M4 and M5 built** (`docs/superpowers/plans/2026-10-14-m3-authorship-and-profile-split.md`, `...-m4-letterhead-scope-and-op-prefix.md`, `...-m5-team-screen.md`) on top of M1, M2a, M2b and M2c.

**Plan 7 of 7 (M6).** The suite was 597 passed, 1 skipped at `ae5864c`; M2c, M3, M4 and M5 add their own. Before Task 1 run `.venv/bin/python -m pytest tests/ -q` and note the count `N`. **This plan adds 59 tests** (9 + 7 + 7 + 9 + 9 + 7 + 6 + 3 + 2) and edits no existing test, so the count after it must be `N + 59`. The one exception is spelled out in Tasks 3 and 5. If finding F1 or F2 is still open, that one test is marked `xfail(strict=True)` and the run reads `N + 58 passed, 1 xfailed`, or `N + 57 passed, 2 xfailed`. The second is the expected result if M3 and M4 are built exactly as planned: neither plan fixes its finding (see Findings).

## Decision: fixed demo passwords (the brief asked to decide and justify)

`seed-demo` gives the three demo doctors **fixed, published passwords** (`demo-rao-pass-1`, `demo-mehta-pass-1`, `demo-iyer-pass-1`) and clears `must_change_password`. It does not print temporary passwords.

- **Why:** the section 13.2 demo is five minutes with two or three windows. `scripts/demo_browser.py` and the isolation fixture must sign in without a person copying passwords from the terminal or doing three forced password changes. Temporary passwords would also make the browser evidence impossible to automate.
- **Why it is safe enough:** it is demo-only by three guards. (1) It refuses unless `DEMO_MODE=1`, exactly. (2) It refuses a data folder that already has **any** clinic, so it can never add known-password accounts to a real installation. (3) Every record is fake. The passwords live in one place (`admin_demo.DOCTORS`). The browser script imports them from there, and a test checks it does not copy them. The CLI prints a `DEMO ONLY` warning.

## Deliberate differences from the spec

- **`seed-demo` also refuses a non-empty data folder** (any registered clinic, or a taken demo username). The spec names only the `DEMO_MODE=1` guard; the extra guard is what makes fixed passwords acceptable.
- **"Edit" is tested as re-save.** There is no separate edit route: the sheet is edited in the browser and persisted by `POST /api/v1/documents` with `document_id` (`doctor_dictation/api/persistence.py:152-276`). The suite checks re-save and correction (`/api/v1/correct`).
- **The route sweep asserts exactly 404 for an id only Clinic A has.** Spec 13.1 allows "404 or 403" in general and says "an id existing only in A returns 404 in B". Every swept id exists only in A, so the sweep demands 404. 403 belongs to the doctor-level tests inside one clinic.
- **The demo script is a README section plus a runnable browser script**, not a new document (user rule: no new documentation files). The README section is the person-run version; `scripts/demo_browser.py` is the automated one.
- **Browser evidence saves the PDFs as files** next to the screenshots. Headless Chromium cannot show its PDF viewer, so a screenshot of a PDF tab would be blank.

## Global Constraints

- **Production code:** only the NEW `doctor_dictation/admin_demo.py` and three one-line edits in `doctor_dictation/admin.py` (import, docstring, registration; 221 lines today, about 223 after). No route, middleware, template, PDF or DB code is changed. If a test exposes a gap in M3, M4 or M5, do not fix production code: report it as a finding for that plan. Only F1 and F2 below get the `xfail(strict=True)` treatment, and only as written in their task.
- Never run `git commit`, `git add` or `git push` (user rule). Each task ends with "Leave uncommitted".
- Every file stays under 500 lines (`tests/test_file_sizes.py` checks the package; keep tests and the script under it too).
- Tests are offline: stub LLM (`LLM_PROVIDER=stub` through `override_settings`), stub STT (`stt_chain=("stub",)`), and a fake browser behind `pdf.renderer.ChromiumPoolRenderer`. They never touch `doctor_dictation/data/`: every test uses the `multi` fixture (`tests/conftest.py:12-19`), directly or through `world`.
- `tests/isolation_fixtures.py` is a helper module (like `tests/template_fixtures.py`), not collected by pytest. Test modules import the `world` fixture by name: `from isolation_fixtures import world  # noqa: F401`.
- Never call the `sql()` inspection helper inside an `opened_files(...)` spy window: it opens a database itself and would pollute the record.

## Assumptions (interfaces from sibling plans; one helper each)

The M3, M4 and M5 plans were written alongside this one. Each row below was checked against the sibling plan as written; the source column cites it. Task 0 checks each row again against the **built** code before any test is written. If one differs, change **only** the named helper or function and say so in the report.

| # | From | Interface (confirmed in the sibling plan) | Where it lives in this plan |
|---|---|---|---|
| A1 | M3 | The author is `encounters.doctor_id`; `documents.finalized_by` is the last saver. A pre-M3 prescription keeps `doctor_id` NULL on re-save and records the saver (M3 plan, "Deliberate differences" and Task 1 `db/authorship.py`). | `admin_demo._prescription` |
| A2 | M3 | A colleague's re-save answers `403 {"error": "This prescription belongs to <author name>. You can view and reprint it."}`, where the name is `author_label`: doctor name, else display name, else username (M3 plan, Global Constraints). For the demo that is `Dr. A. Rao`. The 403 comes before the verify gate. | `isolation_fixtures.owner_refusal` |
| A3 | M3 | `POST /api/v1/correct` takes an optional `document_id`; a colleague gets the same 403 (M3 plan, "Deliberate differences"). | `isolation_fixtures.correct_body` |
| A4 | M3 | `GET /api/v1/encounters/today?scope=mine|clinic`, default `mine`, rows add `author_id` and `doctor_name`. `GET /api/v1/documents/{id}` adds `author` (`user_id, name, ...`) and `can_edit` (M3 plan, Assumption 5). UI: `#todayScope` buttons `data-scope="clinic"` reading "Whole clinic"; `#viewOnlyBanner` reading "<author>'s prescription: view only" (M3 plan, Task 5). | `isolation_fixtures.today`; `scripts/demo_browser.py` `switch_to_whole_clinic` |
| A5 | M3 | `_doctor_top(limit)` passes the scope's `user_id` as `doctor_id` and still feeds `build_hints(top, limit)` (M3 plan, Task 3 "Produces"). | `isolation_fixtures.hint_lookup`; patch point in Task 5 |
| A6 | M3 | `db.details.save_clinic_details(conn, clinic_name="", address="", phone="")` writes the shared clinic part and leaves the doctor columns alone (M3 plan, Task 1 "Produces"). | `admin_demo._set_clinic_details` |
| A7 | M3, M4 | Every PDF still goes through `pdf.renderer.render_prescription` → `get_renderer()` (`pdf/renderer.py:88-104`): M4 renders the doctors block in `pdf/sheet.py` from `meta["doctors"]`, with live profile values winning (M4 plan, Task 3). | `world` fixture patches `get_renderer` |
| A8 | M4 | `templates.owner_user_id` (NULL = clinic), `doctors_mode` (`author|all|selected`, default `author`), `doctors_ids` (JSON text); `tdb.set_template_doctors(conn, template_id, mode, ids)`; `set_template_active(conn, template_id, accepted_at=None, owner_user_id=None)` (M4 plan, Task 1 "Produces"). | `admin_demo._letterhead`; SQL in Task 7 |
| A9 | M4 | Block `{"type": "doctors", "role", "align"}` valid in header and footer. "Doctors" are active users with role `doctor`, oldest first. `selected` skips disabled and unknown ids, and a list that resolves to nobody prints the author (M4 plan, Tasks 3 and 5, "Deliberate differences"). | `admin_demo.rao_pad`; Task 7 |
| A10 | M4 | `PUT /api/v1/templates/{id}/doctors` with `{"mode", "ids"}` returns the view (404 when missing, 409 when archived, 400 for a bad choice) (M4 plan, Task 5). | `isolation_fixtures.set_doctors`; `BODIES` in Task 2 |
| A11 | M4 | `POST /{id}/accept` and `POST /deactivate` take an optional `{"scope": "clinic"|"mine"}`, default `clinic`. Deactivate with `mine` is "Use the clinic letterhead" and answers `{"deactivated": true}` (M4 plan, Task 5). | `isolation_fixtures.accept`, `use_clinic_letterhead` |
| A12 | M4 | Every template view carries `warnings: [{"section", "index", "text"}]` for literal lines matching `\b(dr|mbbs|md|ms|dnb)\b` (M4 plan, Task 4). | `isolation_fixtures.doctor_warning` |
| A13 | M4 | `provision_clinic` mirrors the directory's prefix into `clinic_profile.op_prefix` (`_mirror_prefix`). `create_patient_with_new_op(conn, name, age_sex)` keeps its signature and issues `<PREFIX>-YYYYMMDD-NNN` (M4 plan, Task 2). | `admin_demo._prescription` (no prefix code needed) |
| A14 | M5 | `POST /api/v1/users/{user_id}/disable|enable|reset-password` answer 200 in the caller's clinic and `404 {"error": "no such user"}` for an id that is not in it. `GET /api/v1/users` lists the caller's clinic only (M5 plan, Task 2 route table). | `isolation_fixtures.disable_user`, `enable_user`, `reset_user` |
| A15 | today | No route serves a stored logo or an original upload directly. Logos reach output only through `templates/service.py:194-199` `logo_data_uri` (`api/templates.py` has no file route; M4 adds none). | Task 3 |

## Findings for sibling plans (found while writing this plan)

- **F1, for M4: logo paths are not confined to the clinic's folder.** `templates/service.py:194-199` `logo_data_uri(path)` reads whatever path is stored in `templates.logo_path`, and its callers embed it with no check: `api/persistence.py:126-130` (save and on-demand PDF) and `api/templates.py:109` (preview). `_unlink(row["logo_path"])` (`service.py:47,162,172`) deletes any stored path the same way. The PDF route already guards this case (`api/persistence.py:308-319` `_stored_pdf`, `is_relative_to(pdf_dir())`); logos have no guard. **The M4 plan as written does not change `logo_data_uri`**, so F1 stays open unless M4 adds the confinement. A dry run of this plan's tests against the current code confirmed it: B's PDF embeds A's logo. Covered by `test_a_logo_stored_in_clinic_a_is_never_embedded_for_clinic_b` (Task 3). The team lead was told while this plan was being written.
- **F2, for M3, and a user decision: `POST /api/v1/encounters` takes `doctor_id` from the request body** (`api/persistence.py:31-37,76`). A signed-in colleague can create an encounter in another doctor's name. The M3 plan leaves this on purpose (its Assumption 6: "not an edit path"). The dry run confirmed it: Mehta created an encounter with `doctor_id` = Rao. It cannot change a prescription, but it is an authorship spoof in the data. The user decides whether M3 (or a follow-up) overrides it with the signed-in user. Covered by `test_an_encounter_cannot_be_created_in_a_colleagues_name` (Task 5).

## Dry run of this plan's code (while writing it)

Every code block here was extracted and run against the working tree of 2026-10-14 evening. M2c and M3 were in place; M4 and M5 were not built. A conftest shim stood in for the one-line `admin.py` registration and for M4's `set_template_doctors`. **42 of the 59 tests passed:** the whole route sweep, the files tests except F1, all fail-closed and worker-thread tests, every M3-dependent doctor-level test (403 body, view with `author`/`can_edit`, Today scopes, per-doctor hints), and the cookie, CSRF, lockout and timing tests. The 17 failures all have a known cause:
- M4 is not built: OP prefixes, the doctors block, letterhead scope and warnings (2 seed tests, 6 letterhead tests, 3 OP tests).
- M5 is not built: the disable and reset routes (2 auth tests).
- Finding F1 (1 test) and finding F2 (1 test).
- Only the shim covered the CLI: with the registration line applied, both CLI tests pass.

## Review Focus

1. **The sweep covers every id route, including future ones.** A new route with a path parameter that has no table mapping fails loudly: Task 2 `test_every_route_with_an_id_is_mapped_to_a_clinic_table`. The 404 rule: `test_every_id_route_answers_404_for_an_id_only_clinic_a_has`.
2. **Clinic A is byte-for-byte untouched by Clinic B's write attempts** (row fingerprint of seven tables plus file names): Task 2 sweep and `test_ids_inside_bodies_and_queries_stay_in_the_callers_clinic`.
3. **Clinic B's requests never open Clinic A's database file** (spy on `sqlite3.connect` across all threads): Task 2 `test_clinic_b_requests_never_open_a_clinic_a_database`; the same for normal work in both clinics: Task 4 `test_every_database_a_request_opens_belongs_to_the_signed_in_clinic`.
4. **The PDF worker thread never opens a database**, through a real save, reprint and preview: Task 4 `test_the_pdf_worker_thread_never_opens_a_database`.
5. **Stored paths into the other clinic** (absolute, `..`, symlink) for PDFs and logos: Task 3 `test_a_stored_path_into_clinic_a_is_never_served_to_clinic_b[*]` and `test_a_logo_stored_in_clinic_a_is_never_embedded_for_clinic_b` (finding F1).
6. **seed-demo cannot reach a real installation**: Task 1 `test_seed_demo_refuses_unless_demo_mode_is_exactly_1` and `test_seed_demo_refuses_a_data_folder_that_already_has_a_clinic`.

---

### Task 0: Confirm the sibling interfaces (no code, no tests)

- [ ] **Step 1: Check each assumption against the built code**

Run each and compare with the Assumptions table:

```bash
cd /Users/narenlingala/Documents/workspace/work/Zebra/doctor-dic/doctor-dictation-main
grep -n "doctor_id\|finalized_by\|can(\|belongs to" doctor_dictation/api/persistence.py            # A1 A2 F2
grep -n "document_id\|can(" doctor_dictation/api/format.py                                         # A3
grep -n "scope\|doctor_name" doctor_dictation/api/persistence.py doctor_dictation/db/*.py          # A4
grep -n "Whole clinic\|view only" frontend/*.js frontend/*.html                                     # A4 (UI)
grep -n "_doctor_top\|build_hints" doctor_dictation/api/stt.py                                      # A5
grep -n "def save_clinic_details" -A3 doctor_dictation/db/details.py                                # A6
grep -rn "render_prescription\|get_renderer" doctor_dictation/api doctor_dictation/pdf             # A7
grep -rn "owner_user_id\|doctors_mode\|doctors_ids\|op_prefix" doctor_dictation/db/migrations/     # A8 A13
grep -n "def set_template_doctors\|def set_template_active" doctor_dictation/db/templates.py       # A8
grep -n "doctors" doctor_dictation/pdf/layout.py                                                    # A9
grep -n "@router\|scope" doctor_dictation/api/templates.py                                          # A10 A11
grep -rn "warnings" doctor_dictation/templates/ doctor_dictation/api/templates.py                   # A12
grep -n "_mirror_prefix" doctor_dictation/clinics.py; grep -n "def " doctor_dictation/db/opno.py    # A13
grep -n "@router" doctor_dictation/api/users.py                                                     # A14
grep -n "logo_data_uri\|is_relative_to" doctor_dictation/templates/service.py                       # F1 status
```

Expected: every interface is present as described. Where one differs, write down the real name and edit only the helper the table names, while transcribing Tasks 1 and 2. Also note whether F1 (logo confinement) and F2 (encounter `doctor_id` from the body) were fixed. The results decide the xfail notes in Tasks 3 and 5.

- [ ] **Step 2: Note the baseline.** Run `.venv/bin/python -m pytest tests/ -q` and write down `N` (passed) and the skipped count.

---

### Task 1: `seed-demo` (the demo world)

**Files:**
- Create: `doctor_dictation/admin_demo.py`, `tests/test_admin_demo.py`
- Modify: `doctor_dictation/admin.py` (three one-line edits), `.env.example` (three comment lines at the end of the multi-clinic block)

**Interfaces:**
- Consumes: `accounts.create_user` (`accounts.py:44-80`), `clinics.provision_clinic` (`clinics.py:25-36`; mirrors the OP prefix after M4, A13), `db.get_conn`/`create_encounter`/`save_document`/`log_audit`/`_utcnow` (`db/__init__.py`), `db.details.save_clinic_details` (M3, A6), `db.opno.create_patient_with_new_op` (`db/opno.py:39-55`), `db.templates.create_template_draft`/`set_template_logo`/`set_template_active` (`db/templates.py:7-41`) and `set_template_doctors` (M4, A8), `directory.open_directory`/`list_clinics`, `directory.logins.lookup_username`, `scope.Scope`/`use_scope`/`clinic_dir`/`data_root`; assumptions A1, A6, A8, A9, A13.
- Produces (`doctor_dictation.admin_demo`): `DEMO_ENV = "DEMO_MODE"`, `ACTOR = "seed-demo"`, `RAO_PAD_LINE`, `IYER_PAD_LINE`, `CLINICS`, `DOCTORS` (dicts with `clinic, username, password, display_name, doctor_name, qualifications, reg_no`), `PRESCRIPTIONS` (tuples `(clinic, author, patient, age_sex, diagnosis, medicines)`), `DemoError(ValueError)`, `doctor(username) -> dict`, `rao_pad() -> dict`, `iyer_pad() -> dict`, `seed_demo() -> dict` (per slug `{"name", "users": {username: id}, "documents": [ids], "template_id"}`), `run(args) -> int`, `register(sub, commands) -> None`. CLI: `python -m doctor_dictation.admin seed-demo`.

The seeded world (fresh clinic files, so ids start at 1):

| Clinic | Users (id) | Documents (id: patient, author) | Letterhead (template 1) |
|---|---|---|---|
| `rao` "Rao Clinic", prefix `RAO` | dr.rao (1), dr.mehta (2) | 1: Asha Verma, Rao; 2: Ravi Kulkarni, Mehta; 3: Lakshmi Narayan, Rao | shared pad, doctors block, mode `all`, blue logo |
| `iyer` "Iyer Clinic", prefix `IYER` | dr.iyer (1) | 1: Bharat Menon, Iyer; 2: Meena Pillai, Iyer | own layout, author fields, mode `author`, green logo |

- [ ] **Step 1: Write the failing tests**

`tests/test_admin_demo.py`:

```python
"""seed-demo: guards, the two clinics, three doctors, a document 1 in each, letterheads, OP prefixes. Offline."""
import json
import re
from contextlib import closing
from pathlib import Path

import pytest

from doctor_dictation import admin, admin_demo, authn, clinics
from doctor_dictation import db as dbmod
from doctor_dictation.directory import list_clinics, open_directory
from doctor_dictation.pdf import validate_layout
from doctor_dictation.scope import clinic_dir


@pytest.fixture()
def demo(multi, monkeypatch):
    monkeypatch.setenv(admin_demo.DEMO_ENV, "1")
    return multi


def _rows(slug, query, *args):
    with closing(dbmod.get_conn(clinic_dir(slug) / "app.db")) as c:
        return c.execute(query, args).fetchall()


def test_seed_demo_refuses_unless_demo_mode_is_exactly_1(multi, monkeypatch):
    for value in (None, "", "0", "true", "yes"):
        if value is None:
            monkeypatch.delenv(admin_demo.DEMO_ENV, raising=False)
        else:
            monkeypatch.setenv(admin_demo.DEMO_ENV, value)
        with pytest.raises(admin_demo.DemoError, match="DEMO_MODE=1"):
            admin_demo.seed_demo()
    assert not (multi / "clinics").exists() and not (multi / "directory.db").exists()


def test_the_cli_refuses_without_demo_mode_and_exits_1(multi, monkeypatch, capsys):
    monkeypatch.setattr(admin, "load_dotenv", lambda *a, **k: False)     # a developer's .env must not switch it on
    monkeypatch.delenv(admin_demo.DEMO_ENV, raising=False)
    assert admin.main(["seed-demo"]) == 1
    assert "DEMO_MODE=1" in capsys.readouterr().err
    assert not (multi / "clinics").exists()


def test_seed_demo_refuses_a_data_folder_that_already_has_a_clinic(demo):
    clinics.provision_clinic("real", "A Real Clinic")
    with pytest.raises(admin_demo.DemoError, match="empty data folder"):
        admin_demo.seed_demo()
    with closing(open_directory()) as d:
        assert [r["slug"] for r in list_clinics(d)] == ["real"]
    assert not clinic_dir("rao").exists() and not clinic_dir("iyer").exists()


def test_three_demo_doctors_sign_in_with_their_published_passwords(demo):
    seeded = admin_demo.seed_demo()
    assert seeded["rao"]["users"] == {"dr.rao": 1, "dr.mehta": 2} and seeded["iyer"]["users"] == {"dr.iyer": 1}
    for d in admin_demo.DOCTORS:
        ident = authn.authenticate(d["username"], d["password"], "10.0.0.9")
        assert ident is not None and ident.clinic_slug == d["clinic"], d["username"]
        assert (ident.display_name, ident.must_change_password) == (d["display_name"], False)
    mehta = admin_demo.doctor("dr.mehta")
    row = _rows("rao", "SELECT doctor_name, qualifications, reg_no FROM users WHERE username = 'dr.mehta'")[0]
    assert tuple(row) == (mehta["doctor_name"], mehta["qualifications"], mehta["reg_no"])


def test_each_clinic_gets_fake_patients_and_its_own_document_1(demo):
    seeded = admin_demo.seed_demo()
    assert seeded["rao"]["documents"] == [1, 2, 3] and seeded["iyer"]["documents"] == [1, 2]

    def first_patient(slug):
        return json.loads(_rows(slug, "SELECT structured_json FROM documents WHERE id = 1")[0][0])["patientName"]

    assert (first_patient("rao"), first_patient("iyer")) == ("Asha Verma", "Bharat Menon")
    authorship = ("SELECT d.id, e.doctor_id, d.finalized_by FROM documents d"
                  " JOIN encounters e ON e.id = d.encounter_id ORDER BY d.id")
    assert [tuple(r) for r in _rows("rao", authorship)] == [(1, 1, 1), (2, 2, 2), (3, 1, 1)]
    assert [tuple(r) for r in _rows("iyer", authorship)] == [(1, 1, 1), (2, 1, 1)]
    start, end = dbmod.local_day_bounds_utc()
    for slug in ("rao", "iyer"):
        assert all(start <= r["created_at"] < end for r in _rows(slug, "SELECT created_at FROM documents"))


def test_seeded_op_numbers_carry_each_clinics_prefix_and_start_at_001(demo):
    admin_demo.seed_demo()
    for slug, prefix, count in (("rao", "RAO", 3), ("iyer", "IYER", 2)):
        ops = [r["op_no"] for r in _rows(slug, "SELECT op_no FROM patients ORDER BY id")]
        assert [o[-3:] for o in ops] == [f"{i:03d}" for i in range(1, count + 1)], ops
        assert all(re.fullmatch(rf"{prefix}-\d{{8}}-\d{{3}}", o) for o in ops), ops
        assert [r["op_no"] for r in _rows(slug, "SELECT op_no FROM encounters ORDER BY id")] == ops


def test_each_clinic_gets_its_own_active_letterhead_and_logo(demo):
    admin_demo.seed_demo()
    logos = {}
    for slug, mode, line in (("rao", "all", admin_demo.RAO_PAD_LINE), ("iyer", "author", admin_demo.IYER_PAD_LINE)):
        rows = _rows(slug, "SELECT * FROM templates WHERE status = 'active'")
        assert len(rows) == 1, slug
        layout = json.loads(rows[0]["layout_json"])
        validate_layout(layout)
        assert rows[0]["owner_user_id"] is None and rows[0]["doctors_mode"] == mode
        assert line in [b.get("text") for b in layout["header"]]
        logo = Path(rows[0]["logo_path"])
        assert logo.is_file() and logo.resolve().is_relative_to((clinic_dir(slug) / "templates").resolve())
        logos[slug] = logo.read_bytes()
    assert logos["rao"] != logos["iyer"]
    rao_layout = json.loads(_rows("rao", "SELECT layout_json FROM templates WHERE id = 1")[0][0])
    assert any(b["type"] == "doctors" for b in rao_layout["header"])


def test_the_cli_prints_the_demo_logins_once_with_a_demo_only_warning(demo, monkeypatch, capsys):
    monkeypatch.setattr(admin, "load_dotenv", lambda *a, **k: False)
    assert admin.main(["seed-demo"]) == 0
    out = capsys.readouterr().out
    assert "DEMO ONLY" in out
    for d in admin_demo.DOCTORS:
        assert d["username"] in out and out.count(d["password"]) == 1


def test_seeded_audit_rows_name_each_prescriptions_author_and_never_a_password(demo):
    admin_demo.seed_demo()
    a = {(r["actor"], r["action"]) for r in _rows("rao", "SELECT actor, action FROM audit_log")}
    b = {(r["actor"], r["action"]) for r in _rows("iyer", "SELECT actor, action FROM audit_log")}
    assert {("dr.rao", "finalize"), ("dr.mehta", "finalize"), ("seed-demo", "user_create")} <= a
    assert ("dr.iyer", "finalize") in b and not {actor for actor, _ in b} & {"dr.rao", "dr.mehta"}
    every = " ".join(str(tuple(r)) for slug in ("rao", "iyer") for r in _rows(slug, "SELECT * FROM audit_log"))
    assert not [d["password"] for d in admin_demo.DOCTORS if d["password"] in every]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_admin_demo.py -q`
Expected: FAIL (`cannot import name 'admin_demo'`).

- [ ] **Step 3: Write the implementation**

`doctor_dictation/admin_demo.py`:

```python
"""``seed-demo``: two fake clinics for the multi-clinic demo (spec sections 11 and 13.2). Demo only.

Rao Clinic (Dr. Rao, Dr. Mehta) and Iyer Clinic (Dr. Iyer) each get clinic details, a few fake patients with
prescriptions saved today (so each clinic has its own "document 1") and an active letterhead: Rao Clinic's
shared pad lists every doctor, Iyer Clinic's prints only the author.

The doctors get FIXED, published passwords with no forced change, so the five-minute demo and
``scripts/demo_browser.py`` sign in repeatably. That is acceptable only because the command refuses unless
``DEMO_MODE=1``, refuses a data folder that already has a clinic (it can never add known-password accounts to a
real installation), and every record is fake.
"""
from __future__ import annotations

import hashlib
import io
import os
from contextlib import closing

from PIL import Image

from doctor_dictation import accounts, clinics
from doctor_dictation import db as dbmod
from doctor_dictation.db import details, opno
from doctor_dictation.db import templates as tdb
from doctor_dictation.directory import list_clinics, open_directory
from doctor_dictation.directory.logins import lookup_username
from doctor_dictation.scope import Scope, clinic_dir, data_root, use_scope

DEMO_ENV = "DEMO_MODE"
ACTOR = "seed-demo"
RAO_PAD_LINE = "Open Mon to Sat, 9 am to 1 pm"
IYER_PAD_LINE = "ENT and allergy care, open daily 10 am to 6 pm"

CLINICS = (
    {"slug": "rao", "name": "Rao Clinic", "op_prefix": "RAO", "address": "12 MG Road, Hyderabad",
     "phone": "040 1111 2222", "logo_rgb": (26, 60, 110), "logo_size": (240, 80), "doctors_mode": "all"},
    {"slug": "iyer", "name": "Iyer Clinic", "op_prefix": "IYER", "address": "4 Temple Street, Chennai",
     "phone": "044 3333 4444", "logo_rgb": (11, 110, 79), "logo_size": (200, 90), "doctors_mode": "author"},
)
DOCTORS = (
    {"clinic": "rao", "username": "dr.rao", "password": "demo-rao-pass-1", "display_name": "Dr. Rao",
     "doctor_name": "Dr. A. Rao", "qualifications": "MBBS, MD (General Medicine)", "reg_no": "TSMC 10001"},
    {"clinic": "rao", "username": "dr.mehta", "password": "demo-mehta-pass-1", "display_name": "Dr. Mehta",
     "doctor_name": "Dr. S. Mehta", "qualifications": "MBBS, DCH (Paediatrics)", "reg_no": "TSMC 10002"},
    {"clinic": "iyer", "username": "dr.iyer", "password": "demo-iyer-pass-1", "display_name": "Dr. Iyer",
     "doctor_name": "Dr. K. Iyer", "qualifications": "MBBS, MS (ENT)", "reg_no": "TNMC 20001"},
)
# (clinic, author, patient, age / sex, diagnosis, medicines). Per clinic, the first row becomes document 1.
PRESCRIPTIONS = (
    ("rao", "dr.rao", "Asha Verma", "34 / F", "Viral fever", ("Paracetamol",)),
    ("rao", "dr.mehta", "Ravi Kulkarni", "8 / M", "Allergic rhinitis", ("Cetirizine", "Montelukast")),
    ("rao", "dr.rao", "Lakshmi Narayan", "61 / F", "Hypertension", ("Amlodipine", "Telmisartan")),
    ("iyer", "dr.iyer", "Bharat Menon", "45 / M", "Acute sinusitis", ("Azithromycin", "Levocetirizine")),
    ("iyer", "dr.iyer", "Meena Pillai", "29 / F", "Acid reflux", ("Pantoprazole",)),
)


class DemoError(ValueError):
    """seed-demo refused: not in demo mode, or the data folder is not empty."""


def doctor(username: str) -> dict:
    return next(d for d in DOCTORS if d["username"] == username)


def _snapshot(clinic: dict) -> dict:
    """The layout's stored profile: clinic fields only; doctor fields come from the author at print time."""
    return {"doctor_name": "", "qualifications": "", "reg_no": "", "clinic_name": clinic["name"],
            "address": clinic["address"], "phone": clinic["phone"]}


def rao_pad() -> dict:
    """Rao Clinic's shared letterpad: logo, clinic name, every doctor (the doctors block), a tagline."""
    return {"header": [{"type": "logo", "crop": [0.0, 0.0, 1.0, 1.0], "align": "left"},
                       {"type": "text", "field": "clinic_name", "role": "title", "align": "center", "color": "#1a3c6e"},
                       {"type": "doctors", "role": "normal", "align": "center"},
                       {"type": "text", "text": RAO_PAD_LINE, "role": "small", "align": "center"},
                       {"type": "rule", "color": "#1a3c6e", "thickness": "thin"}],
            "footer": [{"type": "text", "field": "address", "role": "small", "align": "center"},
                       {"type": "text", "field": "phone", "role": "small", "align": "center"}],
            "body": {"top": 0.24, "bottom": 0.92}, "profile": _snapshot(CLINICS[0])}


def iyer_pad() -> dict:
    """Iyer Clinic's own letterhead: the author's name and qualifications, the clinic, a tagline."""
    return {"header": [{"type": "logo", "crop": [0.0, 0.0, 1.0, 1.0], "align": "right"},
                       {"type": "text", "field": "doctor_name", "role": "title", "align": "left", "color": "#0b6e4f"},
                       {"type": "text", "field": "qualifications", "role": "subtitle", "align": "left"},
                       {"type": "text", "field": "clinic_name", "role": "normal", "align": "left"},
                       {"type": "text", "text": IYER_PAD_LINE, "role": "small", "align": "left"},
                       {"type": "rule", "color": "#0b6e4f", "thickness": "medium"}],
            "footer": [{"type": "text", "field": "address", "role": "small", "align": "left"},
                       {"type": "text", "field": "reg_no", "role": "small", "align": "right"}],
            "body": {"top": 0.26, "bottom": 0.92}, "profile": _snapshot(CLINICS[1])}


def _logo_jpeg(rgb, size) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, rgb).save(buf, "JPEG")
    return buf.getvalue()


def _rx(name: str) -> dict:
    return {"form": "Tab.", "name": name, "strength": "", "dose": "1-0-1", "timing": "After food",
            "duration": "5 days", "instructions": "", "status": "verified"}


def _check_can_seed() -> None:
    if os.getenv(DEMO_ENV, "") != "1":
        raise DemoError(f"seed-demo only runs with {DEMO_ENV}=1: it creates fake clinics with published passwords")
    with closing(open_directory()) as d:
        if list_clinics(d):
            raise DemoError("seed-demo needs an empty data folder; this one already has clinics "
                            "(point DATA_DIR at a new folder)")
        taken = [u["username"] for u in DOCTORS if lookup_username(d, u["username"]) is not None]
    if taken:
        raise DemoError(f"usernames already taken: {', '.join(taken)}")


def _set_clinic_details(conn, clinic: dict) -> None:
    """A6: the shared clinic part of the profile (the OP prefix was mirrored by provision_clinic, A13)."""
    details.save_clinic_details(conn, clinic_name=clinic["name"], address=clinic["address"], phone=clinic["phone"])


def _prescription(conn, author_id: int, author: str, patient: str, age_sex: str, diagnosis: str, medicines) -> int:
    """A1, A13: a finalized prescription by ``author_id`` with an OP number in the clinic's prefix. Returns its id."""
    patient_id, op_no = opno.create_patient_with_new_op(conn, patient, age_sex)
    form = {"patientName": patient, "ageSex": age_sex, "opNo": op_no, "diagnosis": [diagnosis], "complaints": [],
            "investigations": [], "rx": [_rx(m) for m in medicines], "advice": ["Plenty of fluids"],
            "review": "Review after 5 days"}
    encounter_id = dbmod.create_encounter(conn, patient_id, doctor_id=author_id, op_no=op_no, status="finalized")
    sha = hashlib.sha256(f"seed-demo:{patient}".encode("utf-8")).hexdigest()
    document_id = dbmod.save_document(conn, encounter_id, sha, form, engine=ACTOR, finalized_by=author_id,
                                      finalized_at=dbmod._utcnow())
    dbmod.log_audit(conn, actor=author, role="doctor", action="finalize", entity="encounter",
                    entity_id=str(encounter_id), detail={"document_id": document_id, "seeded": True})
    return document_id


def _letterhead(conn, clinic: dict, layout: dict) -> int:
    """A8: an active clinic-wide letterhead with its own logo file inside the clinic's templates folder."""
    template_id = tdb.create_template_draft(conn, layout)
    folder = clinic_dir(clinic["slug"]) / "templates"
    folder.mkdir(parents=True, exist_ok=True)
    logo = folder / f"{template_id}_logo.jpg"
    logo.write_bytes(_logo_jpeg(clinic["logo_rgb"], clinic["logo_size"]))
    tdb.set_template_logo(conn, template_id, str(logo))
    tdb.set_template_active(conn, template_id)                     # owner_user_id stays NULL: clinic-wide
    tdb.set_template_doctors(conn, template_id, clinic["doctors_mode"], [])
    return template_id


def seed_demo() -> dict:
    """Create both demo clinics. Returns, per slug: name, users (username -> id), document ids, template id."""
    _check_can_seed()
    out = {}
    for clinic in CLINICS:
        slug = clinic["slug"]
        clinics.provision_clinic(slug, clinic["name"], clinic["op_prefix"])
        users = {}
        for d in (x for x in DOCTORS if x["clinic"] == slug):
            uid, _ = accounts.create_user(slug, d["username"], display_name=d["display_name"],
                                          doctor_name=d["doctor_name"], qualifications=d["qualifications"],
                                          reg_no=d["reg_no"], password=d["password"], actor=ACTOR)
            users[d["username"]] = uid
        with use_scope(Scope(slug, None, ACTOR, "system")), closing(dbmod.get_conn(clinic_dir(slug) / "app.db")) as conn:
            conn.execute("UPDATE users SET must_change_password = 0")      # published demo passwords: no forced change
            conn.commit()
            _set_clinic_details(conn, clinic)
            docs = [_prescription(conn, users[author], author, *rest)
                    for where, author, *rest in PRESCRIPTIONS if where == slug]
            template_id = _letterhead(conn, clinic, rao_pad() if slug == "rao" else iyer_pad())
        out[slug] = {"name": clinic["name"], "users": users, "documents": docs, "template_id": template_id}
    return out


def run(_args) -> int:
    seed_demo()
    print("DEMO ONLY: fake clinics, fake patients and PUBLISHED passwords. Never put real patients in this data folder.")
    print(f"seeded {data_root()}")
    for d in DOCTORS:
        print(f"  {d['clinic']:<5} {d['username']:<9} password: {d['password']}")
    print("start the app with MULTI_CLINIC=1 and the same DATA_DIR, then sign in at /login")
    return 0


def register(sub, commands: dict) -> None:
    """Add ``seed-demo`` to the operator CLI (``admin.main`` calls this once per run)."""
    sub.add_parser("seed-demo", help="DEMO ONLY: two fake clinics, three doctors with published passwords (DEMO_MODE=1)")
    commands["seed-demo"] = run
```

In `doctor_dictation/admin.py` make exactly three one-line edits:

1. Line 3 of the docstring, from
   `Commands: create-clinic, list-clinics, migrate-all, adopt-existing, create-user, reset-password.`
   to
   `Commands: create-clinic, list-clinics, migrate-all, adopt-existing, create-user, reset-password, seed-demo (demo only).`
2. Line 19, from `from doctor_dictation import accounts, clinics` to `from doctor_dictation import accounts, admin_demo, clinics`.
3. Immediately before the line `    args = parser.parse_args(argv)` (line 212), insert:

```python
    admin_demo.register(sub, COMMANDS)          # seed-demo: DEMO_MODE=1 only
```

A `DemoError` is a `ValueError`, so `admin.main`'s existing handler (`admin.py:215-217`) prints `error: ...` and returns 1.

In `.env.example`, after the last line `# DEV_INSECURE_SESSION_SECRET=1`, append:

```
# Demo only: lets `python -m doctor_dictation.admin seed-demo` create two FAKE clinics whose doctors have published
# passwords. It refuses a data folder that already has clinics. Never set this outside a demo.
# DEMO_MODE=1
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_admin_demo.py tests/test_admin.py tests/test_file_sizes.py -q`
Expected: all passed (9 new; `test_admin.py` unchanged). If `test_seeded_op_numbers_carry_each_clinics_prefix_and_start_at_001` or `test_each_clinic_gets_its_own_active_letterhead_and_logo` fails, compare with Task 0's notes on A8, A9 and A13 and adjust `_set_clinic_details` / `_letterhead` / `rao_pad` only.
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 9` passed.

- [ ] **Step 5: Leave uncommitted.**

---

### Task 2: Isolation fixtures and the route sweep

**Files:**
- Create: `tests/isolation_fixtures.py`, `tests/test_isolation_routes.py`

**Interfaces:**
- Consumes: `admin_demo.seed_demo`, `admin_demo.rao_pad`, `admin_demo.doctor`, `admin_demo.DEMO_ENV`, `RAO_PAD_LINE`, `IYER_PAD_LINE` (Task 1); `api.app.create_app`; `config.override_settings` (`config.py:134-138`); `pdf.renderer.ChromiumPoolRenderer` (`pdf/renderer.py:34-84`) and its module-level `get_renderer`; `db.templates.create_template_draft`; `template_fixtures.make_jpeg` (`tests/template_fixtures.py:27-30`); the `multi` fixture; assumptions A2 to A5, A7, A10 to A12, A14.
- Produces (`tests/isolation_fixtures.py`): fixture `world` (a `SimpleNamespace` with `root, seeded, app, renders, rao, mehta, iyer`); constants `H, A, B, A_MARKERS, B_MARKERS, UPLOAD_PAD, UPLOAD_PAD_LINE, TABLES`; helpers `login, user_id, sql, fingerprint, a_only_id, leaks, pdf_text, reprint, save_body, save, upload, opened_files`; assumption helpers `owner_refusal (A2), correct_body (A3), today (A4), hint_lookup (A5), set_doctors (A10), accept, use_clinic_letterhead (A11), doctor_warning (A12), disable_user, enable_user, reset_user (A14)`.

After the fixture, Clinic A has template ids {1 active, 2 draft} and Clinic B has {1 active}, so every clinic table has an id that only A has: documents 3, encounters 3, patients 3, templates 2, users 2.

- [ ] **Step 1: Write the fixture module**

`tests/isolation_fixtures.py`:

```python
"""Shared world for the isolation suite (spec 13.1): seed-demo's two clinics, three signed-in doctors, fake Chromium.

Offline: stub LLM and STT, and a fake browser behind the REAL pdf-worker thread, so a stored "PDF" is
``%PDF-fake`` plus the exact sheet HTML that would have printed (tests assert on printed names). Every interface
assumed from M3, M4 or M5 is one small helper at the bottom, tagged with its assumption number from
docs/superpowers/plans/2026-10-14-m6-isolation-suite-and-demo.md; if a sibling plan named something
differently, change the helper, not the tests.
"""
import json
import sqlite3
import threading
from contextlib import ExitStack, closing, contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import admin_demo
from doctor_dictation import db as dbmod
from doctor_dictation.api import stt
from doctor_dictation.api.app import create_app
from doctor_dictation.config import override_settings
from doctor_dictation.db import templates as tdb
from doctor_dictation.pdf import renderer as R
from doctor_dictation.scope import clinic_dir
from template_fixtures import make_jpeg

H = {"X-DD-Client": "1"}
A, B = "rao", "iyer"
A_MARKERS = ("Rao Clinic", "Asha Verma", "Ravi Kulkarni", "Lakshmi Narayan", "Dr. A. Rao", "Dr. S. Mehta",
             "dr.rao", "dr.mehta", "RAO-", admin_demo.RAO_PAD_LINE)
B_MARKERS = ("Iyer Clinic", "Bharat Menon", "Meena Pillai", "Dr. K. Iyer", "dr.iyer", "IYER-",
             admin_demo.IYER_PAD_LINE)
UPLOAD_PAD_LINE = "Child care, Tue and Thu evenings"
UPLOAD_PAD = {"header": [{"type": "logo", "crop": [0.05, 0.02, 0.25, 0.10], "align": "left"},
                         {"type": "text", "field": "doctor_name", "role": "title", "align": "center"},
                         {"type": "text", "text": UPLOAD_PAD_LINE, "role": "small", "align": "center"}],
              "footer": [], "body": {"top": 0.22, "bottom": 0.92}, "profile": {}}
TABLES = ("patients", "encounters", "documents", "templates", "users", "clinic_profile", "audit_log")


class _Page:
    def __init__(self, sink):
        self.sink, self.html = sink, ""

    def set_content(self, html, **_kw):
        self.html = html

    def pdf(self, path, **_kw):
        self.sink.append({"thread": threading.current_thread().name, "html": self.html})
        Path(path).write_bytes(b"%PDF-fake\n" + self.html.encode("utf-8"))


class _Context:
    def __init__(self, sink):
        self.sink = sink

    def new_page(self):
        return _Page(self.sink)

    def close(self):
        pass


class _Browser:
    def __init__(self, sink):
        self.sink = sink

    def new_context(self, **_kw):
        return _Context(self.sink)

    def is_connected(self):
        return True


@pytest.fixture()
def world(multi, monkeypatch):
    """The seeded clinics, a draft letterhead only Clinic A has, and one signed-in client per doctor."""
    monkeypatch.setenv(admin_demo.DEMO_ENV, "1")
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(UPLOAD_PAD))
    monkeypatch.setenv("STUB_TRANSCRIPT", "paracetamol 650 mg twice daily")
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, stt_chain=("stub",),
                      stt_use_hints=False, stt_trim_silence=False)
    renders = []
    fake = R.ChromiumPoolRenderer(lambda: (_Browser(renders), lambda: None))
    monkeypatch.setattr(R, "get_renderer", lambda: fake)     # A7: the real worker thread, a fake browser
    seeded = admin_demo.seed_demo()
    with closing(dbmod.get_conn(clinic_dir(A) / "app.db")) as conn:
        tdb.create_template_draft(conn, admin_demo.rao_pad())   # template 2: an id only Clinic A has
    app = create_app()
    try:
        with ExitStack() as stack:
            clients = {}
            for who in ("rao", "mehta", "iyer"):
                client = stack.enter_context(TestClient(app, follow_redirects=False))
                r = login(client, f"dr.{who}")
                assert r.status_code == 200 and r.json()["must_change_password"] is False, r.text
                clients[who] = client
            yield SimpleNamespace(root=multi, seeded=seeded, app=app, renders=renders, **clients)
    finally:
        fake.close()


def login(client, username, password=None):
    secret = admin_demo.doctor(username)["password"] if password is None else password
    return client.post("/api/v1/auth/login", json={"username": username, "password": secret}, headers=H)


def user_id(world, username):
    return world.seeded[admin_demo.doctor(username)["clinic"]]["users"][username]


def sql(slug, query, *args):
    """One statement on a clinic file, opened by path (setup and inspection only; never inside a spy window)."""
    with closing(dbmod.get_conn(clinic_dir(slug) / "app.db")) as conn:
        rows = conn.execute(query, args).fetchall()
        conn.commit()
    return rows


def fingerprint(slug):
    """Every row of the clinic's data tables plus its file names: equal before and after means untouched."""
    rows = {t: [tuple(r) for r in sql(slug, f"SELECT * FROM {t} ORDER BY rowid")] for t in TABLES}
    root = clinic_dir(slug)
    files = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and not p.name.startswith("app.db"))
    return rows, files


def a_only_id(table):
    """The largest id Clinic A has in ``table`` that Clinic B does not."""
    mine = {r[0] for r in sql(A, f"SELECT id FROM {table}")}
    theirs = {r[0] for r in sql(B, f"SELECT id FROM {table}")}
    only = sorted(mine - theirs)
    assert only, f"the seeded world gives clinic A no {table} id that clinic B lacks"
    return only[-1]


def leaks(text, markers):
    return [m for m in markers if m in text]


def pdf_text(response):
    return response.content.decode("utf-8", "replace")


def reprint(client, slug, document_id):
    """Drop the stored PDF so the next GET renders now (today's letterhead rules), then return the printed text."""
    sql(slug, "UPDATE documents SET pdf_path = NULL WHERE id = ?", document_id)
    r = client.get(f"/api/v1/documents/{document_id}/pdf")
    assert r.status_code == 200, r.text
    return pdf_text(r)


def save_body(patient, op="", document_id=None, medicine="Paracetamol"):
    body = {"structured": {"patientName": patient, "ageSex": "40 / M", "opNo": op,
                           "rx": [{"form": "Tab.", "name": medicine, "status": "verified"}]},
            "confirmed_rows": []}
    if document_id is not None:
        body["document_id"] = document_id
    return body


def save(client, patient, op=""):
    r = client.post("/api/v1/documents", json=save_body(patient, op), headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def upload(client):
    return client.post("/api/v1/templates", files={"image": ("pad.jpg", make_jpeg(), "image/jpeg")}, headers=H)


@contextmanager
def opened_files(monkeypatch):
    """Record (thread name, path) for every sqlite3.connect, from any thread, while the block runs."""
    seen, real = [], sqlite3.connect

    def spy(database, *args, **kwargs):
        seen.append((threading.current_thread().name, str(database)))
        return real(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", spy)
    try:
        yield seen
    finally:
        monkeypatch.setattr(sqlite3, "connect", real)


# --- interfaces assumed from M3, M4 and M5: one helper each (the plan's Assumptions table) ----------------------

def owner_refusal(author_name):                                             # A2: doctor name, else display name
    return {"error": f"This prescription belongs to {author_name}. You can view and reprint it."}


def correct_body(document_id):                                              # A3
    return {"transcript": "make paracetamol 650 mg", "current_form": save_body("Asha Verma")["structured"],
            "document_id": document_id}


def today(client, scope=None):                                              # A4
    r = client.get("/api/v1/encounters/today" + (f"?scope={scope}" if scope else ""))
    assert r.status_code == 200, r.text
    return r.json()


def hint_lookup():                                                          # A5
    return stt._doctor_top(5)


def set_doctors(client, template_id, mode, ids=()):                         # A10
    return client.put(f"/api/v1/templates/{template_id}/doctors", json={"mode": mode, "ids": list(ids)}, headers=H)


def accept(client, template_id, scope="clinic"):                            # A11
    return client.post(f"/api/v1/templates/{template_id}/accept", json={"scope": scope}, headers=H)


def use_clinic_letterhead(client):                                          # A11
    return client.post("/api/v1/templates/deactivate", json={"scope": "mine"}, headers=H)


def doctor_warning(view, text) -> bool:                                     # A12
    for w in view.get("warnings") or []:
        if text in json.dumps(w, ensure_ascii=False):
            return True
        if isinstance(w, dict) and w.get("section") in ("header", "footer") and isinstance(w.get("index"), int):
            blocks = view.get("layout", {}).get(w["section"], [])
            if 0 <= w["index"] < len(blocks) and blocks[w["index"]].get("text") == text:
                return True
    return False


def disable_user(client, uid):                                              # A14
    return client.post(f"/api/v1/users/{uid}/disable", headers=H)


def enable_user(client, uid):                                               # A14
    return client.post(f"/api/v1/users/{uid}/enable", headers=H)


def reset_user(client, uid):                                                # A14
    return client.post(f"/api/v1/users/{uid}/reset-password", headers=H)
```

- [ ] **Step 2: Write the route-sweep tests**

`tests/test_isolation_routes.py`:

```python
"""Route sweep (spec 13.1): as Clinic B, ask every route for ids only Clinic A has. Nothing of A comes back,
nothing of A changes, and B never even opens A's database file. Offline; seeded world from isolation_fixtures."""
import os
import re

from doctor_dictation.scope import clinic_dir
from isolation_fixtures import (A, A_MARKERS, B_MARKERS, H, a_only_id, fingerprint, leaks, opened_files, pdf_text,
                                save_body, world)  # noqa: F401

WRITE = {"POST", "PUT", "DELETE", "PATCH"}
ID_TABLE = (("/api/v1/documents/", "documents"), ("/api/v1/templates/", "templates"), ("/api/v1/users/", "users"),
            ("/api/v1/patients/", "patients"), ("/api/v1/encounters/", "encounters"))
BODIES = {   # so an id route reaches its lookup instead of a 422 (A10, A11)
    ("PUT", "/api/v1/templates/{id}"): {"profile": {}, "lines": []},
    ("PUT", "/api/v1/templates/{id}/doctors"): {"mode": "all", "ids": []},
    ("POST", "/api/v1/templates/{id}/accept"): {"scope": "clinic"},
}
EXTRA_GETS = ("/api/v1/encounters/today?scope=clinic",)                     # A4


def _norm(path):
    return re.sub(r"\{[^}]+\}", "{id}", path)


def id_routes(app):
    out = []
    for path, ops in app.openapi()["paths"].items():
        if "{" in path:
            out.extend((m.upper(), path) for m in ops if m.upper() in WRITE | {"GET"})
    return sorted(out)


def plain_gets(app):
    return sorted(p for p, ops in app.openapi()["paths"].items() if "get" in ops and "{" not in p)


def table_for(path):
    assert path.count("{") == 1, f"{path}: the sweep handles one id per route; extend table_for"
    for prefix, table in ID_TABLE:
        if path.startswith(prefix):
            return table
    raise AssertionError(f"unmapped id route {path}: add its clinic table to ID_TABLE")


def _a_only_url(path):
    return re.sub(r"\{[^}]+\}", str(a_only_id(table_for(path))), path)


def test_the_world_signs_in_three_doctors_in_two_clinics(world):
    me = [getattr(world, who).get("/api/v1/auth/me").json() for who in ("rao", "mehta", "iyer")]
    assert [(m["clinic_slug"], m["username"]) for m in me] == [("rao", "dr.rao"), ("rao", "dr.mehta"), ("iyer", "dr.iyer")]
    assert [m["clinic_name"] for m in me] == ["Rao Clinic", "Rao Clinic", "Iyer Clinic"]


def test_every_route_with_an_id_is_mapped_to_a_clinic_table(world):
    routes = id_routes(world.app)
    assert len(routes) >= 7, routes
    for _method, path in routes:
        table_for(path)                       # raises, naming the route, when a new id route has no mapping


def test_every_id_route_answers_404_for_an_id_only_clinic_a_has(world):
    before = fingerprint(A)
    wrong, checked = [], 0
    for method, path in id_routes(world.app):
        url = _a_only_url(path)
        r = world.iyer.request(method, url, json=BODIES.get((method, _norm(path))), headers=H)
        checked += 1
        if r.status_code != 404 or leaks(r.text, A_MARKERS):
            wrong.append(f"{method} {url} -> {r.status_code} {r.text[:160]}")
    assert checked >= 7
    assert not wrong, wrong
    assert fingerprint(A) == before


def test_clinic_b_requests_never_open_a_clinic_a_database(world, monkeypatch):
    targets = [(method, _a_only_url(path), path) for method, path in id_routes(world.app)]   # ids looked up first
    with opened_files(monkeypatch) as seen:
        for method, url, path in targets:
            world.iyer.request(method, url, json=BODIES.get((method, _norm(path))), headers=H)
        for url in plain_gets(world.app):
            world.iyer.get(url)
    a_dir = str(clinic_dir(A)) + os.sep
    assert seen, "the spy saw no database opens"
    assert [p for _thread, p in seen if p.startswith(a_dir)] == []


def test_both_clinics_have_a_document_1_and_each_sees_its_own(world):
    a, b = world.rao.get("/api/v1/documents/1"), world.iyer.get("/api/v1/documents/1")
    assert (a.status_code, b.status_code) == (200, 200)
    assert (a.json()["structured"]["patientName"], b.json()["structured"]["patientName"]) == ("Asha Verma", "Bharat Menon")
    pa, pb = world.rao.get("/api/v1/documents/1/pdf"), world.iyer.get("/api/v1/documents/1/pdf")
    assert (pa.status_code, pb.status_code) == (200, 200)
    assert "Rao Clinic" in pdf_text(pa) and not leaks(pdf_text(pa), B_MARKERS)
    assert "Iyer Clinic" in pdf_text(pb) and not leaks(pdf_text(pb), A_MARKERS)


def test_no_list_or_page_shows_the_other_clinics_data(world):
    found = []
    for who, theirs in (("iyer", A_MARKERS), ("rao", B_MARKERS), ("mehta", B_MARKERS)):
        client = getattr(world, who)
        for url in [*plain_gets(world.app), *EXTRA_GETS]:
            r = client.get(url)
            assert r.status_code < 500, (who, url, r.status_code)
            if leaks(r.text, theirs):
                found.append((who, url, leaks(r.text, theirs)))
    assert not found, found
    assert "Asha Verma" in world.rao.get("/api/v1/patients").text           # the lists are not simply empty
    assert "Bharat Menon" in world.iyer.get("/api/v1/patients").text


def test_ids_inside_bodies_and_queries_stay_in_the_callers_clinic(world):
    before = fingerprint(A)
    doc, patient = a_only_id("documents"), a_only_id("patients")
    r = world.iyer.post("/api/v1/documents", json=save_body("Bharat Menon", document_id=doc), headers=H)
    assert r.status_code == 404, r.text
    r = world.iyer.post("/api/v1/encounters", json={"patient_id": patient}, headers=H)
    assert r.status_code == 404, r.text
    r = world.iyer.get(f"/api/v1/encounters?patient_id={patient}")
    assert (r.status_code, r.json()) == (200, [])
    assert fingerprint(A) == before
```

- [ ] **Step 3: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_isolation_routes.py -q`
Expected: 7 passed. A failure is a finding, not something to fix in production code. A 422 in the sweep means a route needs a body in `BODIES` (add it). An `unmapped id route` means a new route needs a row in `ID_TABLE`. A non-404 status or a leaked marker is an isolation bug: report it with the route and plan (M3, M4 or M5) and stop.
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 16` passed.

- [ ] **Step 4: Leave uncommitted.**

---

### Task 3: Files (PDFs, logos, uploads, the data folder)

**Files:**
- Create: `tests/test_isolation_files.py`

**Interfaces:**
- Consumes: `world`, `A`, `B`, `A_MARKERS`, `leaks`, `pdf_text`, `reprint`, `sql`, `upload` (Task 2); `directory.directory_path`, `directory.open_directory`; `scope.clinic_dir`. This is the cross-clinic form of `tests/test_document_pdf.py:67-86` (stored path outside `pdf_dir`, `..` escape), plus the symlink case and logos.
- Produces: tests only.

- [ ] **Step 1: Write the tests**

`tests/test_isolation_files.py`:

```python
"""Files (spec 13.1): Clinic A's PDFs, logos and uploads are unreadable through Clinic B, including stored paths
that point into A by absolute path, ".." traversal or a symlink (the cross-clinic form of
tests/test_document_pdf.py:67-86). Offline."""
import base64
import os
from contextlib import closing
from pathlib import Path

import pytest

from doctor_dictation.directory import directory_path, open_directory
from doctor_dictation.scope import clinic_dir
from isolation_fixtures import A, A_MARKERS, B, leaks, pdf_text, reprint, sql, upload, world  # noqa: F401


def _a_pdf(world):
    """Render and store Clinic A's document 3 (only A has it); return the stored file."""
    assert world.rao.get("/api/v1/documents/3/pdf").status_code == 200
    path = Path(sql(A, "SELECT pdf_path FROM documents WHERE id = 3")[0]["pdf_path"])
    assert path.is_file() and b"Lakshmi Narayan" in path.read_bytes()
    return path


def test_clinic_a_pdf_is_404_through_clinic_b(world):
    _a_pdf(world)
    r = world.iyer.get("/api/v1/documents/3/pdf")
    assert r.status_code == 404 and b"Lakshmi" not in r.content


@pytest.mark.parametrize("shape", ["absolute", "dotdot", "symlink"])
def test_a_stored_path_into_clinic_a_is_never_served_to_clinic_b(world, shape):
    target = _a_pdf(world)
    secret = target.read_bytes()
    b_pdfs = clinic_dir(B) / "pdfs"
    b_pdfs.mkdir(parents=True, exist_ok=True)
    if shape == "absolute":
        raw = str(target)
    elif shape == "dotdot":
        raw = str(b_pdfs / ".." / ".." / A / "pdfs" / target.name)
    else:
        link = b_pdfs / "looks_local.pdf"
        link.symlink_to(target)
        raw = str(link)
    sql(B, "UPDATE documents SET pdf_path = ? WHERE id = 1", raw)
    r = world.iyer.get("/api/v1/documents/1/pdf")
    assert r.status_code == 200
    body = pdf_text(r)
    assert "Bharat Menon" in body and not leaks(body, A_MARKERS)       # B's own document 1, rendered afresh
    assert target.read_bytes() == secret                               # A's file untouched


def test_a_logo_stored_in_clinic_a_is_never_embedded_for_clinic_b(world):      # finding F1 if it fails
    a_logo = Path(sql(A, "SELECT logo_path FROM templates WHERE id = 1")[0]["logo_path"])
    b_logo = Path(sql(B, "SELECT logo_path FROM templates WHERE id = 1")[0]["logo_path"])
    secret = base64.b64encode(a_logo.read_bytes()).decode("ascii")
    own = base64.b64encode(b_logo.read_bytes()).decode("ascii")
    assert secret != own and own in reprint(world.iyer, B, 1)            # positive control: B's own logo prints
    link = b_logo.parent / "looks_local_logo.jpg"
    link.symlink_to(a_logo)
    for raw in (str(a_logo), str(b_logo.parent / ".." / ".." / A / "templates" / a_logo.name), str(link)):
        sql(B, "UPDATE templates SET logo_path = ? WHERE id = 1", raw)
        assert secret not in reprint(world.iyer, B, 1), raw
        preview = world.iyer.get("/api/v1/templates/1/preview.pdf")
        assert preview.status_code == 200 and secret.encode() not in preview.content, raw
    assert a_logo.is_file()


def test_an_upload_lands_in_the_uploading_clinics_folder_only(world):
    a_dir, b_dir = clinic_dir(A) / "templates", clinic_dir(B) / "templates"
    before = sorted(p.name for p in a_dir.iterdir())
    r = upload(world.iyer)
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    assert (b_dir / f"{tid}_original.jpg").is_file() and (b_dir / f"{tid}_logo.jpg").is_file()
    assert sorted(p.name for p in a_dir.iterdir()) == before
    stored = sql(B, "SELECT logo_path FROM templates WHERE id = ?", tid)[0]["logo_path"]
    assert Path(stored).resolve().is_relative_to(b_dir.resolve())


def test_the_directory_holds_no_patient_data_and_each_clinic_has_its_own_file(world):
    a_db, b_db = clinic_dir(A) / "app.db", clinic_dir(B) / "app.db"
    assert a_db.is_file() and b_db.is_file() and not os.path.samefile(a_db, b_db)
    with closing(open_directory()) as d:
        tables = {r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert not tables & {"patients", "encounters", "documents", "users", "audit_log", "templates", "clinic_profile"}
    raw = b"".join(p.read_bytes() for p in directory_path().parent.glob("directory.db*"))
    for value in ("Asha Verma", "Bharat Menon", "Paracetamol", "12 MG Road", "demo-rao-pass-1"):
        assert value.encode() not in raw, value
```

- [ ] **Step 2: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_isolation_files.py -q`
Expected: 7 passed.
**If only `test_a_logo_stored_in_clinic_a_is_never_embedded_for_clinic_b` fails, with A's logo found in B's output, finding F1 is still open.** This is expected if M4 was built as planned, since its plan does not touch `logo_data_uri`. Do not change production code. Put this line directly above that test and report F1 (for M4) in your final message:

```python
@pytest.mark.xfail(strict=True, reason="F1 (M4): templates/service.py logo_data_uri reads any stored path; confine it to templates_dir()")
```

Expected then: 6 passed, 1 xfailed. `strict=True` turns the marker into a failure on the day M4 fixes F1, so it cannot rot.
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 23` passed (or `N + 22` passed, 1 xfailed).

- [ ] **Step 3: Leave uncommitted.**

---

### Task 4: Fail-closed scope and the PDF worker thread

**Files:**
- Create: `tests/test_isolation_scope.py`

**Interfaces:**
- Consumes: `world`, `A`, `B`, `hint_lookup`, `opened_files`, `save` (Task 2); `db.db_path`/`pdf_dir`/`get_conn` (`db/__init__.py:35-69`); `templates.service.templates_dir`/`original_path` (`templates/service.py:21-27`); `scope.Scope`/`use_scope`/`NoScope`/`clinic_dir`; `directory.directory_path`. The "no scope inside a request answers 401" case is already pinned by `tests/test_startup.py:77-91`, and get_conn in a bare thread by `tests/test_clinic_paths.py:42-56`. This task widens both to every path helper and adds the real-request and real-worker checks.
- Produces: tests only.

- [ ] **Step 1: Write the tests**

`tests/test_isolation_scope.py`:

```python
"""Fail-closed scope (spec 5.3, 13.1): with no scope every clinic path helper raises NoScope, in a bare thread and
in a fresh pool thread; a signed-in request only ever opens its own clinic's file; the PDF worker thread never
opens a database. Offline. "No scope inside a request answers 401" is pinned by tests/test_startup.py:77."""
import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation import scope as S
from doctor_dictation.directory import directory_path
from doctor_dictation.templates import service
from isolation_fixtures import A, B, hint_lookup, opened_files, save, world  # noqa: F401

HELPERS = {
    "db_path": dbmod.db_path,
    "pdf_dir": dbmod.pdf_dir,
    "templates_dir": service.templates_dir,
    "original_path": lambda: service.original_path(1),
    "get_conn": lambda: dbmod.get_conn(),
    "doctor_hints": hint_lookup,
}


def _error_type(fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - the type is the point
        return type(exc)
    return None


@pytest.mark.parametrize("name", sorted(HELPERS))
def test_every_clinic_path_helper_fails_closed_in_a_bare_thread(multi, name):
    seen = []
    with S.use_scope(S.Scope("rao")):
        t = threading.Thread(target=lambda: seen.append(_error_type(HELPERS[name])))
        t.start()
        t.join()
    assert seen == [S.NoScope]
    assert not (multi / "clinics").exists()


def test_a_thread_pool_started_inside_a_scope_starts_empty_but_to_thread_keeps_it(multi):
    with S.use_scope(S.Scope("rao")):
        with ThreadPoolExecutor(2) as pool:
            errors = {name: pool.submit(_error_type, fn).result() for name, fn in HELPERS.items()}
        kept = asyncio.run(asyncio.to_thread(dbmod.db_path))
    assert errors == dict.fromkeys(HELPERS, S.NoScope)
    assert kept == S.clinic_dir("rao") / "app.db"
    assert not (multi / "clinics").exists()


def test_the_pdf_worker_thread_never_opens_a_database(world, monkeypatch):
    with opened_files(monkeypatch) as seen:
        save(world.rao, "Worker Probe")
        assert world.iyer.get("/api/v1/documents/2/pdf").status_code == 200
        assert world.iyer.get("/api/v1/templates/1/preview.pdf").status_code == 200
    threads = {r["thread"] for r in world.renders}
    assert threads and all(t.startswith("pdf-worker") for t in threads)
    assert [s for s in seen if s[0].startswith("pdf-worker")] == []


def test_every_database_a_request_opens_belongs_to_the_signed_in_clinic(world, monkeypatch):
    shared = str(directory_path())
    for who, mine in (("rao", A), ("iyer", B)):
        client = getattr(world, who)
        with opened_files(monkeypatch) as seen:
            save(client, "Scope Probe")
            for url in ("/api/v1/encounters/today", "/api/v1/profile", "/api/v1/patients",
                        "/api/v1/documents/1/pdf", "/api/v1/templates/active"):
                assert client.get(url).status_code == 200, url
        own = str(S.clinic_dir(mine)) + os.sep
        stray = [p for _thread, p in seen if p != shared and not p.startswith(own)]
        assert seen and stray == [], (who, stray)
```

- [ ] **Step 2: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_isolation_scope.py -q`
Expected: 9 passed. If `doctor_hints` fails because M3 changed `_doctor_top`'s signature, adjust `hint_lookup` (A5) only.
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 32` passed (minus any F1 xfail from Task 3).

- [ ] **Step 3: Leave uncommitted.**

---

### Task 5: Doctor level inside one clinic

**Files:**
- Create: `tests/test_isolation_doctors.py`

**Interfaces:**
- Consumes: `world`, `A`, `H`, `correct_body` (A3), `owner_refusal` (A2), `reprint`, `save_body`, `sql`, `today` (A4), `user_id` (Task 2); `admin_demo.doctor`, `admin_demo.PRESCRIPTIONS`; `config.override_settings`; patch point `doctor_dictation.api.stt.build_hints` (A5); `db.create_patient`/`create_encounter`/`save_document`.
- Produces: tests only.

- [ ] **Step 1: Write the tests**

`tests/test_isolation_doctors.py`:

```python
"""Doctor level inside Clinic A (spec 7, 13.1): Mehta views and reprints Rao's prescription with Rao's details,
cannot re-save or correct it, and hints and Today are per doctor. Offline."""
from contextlib import closing

from doctor_dictation import admin_demo
from doctor_dictation import db as dbmod
from doctor_dictation.config import override_settings
from doctor_dictation.scope import clinic_dir
from isolation_fixtures import (A, H, correct_body, owner_refusal, reprint, save_body, sql, today, user_id,
                                world)  # noqa: F401

RAO, MEHTA = admin_demo.doctor("dr.rao"), admin_demo.doctor("dr.mehta")


def _medicines(username):
    return {m for (_c, author, _p, _a, _d, meds) in admin_demo.PRESCRIPTIONS if author == username for m in meds}


def _doc_row(doc_id):
    return [tuple(r) for r in sql(A, "SELECT d.*, e.doctor_id FROM documents d"
                                     " JOIN encounters e ON e.id = d.encounter_id WHERE d.id = ?", doc_id)]


def test_a_colleague_can_view_the_prescription(world):
    r = world.mehta.get("/api/v1/documents/1")
    assert r.status_code == 200 and r.json()["structured"]["patientName"] == "Asha Verma"
    assert (r.json()["author"]["user_id"], r.json()["can_edit"]) == (user_id(world, "dr.rao"), False)   # A4
    assert world.rao.get("/api/v1/documents/1").json()["can_edit"] is True


def test_a_colleague_reprint_prints_the_authors_details(world):
    sql(A, "UPDATE templates SET status = 'archived' WHERE status = 'active'")    # built-in layout: author fields only
    html = reprint(world.mehta, A, 1)
    for value in (RAO["doctor_name"], RAO["qualifications"], RAO["reg_no"], "Rao Clinic"):
        assert value in html, value
    assert MEHTA["doctor_name"] not in html and MEHTA["reg_no"] not in html


def test_a_colleague_resave_is_403_and_changes_nothing(world):
    before = _doc_row(1)
    r = world.mehta.post("/api/v1/documents", json=save_body("Asha Verma", document_id=1), headers=H)
    assert (r.status_code, r.json()) == (403, owner_refusal(RAO["doctor_name"]))
    assert _doc_row(1) == before


def test_a_colleague_correction_is_403(world):
    r = world.mehta.post("/api/v1/correct", json=correct_body(1), headers=H)
    assert (r.status_code, r.json()) == (403, owner_refusal(RAO["doctor_name"]))


def test_the_author_can_still_resave_and_keeps_authorship(world):
    r = world.rao.post("/api/v1/documents", json=save_body("Asha Verma", document_id=1), headers=H)
    assert r.status_code == 200, r.text
    row = sql(A, "SELECT d.finalized_by, e.doctor_id FROM documents d JOIN encounters e ON e.id = d.encounter_id"
                 " WHERE d.id = 1")[0]
    rao = user_id(world, "dr.rao")
    assert (row["finalized_by"], row["doctor_id"]) == (rao, rao)


def test_a_prescription_with_no_recorded_author_stays_editable_by_anyone_in_the_clinic(world):
    with closing(dbmod.get_conn(clinic_dir(A) / "app.db")) as conn:
        pid = dbmod.create_patient(conn, "Legacy Patient", "50 / M", "OLD-1")
        eid = dbmod.create_encounter(conn, pid, op_no="OLD-1", status="finalized")
        doc = dbmod.save_document(conn, eid, "legacy-sha", save_body("Legacy Patient", "OLD-1")["structured"],
                                  finalized_at=dbmod._utcnow())
    r = world.mehta.post("/api/v1/documents", json=save_body("Legacy Patient", document_id=doc), headers=H)
    assert r.status_code == 200, r.text
    assert sql(A, "SELECT finalized_by FROM documents WHERE id = ?", doc)[0]["finalized_by"] == user_id(world, "dr.mehta")


def test_an_encounter_cannot_be_created_in_a_colleagues_name(world):          # finding F2 if it fails
    r = world.mehta.post("/api/v1/encounters", json={"patient_id": 1, "doctor_id": user_id(world, "dr.rao")}, headers=H)
    if r.status_code == 201:
        assert r.json()["doctor_id"] == user_id(world, "dr.mehta")            # the signed-in user, never the body's
    else:
        assert r.status_code in (400, 403, 422), r.text


def test_hints_come_from_the_signed_in_doctors_own_prescriptions(world, monkeypatch):
    override_settings(monkeypatch, stt_use_hints=True)
    seen = []
    monkeypatch.setattr("doctor_dictation.api.stt.build_hints", lambda top, limit: seen.append(set(top)) or [])
    for who in ("rao", "mehta", "iyer"):
        r = getattr(world, who).post("/api/transcribe", files={"audio": ("d.webm", b"fake audio", "audio/webm")},
                                     headers=H)
        assert r.status_code == 200, r.text
    assert seen == [_medicines("dr.rao"), _medicines("dr.mehta"), _medicines("dr.iyer")]


def test_today_mine_and_whole_clinic_differ(world):
    assert [r["document_id"] for r in today(world.mehta)] == [2]
    clinic = today(world.mehta, "clinic")
    assert [r["document_id"] for r in clinic] == [1, 2, 3]
    names = {r["document_id"]: r["doctor_name"] for r in clinic}
    assert names[1] in (RAO["display_name"], RAO["doctor_name"])
    assert names[2] in (MEHTA["display_name"], MEHTA["doctor_name"])
    assert [r["document_id"] for r in today(world.rao)] == [1, 3]
    assert [r["document_id"] for r in today(world.iyer, "clinic")] == [1, 2]
```

- [ ] **Step 2: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_isolation_doctors.py -q`
Expected: 9 passed.
**If only `test_an_encounter_cannot_be_created_in_a_colleagues_name` fails, with the stored `doctor_id` being Rao's, finding F2 is still open.** This is expected if M3 was built as planned, since its Assumption 6 leaves the route alone. Do not change production code. Put this line directly above that test and report F2 (for M3):

```python
@pytest.mark.xfail(strict=True, reason="F2 (M3): POST /api/v1/encounters stores doctor_id from the body; use the signed-in user")
```

and add `import pytest` at the top. Expected then: 8 passed, 1 xfailed. Any other failure is a finding against A1 to A5: check Task 0's notes, adjust the helper if only a name differs, otherwise report it.
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 41` passed (minus any F1/F2 xfails).

- [ ] **Step 3: Leave uncommitted.**

---

### Task 6: Auth in the seeded world

**Files:**
- Create: `tests/test_isolation_auth.py`

**Interfaces:**
- Consumes: `world`, `A`, `B`, `disable_user`, `enable_user`, `reset_user` (A14), `fingerprint`, `login`, `sql`, `user_id` (Task 2); `sessions.COOKIE_NAME`, `LIFETIME_SECONDS`, `sign`, `_b64`, `_unb64` (`sessions.py:18-89`); the middleware's CSRF response (`api/session.py:41-42`) and the login error (`api/auth.py:24`). Unit-level auth (scrypt, cookie format, throttling counters) is already covered by `tests/test_passwords.py`, `test_sessions.py`, `test_authn.py`, `test_session_middleware.py`, `test_auth_routes.py`. These tests add the cross-clinic and through-the-app cases section 13.1 lists.
- Produces: tests only.

- [ ] **Step 1: Write the tests**

`tests/test_isolation_auth.py`:

```python
"""Auth in the seeded world (spec 6.2, 13.1): forged and expired cookies, disable and reset end sessions, CSRF on
every write route, a lockout stays per user, and unknown-user timing stays close to a wrong password. Offline."""
import json
import os
import re
import statistics
import time

from fastapi.testclient import TestClient

from doctor_dictation import sessions
from isolation_fixtures import (A, B, disable_user, enable_user, fingerprint, login, reset_user, sql, user_id,
                                world)  # noqa: F401

BAD = {"error": "Wrong username or password"}


def _me_status(app, token):
    c = TestClient(app, follow_redirects=False)
    c.cookies.set(sessions.COOKIE_NAME, token)
    return c.get("/api/v1/auth/me").status_code


def _fresh_login(app, username, password=None):
    return login(TestClient(app, follow_redirects=False), username, password)


def test_a_cookie_edited_to_name_another_clinic_is_rejected(world, monkeypatch):
    body, sig = world.rao.cookies.get(sessions.COOKIE_NAME).split(".")
    payload = json.loads(sessions._unb64(body))
    payload["clinic"] = B
    forged = sessions._b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()) + "." + sig
    real = os.environ["SESSION_SECRET"]
    monkeypatch.setenv("SESSION_SECRET", "a-different-secret-" + "z" * 30)
    foreign = sessions.sign(B, 1, 0)                      # validly signed, but with someone else's key
    monkeypatch.setenv("SESSION_SECRET", real)
    for token in (forged, foreign):
        assert _me_status(world.app, token) == 401


def test_an_expired_cookie_is_rejected_but_a_fresh_one_for_the_same_user_works(world):
    rao = user_id(world, "dr.rao")
    ver = sql(A, "SELECT session_version FROM users WHERE id = ?", rao)[0][0]
    stale = sessions.sign(A, rao, ver, now=time.time() - sessions.LIFETIME_SECONDS - 5)
    assert _me_status(world.app, stale) == 401
    assert _me_status(world.app, sessions.sign(A, rao, ver)) == 200


def test_disabling_a_colleague_ends_their_session_at_once(world):
    mehta = user_id(world, "dr.mehta")
    assert world.mehta.get("/api/v1/auth/me").status_code == 200
    assert disable_user(world.rao, mehta).status_code == 200
    assert world.mehta.get("/api/v1/auth/me").status_code == 401
    assert _fresh_login(world.app, "dr.mehta").status_code == 401
    assert enable_user(world.rao, mehta).status_code == 200
    assert _fresh_login(world.app, "dr.mehta").status_code == 200


def test_a_password_reset_ends_the_session_and_retires_the_old_password(world):
    assert reset_user(world.rao, user_id(world, "dr.mehta")).status_code == 200
    assert world.mehta.get("/api/v1/auth/me").status_code == 401
    assert _fresh_login(world.app, "dr.mehta").status_code == 401


def test_every_write_route_refuses_a_request_without_the_csrf_header(world):
    before = fingerprint(A)
    wrong, checked = [], 0
    for path, ops in world.app.openapi()["paths"].items():
        for method in (m.upper() for m in ops):
            if method not in {"POST", "PUT", "DELETE", "PATCH"}:
                continue
            r = world.rao.request(method, re.sub(r"\{[^}]+\}", "1", path), json={})
            checked += 1
            if (r.status_code, r.json()) != (403, {"error": "missing X-DD-Client header"}):
                wrong.append(f"{method} {path} -> {r.status_code}")
    assert checked >= 10 and not wrong, wrong
    assert fingerprint(A) == before
    assert world.rao.get("/api/v1/auth/me").status_code == 200          # the refused logout ended nothing


def test_a_lockout_in_one_clinic_never_locks_the_other(world):
    for _ in range(5):
        assert _fresh_login(world.app, "dr.rao", "wrong-password-0").status_code == 401
    r = _fresh_login(world.app, "dr.rao")
    assert (r.status_code, r.json()) == (401, BAD)                        # locked: same answer as a wrong password
    assert _fresh_login(world.app, "dr.iyer").status_code == 200
    assert _fresh_login(world.app, "dr.mehta").status_code == 200
    assert world.rao.get("/api/v1/auth/me").status_code == 200           # an open session survives a lockout


def test_unknown_usernames_cost_about_the_same_as_a_wrong_password(world):
    def took(username):
        start = time.perf_counter()
        assert _fresh_login(world.app, username, "not-the-password-1").status_code == 401
        return time.perf_counter() - start

    took("dr.iyer")                                                     # warm up: first clinic open
    took("warm-up-ghost")                                               # warm up: the cached dummy hash
    known = statistics.median(took("dr.rao") for _ in range(3))
    unknown = statistics.median(took(f"ghost-{i}") for i in range(3))
    assert 0.25 < unknown / known < 4, (unknown, known)                 # a loose bound, not a timing test
```

- [ ] **Step 2: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_isolation_auth.py -q`
Expected: 7 passed. If the timing test is flaky on a loaded machine, rerun once. Do not tighten or widen the bound; report it if it fails twice.
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 48` passed (minus any F1/F2 xfails).

- [ ] **Step 3: Leave uncommitted.**

---

### Task 7: Letterhead through HTTP

**Files:**
- Create: `tests/test_isolation_letterhead.py`

**Interfaces:**
- Consumes: `world`, `A`, `B`, `A_MARKERS`, `H`, `UPLOAD_PAD`, `UPLOAD_PAD_LINE`, `accept`, `use_clinic_letterhead` (A11), `disable_user` (A14), `doctor_warning` (A12), `leaks`, `reprint`, `set_doctors` (A10), `sql`, `upload`, `user_id` (Task 2); `admin_demo.doctor`, `RAO_PAD_LINE`, `IYER_PAD_LINE`; the `doctors_mode`/`doctors_ids` columns (A8).
- Produces: tests only. M4's own unit tests cover the vocabulary and resolution rules. These tests prove the same rules end to end through the seeded world, and that nothing crosses clinics.

- [ ] **Step 1: Write the tests**

`tests/test_isolation_letterhead.py`:

```python
"""Letterhead through HTTP (spec 9, 13.1): clinic default, a doctor's opt-in and switch back, the doctors block in
all three modes, a disabled doctor left off, the review warning, and no effect across clinics. Offline."""
import json

from doctor_dictation import admin_demo
from isolation_fixtures import (A, A_MARKERS, B, H, UPLOAD_PAD, UPLOAD_PAD_LINE, accept, disable_user,
                                doctor_warning, leaks, reprint, set_doctors, sql, upload, use_clinic_letterhead,
                                user_id, world)  # noqa: F401

RAO, MEHTA = admin_demo.doctor("dr.rao")["doctor_name"], admin_demo.doctor("dr.mehta")["doctor_name"]
SUSPICIOUS = "Dr. K. Iyer, MBBS, MS (ENT)"


def test_each_clinic_prints_on_its_own_clinic_letterhead(world):
    a, b = reprint(world.mehta, A, 2), reprint(world.iyer, B, 1)
    assert admin_demo.RAO_PAD_LINE in a and admin_demo.IYER_PAD_LINE not in a
    assert RAO in a and MEHTA in a                                   # the shared pad lists every doctor ("all")
    assert admin_demo.IYER_PAD_LINE in b and not leaks(b, A_MARKERS)


def test_a_doctor_can_opt_in_to_their_own_letterhead_and_switch_back(world):
    r = upload(world.mehta)                                          # the stub reads UPLOAD_PAD
    assert r.status_code == 201, r.text
    assert accept(world.mehta, r.json()["id"], scope="mine").status_code == 200
    assert UPLOAD_PAD_LINE in reprint(world.mehta, A, 2)             # Mehta's own prescription: Mehta's pad
    assert UPLOAD_PAD_LINE in reprint(world.rao, A, 2)               # the AUTHOR's choice, whoever reprints
    rao_own = reprint(world.rao, A, 1)
    assert admin_demo.RAO_PAD_LINE in rao_own and UPLOAD_PAD_LINE not in rao_own
    assert admin_demo.IYER_PAD_LINE in reprint(world.iyer, B, 1)
    assert use_clinic_letterhead(world.mehta).status_code == 200
    back = reprint(world.mehta, A, 2)
    assert admin_demo.RAO_PAD_LINE in back and UPLOAD_PAD_LINE not in back


def test_the_doctors_block_follows_author_all_and_selected(world):
    tid, mehta = world.seeded[A]["template_id"], user_id(world, "dr.mehta")
    assert set_doctors(world.rao, tid, "author").status_code == 200
    html = reprint(world.rao, A, 3)                                  # document 3 is Rao's
    assert RAO in html and MEHTA not in html
    assert set_doctors(world.rao, tid, "all").status_code == 200
    by_rao, by_mehta = reprint(world.rao, A, 3), reprint(world.mehta, A, 3)
    assert RAO in by_rao and MEHTA in by_rao
    assert (by_rao.index(RAO) < by_rao.index(MEHTA)) == (by_mehta.index(RAO) < by_mehta.index(MEHTA))   # stable
    assert set_doctors(world.rao, tid, "selected", [mehta]).status_code == 200
    sql(A, "UPDATE templates SET doctors_ids = ? WHERE id = ?", json.dumps([mehta, 99]), tid)        # A8: unknown id
    html = reprint(world.rao, A, 3)
    assert MEHTA in html and RAO not in html


def test_a_disabled_doctor_is_left_off_the_letterhead(world):
    tid, mehta = world.seeded[A]["template_id"], user_id(world, "dr.mehta")
    assert set_doctors(world.rao, tid, "all").status_code == 200
    assert disable_user(world.rao, mehta).status_code == 200
    html = reprint(world.rao, A, 3)
    assert RAO in html and MEHTA not in html
    sql(A, "UPDATE templates SET doctors_mode = 'selected', doctors_ids = ? WHERE id = ?", json.dumps([mehta]), tid)
    assert MEHTA not in reprint(world.rao, A, 3)


def test_the_review_warns_about_a_literal_line_that_looks_like_a_doctor(world, monkeypatch):
    pad = json.loads(json.dumps(UPLOAD_PAD))
    pad["header"].append({"type": "text", "text": SUSPICIOUS, "role": "small", "align": "center"})
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(pad))
    r = upload(world.iyer)
    assert r.status_code == 201, r.text
    assert doctor_warning(r.json(), SUSPICIOUS)
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(UPLOAD_PAD))
    clean = upload(world.iyer)
    assert clean.status_code == 201 and not doctor_warning(clean.json(), UPLOAD_PAD_LINE)


def test_letterhead_changes_in_one_clinic_never_reach_the_other(world):
    before = [tuple(r) for r in sql(B, "SELECT * FROM templates ORDER BY id")]
    tid = world.seeded[A]["template_id"]
    assert set_doctors(world.rao, tid, "author").status_code == 200
    assert world.rao.post("/api/v1/templates/deactivate", headers=H).status_code == 200
    assert [tuple(r) for r in sql(B, "SELECT * FROM templates ORDER BY id")] == before
    assert admin_demo.IYER_PAD_LINE in reprint(world.iyer, B, 1)
    assert admin_demo.RAO_PAD_LINE not in reprint(world.rao, A, 1)   # A is on the built-in layout now
```

- [ ] **Step 2: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_isolation_letterhead.py -q`
Expected: 6 passed. If `test_the_review_warns_about_a_literal_line_that_looks_like_a_doctor` fails because M4 shows the warning only in `letterhead.js` (A12), replace its body with a static check. Read `frontend/letterhead.js`, assert it contains the heuristic's whole-word list (`Dr`, `MBBS`, `MD`, `MS`, `DNB`) and its warning text. Keep the test name and tell the user.
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 54` passed (minus any F1/F2 xfails).

- [ ] **Step 3: Leave uncommitted.**

---

### Task 8: OP numbers across clinics

**Files:**
- Create: `tests/test_isolation_opno.py`

**Interfaces:**
- Consumes: `world`, `A`, `B`, `H`, `save`, `save_body`, `sql` (Task 2); A13. Within-clinic sequencing and the single-clinic concurrency rule are already covered by `tests/test_opno.py:20-200` (single-database mode); this adds two clinics at once.
- Produces: tests only.

- [ ] **Step 1: Write the tests**

`tests/test_isolation_opno.py`:

```python
"""OP numbers (spec 10, 13.1): each clinic has its own prefix and its own sequence, and concurrent saves inside a
clinic still get distinct numbers while the other clinic saves too. Offline."""
import re
from concurrent.futures import ThreadPoolExecutor

from isolation_fixtures import A, B, H, save, save_body, sql, world  # noqa: F401


def _ops(slug):
    return [r["op_no"] for r in sql(slug, "SELECT op_no FROM patients ORDER BY id")]


def test_both_clinics_start_the_day_at_001_with_their_own_prefix(world):
    a, b = _ops(A)[0], _ops(B)[0]
    assert re.fullmatch(r"RAO-\d{8}-001", a) and re.fullmatch(r"IYER-\d{8}-001", b)
    assert a != b and a[-12:] == b[-12:]                 # same day and sequence number, different prefix


def test_the_next_number_continues_inside_each_clinic_only(world):
    a, b = save(world.mehta, "Next A Patient"), save(world.iyer, "Next B Patient")
    day = _ops(A)[0][4:12]
    assert (a["op_no"], b["op_no"]) == (f"RAO-{day}-004", f"IYER-{day}-003")


def test_concurrent_saves_get_distinct_numbers_inside_each_clinic(world):
    jobs = ([(world.rao, f"Rao Rush {i}") for i in range(4)] + [(world.mehta, f"Mehta Rush {i}") for i in range(4)]
            + [(world.iyer, f"Iyer Rush {i}") for i in range(4)])
    with ThreadPoolExecutor(12) as pool:
        results = list(pool.map(lambda job: job[0].post("/api/v1/documents", json=save_body(job[1]), headers=H), jobs))
    assert all(r.status_code == 200 for r in results), [r.text for r in results if r.status_code != 200]
    a_ops, b_ops = {r.json()["op_no"] for r in results[:8]}, {r.json()["op_no"] for r in results[8:]}
    assert len(a_ops) == 8 and all(o.startswith("RAO-") for o in a_ops)
    assert len(b_ops) == 4 and all(o.startswith("IYER-") for o in b_ops)
    assert (len(_ops(A)), len(_ops(B))) == (3 + 8, 2 + 4)
```

- [ ] **Step 2: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_isolation_opno.py -q`
Expected: 3 passed. (If this runs across local midnight, the day changes between seed and save; rerun.)
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 57` passed (minus any F1/F2 xfails).

- [ ] **Step 3: Leave uncommitted.**

---

### Task 9: Demo script (README) and browser evidence

**Files:**
- Create: `scripts/demo_browser.py`, `tests/test_demo_script.py`
- Modify: `README.md` (one new section after "Multi-clinic sign-in", before `## Notes`, line 119)

**Interfaces:**
- Consumes: `admin_demo.DOCTORS` (Task 1); a running server; the page ids `#username`, `#password`, `#loginForm` (`frontend/login.html:14-21`), `#topClinic`, `#todayList`, `.today-item`, `.today-name` (`frontend/index.html:15,32`, `frontend/app.js:222-251`), `#recBtn`, `#saveBtn`, `#printBtn`, `#blockPanel`, `#confirmAllBtn`, `#profileOpenBtn`, `#profilePanel` (`frontend/index.html`); M3's `#todayScope [data-scope="clinic"]` and `#viewOnlyBanner` (A4).
- Produces: `scripts/demo_browser.py` with `EVIDENCE`, `STEPS` (6 literal step names), `SERVER_ENV`, `main(argv) -> int` (`--print-env`, `--base`, `--data-dir`, `--headed`). Output: `.superpowers/demo-evidence/<YYYYMMDD-HHMMSS>/` (`.superpowers/` is already in `.gitignore`), holding PNGs, PDFs and `evidence.txt`.

- [ ] **Step 1: Write the failing tests**

`tests/test_demo_script.py`:

```python
"""The browser evidence script (spec 13.1 "Browser", 13.2): it compiles, follows the six demo steps, takes the demo
logins from the seed, and writes only under a git-ignored folder. No browser is started."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "demo_browser.py"


def _assigned(tree, name):
    return next(ast.literal_eval(n.value) for n in tree.body
                if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets))


def test_the_browser_script_compiles_and_writes_only_under_an_ignored_folder():
    src = SCRIPT.read_text(encoding="utf-8")
    compile(src, str(SCRIPT), "exec")
    assert 'EVIDENCE = ROOT / ".superpowers" / "demo-evidence"' in src
    assert ".superpowers/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_the_browser_script_walks_the_six_demo_steps_with_the_seeded_logins():
    src = SCRIPT.read_text(encoding="utf-8")
    steps = _assigned(ast.parse(src), "STEPS")
    assert [s.split("-", 1)[0] for s in steps] == ["1", "2", "3", "4", "5", "6"]
    assert "from doctor_dictation.admin_demo import DOCTORS" in src
    assert "demo-rao-pass" not in src                  # one source for the demo passwords: admin_demo.py
```

Run: `.venv/bin/python -m pytest tests/test_demo_script.py -q`
Expected: FAIL (`FileNotFoundError` for `scripts/demo_browser.py`).

- [ ] **Step 2: Write the browser script**

`scripts/demo_browser.py`:

```python
"""Browser evidence for the multi-clinic demo (spec 13.1 "Browser" and the 13.2 demo script).

Signs Dr. Rao and Dr. Iyer in to two separate browser contexts (separate cookie jars, like two windows), later
Dr. Mehta in a third, walks the six demo steps against a RUNNING server, and saves screenshots, PDFs and an
evidence.txt log under .superpowers/demo-evidence/<timestamp>/ (git-ignored). Automatic checks print PASS/FAIL;
a person still reads every screenshot (the list is in the M6 plan, Task 9).

    .venv/bin/python scripts/demo_browser.py --print-env      # the stub STT/LLM settings the server must use
    .venv/bin/python scripts/demo_browser.py --base http://127.0.0.1:8765 --data-dir <the server's DATA_DIR>
"""
from __future__ import annotations

import argparse
import json
import shlex
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import TimeoutError as PwTimeout  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from doctor_dictation.admin_demo import DOCTORS  # noqa: E402

EVIDENCE = ROOT / ".superpowers" / "demo-evidence"
STEPS = ("1-two-windows", "2-rao-dictates-and-saves", "3-mehta-views-reprints-edit-refused", "4-letterheads",
         "5-pasted-link-404", "6-audit-and-data-folder")
PASSWORD = {d["username"]: d["password"] for d in DOCTORS}
JSON_HEADERS = {"Content-Type": "application/json", "X-DD-Client": "1"}
NEW_PATIENT = "Kiran Joshi"
STUB_FORM = {"patientName": NEW_PATIENT, "ageSex": "40 / M", "opNo": "", "diagnosis": ["Viral fever"],
             "complaints": ["Fever since 2 days"], "investigations": [],
             "rx": [{"form": "Tab.", "name": "Paracetamol", "strength": "650 mg", "dose": "1-0-1",
                     "timing": "After food", "duration": "3 days", "instructions": ""}],
             "advice": ["Plenty of fluids"], "review": "Review after 3 days"}
SERVER_ENV = {"ALLOW_STUB_PROVIDERS": "1", "STT_CHAIN": "stub", "LLM_PROVIDER": "stub",
              "STUB_TRANSCRIPT": "patient Kiran Joshi 40 year old male, fever since two days, tablet paracetamol "
                                 "650 mg twice daily after food for 3 days",
              "STUB_LLM_JSON": json.dumps(STUB_FORM)}


class Evidence:
    """The log, the PASS/FAIL checks and the saved files of one run."""

    def __init__(self, out: Path):
        self.out, self.lines, self.failed = out, [], []
        out.mkdir(parents=True, exist_ok=True)

    def log(self, text: str) -> None:
        print(text, flush=True)
        self.lines.append(text)

    def check(self, ok: bool, what: str) -> None:
        self.log(("PASS  " if ok else "FAIL  ") + what)
        if not ok:
            self.failed.append(what)

    def shot(self, page, name: str) -> None:
        page.screenshot(path=str(self.out / f"{name}.png"), full_page=True)
        self.log(f"saved {name}.png")

    def save(self, name: str, body: bytes) -> None:
        (self.out / name).write_bytes(body)
        self.log(f"saved {name}")

    def close(self) -> None:
        (self.out / "evidence.txt").write_text("\n".join(self.lines) + "\n", encoding="utf-8")


def wait_today(page) -> None:
    page.wait_for_selector("#todayList .today-item, #todayList .today-empty")


def today_names(page) -> list[str]:
    return page.locator("#todayList .today-item .today-name").all_inner_texts()


def visible(page, selector: str, timeout: int = 10_000) -> bool:
    try:
        page.wait_for_selector(selector, state="visible", timeout=timeout)
        return True
    except PwTimeout:
        return False


def sign_in(browser, base: str, username: str):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, permissions=["microphone"])
    page = ctx.new_page()
    page.on("dialog", lambda dialog: dialog.accept())
    page.goto(f"{base}/login")
    page.fill("#username", username)
    page.fill("#password", PASSWORD[username])
    page.click("#loginForm button[type=submit]")
    page.wait_for_url(f"{base}/")
    page.wait_for_function("document.getElementById('topClinic').textContent.trim() !== 'Clinic'")
    wait_today(page)
    return ctx, page


def api(ctx, base: str, method: str, path: str, body=None):
    r = ctx.request.fetch(base + path, method=method, headers=JSON_HEADERS,
                          data=None if body is None else json.dumps(body))
    return r.status, r.body()


def api_json(ctx, base: str, path: str):
    status, body = api(ctx, base, "GET", path)
    if status != 200:
        raise RuntimeError(f"GET {path} answered {status}")
    return json.loads(body)


def switch_to_whole_clinic(page) -> bool:
    """A4 (M3): the Today toggle is #todayScope; its "Whole clinic" button has data-scope="clinic"."""
    try:
        page.click('#todayScope [data-scope="clinic"]', timeout=5_000)
        page.wait_for_timeout(800)
        return True
    except PwTimeout:
        return False


def dictate_and_save(ctx, page, base: str, ev: Evidence) -> None:
    """Fake microphone -> stub STT -> stub LLM -> Save. Falls back to the save API if no sheet appears."""
    try:
        page.click("#recBtn")
        page.wait_for_timeout(2_500)
        page.click("#recBtn")
        page.wait_for_selector("#saveBtn:not([hidden])", timeout=60_000)
        page.click("#saveBtn")
        if visible(page, "#blockPanel", timeout=3_000):       # the verify gate asks to confirm medicines
            page.click("#confirmAllBtn")
        page.wait_for_function("!document.getElementById('printBtn').disabled", timeout=60_000)
        ev.log("dictated through the fake microphone and saved with the Save button")
    except PwTimeout:
        form = {**STUB_FORM, "rx": [{**row, "status": "verified"} for row in STUB_FORM["rx"]]}
        status, _ = api(ctx, base, "POST", "/api/v1/documents", {"structured": form, "confirmed_rows": [0]})
        ev.log(f"FALLBACK: no sheet from the fake microphone; saved through the API instead (status {status})")


def run(browser, base: str, data_dir: Path, ev: Evidence) -> None:
    rao_ctx, rao = sign_in(browser, base, "dr.rao")
    iyer_ctx, iyer = sign_in(browser, base, "dr.iyer")

    ev.log(f"== {STEPS[0]}")
    ev.shot(rao, "1-rao-today")
    ev.shot(iyer, "1-iyer-today")
    rao_list, iyer_list = today_names(rao), today_names(iyer)
    ev.log(f"Rao Clinic Today: {rao_list}")
    ev.log(f"Iyer Clinic Today: {iyer_list}")
    ev.check(bool(rao_list) and bool(iyer_list) and not set(rao_list) & set(iyer_list), "the two Today lists differ")

    ev.log(f"== {STEPS[1]}")
    dictate_and_save(rao_ctx, rao, base, ev)
    new_id = max(row["document_id"] for row in api_json(rao_ctx, base, "/api/v1/encounters/today"))
    for page in (rao, iyer):
        page.reload()
        wait_today(page)
    ev.shot(rao, "2-rao-after-save")
    ev.shot(iyer, "2-iyer-unchanged")
    ev.check(NEW_PATIENT in today_names(rao) and NEW_PATIENT not in today_names(iyer),
             f"{NEW_PATIENT} (document {new_id}) shows in Rao Clinic only")
    firsts = {}
    for who, ctx in (("rao", rao_ctx), ("iyer", iyer_ctx)):
        page = ctx.new_page()
        page.goto(f"{base}/api/v1/documents/1")
        ev.shot(page, f"2-{who}-document-1")
        page.close()
        firsts[who] = api_json(ctx, base, "/api/v1/documents/1")["structured"]["patientName"]
    ev.check(firsts["rao"] != firsts["iyer"], f"document 1 is different in each clinic: {firsts}")

    ev.log(f"== {STEPS[2]}")
    mehta_ctx, mehta = sign_in(browser, base, "dr.mehta")
    switched = switch_to_whole_clinic(mehta)
    ev.shot(mehta, "3-mehta-whole-clinic")
    ev.check(switched and NEW_PATIENT in today_names(mehta), "Mehta's Whole clinic list shows Rao's new prescription")
    try:
        mehta.locator("#todayList .today-item", has_text=NEW_PATIENT).first.click(timeout=5_000)
    except PwTimeout:
        ev.log("could not click Rao's prescription in Mehta's Today list")
    banner = visible(mehta, "#viewOnlyBanner") and "view only" in mehta.inner_text("#viewOnlyBanner")
    ev.shot(mehta, "3-mehta-view-only")
    ev.check(banner, "a 'view only' banner shows on Rao's prescription")
    ev.check(mehta.is_disabled("#recBtn") and (mehta.is_hidden("#saveBtn") or mehta.is_disabled("#saveBtn")),
             "mic and Save are disabled for Mehta")
    status, body = api(mehta_ctx, base, "GET", f"/api/v1/documents/{new_id}/pdf")
    ev.save("3-mehta-reprint-of-rao.pdf", body)
    ev.check(status == 200 and body.startswith(b"%PDF"), f"Mehta can reprint Rao's prescription (status {status})")
    doc = api_json(mehta_ctx, base, f"/api/v1/documents/{new_id}")
    rows = list(range(len(doc["structured"].get("rx") or [])))
    status, body = api(mehta_ctx, base, "POST", "/api/v1/documents",
                       {"structured": doc["structured"], "confirmed_rows": rows, "document_id": new_id})
    ev.log(f"Mehta re-saving Rao's prescription: {status} {body.decode('utf-8', 'replace')}")
    ev.check(status == 403, "Mehta's re-save of Rao's prescription is refused (403)")

    ev.log(f"== {STEPS[3]}")
    for who, ctx, page in (("rao", rao_ctx, rao), ("iyer", iyer_ctx, iyer)):
        status, body = api(ctx, base, "GET", "/api/v1/documents/1/pdf")
        ev.save(f"4-{who}-clinic-letterhead.pdf", body)
        ev.check(status == 200 and body.startswith(b"%PDF"), f"{who}: document 1 prints as a PDF")
        page.click("#profileOpenBtn")
        page.wait_for_selector("#profilePanel[open]")
        page.wait_for_timeout(800)                       # the letterhead status loads after the dialog opens
        ev.shot(page, f"4-{who}-profile-letterhead")
        page.keyboard.press("Escape")

    ev.log(f"== {STEPS[4]}")
    link = f"{base}/api/v1/documents/{new_id}/pdf"
    resp = iyer.goto(link)
    got = resp.status if resp else None
    ev.shot(iyer, "5-iyer-opens-rao-pdf-link")
    ev.check(got == 404, f"Iyer opening {link} gets 404 (got {got})")

    ev.log(f"== {STEPS[5]}")
    ev.log(f"data folder {data_dir}:")
    for f in sorted(p for p in data_dir.rglob("*") if p.is_file()):
        ev.log(f"  {f.relative_to(data_dir)}  ({f.stat().st_size} bytes)")
    dbs = sorted((data_dir / "clinics").glob("*/app.db"))
    ev.check([d.parent.name for d in dbs] == ["iyer", "rao"] and (data_dir / "directory.db").is_file(),
             "directory.db plus one app.db per clinic (iyer, rao)")
    actors = {}
    for db in dbs:
        with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
            found = con.execute("SELECT COALESCE(actor, '-'), action, COUNT(*) FROM audit_log"
                                " GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
        actors[db.parent.name] = {r[0] for r in found}
        ev.log(f"audit log of {db.parent.name}:")
        for actor, action, n in found:
            ev.log(f"  {actor:<10} {action:<18} {n}")
    ev.check("dr.iyer" not in actors.get("rao", set()) and not {"dr.rao", "dr.mehta"} & actors.get("iyer", set()),
             "each clinic's audit log names only its own doctors")
    for ctx in (rao_ctx, iyer_ctx, mehta_ctx):
        ctx.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Browser evidence for the multi-clinic demo (spec 13.2).")
    parser.add_argument("--print-env", action="store_true", help="print the stub settings the server needs, then exit")
    parser.add_argument("--base", default="http://127.0.0.1:8765", help="where the server runs")
    parser.add_argument("--data-dir", type=Path, help="the server's DATA_DIR (for step 6)")
    parser.add_argument("--headed", action="store_true", help="show the browser windows")
    args = parser.parse_args(argv)
    if args.print_env:
        for key, value in SERVER_ENV.items():
            print(f"export {key}={shlex.quote(value)}")
        return 0
    if args.data_dir is None:
        parser.error("--data-dir is required (the DATA_DIR the server was started with)")
    ev = Evidence(EVIDENCE / datetime.now().strftime("%Y%m%d-%H%M%S"))
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not args.headed,
                                         args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
            try:
                run(browser, args.base.rstrip("/"), args.data_dir.resolve(), ev)
            finally:
                browser.close()
    finally:
        ev.close()
    print(f"\nevidence saved in {ev.out}")
    if ev.failed:
        print(f"{len(ev.failed)} automatic check(s) failed:\n  " + "\n  ".join(ev.failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Add the demo script to the README**

In `README.md`, after the line beginning `- Forgotten password: ...` (line 117) and its blank line, before `## Notes`, insert:

````markdown
## Multi-clinic demo (about 5 minutes)
Fake data only. `seed-demo` refuses to run unless `DEMO_MODE=1`, and only into an empty data folder; its three
doctors have published passwords (printed by the command), so never point it at real data.

```bash
export DEMO_DIR="$(mktemp -d)" MULTI_CLINIC=1 DEMO_MODE=1
export DATA_DIR="$DEMO_DIR" SESSION_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
python -m doctor_dictation.admin seed-demo         # Rao Clinic: dr.rao, dr.mehta; Iyer Clinic: dr.iyer
uvicorn doctor_dictation.main:app --port 8000
```

Use two browsers, or one normal and one private window (one window per clinic: they must not share cookies).
1. Sign in as `dr.rao` in one window and `dr.iyer` in the other: different clinic names and different Today lists.
2. Rao dictates and saves: it appears in Rao's Today only. Open `/api/v1/documents/1` in each window: both clinics
   have a document 1, with different patients.
3. Sign in as `dr.mehta` (a third window, or after Rao signs out), switch Today to "Whole clinic" and open Rao's
   prescription: a "view only" banner, mic and Save disabled. Print works and shows Dr. A. Rao. A re-save is refused.
4. Print a Rao Clinic prescription: the shared letterpad lists both doctors. Print an Iyer Clinic one: its own letterhead.
5. Copy the PDF link of Rao's new prescription (`/api/v1/documents/<id>/pdf`) into Iyer's window: 404.
6. Show the audit actors and the folder: `sqlite3 "$DEMO_DIR/clinics/rao/app.db" "SELECT actor, action FROM audit_log"`
   (and the same for `iyer`), then `ls -R "$DEMO_DIR"`: `directory.db` plus one `app.db` per clinic.

Automated run with screenshots for review: `scripts/demo_browser.py` (writes to `.superpowers/demo-evidence/`).
````

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_demo_script.py -q`
Expected: 2 passed.
Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N + 59` passed (or `N + 58` / `N + 57` passed with 1 / 2 xfailed for F1 / F2).

- [ ] **Step 5: Produce the browser evidence** (a subagent can do every step with Bash; nothing here is committed)

The harness keeps no shell state between calls, so the environment goes into a file under the ignored `.superpowers/demo-run/`:

```bash
cd /Users/narenlingala/Documents/workspace/work/Zebra/doctor-dic/doctor-dictation-main && rm -rf .superpowers/demo-run && mkdir -p .superpowers/demo-run && {
  echo "export MULTI_CLINIC=1 DEMO_MODE=1 DATA_DIR=$PWD/.superpowers/demo-run/data"
  echo "export SESSION_SECRET=$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
  .venv/bin/python scripts/demo_browser.py --print-env
} > .superpowers/demo-run/env.sh && . .superpowers/demo-run/env.sh && .venv/bin/python -m doctor_dictation.admin seed-demo
```

Expected: `DEMO ONLY: ...` and the three logins.

Start the server **in the background** (Bash `run_in_background: true`):

```bash
cd /Users/narenlingala/Documents/workspace/work/Zebra/doctor-dic/doctor-dictation-main && . .superpowers/demo-run/env.sh && exec .venv/bin/uvicorn doctor_dictation.main:app --host 127.0.0.1 --port 8765
```

Wait for it without `sleep`: `curl -sf --retry 30 --retry-connrefused --retry-delay 1 http://127.0.0.1:8765/api/health`. Expected: JSON with `"ok": true` and `"stt_engine_active": "stub"`.

Run the evidence script:

```bash
cd /Users/narenlingala/Documents/workspace/work/Zebra/doctor-dic/doctor-dictation-main && .venv/bin/python scripts/demo_browser.py --base http://127.0.0.1:8765 --data-dir .superpowers/demo-run/data
```

Expected: every line `PASS`, exit 0, and `evidence saved in .../.superpowers/demo-evidence/<timestamp>`. A `FALLBACK:` line in step 2 means headless Chromium's fake microphone did not produce a sheet. It is acceptable, because the save then goes through the same API, but say so in the report. Then stop the background server (TaskStop or `kill` its pid).

Read each PNG with the Read tool and check it against the table below. Report what you saw for each file, and every `FAIL`. **The user reads the screenshots too.** Your report is a first pass, not the sign-off.

| File | What a person must see |
|---|---|
| `1-rao-today.png` | Top bar "Rao Clinic" and "Dr. Rao". Today (My prescriptions) lists Asha Verma and Lakshmi Narayan, and nothing from Iyer Clinic. |
| `1-iyer-today.png` | Top bar "Iyer Clinic" and "Dr. Iyer". Today lists Bharat Menon and Meena Pillai, and none of Rao Clinic's names. |
| `2-rao-after-save.png` | Kiran Joshi added to Rao's Today with an OP number starting `RAO-` (ends `-004`). The sheet shows the saved prescription and Print is enabled. |
| `2-iyer-unchanged.png` | Iyer's Today exactly as in step 1: no Kiran Joshi. |
| `2-rao-document-1.png`, `2-iyer-document-1.png` | Both show `"document_id": 1`, with `patientName` "Asha Verma" for Rao and "Bharat Menon" for Iyer. |
| `3-mehta-whole-clinic.png` | Top bar "Dr. Mehta". The Today toggle is on "Whole clinic", and rows show author names, including Kiran Joshi by Dr. A. Rao. |
| `3-mehta-view-only.png` | Banner "Dr. A. Rao's prescription: view only". The sheet header shows Dr. A. Rao and TSMC 10001. Mic and Save are greyed out; Print is available. |
| `3-mehta-reprint-of-rao.pdf` | Rao Clinic's pad, patient Kiran Joshi, and "Dr. A. Rao" printed. Nothing says Mehta wrote it. |
| `evidence.txt`, step 3 | `Mehta re-saving Rao's prescription: 403 {"error": "This prescription belongs to Dr. A. Rao. You can view and reprint it."}` |
| `4-rao-clinic-letterhead.pdf` | Blue logo, "Rao Clinic", both "Dr. A. Rao" and "Dr. S. Mehta" listed, "Open Mon to Sat, 9 am to 1 pm", Hyderabad address. |
| `4-iyer-clinic-letterhead.pdf` | Green logo on the right, "Dr. K. Iyer", "MBBS, MS (ENT)", "ENT and allergy care, open daily 10 am to 6 pm", Chennai address. Nothing from Rao Clinic. |
| `4-rao-profile-letterhead.png`, `4-iyer-profile-letterhead.png` | Profile dialog with Clinic details for the right clinic. The letterhead section shows the clinic letterhead active and "My own letterhead: none". |
| `5-iyer-opens-rao-pdf-link.png` | A JSON page `{"error": "document_id <n> not found"}`: no PDF, no Rao data. |
| `evidence.txt`, step 6 | Files: `directory.db`, `clinics/iyer/app.db`, `clinics/rao/app.db` (plus `pdfs/`, `templates/`). Rao's audit actors are only `dr.rao`, `dr.mehta`, `seed-demo`; Iyer's only `dr.iyer`, `seed-demo`. |

**Fallback if Python Playwright cannot run but the Playwright MCP tools can:** use the same server. The MCP browser has one cookie jar, so put the two clinics on two host names: `http://127.0.0.1:8765` for Rao Clinic and `http://localhost:8765` for Iyer Clinic (cookies are per host). Save screenshots with `browser_take_screenshot` to `.superpowers/demo-evidence/mcp-<date>/<the file names above>`.
1. `browser_navigate` `http://127.0.0.1:8765/login`; `browser_fill_form` `#username` = `dr.rao`, `#password` = his password from `admin_demo.DOCTORS`; `browser_click` "Sign in"; screenshot `1-rao-today`.
2. `browser_tabs` (new tab), `browser_navigate` `http://localhost:8765/login`, sign in `dr.iyer`; screenshot `1-iyer-today`.
3. Rao's tab: `browser_evaluate` `fetch("/api/v1/documents", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({structured: {patientName: "Kiran Joshi", ageSex: "40 / M", rx: [{form: "Tab.", name: "Paracetamol", status: "verified"}]}, confirmed_rows: []})}).then(r => r.json())`. The page's `auth.js` adds the CSRF header. Reload; screenshots `2-rao-after-save`, then Iyer's tab `2-iyer-unchanged`; `browser_navigate` to `/api/v1/documents/1` in each tab for the `2-*-document-1` shots.
4. Rao's tab: click "Sign out", sign in `dr.mehta` on the same host, click "Whole clinic", click Kiran Joshi; screenshots `3-mehta-whole-clinic`, `3-mehta-view-only`. Then `browser_evaluate` a re-save `fetch` with `document_id` set to the new id, and record the 403 body.
5. Navigate each tab to `/api/v1/documents/1/pdf` (the headed MCP browser shows the PDF) for the `4-*` shots. Open Profile in each for `4-*-profile-letterhead`.
6. Iyer's tab: `browser_navigate` `http://localhost:8765/api/v1/documents/<new id>/pdf`; screenshot `5-iyer-opens-rao-pdf-link`.
7. Step 6 with Bash: `sqlite3 .superpowers/demo-run/data/clinics/rao/app.db "SELECT actor, action, COUNT(*) FROM audit_log GROUP BY 1, 2"`, the same for `iyer`, and `ls -R .superpowers/demo-run/data`.

- [ ] **Step 6: Leave uncommitted and list the changed files.** `git status --short` should show new: `doctor_dictation/admin_demo.py`, `scripts/demo_browser.py`, `tests/isolation_fixtures.py`, `tests/test_admin_demo.py`, `tests/test_isolation_routes.py`, `tests/test_isolation_files.py`, `tests/test_isolation_scope.py`, `tests/test_isolation_doctors.py`, `tests/test_isolation_auth.py`, `tests/test_isolation_letterhead.py`, `tests/test_isolation_opno.py`, `tests/test_demo_script.py`; modified: `doctor_dictation/admin.py`, `README.md`, `.env.example`. `.superpowers/demo-run/` and `.superpowers/demo-evidence/` are ignored and must not appear.

---

## Self-review (against the spec)

- **11 `seed-demo`:** two clinics (Rao Clinic: Dr. Rao, Dr. Mehta; Iyer Clinic: Dr. Iyer), fake patients and prescriptions, a "document 1" in each, per-clinic letterhead settings (shared pad mode `all`; own pad mode `author`), refuses unless `DEMO_MODE=1`: Task 1 (plus the empty-folder guard, see the differences section). Passwords are a decision, with its justification at the top.
- **13.1 Route sweep:** every route from `app.openapi()`, as Clinic B with Clinic A's ids: 404, no A markers, A's rows and files unchanged, A's file never opened. Both clinics' document 1 return their own record. Ids in bodies and queries too: Task 2.
- **13.1 Files:** A's PDFs, logos and uploads through B's session, including absolute, traversal and symlink paths; the directory holds no patient data: Task 3 (finding F1).
- **13.1 Fail-closed:** every path helper in a bare thread and a fresh pool thread; real requests open only their own clinic; the PDF worker never opens a database: Task 4 (no scope inside a request: existing `tests/test_startup.py:77`).
- **13.1 Doctor level:** view, reprint with Rao's details, re-save and correction refused with the exact message, author re-save, legacy documents editable, per-doctor hints, Today `mine` versus `clinic`: Task 5 (finding F2).
- **13.1 Auth:** success (fixture), failure and lockout, tampered (forged clinic, foreign key) and expired cookie, disable and reset end the session, missing CSRF header on every write route, unknown-user timing with a loose bound: Task 6 (unit cases stay in the existing auth tests).
- **13.1 Letterhead:** clinic default, opt-in and switch back, doctors block in all three modes, disabled and unknown ids skipped, review warning, no cross-clinic effect: Task 7.
- **13.1 OP numbers:** a `-001` in each clinic the same day with different prefixes, sequences per clinic, concurrency inside a clinic while the other clinic saves: Task 8.
- **13.1 Browser and 13.2 demo script:** README section (six steps) and `scripts/demo_browser.py` with three contexts and a screenshot checklist for a person: Task 9.
- **14 M6 row:** isolation suite, `seed-demo`, demo script, browser evidence: all of the above.
- **Placeholder scan:** none; every code block is complete.
- **Type and name consistency:** `world.seeded[slug]["users"][username]`, `["documents"]`, `["template_id"]` are used the same way everywhere. `A = "rao"`, `B = "iyer"`. Every helper the tests import is defined in `isolation_fixtures.py`.
- **Test count:** 9 + 7 + 7 + 9 + 9 + 7 + 6 + 3 + 2 = 59 (Task 3's and Task 4's parametrised tests count 3 and 6).

## Not in this plan

Fixing F1 or F2, or any other gap the suite finds (they go back to M4 and M3). Production changes of any kind beyond `admin_demo.py` and its registration. Real STT, LLM or vision calls; a real iPhone HEIC; printing through the iframe in Chrome and Safari (spec 15 still lists these as unverified). Running the browser script in CI. Load tests (D0b). The Postgres port. Per-clinic backup tooling.
