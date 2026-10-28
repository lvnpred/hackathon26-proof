-- 014: plan FB-D (C2). One private download link per prescription (its encounter). A re-save moves expires_at to
-- save + 7 days; a re-save after a revoke issues a new token. The token is plain text: the QR is redrawn on reprint.
CREATE TABLE share_links (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    encounter_id INTEGER NOT NULL UNIQUE REFERENCES encounters(id),
    token        TEXT    NOT NULL UNIQUE,        -- secrets.token_urlsafe(16): 128 bits, 22 characters
    created_at   TEXT    NOT NULL,
    saved_at     TEXT    NOT NULL,               -- the latest save
    expires_at   TEXT    NOT NULL,               -- saved_at + 7 days
    revoked_at   TEXT,
    revoked_by   INTEGER
);
