"""Private download links (plan FB-D, C2): one row per prescription (its encounter). SQL and token rules only.

A link is live while it is not revoked and ``now < expires_at``. A re-save keeps the token and moves the expiry;
a re-save after a revoke issues a new token, so a revoked token stays dead.
"""
import re
import secrets
from datetime import datetime, timedelta, timezone

TTL = timedelta(days=7)
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{22}")        # token_urlsafe(16); match with fullmatch
_FMT = "%Y-%m-%dT%H:%M:%SZ"


def new_token() -> str:
    return secrets.token_urlsafe(16)               # 128 bits


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("share link times must be timezone-aware (UTC)")
    return dt.astimezone(timezone.utc).strftime(_FMT)


def parse(stamp: str) -> datetime:
    """A stored ``expires_at`` (or other stamp) as an aware UTC datetime."""
    return datetime.strptime(stamp, _FMT).replace(tzinfo=timezone.utc)


def link_for_encounter(conn, encounter_id):
    return conn.execute("SELECT * FROM share_links WHERE encounter_id = ?", (encounter_id,)).fetchone()


def find_by_token(conn, token):
    return conn.execute("SELECT * FROM share_links WHERE token = ?", (token,)).fetchone()


def is_live(row, now: datetime) -> bool:
    return row is not None and row["revoked_at"] is None and iso(now) < row["expires_at"]


def ensure_link(conn, encounter_id, now: datetime):
    """Create the encounter's link, or renew it on a re-save (a revoked one gets a new token). Commits."""
    stamp, expires = iso(now), iso(now + TTL)
    row = link_for_encounter(conn, encounter_id)
    if row is None:
        conn.execute(
            "INSERT INTO share_links(encounter_id, token, created_at, saved_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (encounter_id, new_token(), stamp, stamp, expires),
        )
    elif row["revoked_at"] is not None:
        conn.execute(
            "UPDATE share_links SET token = ?, saved_at = ?, expires_at = ?, revoked_at = NULL, revoked_by = NULL WHERE id = ?",
            (new_token(), stamp, expires, row["id"]),
        )
    else:
        conn.execute("UPDATE share_links SET saved_at = ?, expires_at = ? WHERE id = ?", (stamp, expires, row["id"]))
    conn.commit()
    return link_for_encounter(conn, encounter_id)


def revoke(conn, encounter_id, user_id, now: datetime) -> bool:
    """Kill the encounter's live link. False when there is none (missing, expired or already revoked). Commits."""
    if not is_live(link_for_encounter(conn, encounter_id), now):
        return False
    conn.execute(
        "UPDATE share_links SET revoked_at = ?, revoked_by = ? WHERE encounter_id = ? AND revoked_at IS NULL",
        (iso(now), user_id, encounter_id),
    )
    conn.commit()
    return True


def document_for_encounter(conn, encounter_id):
    """The newest document row of the encounter, or None."""
    return conn.execute(
        "SELECT * FROM documents WHERE encounter_id = ? ORDER BY id DESC LIMIT 1", (encounter_id,)
    ).fetchone()
