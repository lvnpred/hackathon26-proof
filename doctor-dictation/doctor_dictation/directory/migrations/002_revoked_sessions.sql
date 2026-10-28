-- Sessions ended by logout. A row is only needed until the cookie would have expired anyway.
CREATE TABLE IF NOT EXISTS revoked_sessions (
    sid        TEXT PRIMARY KEY,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_revoked_sessions_expires ON revoked_sessions(expires_at);
