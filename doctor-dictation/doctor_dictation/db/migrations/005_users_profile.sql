-- 005: per-user identity fields and session control. Applied once per clinic database; recorded in schema_migrations.
ALTER TABLE users ADD COLUMN display_name          TEXT    NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN doctor_name           TEXT    NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN qualifications        TEXT    NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN reg_no                TEXT    NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN session_version       INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN must_change_password  INTEGER NOT NULL DEFAULT 1;
ALTER TABLE users ADD COLUMN last_login_at         TEXT;
