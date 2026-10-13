"""Shared helpers for the template tests. Offline: stub LLM only."""
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from doctor_dictation import db as dbmod
from doctor_dictation.config import override_settings

PROFILE = {"doctor_name": "Dr A. Rao", "qualifications": "MBBS, MD", "reg_no": "TS-12345",
           "clinic_name": "Meridian Clinic", "address": "12 MG Road, Hyderabad", "phone": "040 1234 5678"}
GOOD_LAYOUT = {
    "header": [
        {"type": "logo", "crop": [0.05, 0.02, 0.25, 0.10], "align": "left"},
        {"type": "text", "field": "doctor_name", "role": "title", "align": "center", "color": "#1a3c6e"},
        {"type": "text", "text": "Open Mon to Sat", "role": "small", "align": "center"},
        {"type": "rule", "color": "#1a3c6e", "thickness": "thin"},
    ],
    "footer": [{"type": "text", "field": "address", "role": "small", "align": "center"}],
    "body": {"top": 0.22, "bottom": 0.92},
    "profile": PROFILE,
}


def make_jpeg(size=(800, 1000), color=(240, 240, 255)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "JPEG")
    return b.getvalue()


@pytest.fixture()
def tconn(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    c = dbmod.get_conn()
    dbmod.migrate(c)
    yield c
    c.close()


@pytest.fixture()
def tclient(tmp_path, monkeypatch):
    """App with the stub LLM returning GOOD_LAYOUT; temp DB; lifespan runs."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(GOOD_LAYOUT))
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True)
    from doctor_dictation.api.app import create_app
    with TestClient(create_app()) as c:
        yield c
