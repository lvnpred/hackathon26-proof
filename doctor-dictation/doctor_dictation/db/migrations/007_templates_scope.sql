-- 007: letterhead scope (owner_user_id NULL = the whole clinic, else that doctor's own) and which doctors a
-- letterhead lists (author | all | selected; doctors_ids is a JSON list used by 'selected').
-- Applied once per clinic database; existing rows become clinic letterheads that list the author.
ALTER TABLE templates ADD COLUMN owner_user_id INTEGER;
ALTER TABLE templates ADD COLUMN doctors_mode TEXT NOT NULL DEFAULT 'author'
    CHECK (doctors_mode IN ('author', 'all', 'selected'));
ALTER TABLE templates ADD COLUMN doctors_ids TEXT NOT NULL DEFAULT '[]';
CREATE INDEX IF NOT EXISTS idx_templates_owner ON templates(owner_user_id, status);
