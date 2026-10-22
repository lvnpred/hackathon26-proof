"""Multipart text fields up to 5 MB reach the upload routes (Starlette's own default is 1 MB); larger ones get a 400."""
import pytest
from fastapi.testclient import TestClient

from doctor_dictation.api import stt as route_mod
from doctor_dictation.api.app import create_app
from doctor_dictation.api.forms import FORM_PART_LIMIT
from doctor_dictation.providers.stt.base import Transcript


class Recorder:
    name = "recorder"
    available = staticmethod(lambda: True)

    async def transcribe(self, audio, filename, hints=()):
        return Transcript(text="hello", engine="recorder")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "forms.db"))
    monkeypatch.setattr(route_mod, "make_stt", lambda settings: Recorder())
    with TestClient(create_app()) as c:
        yield c


def _post(client, field_bytes):
    return client.post("/api/transcribe", files={"audio": ("note.webm", b"RAWBYTES", "audio/webm")},
                       data={"note": "x" * field_bytes})


def test_the_limit_is_5_mb():
    assert FORM_PART_LIMIT == 5 * 1024 * 1024


def test_a_2_mb_text_field_is_accepted(client):
    r = _post(client, 2 * 1024 * 1024)
    assert r.status_code == 200 and r.json()["transcript"] == "hello"


def test_a_json_route_on_an_upload_router_keeps_fastapis_own_error(client):
    # deactivate takes a JSON body; a multipart body is FastAPI's 422 as before, not a pre-read 400
    r = client.post("/api/v1/templates/deactivate", files={"x": ("a.txt", b"x", "text/plain")})
    assert r.status_code == 422


def test_a_text_field_over_5_mb_is_refused(client):
    r = _post(client, FORM_PART_LIMIT + 1)
    assert r.status_code == 400 and "5120KB" in r.json()["detail"]
