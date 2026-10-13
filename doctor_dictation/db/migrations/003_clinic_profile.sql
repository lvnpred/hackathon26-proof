-- 003_clinic_profile.sql — clinic/doctor profile (Task 1).
-- Single-row settings table: the CHECK(id = 1) constraint pins the upsert
-- target so save_profile() always updates the same row.
CREATE TABLE IF NOT EXISTS clinic_profile (
    id             INTEGER PRIMARY KEY CHECK (id = 1),
    doctor_name    TEXT NOT NULL DEFAULT '',
    qualifications TEXT NOT NULL DEFAULT '',
    reg_no         TEXT NOT NULL DEFAULT '',
    clinic_name    TEXT NOT NULL DEFAULT '',
    address        TEXT NOT NULL DEFAULT '',
    phone          TEXT NOT NULL DEFAULT '',
    updated_at     TEXT NOT NULL
);
