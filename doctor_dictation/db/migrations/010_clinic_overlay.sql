-- 010: this clinic's overlay on the shipped medicine and investigation lists. One row per (kind, entry_key).
-- A row is ACTIVE when removed_at IS NULL and (source = 'admin' or confirm_count >= 2). Other live rows are pending.
-- The ledger below keeps the documents already counted, so a re-save of one document never counts twice.
CREATE TABLE clinic_overlay (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT    NOT NULL CHECK (kind IN ('medicine','investigation')),
    entry_key     TEXT    NOT NULL,
    action        TEXT    NOT NULL CHECK (action IN ('add','edit','hide')),
    data          TEXT    NOT NULL DEFAULT '{}',
    base_sha      TEXT    NOT NULL DEFAULT '',
    source        TEXT    NOT NULL CHECK (source IN ('doctor','admin','learned')),
    confirm_count INTEGER NOT NULL DEFAULT 0,
    created_by    INTEGER REFERENCES users(id),
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL,
    removed_at    TEXT,
    UNIQUE (kind, entry_key)
);
CREATE TABLE clinic_overlay_docs (
    overlay_id  INTEGER NOT NULL REFERENCES clinic_overlay(id),
    document_id INTEGER NOT NULL REFERENCES documents(id),
    PRIMARY KEY (overlay_id, document_id)
);
