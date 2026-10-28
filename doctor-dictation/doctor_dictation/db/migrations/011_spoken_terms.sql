-- The doctor's spoken terms (plan SH-H1): each medicine or test as the doctor said it, counted once per saved document.
CREATE TABLE spoken_terms (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id     INTEGER NOT NULL DEFAULT 0,      -- users.id; 0 = single-database mode
    kind          TEXT    NOT NULL CHECK (kind IN ('medicine','investigation')),
    term_key      TEXT    NOT NULL,                -- spoken.key(spoken)
    spoken        TEXT    NOT NULL,                -- as shown and printed, no strength: "Dolo"
    form          TEXT    NOT NULL DEFAULT '',     -- latest form seen: "Tab"
    generic       TEXT    NOT NULL DEFAULT '',     -- checks only; never hinted in place of spoken
    uses          INTEGER NOT NULL DEFAULT 0,
    first_used_at TEXT    NOT NULL,
    last_used_at  TEXT    NOT NULL,
    removed_at    TEXT,
    UNIQUE (doctor_id, kind, term_key)
);
CREATE TABLE spoken_term_strengths (
    term_id  INTEGER NOT NULL REFERENCES spoken_terms(id),
    strength TEXT    NOT NULL,                     -- as saved: "650 mg"
    uses     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (term_id, strength)
);
CREATE TABLE spoken_term_docs (
    term_id     INTEGER NOT NULL REFERENCES spoken_terms(id),
    document_id INTEGER NOT NULL REFERENCES documents(id),
    PRIMARY KEY (term_id, document_id)
);
