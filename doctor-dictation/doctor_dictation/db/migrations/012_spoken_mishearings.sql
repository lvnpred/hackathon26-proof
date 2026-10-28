-- 012 (plan SH-H2): a doctor's misheard words, counted once per document; active at 2; a removal resets the count, like 009.
CREATE TABLE spoken_mishearings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    term_id       INTEGER NOT NULL REFERENCES spoken_terms(id),
    heard_key     TEXT    NOT NULL,                -- spoken.key(heard)
    heard         TEXT    NOT NULL,                -- "dollo"
    confirm_count INTEGER NOT NULL DEFAULT 0,      -- active at >= formulary.THRESHOLD (2)
    first_seen_at TEXT    NOT NULL,
    last_seen_at  TEXT    NOT NULL,
    removed_at    TEXT,
    UNIQUE (term_id, heard_key)
);
CREATE TABLE spoken_mishearing_docs (mishearing_id INTEGER NOT NULL REFERENCES spoken_mishearings(id),
    document_id INTEGER NOT NULL REFERENCES documents(id), PRIMARY KEY (mishearing_id, document_id));
