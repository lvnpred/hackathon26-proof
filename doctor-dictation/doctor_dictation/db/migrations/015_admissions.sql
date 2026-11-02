-- 015: DD -> Count Guard (spec §7.1). One row per document the doctor admitted to the ward. status is 'admit', or
-- 'send_home' when an admitted document is re-saved without admit. pushed_at / last_error record the latest push;
-- Count Guard's Sync reads the same rows through GET /api/v1/admissions.
CREATE TABLE IF NOT EXISTS admissions (
    document_id INTEGER PRIMARY KEY,
    status      TEXT NOT NULL,
    reason      TEXT,
    admitted_at TEXT,
    pushed_at   TEXT,
    last_error  TEXT
);
