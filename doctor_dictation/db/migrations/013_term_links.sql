-- 013: per doctor, how many saved documents paired a diagnosis line (spoken.diagnosis_key) with a medicine or investigation term. A link is used at count >= 2; term_link_docs counts each document once (plan SH-H3). A re-save replaces the document's links.
CREATE TABLE term_links (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id     INTEGER NOT NULL DEFAULT 0,
    diagnosis_key TEXT    NOT NULL,                -- spoken.diagnosis_key(line)
    term_id       INTEGER NOT NULL REFERENCES spoken_terms(id),
    count         INTEGER NOT NULL DEFAULT 0,      -- used at >= 2
    last_seen_at  TEXT    NOT NULL,
    UNIQUE (doctor_id, diagnosis_key, term_id)
);
CREATE TABLE term_link_docs (link_id INTEGER NOT NULL REFERENCES term_links(id),
    document_id INTEGER NOT NULL REFERENCES documents(id), PRIMARY KEY (link_id, document_id));
