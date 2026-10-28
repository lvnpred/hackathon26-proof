-- 008: the clinic's OP-number prefix, a copy of the directory's clinics.op_prefix (the record).
-- NULL until mirrored; OP numbers then use 'OP'. Numbers already issued are never rewritten.
ALTER TABLE clinic_profile ADD COLUMN op_prefix TEXT;
