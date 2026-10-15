"""SQLite persistence layer (P0-4): connection factory + thin repositories.

Stdlib ``sqlite3`` only (decision P-7 — no SQLAlchemy/Alembic yet). Migrations
are numbered SQL files in ``doctor_dictation/db/migrations/`` applied in filename order
and tracked in ``schema_migrations`` so ``init_db()`` is idempotent.

Timestamps are ISO-8601 UTC text (``2026-10-12T09:30:00Z``); IDs are
``INTEGER PRIMARY KEY AUTOINCREMENT``. Repository functions contain SQL only —
no business logic. All read helpers return ``sqlite3.Row`` (or ``None``) and
write helpers return the new row id.
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from doctor_dictation.scope import clinic_dir, current_scope, multi_clinic_enabled, require_scope

# This file *is* the ``doctor_dictation.db`` package, so ``__file__`` is
# ``doctor_dictation/db/__init__.py``. Resolve relative to the package directory
# (``doctor_dictation/db``) and its parent (``doctor_dictation``) explicitly so both paths match
# the originals from when this was the module ``doctor_dictation/db.py``:
#   DEFAULT_DB_PATH  -> doctor_dictation/data/app.db
#   MIGRATIONS_DIR   -> doctor_dictation/db/migrations
_PACKAGE_DIR = Path(__file__).resolve().parent  # doctor_dictation/db
# Default DB location (decision: env DB_PATH, else doctor_dictation/data/app.db).
DB_PATH_ENV = "DB_PATH"
DEFAULT_DB_PATH = _PACKAGE_DIR.parent / "data" / "app.db"
MIGRATIONS_DIR = _PACKAGE_DIR / "migrations"


# --- connection + migrations ----------------------------------------------

def db_path() -> Path:
    """Resolve the DB path at call time (monkeypatch-friendly).

    Multi-clinic mode (``MULTI_CLINIC=1``): the scoped clinic's ``app.db``; ``NoScope`` when
    there is no scope. ``DB_PATH`` is ignored there and nothing falls back to a default.
    """
    if multi_clinic_enabled():
        return clinic_dir(require_scope().clinic_slug) / "app.db"
    env = os.getenv(DB_PATH_ENV)
    return Path(env) if env else DEFAULT_DB_PATH


def pdf_dir() -> Path:
    """Directory rendered PDFs are written to (sibling of the DB file).

    Defaults to ``doctor_dictation/data/pdfs``; follows ``DB_PATH`` so tests/installs get
    an isolated folder. Created on demand by the renderer's caller (Task 8).
    """
    return db_path().parent / "pdfs"


def get_conn(path=None) -> sqlite3.Connection:
    """Open a connection: Row factory, foreign keys ON, WAL journal mode.

    ``path`` defaults to :func:`db_path`. The parent directory is created if
    missing. Callers own the connection and must close it.
    """
    p = Path(path) if path is not None else db_path()
    if str(p) != ":memory:":
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def discover_migrations(migrations_dir=None):
    """Return ``[(version, path)]`` for ``*.sql`` sorted by filename."""
    d = Path(migrations_dir) if migrations_dir is not None else MIGRATIONS_DIR
    if not d.exists():
        return []
    return [(p.name, p) for p in sorted(d.glob("*.sql"))]


def migrate(conn, migrations_dir=None) -> list:
    """Apply pending migrations idempotently; return the versions applied now.

    ``schema_migrations`` records each applied ``version`` (the SQL filename).
    A version already present is skipped, so a second call is a no-op.
    """
    conn.executescript(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    conn.commit()
    applied = {
        r["version"] for r in conn.execute("SELECT version FROM schema_migrations")
    }
    newly_applied = []
    for version, path in discover_migrations(migrations_dir):
        if version in applied:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, _utcnow()),
        )
        conn.commit()
        newly_applied.append(version)
    return newly_applied


def init_db(path=None) -> list:
    """Open the DB, apply migrations, close. Called on app startup."""
    conn = get_conn(path)
    try:
        return migrate(conn)
    finally:
        conn.close()


# --- helpers ---------------------------------------------------------------

def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_json(value):
    """Store dict/list/dict-like as JSON text; pass strings through; None stays None."""
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


# --- patients --------------------------------------------------------------

def create_patient(conn, name, age_sex="", op_no=None, created_at=None) -> int:
    cur = conn.execute(
        "INSERT INTO patients(name, age_sex, op_no, created_at) VALUES (?, ?, ?, ?)",
        (name, age_sex, op_no, created_at or _utcnow()),
    )
    conn.commit()
    return cur.lastrowid


def get_patient(conn, patient_id):
    return conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()


def list_patients(conn, limit=100, offset=0):
    return conn.execute(
        "SELECT * FROM patients ORDER BY id LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()


def find_patient_by_op(conn, op_no):
    """Return the first patient matching ``op_no`` (or None)."""
    return conn.execute(
        "SELECT * FROM patients WHERE op_no = ? ORDER BY id LIMIT 1", (op_no,)
    ).fetchone()


def find_patients_by_op(conn, op_no):
    """Return every patient sharing ``op_no`` (ordered by id); empty when none.

    OP numbers are not unique in practice (two patients can share one), so the
    caller needs the full set to tie-break by name before deciding.
    """
    return conn.execute(
        "SELECT * FROM patients WHERE op_no = ? ORDER BY id", (op_no,)
    ).fetchall()


def upsert_patient(conn, name, age_sex="", op_no=None) -> int:
    """Insert a patient, or update the existing one when ``op_no`` is non-empty.

    A falsy ``op_no`` (None or "") never matches, so it always inserts a new row.
    OP is primary: exactly one patient with the OP is updated in place (a dictated
    name correction updates the same patient). When several share the OP, the
    tie is broken by name (trimmed, case-insensitive); if none matches, a new
    patient is inserted rather than clobbering another patient's row.
    Returns the patient id (existing row's id when updating).
    """
    if op_no:
        matches = find_patients_by_op(conn, op_no)
        existing = None
        if len(matches) == 1:
            existing = matches[0]
        elif len(matches) > 1:
            want = (name or "").strip().lower()
            existing = next(
                (r for r in matches if (r["name"] or "").strip().lower() == want),
                None,
            )
        if existing is not None:
            conn.execute(
                "UPDATE patients SET name = ?, age_sex = ? WHERE id = ?",
                (name, age_sex, existing["id"]),
            )
            conn.commit()
            return existing["id"]
    return create_patient(conn, name, age_sex, op_no)


# --- encounters ------------------------------------------------------------

def create_encounter(
    conn,
    patient_id,
    doctor_id=None,
    op_no=None,
    status="draft",
    consent_at=None,
    created_at=None,
) -> int:
    cur = conn.execute(
        "INSERT INTO encounters"
        "(patient_id, doctor_id, op_no, status, consent_at, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (patient_id, doctor_id, op_no, status, consent_at, created_at or _utcnow()),
    )
    conn.commit()
    return cur.lastrowid


def get_encounter(conn, encounter_id):
    return conn.execute(
        "SELECT * FROM encounters WHERE id = ?", (encounter_id,)
    ).fetchone()


def list_encounters(conn, patient_id=None, limit=100, offset=0):
    if patient_id is None:
        return conn.execute(
            "SELECT * FROM encounters ORDER BY id LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
    return conn.execute(
        "SELECT * FROM encounters WHERE patient_id = ? ORDER BY id LIMIT ? OFFSET ?",
        (patient_id, limit, offset),
    ).fetchall()


# --- users -----------------------------------------------------------------

def create_user(
    conn, username, password_hash, role="doctor", is_active=1, created_at=None
) -> int:
    cur = conn.execute(
        "INSERT INTO users(username, password_hash, role, is_active, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (username, password_hash, role, is_active, created_at or _utcnow()),
    )
    conn.commit()
    return cur.lastrowid


def get_user_by_username(conn, username):
    return conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()


# --- audit log -------------------------------------------------------------

def log_audit(
    conn,
    actor=None,
    role=None,
    action="",
    entity=None,
    entity_id=None,
    detail=None,
    ip=None,
    at=None,
) -> int:
    if actor is None and (sc := current_scope()) is not None:
        actor, role = sc.username, role or sc.role
    cur = conn.execute(
        "INSERT INTO audit_log(actor, role, action, entity, entity_id, detail, ip, at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (actor, role, action, entity, entity_id, _as_json(detail), ip, at or _utcnow()),
    )
    conn.commit()
    return cur.lastrowid


# --- documents -------------------------------------------------------------

def save_document(
    conn,
    encounter_id,
    transcript_sha,
    structured_json,
    engine=None,
    model_versions=None,
    finalized_by=None,
    finalized_at=None,
    created_at=None,
    pdf_path=None,
) -> int:
    cur = conn.execute(
        "INSERT INTO documents"
        "(encounter_id, transcript_sha, structured_json, engine, model_versions,"
        " finalized_by, finalized_at, created_at, pdf_path)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            encounter_id,
            transcript_sha,
            _as_json(structured_json),
            engine,
            _as_json(model_versions),
            finalized_by,
            finalized_at,
            created_at or _utcnow(),
            pdf_path,
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_document_by_sha(conn, transcript_sha):
    """Return the most recently saved document for a transcript hash (or None)."""
    return conn.execute(
        "SELECT * FROM documents WHERE transcript_sha = ? ORDER BY id DESC LIMIT 1",
        (transcript_sha,),
    ).fetchone()


def update_document(
    conn,
    document_id,
    structured_json,
    engine=None,
    finalized_at=None,
    transcript_sha=None,
    pdf_path=None,
) -> int:
    """Overwrite an existing document row in place; return the affected row count.

    Used when a reopened "today" document is saved again so the sheet does not
    accumulate duplicate rows. ``transcript_sha`` is ``NOT NULL``, so a ``None``
    keeps the stored hash rather than clearing it (a re-save with no fresh
    transcript). An unknown ``document_id`` affects 0 rows; the caller maps that
    to a 404.
    """
    cur = conn.execute(
        "UPDATE documents SET structured_json = ?, engine = ?, finalized_at = ?,"
        " transcript_sha = COALESCE(?, transcript_sha), pdf_path = ?"
        " WHERE id = ?",
        (
            _as_json(structured_json),
            engine,
            finalized_at,
            transcript_sha,
            pdf_path,
            document_id,
        ),
    )
    conn.commit()
    return cur.rowcount


def set_document_pdf_path(conn, document_id, pdf_path) -> int:
    """Record (or clear) a document's rendered PDF path; return rows changed."""
    cur = conn.execute(
        "UPDATE documents SET pdf_path = ? WHERE id = ?", (pdf_path, document_id)
    )
    conn.commit()
    return cur.rowcount


def get_document(conn, document_id):
    """Return the document row for ``document_id`` (or None)."""
    return conn.execute(
        "SELECT * FROM documents WHERE id = ?", (document_id,)
    ).fetchone()


TOP_MEDICINES_WINDOW = 500  # newest finalized documents scanned


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
    counts: dict[str, int] = {}
    display: dict[str, str] = {}
    for (raw,) in rows:                      # newest first: dict order is recency order
        try:
            rx = json.loads(raw).get("rx")
        except (TypeError, ValueError, AttributeError):
            continue
        for row in rx if isinstance(rx, list) else ():
            name = row.get("name") if isinstance(row, dict) else None
            if not isinstance(name, str) or not name.strip():
                continue
            clean = " ".join(name.split())
            counts[clean.casefold()] = counts.get(clean.casefold(), 0) + 1
            display.setdefault(clean.casefold(), clean)
    ranked = sorted(counts, key=lambda k: -counts[k])   # stable: recency breaks ties
    return [display[k] for k in ranked[:limit]]


def local_day_bounds_utc(now=None) -> tuple[str, str]:
    """UTC ISO bounds ``[start, end)`` of the server-local calendar day.

    ``now`` may be timezone-aware; its ``tzinfo`` determines which local
    calendar day is used (tests pin a fixed offset). When ``None``, the server's
    local timezone is used. Both bounds are formatted exactly like stored
    ``created_at`` values (``%Y-%m-%dT%H:%M:%SZ``) so a caller can filter with
    ``created_at >= start AND created_at < end``.
    """
    if now is None:
        now = datetime.now().astimezone()
    tz = now.tzinfo
    start_local = datetime(now.year, now.month, now.day, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return (
        start_local.astimezone(timezone.utc).strftime(fmt),
        end_local.astimezone(timezone.utc).strftime(fmt),
    )


def list_documents_between(conn, start_iso, end_iso):
    """Documents saved in the half-open UTC range ``[start_iso, end_iso)``.

    Joined to their encounter and patient for the "Today" sidebar, each row
    exposes ``document_id, encounter_id, patient_name, op_no, created_at``,
    ordered oldest-first by save time.
    """
    return conn.execute(
        "SELECT d.id AS document_id, d.encounter_id AS encounter_id,"
        " p.name AS patient_name, e.op_no AS op_no, d.created_at AS created_at"
        " FROM documents d"
        " JOIN encounters e ON e.id = d.encounter_id"
        " JOIN patients p ON p.id = e.patient_id"
        " WHERE d.created_at >= ? AND d.created_at < ?"
        " ORDER BY d.created_at, d.id",
        (start_iso, end_iso),
    ).fetchall()


# --- clinic profile --------------------------------------------------------

def get_profile(conn):
    """Return the single clinic-profile row (or None when never saved)."""
    return conn.execute("SELECT * FROM clinic_profile WHERE id = 1").fetchone()


def save_profile(
    conn,
    doctor_name="",
    qualifications="",
    reg_no="",
    clinic_name="",
    address="",
    phone="",
    updated_at=None,
) -> None:
    """Upsert the single clinic-profile row (``id=1``)."""
    conn.execute(
        "INSERT INTO clinic_profile"
        "(id, doctor_name, qualifications, reg_no, clinic_name, address, phone,"
        " updated_at)"
        " VALUES (1, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET"
        " doctor_name = excluded.doctor_name,"
        " qualifications = excluded.qualifications,"
        " reg_no = excluded.reg_no,"
        " clinic_name = excluded.clinic_name,"
        " address = excluded.address,"
        " phone = excluded.phone,"
        " updated_at = excluded.updated_at",
        (
            doctor_name,
            qualifications,
            reg_no,
            clinic_name,
            address,
            phone,
            updated_at or _utcnow(),
        ),
    )
    conn.commit()
