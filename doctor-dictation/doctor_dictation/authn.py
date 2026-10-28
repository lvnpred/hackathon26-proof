"""Login and per-request identity. Every credential failure looks the same to the caller: ``None``."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import replace

from doctor_dictation import db as dbmod
from doctor_dictation import passwords, sessions
from doctor_dictation.directory import get_clinic, open_directory
from doctor_dictation.directory.revocations import is_revoked
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
        if clinic is None or clinic["status"] != "active" or is_revoked(d, payload["sid"]):
            return None
    row = _user_row(payload["clinic"], payload["uid"])
    if row is None or not row["is_active"] or row["session_version"] != payload["ver"]:
        return None
    return replace(_identity(payload["clinic"], row), sid=payload["sid"])


def clinic_name(slug) -> str:
    with closing(open_directory()) as d:
        row = get_clinic(d, slug)
    return row["name"] if row else ""
