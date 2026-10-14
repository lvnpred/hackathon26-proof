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
