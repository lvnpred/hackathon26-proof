import json

import pytest

from doctor_dictation import db as dbmod

@pytest.fixture()
def conn(tmp_path):
    c = dbmod.get_conn(tmp_path / "top.db")
    dbmod.migrate(c)
    yield c
    c.close()

def _doc(conn, names=(), finalized="2026-10-13T00:00:00Z", raw=None):
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "40 / M", None))
    body = raw if raw is not None else json.dumps({"rx": [{"name": n} for n in names]})
    conn.execute("INSERT INTO documents(encounter_id, transcript_sha, structured_json,"
                 " finalized_at, created_at) VALUES (?, 'sha', ?, ?, '2026-10-13T00:00:00Z')",
                 (eid, body, finalized))
    conn.commit()

def test_most_frequent_first_case_insensitive_newest_spelling(conn):
    assert dbmod.top_medicines(conn) == []                       # empty DB
    _doc(conn, ["Paracetamol", "Tamsulosin"])
    _doc(conn, ["paracetamol"])
    _doc(conn, ["PARACETAMOL", "Zincovit"])
    assert dbmod.top_medicines(conn) == ["PARACETAMOL", "Zincovit", "Tamsulosin"]   # ties: most recent first
    assert dbmod.top_medicines(conn, limit=1) == ["PARACETAMOL"]
    assert dbmod.top_medicines(conn, limit=0) == []

def test_unfinalized_and_malformed_rows_are_ignored(conn):
    _doc(conn, ["Draftmed"], finalized=None)
    for raw in ("not json", "[]", "null", "", '{"rx": "x"}',
                '{"rx": [1, "s", null, {"name": 5}, {"name": "  "}, {}]}'):
        _doc(conn, raw=raw)
    _doc(conn, ["Goodmed"])
    assert dbmod.top_medicines(conn) == ["Goodmed"]
