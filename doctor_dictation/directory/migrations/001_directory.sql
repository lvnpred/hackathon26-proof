-- Directory database: which clinics exist, who may log in where, login throttling.
-- It never stores patient data, passwords or profile content.
CREATE TABLE IF NOT EXISTS clinics (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    slug       TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    op_prefix  TEXT NOT NULL DEFAULT 'OP',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS login_index (
    username    TEXT PRIMARY KEY COLLATE NOCASE,
    clinic_slug TEXT NOT NULL REFERENCES clinics(slug),
    user_id     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS login_attempts (
    username     TEXT NOT NULL COLLATE NOCASE,
    ip           TEXT NOT NULL,
    failed_count INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (username, ip)
);
