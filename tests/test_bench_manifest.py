import json
from pathlib import Path

import pytest

from doctor_dictation.bench.manifest import ManifestError, load_manifest


def _write(tmp_path: Path, data) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def test_relative_audio_resolves_against_manifest_folder(tmp_path):
    (tmp_path / "clips").mkdir()
    (tmp_path / "clips" / "a.wav").write_bytes(b"x")
    clip, = load_manifest(_write(tmp_path, [{"audio": "clips/a.wav", "reference": " tab dolo ", "seconds": 4}]))
    assert clip.audio == tmp_path.resolve() / "clips" / "a.wav"
    assert (clip.reference, clip.seconds) == ("tab dolo", 4.0)


@pytest.mark.parametrize("data,message", [
    ("{not json", "not readable JSON"),
    ([], "non-empty JSON list"),
    (["a.wav"], "entry 0: expected an object"),
    ([{"reference": "x"}], "entry 0: 'audio' must be"),
    ([{"audio": "gone.wav", "reference": "x"}], r"entry 0 \(gone\.wav\): audio file not found"),
    ([{"audio": "a.wav", "reference": "  "}], r"entry 0 \(a\.wav\): 'reference' must be non-empty"),
    ([{"audio": "a.wav", "reference": "x", "seconds": 0}], "'seconds' must be a positive number"),
])
def test_invalid_manifests_raise_clear_errors(tmp_path, data, message):
    (tmp_path / "a.wav").write_bytes(b"x")
    with pytest.raises(ManifestError, match=message):
        load_manifest(_write(tmp_path, data))


def test_missing_manifest(tmp_path):
    with pytest.raises(ManifestError, match="manifest not found"):
        load_manifest(tmp_path / "nope.json")
