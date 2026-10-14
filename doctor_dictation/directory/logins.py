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
