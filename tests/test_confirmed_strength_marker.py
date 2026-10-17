"""Final-fix I1: a strength the doctor confirmed does not print "[unverified strength: confirm with doctor]" (server side).
Offline: blank provider keys, temp DB."""
import json

from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation import db as dbmod
from doctor_dictation.api import persistence
from doctor_dictation.core.safety import strip_grounding_markers
from doctor_dictation.pdf import build_sheet_html

NAME = "[unverified: confirm with doctor]"
STR = "[unverified strength: confirm with doctor]"


def _row(**kw):
    return {"form": "Tab.", "name": "Amlodipine", "strength": "250 mg", "dose": "1-0-0", "timing": "", "duration": "",
            "instructions": f"after food {STR}", "status": "unverified-strength", "lexicon_match": "Amlodipine", **kw}


def test_strip_grounding_markers_removes_exactly_the_two_markers_and_one_space_before_each():
    s = {"rx": [{"instructions": f"after food {STR}"}, {"instructions": NAME}, {"instructions": f"a {NAME} b {STR}"},
                {"instructions": "[unverified: please confirm]"}, {"instructions": "unverified strength: confirm with doctor"},
                {"instructions": "[Unverified: confirm with doctor]"}, {"instructions": "ask: confirm with doctor"}, {"instructions": ""}, {}, "junk"]}
    out = strip_grounding_markers(s)
    assert out is s
    assert [r.get("instructions") for r in s["rx"][:-1]] == [
        "after food", "", "a b", "[unverified: please confirm]", "unverified strength: confirm with doctor",
        "[Unverified: confirm with doctor]", "ask: confirm with doctor", "", None] and s["rx"][-1] == "junk"
    assert strip_grounding_markers({"rx": "x"}) == {"rx": "x"} and strip_grounding_markers({}) == {}
    before = json.dumps(s)
    strip_grounding_markers(s)
    assert json.dumps(s) == before                                                       # idempotent


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "m.db"))
    conn = dbmod.get_conn(tmp_path / "m.db")
    dbmod.migrate(conn)
    return TestClient(M.app), conn


def test_save_with_a_confirmed_unverified_strength_stores_and_prints_no_marker(tmp_path, monkeypatch):
    client, conn = _client(tmp_path, monkeypatch)
    sent = []
    monkeypatch.setattr(persistence, "render_prescription", lambda structured, meta, out, layout=None: sent.append(json.loads(json.dumps(structured))) or out)
    r = client.post("/api/v1/documents", json={"structured": {"patientName": "Anita", "opNo": "OP-5", "rx": [_row()]}, "confirmed_rows": [0]})
    assert r.status_code == 200, r.text
    saved = json.loads(dbmod.get_document(conn, r.json()["document_id"])["structured_json"])["rx"][0]
    assert (saved["status"], saved["instructions"]) == ("unverified-strength", "after food")      # the audit status stays; the text goes
    assert sent and sent[0]["rx"][0]["instructions"] == "after food"
    html = build_sheet_html(sent[0], {})
    assert "unverified" not in html.lower() and "after food" in html
    conn.close()


def test_a_name_marker_on_a_confirmed_unknown_row_is_stripped_too_and_doctor_text_is_kept(tmp_path, monkeypatch):
    client, conn = _client(tmp_path, monkeypatch)
    rows = [_row(name="Zzqxwv", status="unknown-medicine", lexicon_match="", strength="", instructions=f"[unverified] tell me {NAME}"),
            _row(name="Amlodipine", status="verified", strength="5 mg", instructions="note: unverified strength: confirm with doctor [x]")]
    r = client.post("/api/v1/documents", json={"structured": {"patientName": "Anita", "opNo": "OP-6", "rx": rows}, "confirmed_rows": [0]})
    assert r.status_code == 200, r.text
    got = json.loads(dbmod.get_document(conn, r.json()["document_id"])["structured_json"])["rx"]
    assert got[0]["instructions"] == "[unverified] tell me"
    assert got[1]["instructions"] == "note: unverified strength: confirm with doctor [x]"           # not the exact marker: untouched
    conn.close()


def test_an_unconfirmed_unverified_strength_row_still_cannot_be_saved(tmp_path, monkeypatch):
    client, conn = _client(tmp_path, monkeypatch)
    r = client.post("/api/v1/documents", json={"structured": {"patientName": "Anita", "opNo": "OP-7", "rx": [_row()]}, "confirmed_rows": []})
    assert r.status_code == 409 and r.json()["block"][0]["status"] == "unverified-strength"
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
    conn.close()
