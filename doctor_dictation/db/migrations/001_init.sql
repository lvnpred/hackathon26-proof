-- 001_init.sql — Doctor Dictation baseline schema (P0-4).
-- Engine: stdlib sqlite3. Applied once; the version is recorded in
-- schema_migrations so re-running init_db() is a no-op.
--
-- Timestamps are ISO-8601 UTC text, e.g. '2026-10-12T09:30:00Z'.
-- IDs are INTEGER PRIMARY KEY AUTOINCREMENT.

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'doctor'
                          CHECK (role IN ('doctor', 'assistant', 'admin')),
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS patients (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    age_sex    TEXT    NOT NULL DEFAULT '',
    op_no      TEXT,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS encounters (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    doctor_id  INTEGER          REFERENCES users(id),
    op_no      TEXT,
    status     TEXT    NOT NULL DEFAULT 'draft',
    consent_at TEXT,
    created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_encounters_patient ON encounters(patient_id);
CREATE INDEX IF NOT EXISTS idx_encounters_doctor  ON encounters(doctor_id);

CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    encounter_id    INTEGER NOT NULL REFERENCES encounters(id),
    transcript_sha  TEXT    NOT NULL,
    structured_json TEXT,
    engine          TEXT,
    model_versions  TEXT,
    finalized_by    INTEGER,
    finalized_at    TEXT,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_sha       ON documents(transcript_sha);
CREATE INDEX IF NOT EXISTS idx_documents_encounter ON documents(encounter_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    actor     TEXT,
    role      TEXT,
    action    TEXT NOT NULL,
    entity    TEXT,
    entity_id TEXT,
    detail    TEXT,
    ip        TEXT,
    at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity, entity_id);
