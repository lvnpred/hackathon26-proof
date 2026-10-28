"""A first save records the speech settings it ran with (documents.model_versions), so the edit rate can later be
compared with hints and silence trimming on and off. A re-save keeps what the first save recorded."""
import json

import pytest

from doctor_dictation import db as dbmod
from doctor_dictation.config import override_settings
from doctor_dictation.pdf import PdfUnavailable
from template_fixtures import make_jpeg, tclient  # noqa: F401

SAVE = {"structured": {"patientName": "Anita", "opNo": "OP-1", "rx": [{"name": "Tamsulosin", "status": "verified"}]},
        "confirmed_rows": []}


@pytest.fixture(autouse=True)
def _no_pdf(monkeypatch):
    def fail(*args, **kwargs):
        raise PdfUnavailable("no chromium in tests")
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fail)


def _versions(doc_id):
    conn = dbmod.get_conn()
    try:
        raw = dbmod.get_document(conn, doc_id)["model_versions"]
    finally:
        conn.close()
    return json.loads(raw) if raw else None


def _save(c, body=SAVE):
    r = c.post("/api/v1/documents", json=body)
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


@pytest.mark.parametrize("hints,trim", [(True, True), (False, False), (True, False)])
def test_first_save_records_the_speech_settings(tclient, monkeypatch, hints, trim):  # noqa: F811
    override_settings(monkeypatch, stt_use_hints=hints, stt_trim_silence=trim)
    stt = _versions(_save(tclient))["stt"]
    assert stt["hints"] is hints and stt["trim"] is trim
    assert isinstance(stt["engine"], str) and stt["engine"]


def test_a_resave_keeps_the_first_saves_settings(tclient, monkeypatch):  # noqa: F811
    override_settings(monkeypatch, stt_use_hints=False, stt_trim_silence=False)
    doc = _save(tclient)
    override_settings(monkeypatch, stt_use_hints=True, stt_trim_silence=True)
    assert _save(tclient, {**SAVE, "document_id": doc}) == doc
    assert _versions(doc)["stt"]["hints"] is False and _versions(doc)["stt"]["trim"] is False
