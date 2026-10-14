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
            except (DirectoryError, sqlite3.Error) as exc:  # undo our own insert: no half-created user
                conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
                conn.commit()
                if isinstance(exc, DirectoryError):
                    raise AccountError(str(exc)) from None
                raise AccountError("could not index the username") from exc
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
        cur = conn.execute("UPDATE users SET password_hash = ?, must_change_password = 1, session_version = session_version + 1"
                           " WHERE id = ?", (hash_password(secret), entry["user_id"]))
        conn.commit()
        if cur.rowcount != 1:                              # directory index points at a missing user row
            raise AccountError("no such user")
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
        # one statement guarded by the hash we verified: a reset landing since the read makes this match nothing
        updated = conn.execute(
            "UPDATE users SET password_hash = ?, session_version = session_version + 1, must_change_password = 0"
            " WHERE id = ? AND password_hash = ? RETURNING session_version",
            (hash_password(new), identity.user_id, row["password_hash"])).fetchone()
        conn.commit()
        if updated is None:
            raise AccountError("Password was changed elsewhere, sign in again")
        version = updated["session_version"]
        dbmod.log_audit(conn, actor=identity.username, role=identity.role, action="password_change", entity="user",
                        entity_id=str(identity.user_id))
    return version
