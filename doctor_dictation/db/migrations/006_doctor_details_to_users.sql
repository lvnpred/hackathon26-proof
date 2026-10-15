-- 006: the doctor fields move from the shared clinic profile to each user's own row (spec 8.1).
-- Copies the saved doctor name, qualifications and registration no. onto the clinic's first user when that
-- user has none yet. Idempotent: a user who already has any detail is never touched; no user, no change.
-- clinic_profile keeps its doctor columns: single-database mode and pre-authorship prescriptions print from them.
UPDATE users SET
    doctor_name    = (SELECT doctor_name    FROM clinic_profile WHERE id = 1),
    qualifications = (SELECT qualifications FROM clinic_profile WHERE id = 1),
    reg_no         = (SELECT reg_no         FROM clinic_profile WHERE id = 1)
WHERE id = (SELECT MIN(id) FROM users)
  AND doctor_name = '' AND qualifications = '' AND reg_no = ''
  AND EXISTS (SELECT 1 FROM clinic_profile WHERE id = 1);
