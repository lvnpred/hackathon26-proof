"""make live-check (spec §11 A9): one real call per §6.7 model, artifacts under eval/live/<date>/. Adapters are faked here."""
import dataclasses
import json

import pytest

from app import live_check
from app.config import get_settings


def _settings(tmp_path, key):
    return dataclasses.replace(get_settings(), meta_api_key=key, data_dir=tmp_path / "data")


class FakeVoice:
    def __init__(self, settings):
        self.settings = settings

    def transcribe(self, path, offset_ms=0, content_type="audio/wav"):
        assert path.name == "drug-lignocaine.wav"
        return [{"text": "lignocaine two percent", "start_ms": 0, "end_ms": 900}]


class FakeSpark:
    def __init__(self, settings):
        pass

    def write(self, prompt):
        assert "synthetic" in prompt
        return "BP 86/50, down 28% in 4 min."

    def check_photo(self, raw, content_type, expect):
        assert raw and content_type == "image/png"
        return {"verdict": "accepted", "why": "A wristband."}


class FakeSam:
    def __init__(self, settings):
        pass

    def segment_images(self, data_urls, concepts):
        assert len(data_urls) == 1 and data_urls[0].startswith("data:image/png;base64,")
        return [{"frame_index": 0, "label": concepts[0], "bbox": [1, 2, 3, 4]}]


FAKES = {"voice": FakeVoice, "spark": FakeSpark, "sam": FakeSam}


@pytest.fixture()
def media(tmp_path):
    root = tmp_path / "eval"
    for rel in live_check.MEDIA.values():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(b"\x89PNG fake" if rel.endswith(".png") else b"RIFF fake")
    return root


def test_live_check_refuses_without_key(tmp_path, media):
    with pytest.raises(live_check.NoKey):
        live_check.run(_settings(tmp_path, ""), tmp_path / "out", adapters=FAKES, root=media)
    assert not (tmp_path / "out").exists()


def test_live_check_writes_one_row_per_model(tmp_path, media):
    out = tmp_path / "out"
    rows = live_check.run(_settings(tmp_path, "k" * 12), out, adapters=FAKES, root=media)
    assert [r["model"] for r in rows] == list(live_check.MODELS)
    assert len(rows) == 4
    for row in rows:
        assert set(row) == {"model", "ok", "seconds", "artifact"}
        assert row["ok"] is True and row["seconds"] >= 0
        saved = json.loads((out / row["artifact"]).read_text())
        assert saved["model"] == row["model"] and saved["ok"] is True
    assert "k" * 12 not in "".join(p.read_text() for p in out.iterdir())


def test_a_failed_call_is_a_row_not_a_crash(tmp_path, media):
    class Broken(FakeSpark):
        def write(self, prompt):
            raise RuntimeError("upstream 503")

    rows = live_check.run(_settings(tmp_path, "k" * 12), tmp_path / "out", adapters={**FAKES, "spark": Broken}, root=media)
    by = {r["model"]: r for r in rows}
    assert by["spark-text"]["ok"] is False
    assert by["voice"]["ok"] is True and by["spark-vision"]["ok"] is True
    assert "upstream 503" in (tmp_path / "out" / by["spark-text"]["artifact"]).read_text()


def test_out_dir_is_dated_under_eval_live():
    assert live_check.out_dir_for("2026-11-02").parts[-3:] == ("eval", "live", "2026-11-02")


def test_cost_lines_name_make_cost(monkeypatch, tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    monkeypatch.setattr(live_check, "clip_seconds", lambda path: 4.0)
    lines = live_check.cost_lines([clip], fps=5)
    assert any("make cost CLIP=" in line for line in lines)
    assert any("$" in line for line in lines)


def test_eval_live_is_git_ignored():
    from pathlib import Path
    ignore = (Path(__file__).resolve().parents[2] / ".gitignore").read_text()
    assert "eval/live/" in ignore.splitlines()
