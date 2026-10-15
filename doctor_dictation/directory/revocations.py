"""Sessions ended by logout, in the directory database. Keyed by the cookie's random ``sid``."""
from __future__ import annotations

import time


def revoke_session(conn, sid, expires_at, now=None) -> None:
    """Mark ``sid`` revoked until ``expires_at`` (epoch seconds); idempotent. Also purges rows already past their expiry."""
    moment = int(time.time() if now is None else now)
    conn.execute("DELETE FROM revoked_sessions WHERE expires_at <= ?", (moment,))
    conn.execute("INSERT OR IGNORE INTO revoked_sessions(sid, expires_at) VALUES (?, ?)", (sid, int(expires_at)))
    conn.commit()


def is_revoked(conn, sid) -> bool:
    return conn.execute("SELECT 1 FROM revoked_sessions WHERE sid = ?", (sid,)).fetchone() is not None
