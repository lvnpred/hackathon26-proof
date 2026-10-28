"""SH-B2 data: the labelled Spell it context groups (pure) and the readers behind them. Offline."""
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api import stt as api_stt
from doctor_dictation.api.app import create_app
from doctor_dictation.core import spellctx
from doctor_dictation.core import spoken
from doctor_dictation.db import spoken as sdb
from doctor_dictation.providers.stt.base import Transcript

H = {"X-DD-Client": "1"}


def test_groups_order_cap_dedupe_and_skips():
    n = lambda i, name, w: spellctx.CtxName(i, spoken.key(name), name, "", w)     # noqa: E731
    names = [n(1, "Urimax", 3.0), n(2, "Dutas", 2.0), n(3, "Silodal", 1.0), n(4, "Veltam", 0.5), n(5, "Gone", 9.0), n(6, "Yurimacks", 9.0)]
    out = spellctx.groups(names, {"bph": {1, 2, 3, 4, 5}}, {"bph": "BPH"}, {"urimax", "flomax"}, "yurimacks",
                          blocked=lambda name: name == "Gone")
    assert out == [{"kind": "diagnosis", "for": "BPH", "items": [{"name": "Urimax", "generic": ""}, {"name": "Dutas", "generic": ""},
                                                                  {"name": "Silodal", "generic": ""}]}]
    assert spellctx.groups(names, {"bph": {1}, "luts": {2}}, {"bph": "BPH", "luts": "LUTS"}, set(), "", lambda _n: False)[0]["for"] == ""
    assert spellctx.prefer_keys(names, {"bph": {1}}, {"flomax"}) == frozenset({"urimax", "flomax"})


def test_a_patient_group_follows_and_repeats_nothing_from_the_diagnosis_group():
    n = lambda i, name, w: spellctx.CtxName(i, spoken.key(name), name, "Gen", w)  # noqa: E731
    names = [n(1, "Urimax", 3.0), n(2, "Dutas", 2.0), n(3, "Aaa", 2.0), n(4, "Zed", 2.0)]
    out = spellctx.groups(names, {"bph": {1}}, {"bph": "BPH"}, {"urimax", "dutas", "aaa", "zed"}, "zed", lambda _n: False)
    assert [(g["kind"], g["for"], [i["name"] for i in g["items"]]) for g in out] == [
        ("diagnosis", "BPH", ["Urimax"]), ("patient", "", ["Aaa", "Dutas"])]       # weight desc, then name; the row's own name dropped
    assert spellctx.groups(names, {}, {}, set(), "", lambda _n: False) == []


class Recorder:
    async def transcribe(self, audio, filename, hints=()):
        return Transcript(text="hello", engine="recorder")


def _fake_pdf(structured, meta, out_path, layout=None):
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(b"%PDF-fake")
    return Path(out_path)


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))                       # never the real dev database
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", _fake_pdf)
    monkeypatch.setattr(api_stt, "make_stt", lambda settings: Recorder())
    with TestClient(create_app()) as c:
        yield c


def _save(c, diagnosis, name):
    row = {"form": "Tab.", "name": name, "strength": "10 mg", "dose": "1-0-1", "status": "verified"}
    body = {"structured": {"patientName": "Asha Verma", "ageSex": "40 / F", "diagnosis": diagnosis, "rx": [row]},
            "confirmed_rows": [0]}
    r = c.post("/api/v1/documents", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def test_readers_skip_removed_terms_and_the_current_document(app_client):
    c = app_client
    _save(c, ["BPH"], "Urimax")
    _save(c, ["BPH"], "Urimax")
    d3 = _save(c, ["BPH"], "Dutas")
    conn = dbmod.get_conn()
    try:
        pid = tuple(r[0] for r in conn.execute("SELECT id FROM patients ORDER BY id"))   # each save made its own patient row: read them as one person's rows
        urimax = conn.execute("SELECT id FROM spoken_terms WHERE term_key = 'urimax'").fetchone()[0]
        assert sdb.linked_ids_by_key(conn, 0, ["bph", "fever"]) == {"bph": {urimax}}     # Dutas: one document, under LINK_MIN
        assert sdb.patient_term_keys(conn, pid, 0, exclude_document=d3) == {"urimax"}
        assert sdb.patient_term_keys(conn, pid, 0) == {"urimax", "dutas"}
        today = date.today()
        assert "Urimax" in [x.name for x in sdb.doctor_medicine_names(conn, 0, today)]
        conn.execute("UPDATE spoken_terms SET removed_at = '2026-10-28T00:00:00Z' WHERE id = ?", (urimax,))
        conn.commit()
        assert "Urimax" not in [x.name for x in sdb.doctor_medicine_names(conn, 0, today)]
        assert sdb.linked_ids_by_key(conn, 0, ["bph"]) == {}
    finally:
        conn.close()
