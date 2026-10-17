-- 009: this clinic's own drug list, learned from confirmed prescriptions. One row per name (name_key = casefolded).
-- A name is ACTIVE when removed_at IS NULL and confirm_count >= 2. A removal sets removed_at and resets confirm_count;
-- the ledger below keeps the documents already counted, so only NEW prescriptions count towards a re-learn.
CREATE TABLE clinic_formulary (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name_key      TEXT    NOT NULL UNIQUE,
    name          TEXT    NOT NULL,
    generic       TEXT,
    confirm_count INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT    NOT NULL,
    last_seen_at  TEXT    NOT NULL,
    added_by      INTEGER REFERENCES users(id),
    removed_at    TEXT
);
CREATE TABLE clinic_formulary_docs (
    formulary_id INTEGER NOT NULL REFERENCES clinic_formulary(id),
    document_id  INTEGER NOT NULL REFERENCES documents(id),
    PRIMARY KEY (formulary_id, document_id)
);
