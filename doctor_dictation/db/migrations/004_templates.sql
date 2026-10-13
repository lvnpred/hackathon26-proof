CREATE TABLE IF NOT EXISTS templates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    clinic      TEXT NOT NULL DEFAULT 'default',
    layout_json TEXT NOT NULL,
    logo_path   TEXT,
    status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','archived')),
    created_at  TEXT NOT NULL,
    accepted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_templates_status ON templates(clinic, status);
