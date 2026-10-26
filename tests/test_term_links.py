"""Plan SH-H3: diagnosis <-> term links learned on save; a correction's context lifts linked terms in the hints. Offline."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api import stt as api_stt
from doctor_dictation.api.app import create_app
from doctor_dictation.config import override_settings
from doctor_dictation.core import spoken as S
from doctor_dictation.db import spoken as sdb
from doctor_dictation.providers.stt.base import Transcript

H = {"X-DD-Client": "1"}


def test_diagnosis_keys_and_the_context_rules():
    assert S.diagnosis_key(" Acute  Pharyngitis. ") == "acute pharyngitis" and S.diagnosis_key("T2DM & HTN") == "t2dm and htn"
    assert S.diagnosis_key("Hb") == "" and S.diagnosis_key("UTI") == "uti" and S.diagnosis_key("x" * 100) == "x" * 80
    lines = ["Fever", "fever!", 7, "", "Hb"] + [f"Disease {i}" for i in range(12)]
    assert S.diagnosis_keys(lines) == ["fever"] + [f"disease {i}" for i in range(9)]          # unique, at most 10
    ok = json.dumps({"diagnosis": [" Acute  pharyngitis ", ""], "patient": {"name": "Asha  Verma", "op_no": "OP 7"}, "later": 1})
    assert S.parse_context(ok) == ({"diagnosis": ["Acute pharyngitis"],
                                    "patient": {"name": "Asha Verma", "age_sex": "", "op_no": "OP 7"}}, "")
    assert S.parse_context(None) == S.parse_context("") == (None, "")
    bad = [(b"{}", "not text"), ("x" * 4097, "over 4096 bytes"), ("{", "not JSON"), ("[]", "not an object"),
           (json.dumps({"diagnosis": ["a"] * 11}), "bad diagnosis"), (json.dumps({"diagnosis": ["a" * 201]}), "bad diagnosis"),
           (json.dumps({"diagnosis": "fever"}), "bad diagnosis"), (json.dumps({"patient": {"name": 7}}), "bad patient"),
           (json.dumps({"patient": "Asha"}), "bad patient")]
    for raw, reason in bad:
        assert S.parse_context(raw) == (None, reason), raw
    wide = json.dumps({"diagnosis": ["अ" * 200] * 6}, ensure_ascii=False)     # characters per line; bytes for the whole field
    assert S.parse_context(wide)[0]["diagnosis"] == ["अ" * 200] * 6


def test_links_count_once_per_document_need_two_documents_and_stay_per_doctor(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "links.db"))
    conn = dbmod.get_conn()
    dbmod.migrate(conn)
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "40 / M", None))
    d1, d2 = (dbmod.save_document(conn, eid, f"sha{i}", {"rx": []}) for i in range(2))
    now = "2026-10-21T08:00:00Z"

    def term(doctor, kind, key, spoken, strengths=()):
        tid = conn.execute("INSERT INTO spoken_terms(doctor_id, kind, term_key, spoken, uses, first_used_at, last_used_at)"
                           " VALUES (?, ?, ?, ?, 2, ?, ?)", (doctor, kind, key, spoken, now, now)).lastrowid
        conn.executemany("INSERT INTO spoken_term_strengths(term_id, strength, uses) VALUES (?, ?, ?)",
                         [(tid, s, n) for s, n in strengths])
        return tid
    dolo, cbc = term(7, "medicine", "dolo", "Dolo", [("650 mg", 2)]), term(7, "investigation", "cbc", "CBC")
    term(8, "medicine", "dolo", "Dolo")                                        # a colleague's own term, same key
    refs, keys = [("medicine", "dolo"), ("investigation", "cbc"), ("medicine", "nope")], ["acute pharyngitis", "fever"]
    assert sdb.record_links(conn, 7, keys, refs, d1) == 4                      # 2 keys x 2 known terms; "nope" skipped
    assert sdb.record_links(conn, 7, keys, refs, d1) == 0                      # the same document again (S5)
    assert sdb.linked_term_ids(conn, 7, ["acute pharyngitis"]) == set()       # one document is not enough
    assert sdb.record_links(conn, 7, ["acute pharyngitis"], refs, d2) == 2
    assert sdb.linked_term_ids(conn, 7, ["acute pharyngitis", "gastritis"]) == {dolo, cbc}
    assert sdb.linked_term_ids(conn, 7, ["fever"]) == sdb.linked_term_ids(conn, 8, ["acute pharyngitis"]) == set()
    assert sdb.linked_term_ids(conn, 7, []) == set()
    conn.execute("UPDATE spoken_terms SET removed_at = ? WHERE id = ?", (now, cbc))
    conn.commit()
    assert sdb.linked_term_ids(conn, 7, ["acute pharyngitis"]) == {dolo}      # a removed term is never lifted
    conn.close()


class Recorder:
    def __init__(self):
        self.calls = []

    async def transcribe(self, audio, filename, hints=()):
        self.calls.append({"audio": audio, "filename": filename, "hints": hints})
        return Transcript(text="hello", engine="recorder")


def _fake_pdf(structured, meta, out_path, layout=None):
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(b"%PDF-fake")
    return Path(out_path)


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))                       # never the real dev database
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", _fake_pdf)
    rec = Recorder()
    monkeypatch.setattr(api_stt, "make_stt", lambda settings: rec)
    with TestClient(create_app()) as c:
        yield c, rec


def _save(c, diagnosis, name, strength, document_id=None):
    row = {"form": "Tab.", "name": name, "strength": strength, "dose": "1-0-1", "status": "verified"}
    body = {"structured": {"patientName": "Asha Verma", "ageSex": "40 / F", "diagnosis": diagnosis, "rx": [row]},
            "confirmed_rows": [0], **({"document_id": document_id} if document_id else {})}
    r = c.post("/api/v1/documents", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def _links():
    conn = dbmod.get_conn()
    try:
        return [tuple(r) for r in conn.execute("SELECT l.diagnosis_key, t.term_key, l.count FROM term_links l"
                                               " JOIN spoken_terms t ON t.id = l.term_id ORDER BY 1, 2")]
    finally:
        conn.close()


def test_a_save_links_each_diagnosis_line_to_each_term_once_per_document(app_client, monkeypatch):
    c, _ = app_client
    first = _save(c, ["Acute pharyngitis", "Fever"], "Dolo", "650 mg")
    _save(c, ["acute  pharyngitis."], "Dolo", "650 mg")
    _save(c, ["Acute pharyngitis", "Fever"], "Dolo", "650 mg", document_id=first)        # a re-save counts nothing
    assert _links() == [("acute pharyngitis", "dolo", 2), ("fever", "dolo", 1)]
    _save(c, ["Typhoid"], "Dolo", "650 mg", document_id=first)                           # a re-save replaces its links
    assert _links() == [("acute pharyngitis", "dolo", 1), ("fever", "dolo", 0), ("typhoid", "dolo", 1)]
    monkeypatch.setattr(sdb, "record_links", lambda *a, **k: 1 / 0)
    _save(c, ["Fever"], "Dolo", "650 mg")                                               # S4: still saved (200)
    assert _links() == [("acute pharyngitis", "dolo", 1), ("fever", "dolo", 0), ("typhoid", "dolo", 1)]


def _post(c, context=None, files=None):
    files = files or {"audio": ("note.webm", b"RAWBYTES", "audio/webm")}
    return c.post("/api/transcribe", files=files, data={} if context is None else {"context": context}, headers=H)


def test_a_correction_context_puts_linked_terms_first_and_never_reaches_the_engine(app_client, monkeypatch):
    c, rec = app_client
    for _ in range(2):
        _save(c, ["Acute pharyngitis"], "Dolo", "650 mg")
    for _ in range(3):
        _save(c, ["Gastritis"], "Pan", "40 mg")                                        # more used: first without context
    override_settings(monkeypatch, stt_use_hints=True, stt_trim_silence=False, stt_hint_limit=70)
    ctx = json.dumps({"diagnosis": ["ACUTE  pharyngitis"], "patient": {"name": "Asha Verma", "age_sex": "40 / F", "op_no": ""}})
    plain, linked = _post(c), _post(c, ctx)
    assert plain.status_code == linked.status_code == 200 and plain.json() == linked.json()   # the body is unchanged
    h0, h1 = (list(call["hints"]) for call in rec.calls)
    assert h0.index("Pan 40") < h0.index("Dolo 650") and h1.index("Dolo 650") < h1.index("Pan 40")
    sent = " ".join(h0 + h1).casefold()
    assert "pharyngitis" not in sent and "asha" not in sent and "verma" not in sent   # S2: context never leaves
    assert all(set(call) == {"audio", "filename", "hints"} for call in rec.calls)


def test_a_malformed_context_is_ignored_with_one_log_line_and_the_same_body(app_client, monkeypatch, capsys):
    c, _ = app_client
    override_settings(monkeypatch, stt_use_hints=True, stt_trim_silence=False)
    good = _post(c).json()
    assert _post(c, json.dumps({"diagnosis": []})).json() == good
    assert "context ignored" not in capsys.readouterr().out                           # valid and empty: silent
    audio = ("note.webm", b"RAWBYTES", "audio/webm")
    bad = [dict(context="not json"), dict(context="[1]"), dict(context=json.dumps({"diagnosis": "Asha fever"})),
           dict(context=json.dumps({"diagnosis": ["Asha"] * 11})), dict(context=json.dumps({"diagnosis": ["Asha" * 51]})),
           dict(context=json.dumps({"patient": {"name": 7}})), dict(context="Asha " * 900),
           dict(files={"audio": audio, "context": ("c.json", b'{"diagnosis": ["Asha"]}', "application/json")})]
    for kw in bad:
        r = _post(c, **kw)
        out = capsys.readouterr().out
        assert (r.status_code, r.json()) == (200, good), kw
        assert out.count("transcribe: context ignored (") == 1 and "Asha" not in out, (kw, out)


def test_the_backfill_keeps_the_terms_when_the_link_step_fails(app_client, monkeypatch):
    from doctor_dictation.api.spoken import replay_saved
    c, _ = app_client
    _save(c, ["Acute pharyngitis"], "Dolo", "650 mg")
    conn = dbmod.get_conn()
    try:
        for table in ("term_link_docs", "term_links", "spoken_term_strengths", "spoken_term_docs", "spoken_terms"):
            conn.execute(f"DELETE FROM {table}")                                    # children first
        conn.commit()
        monkeypatch.setattr(sdb, "record_links", lambda *a, **k: 1 / 0)
        assert replay_saved(conn, by_doctor=False) == (1, 1)                         # RAISES without _learn_links' own try
        assert [tuple(r) for r in conn.execute("SELECT term_key, uses FROM spoken_terms")] == [("dolo", 1)]
        assert conn.execute("SELECT COUNT(*) FROM term_links").fetchone()[0] == 0
    finally:
        conn.close()
